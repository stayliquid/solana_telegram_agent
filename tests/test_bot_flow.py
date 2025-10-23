import pytest
import os
from dotenv import load_dotenv

# --- Test Setup ---
# Override environment variables to ensure we use real APIs for this test suite.
os.environ["USE_MOCK_OPENAI"] = "False"

# We must import the functions *after* setting the environment variables.
from core.agent import parse_intent_from_text
from core.engine import find_and_propose_pool
from core.raydium_helpers import get_clmm_deposit_amounts

# --- Fixtures ---
@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Automatically loads environment variables from .env file for all tests."""
    load_dotenv()

# --- Pytest Markers ---
# Skips tests if the necessary API keys are not present in the environment.
requires_openai = pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set")
requires_cmc = pytest.mark.skipif(not os.getenv("COINMARKETCAP_API_KEY"), reason="COINMARKETCAP_API_KEY is not set")

# --- Test Cases ---

@requires_openai
@pytest.mark.asyncio
async def test_step_1_intent_parsing_low_risk():
    """
    Tests Step 1: Intent Parsing.
    Verifies that a simple user query is correctly parsed into a structured intent by the LLM.
    """
    # 1. Input: A simple, clear user query.
    user_text = "find a low risk pool for me"

    # 2. Action: Call the intent parsing function.
    intent, conversational_response = await parse_intent_from_text(user_text)

    # 3. Assertions: Check if the output is as expected.
    assert conversational_response is None, "The LLM should have called a tool, not given a conversational response."
    assert isinstance(intent, dict)
    assert "risk_level" in intent
    assert intent["risk_level"] == "low"
    assert "market_cap_rank_limit" in intent, "Default market_cap_rank_limit should be set."

@requires_openai
@requires_cmc
@pytest.mark.asyncio
async def test_step_2_find_pool_with_intent():
    """
    Tests Step 2: Pool Finding.
    Verifies that a valid intent dictionary can be used to fetch a real pool proposal.
    This is a live E2E test against Raydium and CoinMarketCap APIs.
    """
    # 1. Input: A structured intent, similar to what step 1 would produce.
    intent = {"risk_level": "low", "market_cap_rank_limit": 100}

    # 2. Action: Call the pool finding engine.
    proposal = await find_and_propose_pool(intent)

    # 3. Assertions: Check if the proposal is valid and has the correct structure.
    assert proposal is not None, "The engine should have found at least one pool."
    assert isinstance(proposal, dict)
    
    expected_keys = ["pool_id", "pool_name", "apy", "liquidity", "volume_24h", "raw_proposal"]
    for key in expected_keys:
        assert key in proposal, f"Proposal is missing key: {key}"

    assert isinstance(proposal["pool_id"], str) and proposal["pool_id"] != ""
    assert isinstance(proposal["pool_name"], str) and "-" in proposal["pool_name"]
    assert isinstance(proposal["apy"], float) and proposal["apy"] >= 0
    assert isinstance(proposal["liquidity"], float) and proposal["liquidity"] > 0
    assert isinstance(proposal["raw_proposal"], dict)

@requires_openai
@requires_cmc
@pytest.mark.asyncio
async def test_step_3_calculate_deposit_amounts():
    """
    Tests Step 3: Deposit Calculation.
    Verifies that for a valid pool and a USD amount, the correct token breakdown is calculated.
    This test first finds a live pool and then uses its data for the calculation.
    """
    # 1. Input Setup: Find a live pool first to get its raw data.
    intent = {"risk_level": "medium", "market_cap_rank_limit": 150}
    proposal = await find_and_propose_pool(intent)
    assert proposal is not None, "Prerequisite for this test failed: could not find a pool."
    
    pool_data = proposal["raw_proposal"]
    deposit_usd = 1000.0  # A sample deposit amount in USD.

    # 2. Action: Call the deposit calculation helper.
    result = get_clmm_deposit_amounts(pool_data, deposit_usd)

    # 3. Assertions: Check if the calculation result is valid.
    assert result is not None, "Calculation should return a result, not None."
    assert isinstance(result, dict)

    expected_keys = ["deposit_value_usd", "yearly_return_usd", "token_a", "token_b"]
    for key in expected_keys:
        assert key in result, f"Calculation result is missing key: {key}"

    # Verify the values and their types
    assert pytest.approx(result["deposit_value_usd"], 0.01) == deposit_usd
    assert isinstance(result["yearly_return_usd"], float) and result["yearly_return_usd"] >= 0
    
    assert isinstance(result["token_a"], dict)
    assert "symbol" in result["token_a"] and isinstance(result["token_a"]["symbol"], str)
    assert "amount" in result["token_a"] and isinstance(result["token_a"]["amount"], float) and result["token_a"]["amount"] > 0
    
    assert isinstance(result["token_b"], dict)
    assert "symbol" in result["token_b"] and isinstance(result["token_b"]["symbol"], str)
    assert "amount" in result["token_b"] and isinstance(result["token_b"]["amount"], float) and result["token_b"]["amount"] > 0