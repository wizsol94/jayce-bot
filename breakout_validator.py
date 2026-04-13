"""
BREAKOUT VALIDATOR v4
=====================
Detects HISTORICAL breakout with minimum 30% expansion.
This is REQUIRED before any setup is considered valid.

WIZTHEORY RULES:
- Find PRIOR RESISTANCE (major high before expansion, not only ATH)
- Price must BREAK above that resistance
- Price must EXPAND at least 30% above that broken level
- Token can be below ATH currently (retracing is expected)
- If no breakout + expansion >= 30% → REJECT immediately

CORRECT CALCULATION:
expansion_pct = ((expansion_high - breakout_level) / breakout_level) * 100

NOT: (chart_high - chart_low) / chart_low
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def get_ohlcv(candle: dict) -> tuple:
    """Extract OHLCV from candle, handling different key formats."""
    o = float(candle.get('open', candle.get('o', 0)) or 0)
    h = float(candle.get('high', candle.get('h', 0)) or 0)
    l = float(candle.get('low', candle.get('l', 0)) or 0)
    c = float(candle.get('close', candle.get('c', 0)) or 0)
    v = float(candle.get('volume', candle.get('v', 0)) or 0)
    return o, h, l, c, v


def find_prior_resistance(candles: List[dict], ath_index: int) -> tuple:
    """
    Find the major resistance level BEFORE the ATH.
    This is the level that was broken to create the expansion.
    
    Returns: (resistance_price, resistance_index, is_ath_break, is_major_high_break)
    """
    if ath_index < 5:
        return None, None, False, False
    
    # Get all highs before the ATH
    pre_ath_candles = candles[:ath_index]
    
    if len(pre_ath_candles) < 5:
        return None, None, False, False
    
    # Find swing highs (local maxima) before ATH
    swing_highs = []
    for i in range(2, len(pre_ath_candles) - 2):
        _, h, _, _, _ = get_ohlcv(pre_ath_candles[i])
        _, h_prev1, _, _, _ = get_ohlcv(pre_ath_candles[i-1])
        _, h_prev2, _, _, _ = get_ohlcv(pre_ath_candles[i-2])
        _, h_next1, _, _, _ = get_ohlcv(pre_ath_candles[i+1])
        _, h_next2, _, _, _ = get_ohlcv(pre_ath_candles[i+2])
        
        # Is this a swing high? (higher than neighbors)
        if h > h_prev1 and h > h_prev2 and h > h_next1 and h > h_next2:
            swing_highs.append({'index': i, 'price': h})
    
    if not swing_highs:
        # Fallback: use highest high in first 70% of pre-ATH data
        lookback = max(5, int(len(pre_ath_candles) * 0.7))
        search_range = pre_ath_candles[:lookback]
        highs = [get_ohlcv(c)[1] for c in search_range]
        if highs:
            max_h = max(highs)
            max_idx = highs.index(max_h)
            swing_highs.append({'index': max_idx, 'price': max_h})
    
    if not swing_highs:
        return None, None, False, False
    
    # Get the ATH price
    _, ath_price, _, _, _ = get_ohlcv(candles[ath_index])
    
    # Find the highest swing high that is BELOW the ATH (this is the broken resistance)
    valid_resistances = [sh for sh in swing_highs if sh['price'] < ath_price * 0.98]
    
    if not valid_resistances:
        # All prior highs are very close to ATH - use the highest one
        resistance = max(swing_highs, key=lambda x: x['price'])
    else:
        # Use the highest resistance that was broken
        resistance = max(valid_resistances, key=lambda x: x['price'])
    
    resistance_price = resistance['price']
    resistance_index = resistance['index']
    
    # Determine breakout type
    # Check if this was the ATH before current ATH
    all_prior_highs = [get_ohlcv(c)[1] for c in pre_ath_candles]
    prior_ath = max(all_prior_highs) if all_prior_highs else 0
    
    is_ath_break = resistance_price >= prior_ath * 0.98  # Within 2% of prior ATH
    is_major_high_break = resistance_price >= prior_ath * 0.80  # Within 20% of prior ATH
    
    return resistance_price, resistance_index, is_ath_break, is_major_high_break


def validate_breakout(candles: List[dict], symbol: str = "???") -> Dict:
    """
    Validate that a real breakout/expansion occurred.
    
    WIZTHEORY LOGIC:
    1. Find ATH (expansion high)
    2. Find prior resistance BEFORE the ATH
    3. Calculate expansion from resistance to ATH
    4. Require 30% minimum expansion
    
    Returns:
        {
            'valid': bool,
            'reason': str,
            'breakout_level': float (the resistance that was broken),
            'expansion_pct': float (from breakout level to expansion high),
            'expansion_high': float (the ATH),
            'ath_price': float,
            'ath_break': bool,
            'major_high_break': bool
        }
    """
    result = {
        'valid': False,
        'reason': 'Unknown',
        'breakout_level': 0,
        'expansion_pct': 0,
        'expansion_high': 0,
        'ath_price': 0,
        'ath_break': False,
        'major_high_break': False
    }
    
    if not candles or len(candles) < 20:
        result['reason'] = 'Not enough candles'
        logger.debug(f"    [BREAKOUT-VAL] {symbol}: ❌ Not enough candles")
        return result
    
    # Step 1: Find ATH (expansion high)
    highs = [get_ohlcv(c)[1] for c in candles]
    highs_valid = [(i, h) for i, h in enumerate(highs) if h > 0]
    
    if not highs_valid:
        result['reason'] = 'Invalid candle data'
        return result
    
    ath_index, ath_price = max(highs_valid, key=lambda x: x[1])
    result['ath_price'] = ath_price
    result['expansion_high'] = ath_price
    
    # Step 2: Find prior resistance BEFORE the ATH
    resistance_price, resistance_index, is_ath_break, is_major_high_break = find_prior_resistance(candles, ath_index)
    
    if resistance_price is None or resistance_price <= 0:
        result['reason'] = 'Could not find prior resistance'
        logger.info(f"    [BREAKOUT-VAL] {symbol}: ❌ No prior resistance found")
        return result
    
    result['breakout_level'] = resistance_price
    result['ath_break'] = is_ath_break
    result['major_high_break'] = is_major_high_break
    
    # Step 3: Calculate expansion from resistance → ATH (CORRECT per WizTheory)
    expansion_pct = ((ath_price - resistance_price) / resistance_price) * 100
    result['expansion_pct'] = expansion_pct
    
    # Step 4: Require 30% minimum expansion
    MIN_EXPANSION = 30
    if expansion_pct < (MIN_EXPANSION - 0.1):  # Small tolerance for floating point
        result['reason'] = f"Expansion only {expansion_pct:.1f}% above resistance (need {MIN_EXPANSION}%)"
        logger.info(f"    [BREAKOUT-VAL] {symbol}: ❌ Expansion {expansion_pct:.1f}% < {MIN_EXPANSION}% (resistance: {resistance_price:.8f} → ATH: {ath_price:.8f})")
        return result
    
    # Step 5: Verify ATH came AFTER resistance (proper structure)
    if ath_index <= resistance_index:
        result['reason'] = 'Invalid structure (ATH before resistance)'
        logger.info(f"    [BREAKOUT-VAL] {symbol}: ❌ ATH index {ath_index} <= resistance index {resistance_index}")
        return result
    
    # Step 6: Check if breakout is FRESH (ATH must be within last 100 candles)
    total_candles = len(candles)
    candles_since_ath = total_candles - 1 - ath_index
    MAX_CANDLES_SINCE_ATH = 100
    
    if candles_since_ath > MAX_CANDLES_SINCE_ATH:
        result['reason'] = f'Stale breakout - ATH was {candles_since_ath} candles ago (max {MAX_CANDLES_SINCE_ATH})'
        logger.info(f"    [BREAKOUT-VAL] {symbol}: ❌ STALE - ATH {candles_since_ath} candles ago (max {MAX_CANDLES_SINCE_ATH})")
        return result
    
    # VALID BREAKOUT
    result['valid'] = True
    breakout_type = "ATH_BREAK" if is_ath_break else ("MAJOR_HIGH_BREAK" if is_major_high_break else "LOCAL_BREAK")
    result['reason'] = f"Valid {breakout_type}: {expansion_pct:.1f}% expansion"
    
    logger.info(f"    [BREAKOUT-VAL] {symbol}: ✅ {breakout_type} | Expansion: {expansion_pct:.1f}% | Resistance: {resistance_price:.8f} → ATH: {ath_price:.8f}")
    
    return result
