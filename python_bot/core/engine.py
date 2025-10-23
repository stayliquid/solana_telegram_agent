import requests
import logging
import os
import time
import json
from typing import Set, Dict, Any

logger = logging.getLogger(__name__)

# --- API Endpoints ---
RAYDIUM_POOLS_API_URL = "https://api-v3.raydium.io/pools/info/list?poolType=concentrated&poolSortField=volume24h&sortType=desc&pageSize=200&page=1"
COINMARKETCAP_API_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

# --- Caching ---
CMC_CACHE: Dict[str, Any] = {"timestamp": 0, "top_ranked_symbols": set()}
CACHE_DURATION_SECONDS = 3600  # 1 hour

# --- Configuration ---
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY")
RISK_TO_TVL_THRESHOLD = {
    "low": 5_000_000,
    "medium": 1_000_000,
    "high": 100_000,
}


async def get_top_ranked_symbols(rank_limit: int) -> Set[str]:
    """
    Fetches symbols of top-ranked tokens from CoinMarketCap, using a 1-hour cache.
    This is used to filter by market cap.
    """
    global CMC_CACHE
    now = time.time()

    if now - CMC_CACHE["timestamp"] < CACHE_DURATION_SECONDS and CMC_CACHE.get("top_ranked_symbols"):
        logger.info("--- Using cached CoinMarketCap data ---")
        return CMC_CACHE["top_ranked_symbols"]

    if not COINMARKETCAP_API_KEY:
        logger.warning("COINMARKETCAP_API_KEY not set. Market cap filtering will be disabled.")
        return set()

    logger.info(f"--- Fetching top {rank_limit} tokens from CoinMarketCap ---")
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY}
    params = {'limit': rank_limit, 'convert': 'USD'}

    try:
        response = requests.get(COINMARKETCAP_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Log the full response for debugging purposes
        logger.debug(f"--- Full CoinMarketCap API Response ---:\n{json.dumps(data, indent=2)}")

        top_symbols = set()
        for token in data.get('data', []):
            symbol = token.get('symbol')
            if symbol:
                top_symbols.add(symbol)
        
        if 'SOL' in top_symbols:
            top_symbols.add('WSOL')


        CMC_CACHE["timestamp"] = now
        CMC_CACHE["top_ranked_symbols"] = top_symbols
        logger.info(f"Found {len(top_symbols)} top-ranked symbols from CoinMarketCap.")
        return top_symbols
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from CoinMarketCap: {e}")
        return set()


async def find_and_propose_pool(intent: dict) -> dict | None:
    """
    Finds a liquidity pool by combining CoinMarketCap data (for market cap ranking)
    and Raydium data.
    """
    logger.info(f"--- REAL ENGINE: Searching for pool with intent: {intent} ---")

    risk_level = intent.get("risk_level", "low")
    rank_limit = intent.get("market_cap_rank_limit", 100)
    tvl_threshold = RISK_TO_TVL_THRESHOLD.get(risk_level, 0)
    
    # 1. Get the list of top-ranked token symbols from CoinMarketCap.
    top_ranked_symbols = await get_top_ranked_symbols(rank_limit)

    # If CMC filtering is active but fails to return any symbols, we can't proceed.
    if COINMARKETCAP_API_KEY and not top_ranked_symbols:
        logger.error("Market cap filtering is enabled but no top-ranked tokens were found. Cannot find a pool.")
        return None

    try:
        response = requests.get(RAYDIUM_POOLS_API_URL)
        response.raise_for_status()
        api_data = response.json()
        pools = api_data.get("data", {}).get("data", [])

        if not pools:
            logger.warning("Raydium API returned no pools.")
            return None

        best_pool = None
        best_apy = -1

        for pool in pools:
            symbolA = pool.get("mintA", {}).get("symbol")
            symbolB = pool.get("mintB", {}).get("symbol")
            tvl_ok = pool.get("tvl", 0) > tvl_threshold
            
            # A pool is valid if its TVL is sufficient and, if token filtering is on,
            # both of its tokens' symbols are in the top-ranked list.
            is_valid_pair = True
            if top_ranked_symbols: # Only apply this filter if we have a list of symbols
                is_valid_pair = symbolA in top_ranked_symbols and symbolB in top_ranked_symbols
            
            is_valid = tvl_ok and is_valid_pair

            # Find the valid pool with the highest APY.
            if is_valid:
                current_apy = pool.get('day', {}).get('apr', 0)
                if current_apy > best_apy:
                    best_apy = current_apy
                    best_pool = pool

        if not best_pool:
            logger.warning(f"No pools found matching criteria: risk='{risk_level}', tvl > ${tvl_threshold}")
            return None

        proposal = {
            "pool_id": best_pool['id'],
            "pool_name": f"{best_pool['mintA']['symbol']}-{best_pool['mintB']['symbol']}",
            "apy": best_pool['day']['apr'] / 100.0,
            "liquidity": best_pool['tvl'],
            "volume_24h": best_pool['day']['volume'],
            "raw_proposal": best_pool
        }
        logger.info(f"Proposing pool: {proposal['pool_name']} with TVL ${proposal['liquidity']:,.0f} and 24h Vol ${proposal['volume_24h']:,.0f}")
        return proposal

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching pool data from Raydium API: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in the engine: {e}", exc_info=True)
        return None