"""
SELECTIVE CANDLE CACHE
======================
Only caches data for low-priority tokens where timing doesn't matter.
NEVER caches whale tokens, active setups, or tokens near trigger.

WizTheory + Hunter Mode timing is PRESERVED.
"""

import time
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache storage: {token_address: {'candles': [...], 'timestamp': float, 'tier': int}}
_candle_cache: Dict[str, dict] = {}

# Cache settings
CACHE_TTL_TIER2 = 90   # 90 seconds for Tier 2
CACHE_TTL_TIER3 = 120  # 120 seconds for Tier 3
CACHE_TTL_MAX = 120    # Never exceed 120 seconds


def get_token_tier(token: dict) -> int:
    """
    Determine token priority tier.
    
    Tier 1: Whale tokens, breakout tokens, active setups → NEVER CACHE
    Tier 2: Normal tokens, not near trigger → Light cache OK (90s)
    Tier 3: Aging/quiet tokens → Cache OK (120s)
    """
    # Tier 1 conditions - NEVER CACHE
    if token.get('is_whale') or token.get('has_whale'):
        return 1
    if token.get('ath_breakout') or token.get('major_high_break'):
        return 1
    if token.get('passes_382fz_gate') or token.get('passes_50fz_gate'):
        return 1
    if token.get('passes_618fz_gate') or token.get('passes_786fz_gate'):
        return 1
    if token.get('passes_underfib_gate'):
        return 1
    if token.get('is_active_setup'):
        return 1
    if token.get('is_new', True):  # New tokens default to Tier 1
        return 1
    
    # Check structure score - high score = more important
    struct_score = token.get('structure_score', 0)
    if struct_score >= 60:
        return 1
    
    # Tier 3 - quiet/aging tokens
    if struct_score < 40:
        return 3
    
    # Default Tier 2
    return 2


def is_near_trigger(token: dict) -> bool:
    """
    Check if token is near any fib trigger level.
    If near trigger, we MUST use fresh data.
    """
    retrace_pct = token.get('retracement_pct', 0)
    
    # Near any fib level (within 12% of the fib)
    for fib in [38.2, 50, 61.8, 78.6]:
        if abs(retrace_pct - fib) < 12:
            return True
    
    if token.get('at_flip_zone'):
        return True
    if token.get('showing_exhaustion'):
        return True
    if token.get('structure_intact'):
        return True
    
    return False


def should_use_cache(token: dict) -> Tuple[bool, str]:
    """
    Determine if we should use cached candles for this token.
    
    Returns: (use_cache: bool, reason: str)
    """
    address = token.get('address') or token.get('pair_address', '')
    
    if not address:
        return False, "no_address"
    
    tier = get_token_tier(token)
    
    # Tier 1 = ALWAYS fresh
    if tier == 1:
        reasons = []
        if token.get('is_whale') or token.get('has_whale'):
            reasons.append("whale")
        if token.get('ath_breakout') or token.get('major_high_break'):
            reasons.append("breakout")
        if any(token.get(g) for g in ['passes_382fz_gate', 'passes_50fz_gate', 'passes_618fz_gate', 'passes_786fz_gate', 'passes_underfib_gate']):
            reasons.append("gate_passed")
        return False, f"tier1:{'+'.join(reasons) if reasons else 'priority'}"
    
    if is_near_trigger(token):
        return False, "near_trigger"
    
    if address not in _candle_cache:
        return False, "no_cache"
    
    cached = _candle_cache[address]
    age = time.time() - cached['timestamp']
    
    ttl = CACHE_TTL_TIER2 if tier == 2 else CACHE_TTL_TIER3
    
    if age > ttl:
        return False, f"expired:{age:.0f}s"
    
    return True, f"hit:T{tier}:{age:.0f}s"


def get_cached_candles(token: dict) -> Optional[List[dict]]:
    """Get cached candles if valid. Returns None if fresh fetch needed."""
    address = token.get('address') or token.get('pair_address', '')
    symbol = token.get('symbol', '???')
    
    use_cache, reason = should_use_cache(token)
    
    if use_cache:
        cached = _candle_cache.get(address, {})
        candles = cached.get('candles', [])
        if candles:
            logger.info(f"   [CACHE] {symbol}: ✓ Using cached ({reason})")
            return candles
    
    logger.debug(f"   [CACHE] {symbol}: Fresh fetch ({reason})")
    return None


def store_candles(token: dict, candles: List[dict]) -> None:
    """Store candles for Tier 2/3 tokens only."""
    address = token.get('address') or token.get('pair_address', '')
    symbol = token.get('symbol', '???')
    
    if not address or not candles:
        return
    
    tier = get_token_tier(token)
    
    if tier == 1:
        return  # Never cache Tier 1
    
    _candle_cache[address] = {
        'candles': candles,
        'timestamp': time.time(),
        'tier': tier,
        'symbol': symbol
    }


def clear_expired_cache() -> int:
    """Clear expired entries. Returns count cleared."""
    now = time.time()
    expired = [addr for addr, c in _candle_cache.items() if now - c['timestamp'] > CACHE_TTL_MAX]
    
    for addr in expired:
        del _candle_cache[addr]
    
    return len(expired)


def invalidate_token(address: str) -> bool:
    """Invalidate cache for a token when it becomes high priority."""
    if address in _candle_cache:
        del _candle_cache[address]
        return True
    return False


def get_cache_stats() -> dict:
    """Get cache statistics."""
    now = time.time()
    ages = [now - c['timestamp'] for c in _candle_cache.values()]
    return {
        'total': len(_candle_cache),
        'avg_age': sum(ages) / len(ages) if ages else 0
    }
