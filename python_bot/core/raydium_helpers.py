import logging
from decimal import Decimal, getcontext
import requests

# Set precision for Decimal calculations
getcontext().prec = 50

logger = logging.getLogger(__name__)

# Constants ported from Raydium SDK for math operations
Q64 = 2**64
MIN_TICK = -443636
MAX_TICK = 443636

# --- Data Fetching ---

def get_token_prices(mints: list[str]) -> dict[str, float]:
    """Fetches token prices in USD from Raydium's API."""
    try:
        url = f"https://api-v3.raydium.io/mint/price?mints={','.join(mints)}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get('data', {})
        prices = {mint: float(price_data.get('price', 0)) for mint, price_data in data.items()}
        logger.info(f"Fetched prices: {prices}")
        return prices
    except Exception as e:
        logger.error(f"Failed to fetch token prices: {e}")
        return {}

# --- Math Helpers (Python port of Raydium SDK math) ---

def mul_div_ceil(a: int, b: int, d: int) -> int:
    """Equivalent to Raydium SDK's MathUtil.mulDivCeil for precise integer math."""
    if d == 0: raise ValueError("Division by zero")
    return (a * b + d - 1) // d

class SqrtPriceMath:
    @staticmethod
    def get_sqrt_price_x64_from_tick(tick: int) -> int:
        """
        Calculates the sqrt(price) * 2^64 from a given tick index.
        This is a Python approximation of the SDK's bitwise-heavy function.
        """
        if not MIN_TICK <= tick <= MAX_TICK:
            raise ValueError("Tick out of bounds")
        price = Decimal("1.0001") ** Decimal(tick)
        sqrt_price = price.sqrt()
        return int(sqrt_price * Q64)

class LiquidityMath:
    @staticmethod
    def get_amounts_from_liquidity(
        sqrt_price_current_x64: int,
        sqrt_price_lower_x64: int,
        sqrt_price_upper_x64: int,
        liquidity: int,
        round_up: bool,
    ) -> tuple[int, int]:
        """Calculates tokenA and tokenB amounts for a given liquidity and price range."""
        if sqrt_price_lower_x64 > sqrt_price_upper_x64:
            sqrt_price_lower_x64, sqrt_price_upper_x64 = sqrt_price_upper_x64, sqrt_price_lower_x64

        amount_a = 0
        amount_b = 0

        if sqrt_price_current_x64 <= sqrt_price_lower_x64:
            amount_a = LiquidityMath._get_token_a_from_liquidity(
                sqrt_price_lower_x64, sqrt_price_upper_x64, liquidity, round_up
            )
        elif sqrt_price_current_x64 < sqrt_price_upper_x64:
            amount_a = LiquidityMath._get_token_a_from_liquidity(
                sqrt_price_current_x64, sqrt_price_upper_x64, liquidity, round_up
            )
            amount_b = LiquidityMath._get_token_b_from_liquidity(
                sqrt_price_lower_x64, sqrt_price_current_x64, liquidity, round_up
            )
        else:
            amount_b = LiquidityMath._get_token_b_from_liquidity(
                sqrt_price_lower_x64, sqrt_price_upper_x64, liquidity, round_up
            )
        
        return int(amount_a), int(amount_b)

    @staticmethod
    def _get_token_a_from_liquidity(sqrt_price_x64_a: int, sqrt_price_x64_b: int, liquidity: int, round_up: bool) -> int:
        """Helper for calculating amount of token A."""
        if sqrt_price_x64_a > sqrt_price_x64_b:
            sqrt_price_x64_a, sqrt_price_x64_b = sqrt_price_x64_b, sqrt_price_x64_a
        
        numerator1 = liquidity << 64
        numerator2 = sqrt_price_x64_b - sqrt_price_x64_a

        if round_up:
            term1 = mul_div_ceil(numerator1, numerator2, sqrt_price_x64_b)
            return mul_div_ceil(term1, 1, sqrt_price_x64_a)
        else:
            return (numerator1 * numerator2 // sqrt_price_x64_b) // sqrt_price_x64_a

    @staticmethod
    def _get_token_b_from_liquidity(sqrt_price_x64_a: int, sqrt_price_x64_b: int, liquidity: int, round_up: bool) -> int:
        """Helper for calculating amount of token B."""
        if sqrt_price_x64_a > sqrt_price_x64_b:
            sqrt_price_x64_a, sqrt_price_x64_b = sqrt_price_x64_b, sqrt_price_x64_a
        
        if round_up:
            return mul_div_ceil(liquidity, sqrt_price_x64_b - sqrt_price_x64_a, Q64)
        else:
            return (liquidity * (sqrt_price_x64_b - sqrt_price_x64_a)) // Q64

# --- Main Calculation Logic ---

def get_clmm_deposit_amounts(pool_data: dict, deposit_usd: float) -> dict | None:
    """
    Calculates the required amounts of tokenA and tokenB for a given USD deposit
    into a Raydium CLMM pool.
    """
    try:
        # 1. Extract necessary data from the pool proposal
        mint_a_data = pool_data.get("mintA", {})
        mint_b_data = pool_data.get("mintB", {})
        config_data = pool_data.get("config", {})

        mint_a = mint_a_data.get("address")
        mint_b = mint_b_data.get("address")
        decimals_a = mint_a_data.get("decimals")
        decimals_b = mint_b_data.get("decimals")
        
        current_price = Decimal(pool_data.get("price"))
        tick_spacing = config_data.get("tickSpacing")
        apy_24h = pool_data.get("day", {}).get("apr", 0) / 100.0

        if any(v is None for v in [mint_a, mint_b, decimals_a, decimals_b, current_price, tick_spacing]):
            logger.error("Pool data is missing essential fields for calculation.")
            return None

        # 2. Get token prices
        token_prices = get_token_prices([mint_a, mint_b])
        price_a_usd = token_prices.get(mint_a)
        price_b_usd = token_prices.get(mint_b)
        
        if not all([price_a_usd, price_b_usd]):
            logger.error(f"Could not fetch valid prices for tokens {mint_a} or {mint_b}.")
            return None

        # 3. Define the price range (e.g., +/- 10% of current price)
        price_lower = current_price * Decimal("0.9")
        price_upper = current_price * Decimal("1.1")
        
        tick_lower = (int(price_lower.ln() / Decimal("1.0001").ln()) // tick_spacing) * tick_spacing
        tick_upper = (int(price_upper.ln() / Decimal("1.0001").ln()) // tick_spacing) * tick_spacing

        # 4. Convert prices and ticks to Q64.64 format
        sqrt_price_current_x64 = int((current_price.sqrt()) * Q64)
        sqrt_price_lower_x64 = SqrtPriceMath.get_sqrt_price_x64_from_tick(tick_lower)
        sqrt_price_upper_x64 = SqrtPriceMath.get_sqrt_price_x64_from_tick(tick_upper)

        # 5. Calculate amounts for a unit of liquidity to find its value
        unit_liquidity = 1_000_000
        unit_amount_a, unit_amount_b = LiquidityMath.get_amounts_from_liquidity(
            sqrt_price_current_x64, sqrt_price_lower_x64, sqrt_price_upper_x64, unit_liquidity, round_up=False
        )

        # 6. Calculate the USD value of this unit liquidity
        unit_value_a_usd = (unit_amount_a / (10**decimals_a)) * price_a_usd
        unit_value_b_usd = (unit_amount_b / (10**decimals_b)) * price_b_usd
        unit_value_total_usd = unit_value_a_usd + unit_value_b_usd
        
        if unit_value_total_usd == 0:
            logger.error("Calculated unit value is zero, cannot determine liquidity.")
            return None

        # 7. Calculate target liquidity for the user's desired USD deposit
        target_liquidity = (deposit_usd / unit_value_total_usd) * unit_liquidity

        # 8. Calculate final token amounts using the target liquidity
        final_amount_a_raw, final_amount_b_raw = LiquidityMath.get_amounts_from_liquidity(
            sqrt_price_current_x64, sqrt_price_lower_x64, sqrt_price_upper_x64, int(target_liquidity), round_up=False
        )

        # 9. Convert raw amounts to human-readable format
        amount_a = final_amount_a_raw / (10**decimals_a)
        amount_b = final_amount_b_raw / (10**decimals_b)

        # 10. Calculate estimated yearly return in USD
        yearly_return_usd = deposit_usd * apy_24h

        return {
            "deposit_value_usd": deposit_usd,
            "yearly_return_usd": yearly_return_usd,
            "token_a": {"symbol": mint_a_data.get("symbol"), "amount": amount_a},
            "token_b": {"symbol": mint_b_data.get("symbol"), "amount": amount_b},
        }
    except Exception as e:
        logger.error(f"Error in CLMM deposit calculation: {e}", exc_info=True)
        return None