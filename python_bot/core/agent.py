import json
import logging
from python_bot.core.schemas import FIND_LIQUIDITY_POOLS_TOOL
from python_bot.core.openai_client import openai_client, USE_MOCK_OPENAI

logger = logging.getLogger(__name__)


async def parse_intent_from_text(text: str) -> tuple[dict, str | None]:
    """
    Calls OpenAI. Returns a tuple containing the extracted intent dictionary
    and a direct text response if no tool was called.
    """
    if USE_MOCK_OPENAI:
        normalized_text = text.strip().lower()
        if normalized_text == "low":
            logger.info("--- MOCK AGENT: Matched 'low', returning hardcoded low-risk intent ---")
            return {"risk_level": "low", "market_cap_rank_limit": 50}, None
        if normalized_text == "medium":
            logger.info("--- MOCK AGENT: Matched 'medium', returning hardcoded medium-risk intent ---")
            return {"risk_level": "medium", "market_cap_rank_limit": 200}, None
        if normalized_text == "high":
            logger.info("--- MOCK AGENT: Matched 'high', returning hardcoded high-risk intent ---")
            return {"risk_level": "high", "market_cap_rank_limit": 250}, None

    if not openai_client:
        logger.error("OpenAI client not initialized. Cannot parse intent.")
        return {}, "Sorry, the AI model is not configured correctly."

    logger.info(f"--- REAL AGENT: Parsing text: '{text}' ---")

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful DeFi assistant. Your primary task is to determine if the user wants to find a liquidity pool. If they do, use the `find_liquidity_pools` tool to extract their preferences. If the user's message is a greeting or does not seem to be a request for a pool, respond with a friendly, conversational message. If the user does not specify a preference for risk or token rank, use reasonable defaults ('low' risk, rank limit 100).",
                },
                {"role": "user", "content": text},
            ],
            tools=[FIND_LIQUIDITY_POOLS_TOOL],
        )

        message = response.choices[0].message
        
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            function_args_json = tool_call.function.arguments
            logger.info(f"LLM returned function arguments: {function_args_json}")
            intent_dict = json.loads(function_args_json)
            return intent_dict, None
        else:
            logger.info("LLM did not call a tool. Returning conversational response.")
            return {}, message.content

    except Exception as e:
        logger.error(f"Error calling OpenAI or parsing response: {e}", exc_info=True)
        return {}, "Sorry, I encountered an error trying to understand that."