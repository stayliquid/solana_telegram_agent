# python-bot/core/schemas.py
from pydantic import BaseModel

# This file centralizes the schemas for the tools that our OpenAI agent can use.
# By defining them here, we can easily add, remove, or modify the parameters
# the AI can understand and extract, without changing the core agent logic.
#
# To extend the bot's capabilities, you can:
# 1. Add new properties to the existing `find_liquidity_pools` tool.
#    For example, add a `min_tvl_usd` property if you later integrate a
#    data source that provides TVL information.
# 2. Add entirely new tool schemas for different user intents.
#    For example, a `GET_TOKEN_PRICE_TOOL` if you want the bot to answer
#    questions about specific token prices.

FIND_LIQUIDITY_POOLS_TOOL = {
    "type": "function",
    "function": {
        "name": "find_liquidity_pools",
        "description": "Finds liquidity pools based on user-defined criteria such as risk level and token market cap.",
        "parameters": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "description": "The desired risk level for the investment. Defaults to 'low' if not specified.",
                    "enum": ["low", "medium", "high"],
                },
                "market_cap_rank_limit": {
                    "type": "integer",
                    "description": "The maximum market cap rank for tokens to be included in the pool (e.g., 10 for top 10 tokens). Defaults to 100 if not specified.",
                },
                # --- Example of a future extension ---
                # "min_tvl_usd": {
                #     "type": "integer",
                #     "description": "The minimum total value locked (TVL) in USD for a pool to be considered.",
                # }
            },
            "required": ["risk_level", "market_cap_rank_limit"],
        },
    },
}

# --- Solana Action Schemas ---
class ActionPostRequest(BaseModel):
    account: str
    amount: str | None = None