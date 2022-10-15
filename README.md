
# Implied Volatility of Uniswap v3 Pools

## Intro

Based on Guillaume Lambert's [analysis](https://lambert-guillaume.medium.com/on-chain-volatility-and-uniswap-v3-d031b98143d1), we have the following relationship:

$$\textrm{Implied volatility} = 2 \gamma \sqrt{\frac{\textrm{Daily volume}}{\textrm{Tick liquidity}}}$$

Where $\gamma$ is the pool's fee tier (eg. $0.3$% for the [USDC-ETH pool on Ethereum mainnet](https://info.uniswap.org/#/pools/0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8)).

Liquidity at the current tick and daily volume (for the previous day) can be both obtained using the Uniswap v3 subgraph:
https://thegraph.com/hosted-service/subgraph/uniswap/uniswap-v3

To extract the liquidity at the current tick, we make heavy use of the following functions:
https://github.com/atiselsts/uniswap-v3-liquidity-math/blob/master/subgraph-liquidity-range-example.py

To extract the daily volume, we use the `PoolDayData` entity in the subgraph schema:
https://github.com/Uniswap/v3-subgraph/blob/main/schema.graphql

## Running the code

Edit the `POOL_ID` in `implied_vol.py` then run:

    python implied_vol.py

This should output something like:

```
* Pool=0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8, details: {'current_tick': 204741, 'fee_tier': 3000, 'tick_spacing': 60, 'token0': 'USDC', 'token1': 'WETH', 'decimals0': 6, 'decimals1': 18}
* Daily volume of pool for 2022-10-15: 12,386,430$
* Querying ticks............
* Current tick liquidity: USDC=1,037,335.91, WETH=435.12
* Price=1,284.27, total current tick liquidity=1,596,152.74
* Implied volatility (annualized)=31.93%
```

## Caveats

* For this to work, one token of the pool at least needs to be a USD stablecoin, since the daily volume query returns a figure in USD.
* Note that daily volume is seasonal (eg. it tends to be lower on Sundays), so the results will vary depending when the code is run.  An improvement would be to use `PoolHourData` and sum the volume for the last 24 hours.
