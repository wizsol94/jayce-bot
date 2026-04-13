"""
TIERED CACHE SYSTEM v1.0
========================
Behavior-based caching for budget efficiency with edge speed.

TIERS:
- Tier 1: Active edge tokens (30-120s cache)
- Tier 2: Watchlist tokens (3-5 min cache)
- Tier 3: Background tokens (10-15 min cache)

TRIGGER INTELLIGENCE:
- Near fib/flip zone (5-10% distance)
- Directional momentum toward zone
- Key fib breaks (382, 50)
- Exhaustion/rejection behavior
- Structural shift (BOS)
- Active setup candidate
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CACHE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TierConfig:
    name: str
    cache_1m_seconds: int  # 0 = 1m OFF
    cache_5m_seconds: int
    description: str

TIER_CONFIGS = {
    1: TierConfig(
        name="ACTIVE_EDGE",
        cache_1m_seconds=45,      # 30-60 seconds
        cache_5m_seconds=90,      # 60-120 seconds
        description="Active setup candidates, near trigger, whale-priority"
    ),
    2: TierConfig(
        name="WATCHLIST",
        cache_1m_seconds=0,       # 1m OFF
        cache_5m_seconds=240,     # 3-5 minutes
        description="Good structure but not near trigger"
    ),
    3: TierConfig(
        name="BACKGROUND",
        cache_1m_seconds=0,       # 1m OFF
        cache_5m_seconds=720,     # 10-15 minutes
        description="Low priority, no active setup behavior"
    )
}

# ══════════════════════════════════════════════════════════════════════════════
# CACHE STORAGE
# ══════════════════════════════════════════════════════════════════════════════

# Format: {cache_key: {'candles': [...], 'timestamp': datetime, 'timeframe': '5m'|'1m'}}
TIERED_CACHE: Dict[str, dict] = {}

# Token tier assignments: {token_address: tier_number}
TOKEN_TIERS: Dict[str, int] = {}

# Tier statistics
TIER_STATS = {
    'tier1_calls': 0,
    'tier2_calls': 0,
    'tier3_calls': 0,
    'tier1_tokens': set(),
    'tier2_tokens': set(),
    'tier3_tokens': set(),
    'promotions_today': 0,
    'demotions_today': 0,
    'last_reset': datetime.now().date()
}

# ══════════════════════════════════════════════════════════════════════════════
# TRIGGER INTELLIGENCE - Behavior-based tier assignment
# ══════════════════════════════════════════════════════════════════════════════

def assess_token_tier(
    token: Dict,
    candles_5m: List[Dict] = None,
    structure: Dict = None
) -> Tuple[int, str]:
    """
    Assess which tier a token belongs to based on BEHAVIOR, not just distance.
    
    Returns:
        (tier_number, reason)
    """
    reasons = []
    
    # ─────────────────────────────────────────────────
    # TIER 1 CRITERIA (any match = Tier 1)
    # ─────────────────────────────────────────────────
    
    # 1. Whale-priority token
    if token.get('whale_detected') or token.get('whale_priority'):
        return (1, "whale_priority")
    
    # 2. Active setup candidate (gate passed)
    if token.get('passes_50fz_gate') or token.get('passes_underfib_gate'):
        return (1, "setup_gate_passed")
    
    # 3. High hybrid score
    hybrid_score = token.get('hybrid_score', 0) or token.get('score', 0)
    if hybrid_score >= 100:
        return (1, f"high_score_{hybrid_score}")
    
    # 4. Fresh token forming structure (<2 hours)
    pair_created = token.get('pairCreatedAt', 0)
    if pair_created:
        try:
            age_hours = (datetime.now().timestamp() - (pair_created / 1000 if pair_created > 1e12 else pair_created)) / 3600
            if age_hours < 2:
                return (1, f"fresh_{age_hours:.1f}h")
        except:
            pass
    
    # 5-8. Behavior-based checks (require candle data)
    if candles_5m and len(candles_5m) >= 20:
        tier1_reason = _check_behavior_triggers(candles_5m, token, structure)
        if tier1_reason:
            return (1, tier1_reason)
    
    # ─────────────────────────────────────────────────
    # TIER 2 CRITERIA (watchlist-worthy)
    # ─────────────────────────────────────────────────
    
    # Good structure but not near trigger
    if structure:
        if structure.get('has_valid_flip_zone') or structure.get('ath_breakout') or structure.get('major_high_break'):
            return (2, "good_structure")
    
    # Moderate score
    if 60 <= hybrid_score < 100:
        return (2, f"moderate_score_{hybrid_score}")
    
    # Has been in watchlist
    if token.get('in_watchlist') or token.get('watchlist_source'):
        return (2, "watchlist_token")
    
    # ─────────────────────────────────────────────────
    # TIER 3 (default - background)
    # ─────────────────────────────────────────────────
    return (3, "background")


def _check_behavior_triggers(candles: List[Dict], token: Dict, structure: Dict = None) -> Optional[str]:
    """
    Check behavior-based Tier 1 triggers.
    Returns reason string if Tier 1, None otherwise.
    """
    try:
        # Get price data
        recent_close = float(candles[-1].get('c', 0))
        highs = [float(c.get('h', 0)) for c in candles]
        lows = [float(c.get('l', 0)) for c in candles]
        closes = [float(c.get('c', 0)) for c in candles]
        
        if not recent_close or not highs or not lows:
            return None
        
        swing_high = max(highs)
        swing_low = min(lows)
        fib_range = swing_high - swing_low
        
        if fib_range <= 0 or swing_high <= 0:
            return None
        
        # Calculate fib levels
        fib_382 = swing_high - (fib_range * 0.382)
        fib_50 = swing_high - (fib_range * 0.50)
        fib_618 = swing_high - (fib_range * 0.618)
        fib_786 = swing_high - (fib_range * 0.786)
        
        fibs = {'382': fib_382, '50': fib_50, '618': fib_618, '786': fib_786}
        
        # ─────────────────────────────────────────────────
        # TRIGGER 1: Near fib/flip zone (5-10% distance)
        # ─────────────────────────────────────────────────
        for fib_name, fib_level in fibs.items():
            if fib_level > 0:
                distance_pct = abs(recent_close - fib_level) / fib_level * 100
                if distance_pct <= 8:  # Within 8%
                    return f"near_fib_{fib_name}_{distance_pct:.1f}pct"
        
        # ─────────────────────────────────────────────────
        # TRIGGER 2: Directional momentum toward zone
        # ─────────────────────────────────────────────────
        if len(closes) >= 5:
            recent_trend = closes[-1] - closes[-5]
            # Price falling toward lower fibs
            if recent_trend < 0:
                for fib_name in ['618', '786']:
                    fib_level = fibs[fib_name]
                    if recent_close > fib_level and recent_close < fib_level * 1.15:
                        return f"momentum_toward_{fib_name}"
        
        # ─────────────────────────────────────────────────
        # TRIGGER 3: Key fib break (382 or 50)
        # ─────────────────────────────────────────────────
        if len(closes) >= 3:
            prev_close = closes[-3]
            # Broke below 382
            if prev_close > fib_382 and recent_close < fib_382:
                return "broke_382"
            # Broke below 50
            if prev_close > fib_50 and recent_close < fib_50:
                return "broke_50"
        
        # ─────────────────────────────────────────────────
        # TRIGGER 4: Exhaustion/rejection behavior
        # ─────────────────────────────────────────────────
        recent_high = max(highs[-10:]) if len(highs) >= 10 else max(highs)
        from_high_pct = ((recent_high - recent_close) / recent_high) * 100 if recent_high > 0 else 0
        
        if 5 <= from_high_pct <= 20:
            return f"exhaustion_{from_high_pct:.1f}pct"
        
        # ─────────────────────────────────────────────────
        # TRIGGER 5: Structural shift (BOS approximation)
        # ─────────────────────────────────────────────────
        if len(candles) >= 10:
            # Check for recent direction change
            first_half_avg = sum(closes[:len(closes)//2]) / (len(closes)//2)
            second_half_avg = sum(closes[len(closes)//2:]) / (len(closes) - len(closes)//2)
            
            # Significant direction change
            change_pct = abs(second_half_avg - first_half_avg) / first_half_avg * 100 if first_half_avg > 0 else 0
            if change_pct >= 10:
                direction = "bearish" if second_half_avg < first_half_avg else "bullish"
                return f"structural_shift_{direction}"
        
        return None
        
    except Exception as e:
        logger.debug(f"Behavior trigger check error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CACHE OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_cache_key(address: str, timeframe: str) -> str:
    """Generate cache key for address + timeframe."""
    return f"{address}:{timeframe}"


def get_tiered_cache(
    address: str,
    timeframe: str,
    token: Dict = None,
    candles_5m: List[Dict] = None,
    structure: Dict = None
) -> Tuple[Optional[List[Dict]], bool, int]:
    """
    Get cached candles if valid for token's tier.
    
    Returns:
        (candles or None, cache_hit: bool, tier: int)
    """
    # Reset daily stats if new day
    _reset_daily_stats()
    
    # Determine token tier
    tier, reason = assess_token_tier(token or {}, candles_5m, structure)
    tier_config = TIER_CONFIGS[tier]
    
    # Track tier assignment
    token_addr = address or token.get('address', '') if token else ''
    if token_addr:
        old_tier = TOKEN_TIERS.get(token_addr, 3)
        TOKEN_TIERS[token_addr] = tier
        
        # Track promotions/demotions
        if tier < old_tier:
            TIER_STATS['promotions_today'] += 1
        elif tier > old_tier:
            TIER_STATS['demotions_today'] += 1
        
        # Track tokens per tier
        TIER_STATS[f'tier{tier}_tokens'].add(token_addr)
    
    # Check if 1m is allowed for this tier
    if timeframe == '1m' and tier_config.cache_1m_seconds == 0:
        return (None, False, tier)  # 1m not allowed for this tier
    
    # Get cache TTL for this tier/timeframe
    ttl_seconds = tier_config.cache_1m_seconds if timeframe == '1m' else tier_config.cache_5m_seconds
    
    # Check cache
    cache_key = get_cache_key(address, timeframe)
    if cache_key in TIERED_CACHE:
        cached = TIERED_CACHE[cache_key]
        age_seconds = (datetime.now() - cached['timestamp']).total_seconds()
        
        if age_seconds < ttl_seconds:
            return (cached['candles'], True, tier)
    
    return (None, False, tier)


def store_tiered_cache(
    address: str,
    timeframe: str,
    candles: List[Dict],
    tier: int = 3
):
    """Store candles in tiered cache."""
    cache_key = get_cache_key(address, timeframe)
    TIERED_CACHE[cache_key] = {
        'candles': candles,
        'timestamp': datetime.now(),
        'timeframe': timeframe,
        'tier': tier
    }
    
    # Track API call by tier
    TIER_STATS[f'tier{tier}_calls'] += 1


def should_fetch_1m(token: Dict, candles_5m: List[Dict] = None, structure: Dict = None) -> Tuple[bool, str]:
    """
    Determine if 1m should be fetched for this token.
    Only Tier 1 tokens get 1m access.
    
    Returns:
        (should_fetch: bool, reason: str)
    """
    tier, reason = assess_token_tier(token, candles_5m, structure)
    return (tier == 1, reason)


def _reset_daily_stats():
    """Reset daily stats if new day."""
    today = datetime.now().date()
    if today > TIER_STATS['last_reset']:
        TIER_STATS['tier1_calls'] = 0
        TIER_STATS['tier2_calls'] = 0
        TIER_STATS['tier3_calls'] = 0
        TIER_STATS['tier1_tokens'] = set()
        TIER_STATS['tier2_tokens'] = set()
        TIER_STATS['tier3_tokens'] = set()
        TIER_STATS['promotions_today'] = 0
        TIER_STATS['demotions_today'] = 0
        TIER_STATS['last_reset'] = today


def get_tier_stats() -> Dict:
    """Get current tier statistics for visibility."""
    return {
        'tier1_calls': TIER_STATS['tier1_calls'],
        'tier2_calls': TIER_STATS['tier2_calls'],
        'tier3_calls': TIER_STATS['tier3_calls'],
        'tier1_tokens': len(TIER_STATS['tier1_tokens']),
        'tier2_tokens': len(TIER_STATS['tier2_tokens']),
        'tier3_tokens': len(TIER_STATS['tier3_tokens']),
        'promotions_today': TIER_STATS['promotions_today'],
        'demotions_today': TIER_STATS['demotions_today'],
        'total_calls': TIER_STATS['tier1_calls'] + TIER_STATS['tier2_calls'] + TIER_STATS['tier3_calls']
    }


def cleanup_tiered_cache():
    """Remove expired cache entries."""
    now = datetime.now()
    max_age = 900  # 15 minutes max for any entry
    
    expired = [
        key for key, val in TIERED_CACHE.items()
        if (now - val['timestamp']).total_seconds() > max_age
    ]
    
    for key in expired:
        del TIERED_CACHE[key]
    
    if expired:
        logger.debug(f"Cleaned up {len(expired)} expired cache entries")


# ══════════════════════════════════════════════════════════════════════════════
# BUDGET PROJECTION
# ══════════════════════════════════════════════════════════════════════════════

def project_monthly_usage(days_remaining: int = 29) -> Dict:
    """Project monthly API usage based on current tier distribution."""
    stats = get_tier_stats()
    total_today = stats['total_calls']
    
    # Estimate CUs (30 CUs per call)
    cus_today = total_today * 30
    cus_projected = cus_today * days_remaining
    
    return {
        'calls_today': total_today,
        'cus_today': cus_today,
        'cus_projected': cus_projected,
        'budget_remaining': 5000000 - 463000,  # Update with actual
        'safe': cus_projected < (5000000 - 463000),
        'tier_breakdown': {
            'tier1': stats['tier1_calls'],
            'tier2': stats['tier2_calls'],
            'tier3': stats['tier3_calls']
        }
    }


if __name__ == '__main__':
    print("TIERED CACHE SYSTEM v1.0")
    print("=" * 50)
    for tier, config in TIER_CONFIGS.items():
        print(f"Tier {tier} ({config.name}):")
        print(f"  1m cache: {config.cache_1m_seconds}s")
        print(f"  5m cache: {config.cache_5m_seconds}s")
        print(f"  {config.description}")
