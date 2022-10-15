
pool_query = """query get_pools($pool_id: ID!) {
  pools(where: {id: $pool_id}) {
    tick
    sqrtPrice
    liquidity
    feeTier
    token0 {
      symbol
      decimals
    }
    token1 {
      symbol
      decimals
    }
  }
}"""

tick_query = """query get_ticks($num_skip: Int, $pool_id: ID!) {
  ticks(skip: $num_skip, where: {pool: $pool_id}) {
    tickIdx
    liquidityNet
  }
}"""

volume_query = """query get_poolDayDatas($id: ID!) {
  poolDayDatas(where: {id: $id}) {
    volumeUSD
  }
}"""
