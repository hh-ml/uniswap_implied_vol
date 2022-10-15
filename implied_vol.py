
import math
import datetime

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from queries import pool_query, tick_query, volume_query


POOL_ID = '0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8'  # 0.3% USDC/ETH pool
# POOL_ID = '0x99ac8ca7087fa4a2a1fb6357269965a2014abc35'  # 0.3% WBTC/USDC pool

STABLECOIN_S = {"USDC", "DAI", "USDT", "TUSD", "LUSD", "BUSD", "GUSD", "UST"}
TICK_BASE = 1.0001


def get_annualized_implied_volatility(gamma: float, daily_volume: float, tick_liquidity: float) -> float:
    """
    Calculate implied volatility of a pool given its fee tier (%, daily volume, tick liquidity)
    Cf. https://lambert-guillaume.medium.com/on-chain-volatility-and-uniswap-v3-d031b98143d1
    :param gamma: float, fee tier (%)
    :param daily_volume: float, daily USD volume
    :param tick_liquidity: float, USD liquidity at current tick
    :return: float, implied volatility
    """

    return 2 * gamma * math.sqrt(daily_volume/tick_liquidity) * math.sqrt(365)


def get_usd_volume(client: Client, pool_id: str, date: datetime.date) -> float:
    """
    Get USD traded volume on a given date
    :param client: GQL client
    :param pool_id: str, the ID ("contract address") of the pool
    :param date: datetime.date, a date
    :return: float, the USD volume
    """
    volume_usd = 0
    try:
        # See https://github.com/Uniswap/v3-subgraph/blob/main/schema.graphql for the way to build the id
        date_dt = datetime.datetime.combine(date, datetime.time(0, 0))
        pool_date_id = f'{pool_id}-{round(date_dt.timestamp()/86400)}'
        response = client.execute(gql(volume_query), variable_values={"id": pool_date_id})
        volume_usd = float(response['poolDayDatas'][0]['volumeUSD'])

    except Exception as e:

        print(f'Could not fetch pool volume: {e}')

    return volume_usd


# The following functions are mostly taken from the following file, with minor edits:
# https://github.com/atiselsts/uniswap-v3-liquidity-math/blob/master/subgraph-liquidity-range-example.py

def fee_tier_to_tick_spacing(fee_tier: int) -> int:
    """
    Return tick spacing based on fee tier
    :param fee_tier: int
    :return: int, tick spacing
    """
    return {
        100: 1,
        500: 10,
        3000: 60,
        10000: 200
    }.get(fee_tier, 60)


def tick_to_price(tick: int) -> float:
    """
    Return a price given a tick
    :param tick: int, a Uni-v3 tick
    :return: float, the corresponding price
    """
    return TICK_BASE ** tick


def get_pool_info(client: Client, pool_id: str) -> dict:
    """
    Query the UniV3 subgraph for pool info (tokens/decimals/current tick/tick spacing)
    :param client: GQL client
    :param pool_id: str, the pool contract's address
    :return: dict, containing the pool info
    """

    result_d = {}

    try:
        response = client.execute(gql(pool_query), variable_values={"pool_id": pool_id})
        if len(response['pools']) == 0:
            print("pool not found")
            exit(-1)

        pool = response['pools'][0]

        result_d['current_tick'] = int(pool["tick"])
        result_d['fee_tier'] = int(pool["feeTier"])
        result_d['tick_spacing'] = fee_tier_to_tick_spacing(result_d['fee_tier'])
        result_d['token0'] = pool["token0"]["symbol"]
        result_d['token1'] = pool["token1"]["symbol"]
        result_d['decimals0'] = int(pool["token0"]["decimals"])
        result_d['decimals1'] = int(pool["token1"]["decimals"])

    except Exception as e:

        print(f'Could not fetch pool details: {e}')

    return result_d


def get_tick_mapping(client: Client, pool_id: str) -> dict:
    """
    Get tick mapping from a Uniswap v3 pool
    :param client: GQL client
    :param pool_id: str, the V3 pool contract address
    :return: dict, the tick mapping
    """

    tick_d = {}
    num_skip = 0
    try:
        print("* Querying ticks", end='', flush=True)
        while True:
            print('.', end='', flush=True)
            variables = {"num_skip": num_skip, "pool_id": pool_id}
            response = client.execute(gql(tick_query), variable_values=variables)

            if len(response["ticks"]) == 0:
                break
            num_skip += len(response["ticks"])
            for item in response["ticks"]:
                tick_d[int(item["tickIdx"])] = int(item["liquidityNet"])

    except Exception as e:

        print(f'Could not fetch tick mapping: {e}')

    print('')

    return tick_d


def get_liquidity_at_current_tick(pool_info_d: dict, tick_d: dict) -> tuple:
    """
    Iterate from min tick to current tick to find liquidity at current tick
    :param pool_info_d: dict, containing pool info (tokens/decimals/current tick/tick spacing)
    :param tick_d: dict, tick map with liquidity at each level
    :return: tuple of (token 0 liquidity, token 1 liquidity, total liquidity, price)
    """

    token0, token1 = pool_info_d['token0'], pool_info_d['token1']
    decimals0, decimals1 = pool_info_d['decimals0'], pool_info_d['decimals1']
    current_tick = pool_info_d['current_tick']
    tick_spacing = pool_info_d['tick_spacing']

    # Start from zero; if we were iterating from the current tick, would start from the pool's total liquidity
    liquidity = 0

    # Find the boundaries of the price range
    min_tick = min(tick_d.keys())
    max_tick = max(tick_d.keys())

    # Compute the tick range. This code would work as well in Python: `current_tick // tick_spacing * tick_spacing`
    # However, using floor() is more portable.
    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing

    current_price = tick_to_price(current_tick)
    adjusted_current_price = current_price / (10 ** (decimals1 - decimals0))

    # Guess the preferred way to display the price;
    # try to print most assets in terms of USD;
    # if that fails, try to use the price value that's above 1.0 when adjusted for decimals.
    if token0 in STABLECOIN_S and token1 not in STABLECOIN_S:
        invert_price = True
    elif adjusted_current_price < 1.0:
        invert_price = True
    else:
        invert_price = False

    # Iterate over the tick map starting from the bottom
    tick = min_tick
    adjusted_amount0actual = 0
    adjusted_amount1actual = 0
    while tick <= max_tick:
        liquidity_delta = tick_d.get(tick, 0)
        liquidity += liquidity_delta

        price = tick_to_price(tick)
        adjusted_price = price / (10 ** (decimals1 - decimals0))
        if invert_price:
            adjusted_price = 1 / adjusted_price
            tokens = "{} for {}".format(token0, token1)
        else:
            tokens = "{} for {}".format(token1, token0)

        # Compute square roots of prices corresponding to the bottom and top ticks
        bottom_tick = tick
        top_tick = bottom_tick + tick_spacing
        sa = tick_to_price(bottom_tick // 2)
        sb = tick_to_price(top_tick // 2)

        if tick == current_range_bottom_tick:

            current_sqrt_price = tick_to_price(current_tick / 2)
            amount0actual = liquidity * (sb - current_sqrt_price) / (
                        current_sqrt_price * sb)  # eq(12) in technical note
            amount1actual = liquidity * (current_sqrt_price - sa)  # eq(13) in technical note
            adjusted_amount0actual = amount0actual / (10 ** decimals0)
            adjusted_amount1actual = amount1actual / (10 ** decimals1)

            break

        tick += tick_spacing

    price_with_inversion = 1 / adjusted_current_price if invert_price else adjusted_current_price

    total_tick_liquidity = adjusted_amount0actual + price_with_inversion*adjusted_amount1actual if invert_price else \
        adjusted_amount0actual*price_with_inversion + adjusted_amount1actual

    return adjusted_amount0actual, adjusted_amount1actual, total_tick_liquidity, price_with_inversion


if __name__ == '__main__':

    client = Client(
        transport=RequestsHTTPTransport(
            url='https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3',
            verify=True,
            retries=5,
        ))

    pool_info_d = get_pool_info(client, POOL_ID)
    print(f'* Pool={POOL_ID}, details: {pool_info_d}')

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    usd_volume = get_usd_volume(client, POOL_ID, yesterday)
    print(f'* Daily volume of pool for {yesterday:%Y-%m-%d}: {usd_volume:,.0f}$')

    tick_mapping_d = get_tick_mapping(client, POOL_ID)
    liq_0, liq_1, liq_total, price = get_liquidity_at_current_tick(pool_info_d, tick_mapping_d)
    print(f'* Current tick liquidity: {pool_info_d["token0"]}={liq_0:,.2f}, {pool_info_d["token1"]}={liq_1:,.2f}')
    print(f'* Price={price:,.2f}, total current tick liquidity={liq_total:,.2f}')

    implied_vol = get_annualized_implied_volatility(pool_info_d['fee_tier'] * 1e-4, usd_volume, liq_total)
    print(f'* Implied volatility (annualized)={implied_vol:.2f}%')
