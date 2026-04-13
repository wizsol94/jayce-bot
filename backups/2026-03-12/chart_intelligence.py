"""
Chart Intelligence Module for Jayce
====================================
Two pre-analysis layers that evaluate chart quality BEFORE setup detection.

Layer 1: Structure Quality Recognition
Layer 2: Breakout Expansion Recognition

These layers inform the scoring system without blocking valid setups.
"""

import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_ohlcv(candle: Dict) -> Tuple[float, float, float, float, float]:
    """Extract OHLCV from candle dict."""
    o = float(candle.get('open') or candle.get('o') or 0)
    h = float(candle.get('high') or candle.get('h') or 0)
    l = float(candle.get('low') or candle.get('l') or 0)
    c = float(candle.get('close') or candle.get('c') or 0)
    v = float(candle.get('volume') or candle.get('v') or 0)
    return o, h, l, c, v


def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    """Calculate Average True Range."""
    if len(candles) < period + 1:
        return 0
    
    true_ranges = []
    for i in range(1, len(candles)):
        _, h, l, _, _ = get_ohlcv(candles[i])
        _, _, _, prev_c, _ = get_ohlcv(candles[i-1])
        
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0
    
    return sum(true_ranges[-period:]) / period


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: STRUCTURE QUALITY RECOGNITION
# ══════════════════════════════════════════════════════════════════════════════

def analyze_structure_quality(candles: List[Dict], lookback: int = 50) -> Dict:
    """
    Evaluate chart structure quality the WizTheory way.
    
    NOT textbook structure - evaluates:
    - Directional bias (is there a clear trend?)
    - Post-expansion structure (controlled pullback vs chop)
    - Chart rhythm (readable vs messy)
    - Tradability (can you actually trade this?)
    
    Returns:
        {
            'quality': 'STRUCTURE_STRONG' | 'STRUCTURE_USABLE' | 'STRUCTURE_MESSY' | 'STRUCTURE_BAD',
            'score': 0-100,
            'directional_bias': float (-1 to 1),
            'chop_ratio': float (0-1, lower is better),
            'pullback_quality': 'CONTROLLED' | 'ERRATIC' | 'NONE',
            'notes': str
        }
    """
    if not candles or len(candles) < 20:
        return {
            'quality': 'STRUCTURE_BAD',
            'score': 0,
            'directional_bias': 0,
            'chop_ratio': 1,
            'pullback_quality': 'NONE',
            'notes': 'Not enough candles'
        }
    
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. DIRECTIONAL BIAS (-1 to 1)
    # ─────────────────────────────────────────────────────────────────────────
    first_half = recent[:len(recent)//2]
    second_half = recent[len(recent)//2:]
    
    first_avg = sum(get_ohlcv(c)[3] for c in first_half) / len(first_half)
    second_avg = sum(get_ohlcv(c)[3] for c in second_half) / len(second_half)
    
    # Calculate slope
    if first_avg > 0:
        price_change_pct = (second_avg - first_avg) / first_avg
    else:
        price_change_pct = 0
    
    # Normalize to -1 to 1 (cap at 50% move)
    directional_bias = max(-1, min(1, price_change_pct * 2))
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. CHOP RATIO (overlapping candles = bad)
    # ─────────────────────────────────────────────────────────────────────────
    overlap_count = 0
    for i in range(1, len(recent)):
        _, h1, l1, _, _ = get_ohlcv(recent[i-1])
        _, h2, l2, _, _ = get_ohlcv(recent[i])
        
        # Check if candles overlap significantly
        overlap = min(h1, h2) - max(l1, l2)
        range1 = h1 - l1
        range2 = h2 - l2
        avg_range = (range1 + range2) / 2
        
        if avg_range > 0 and overlap > avg_range * 0.5:
            overlap_count += 1
    
    chop_ratio = overlap_count / (len(recent) - 1) if len(recent) > 1 else 1
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. WICK RATIO (excessive wicks = messy)
    # ─────────────────────────────────────────────────────────────────────────
    total_wick = 0
    total_body = 0
    for c in recent:
        o, h, l, close, _ = get_ohlcv(c)
        body = abs(close - o)
        upper_wick = h - max(o, close)
        lower_wick = min(o, close) - l
        total_wick += upper_wick + lower_wick
        total_body += body
    
    wick_ratio = total_wick / total_body if total_body > 0 else 2
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. PULLBACK QUALITY (after expansion)
    # ─────────────────────────────────────────────────────────────────────────
    # Find highest high and check pullback behavior after it
    highs = [get_ohlcv(c)[1] for c in recent]
    highest_idx = highs.index(max(highs))
    
    pullback_quality = 'NONE'
    if highest_idx < len(recent) - 5:  # There's pullback data
        pullback_candles = recent[highest_idx:]
        
        # Check if pullback is controlled (making higher lows or holding)
        lows_after_high = [get_ohlcv(c)[2] for c in pullback_candles]
        
        # Count how many lower lows vs higher lows
        lower_low_count = 0
        for i in range(1, len(lows_after_high)):
            if lows_after_high[i] < lows_after_high[i-1] * 0.98:
                lower_low_count += 1
        
        lower_low_ratio = lower_low_count / len(lows_after_high) if lows_after_high else 1
        
        if lower_low_ratio < 0.3:
            pullback_quality = 'CONTROLLED'
        elif lower_low_ratio < 0.6:
            pullback_quality = 'ERRATIC'
        else:
            pullback_quality = 'NONE'
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. CALCULATE STRUCTURE SCORE
    # ─────────────────────────────────────────────────────────────────────────
    score = 50  # Base score
    
    # Directional bias bonus (up to +20)
    score += abs(directional_bias) * 20
    
    # Chop penalty (up to -30)
    score -= chop_ratio * 30
    
    # Wick penalty (up to -15)
    if wick_ratio > 1.5:
        score -= min(15, (wick_ratio - 1.5) * 10)
    
    # Pullback quality bonus
    if pullback_quality == 'CONTROLLED':
        score += 15
    elif pullback_quality == 'ERRATIC':
        score += 5
    
    # Clamp score
    score = max(0, min(100, score))
    
    # ─────────────────────────────────────────────────────────────────────────
    # 6. CLASSIFY STRUCTURE
    # ─────────────────────────────────────────────────────────────────────────
    if score >= 70:
        quality = 'STRUCTURE_STRONG'
    elif score >= 50:
        quality = 'STRUCTURE_USABLE'
    elif score >= 30:
        quality = 'STRUCTURE_MESSY'
    else:
        quality = 'STRUCTURE_BAD'
    
    # Build notes
    notes_parts = []
    if abs(directional_bias) > 0.3:
        notes_parts.append(f"{'Bullish' if directional_bias > 0 else 'Bearish'} bias")
    if chop_ratio > 0.5:
        notes_parts.append("Choppy")
    if wick_ratio > 1.5:
        notes_parts.append("Wicky")
    if pullback_quality == 'CONTROLLED':
        notes_parts.append("Clean pullback")
    
    return {
        'quality': quality,
        'score': round(score),
        'directional_bias': round(directional_bias, 2),
        'chop_ratio': round(chop_ratio, 2),
        'pullback_quality': pullback_quality,
        'notes': ' | '.join(notes_parts) if notes_parts else 'Neutral'
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: BREAKOUT EXPANSION RECOGNITION
# ══════════════════════════════════════════════════════════════════════════════

def analyze_breakout_expansion(candles: List[Dict], lookback: int = 50) -> Dict:
    """
    Evaluate breakout quality and expansion significance.
    
    Detects:
    - ATH break (strongest)
    - Major high break (valid)
    - Weak local breakout (low quality)
    
    Returns:
        {
            'breakout_type': 'ATH_BREAK' | 'MAJOR_HIGH_BREAK' | 'LOCAL_BREAK' | 'NO_BREAKOUT',
            'expansion_quality': 'STRONG' | 'MODERATE' | 'WEAK' | 'NONE',
            'expansion_pct': float,
            'momentum_score': 0-100,
            'is_setup_worthy': bool,
            'notes': str
        }
    """
    if not candles or len(candles) < 30:
        return {
            'breakout_type': 'NO_BREAKOUT',
            'expansion_quality': 'NONE',
            'expansion_pct': 0,
            'momentum_score': 0,
            'is_setup_worthy': False,
            'notes': 'Not enough candles'
        }
    
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    all_candles = candles  # Full history for ATH check
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. FIND KEY LEVELS
    # ─────────────────────────────────────────────────────────────────────────
    # ATH (all-time high)
    all_highs = [get_ohlcv(c)[1] for c in all_candles]
    ath = max(all_highs)
    ath_idx = all_highs.index(ath)
    
    # Recent high (in lookback period)
    recent_highs = [get_ohlcv(c)[1] for c in recent]
    recent_high = max(recent_highs)
    recent_high_idx = recent_highs.index(recent_high)
    
    # Current price
    _, _, _, current_price, _ = get_ohlcv(recent[-1])
    
    # Pre-breakout resistance (high before the recent high)
    if recent_high_idx > 10:
        pre_breakout_highs = recent_highs[:recent_high_idx-3]
        if pre_breakout_highs:
            pre_breakout_level = max(pre_breakout_highs)
        else:
            pre_breakout_level = recent_highs[0]
    else:
        pre_breakout_level = recent_highs[0]
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. CLASSIFY BREAKOUT TYPE
    # ─────────────────────────────────────────────────────────────────────────
    breakout_type = 'NO_BREAKOUT'
    
    # Check if recent high is ATH (within 2%)
    if recent_high >= ath * 0.98:
        breakout_type = 'ATH_BREAK'
    # Check if recent high broke above pre-breakout level significantly
    elif recent_high > pre_breakout_level * 1.05:
        # Is this a major high? (top 10% of all-time range)
        price_range = ath - min(all_highs)
        if price_range > 0:
            high_percentile = (recent_high - min(all_highs)) / price_range
            if high_percentile > 0.8:
                breakout_type = 'MAJOR_HIGH_BREAK'
            else:
                breakout_type = 'LOCAL_BREAK'
        else:
            breakout_type = 'LOCAL_BREAK'
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. MEASURE EXPANSION
    # ─────────────────────────────────────────────────────────────────────────
    # Find the low before the breakout move
    if recent_high_idx > 5:
        pre_move_candles = recent[:recent_high_idx]
        pre_move_lows = [get_ohlcv(c)[2] for c in pre_move_candles]
        expansion_low = min(pre_move_lows[-10:]) if len(pre_move_lows) >= 10 else min(pre_move_lows)
    else:
        expansion_low = min(get_ohlcv(c)[2] for c in recent[:10])
    
    # Calculate expansion percentage
    if expansion_low > 0:
        expansion_pct = ((recent_high - expansion_low) / expansion_low) * 100
    else:
        expansion_pct = 0
    
    # Classify expansion quality
    if expansion_pct >= 50:
        expansion_quality = 'STRONG'
    elif expansion_pct >= 30:
        expansion_quality = 'MODERATE'
    elif expansion_pct >= 15:
        expansion_quality = 'WEAK'
    else:
        expansion_quality = 'NONE'
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. MOMENTUM ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────
    # Check candle momentum during expansion
    if recent_high_idx > 0:
        expansion_candles = recent[max(0, recent_high_idx-10):recent_high_idx+1]
    else:
        expansion_candles = recent[:10]
    
    bullish_candles = 0
    strong_bullish = 0
    for c in expansion_candles:
        o, h, l, close, _ = get_ohlcv(c)
        if close > o:
            bullish_candles += 1
            body = close - o
            total_range = h - l
            if total_range > 0 and body / total_range > 0.6:
                strong_bullish += 1
    
    bullish_ratio = bullish_candles / len(expansion_candles) if expansion_candles else 0
    strong_ratio = strong_bullish / len(expansion_candles) if expansion_candles else 0
    
    # Calculate momentum score
    momentum_score = 0
    momentum_score += bullish_ratio * 40  # Up to 40 pts
    momentum_score += strong_ratio * 30   # Up to 30 pts
    
    # Breakout type bonus
    if breakout_type == 'ATH_BREAK':
        momentum_score += 30
    elif breakout_type == 'MAJOR_HIGH_BREAK':
        momentum_score += 20
    elif breakout_type == 'LOCAL_BREAK':
        momentum_score += 10
    
    momentum_score = min(100, momentum_score)
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. IS THIS SETUP WORTHY?
    # ─────────────────────────────────────────────────────────────────────────
    is_setup_worthy = (
        breakout_type in ['ATH_BREAK', 'MAJOR_HIGH_BREAK'] and
        expansion_quality in ['STRONG', 'MODERATE'] and
        momentum_score >= 50
    ) or (
        breakout_type == 'LOCAL_BREAK' and
        expansion_quality == 'STRONG' and
        momentum_score >= 60
    )
    
    # Build notes
    notes_parts = []
    if breakout_type == 'ATH_BREAK':
        notes_parts.append("ATH breakout!")
    elif breakout_type == 'MAJOR_HIGH_BREAK':
        notes_parts.append("Major high broken")
    
    if expansion_quality == 'STRONG':
        notes_parts.append(f"Strong expansion ({expansion_pct:.0f}%)")
    elif expansion_quality == 'MODERATE':
        notes_parts.append(f"Moderate expansion ({expansion_pct:.0f}%)")
    
    if momentum_score >= 70:
        notes_parts.append("Good momentum")
    
    return {
        'breakout_type': breakout_type,
        'expansion_quality': expansion_quality,
        'expansion_pct': round(expansion_pct, 1),
        'momentum_score': round(momentum_score),
        'is_setup_worthy': is_setup_worthy,
        'notes': ' | '.join(notes_parts) if notes_parts else 'No significant breakout'
    }


# ══════════════════════════════════════════════════════════════════════════════
# COMBINED ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_chart_intelligence(candles: List[Dict]) -> Dict:
    """
    Run both intelligence layers and return combined analysis.
    
    This runs BEFORE setup detection to evaluate chart quality.
    """
    structure = analyze_structure_quality(candles)
    breakout = analyze_breakout_expansion(candles)
    
    # Combined intelligence score
    combined_score = (structure['score'] * 0.4) + (breakout['momentum_score'] * 0.6)
    
    # Chart is "intelligent" if both layers pass
    is_quality_chart = (
        structure['quality'] in ['STRUCTURE_STRONG', 'STRUCTURE_USABLE'] and
        breakout['is_setup_worthy']
    )
    
    return {
        'structure': structure,
        'breakout': breakout,
        'combined_score': round(combined_score),
        'is_quality_chart': is_quality_chart
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Chart Intelligence Module")
    print("=" * 50)
    print("Layer 1: Structure Quality Recognition")
    print("Layer 2: Breakout Expansion Recognition")
    print("=" * 50)
    print("Ready to analyze charts!")


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: PRIME SETUP CONDITION
# ══════════════════════════════════════════════════════════════════════════════

def check_prime_setup_condition(breakout_result: Dict) -> Dict:
    """
    Pre-condition gate before WizTheory setup detection.
    
    Only allows setup evaluation if a meaningful breakout/expansion occurred.
    
    Valid prime conditions:
    - ATH_BREAK
    - MAJOR_HIGH_BREAK  
    - Strong expansion (>=40%)
    
    Args:
        breakout_result: Output from analyze_breakout_expansion()
    
    Returns:
        {
            'is_prime': bool,
            'reason': str,
            'confidence': 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
        }
    """
    if not breakout_result:
        return {
            'is_prime': False,
            'reason': 'No breakout data',
            'confidence': 'NONE'
        }
    
    breakout_type = breakout_result.get('breakout_type', 'NO_BREAKOUT')
    expansion_pct = breakout_result.get('expansion_pct', 0)
    expansion_quality = breakout_result.get('expansion_quality', 'NONE')
    momentum_score = breakout_result.get('momentum_score', 0)
    
    # ─────────────────────────────────────────────────────────────────────────
    # PRIME CONDITION 1: ATH Break (highest confidence)
    # ─────────────────────────────────────────────────────────────────────────
    if breakout_type == 'ATH_BREAK':
        return {
            'is_prime': True,
            'reason': f'ATH breakout with {expansion_pct:.0f}% expansion',
            'confidence': 'HIGH'
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # PRIME CONDITION 2: Major High Break (high confidence)
    # ─────────────────────────────────────────────────────────────────────────
    if breakout_type == 'MAJOR_HIGH_BREAK':
        return {
            'is_prime': True,
            'reason': f'Major high broken with {expansion_pct:.0f}% expansion',
            'confidence': 'HIGH'
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # PRIME CONDITION 3: Strong expansion (>=40%) even with local break
    # ─────────────────────────────────────────────────────────────────────────
    if expansion_pct >= 40:
        confidence = 'HIGH' if expansion_pct >= 60 else 'MEDIUM'
        return {
            'is_prime': True,
            'reason': f'Strong expansion {expansion_pct:.0f}%',
            'confidence': confidence
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # PRIME CONDITION 4: Local break with decent expansion (30-40%) + momentum
    # ─────────────────────────────────────────────────────────────────────────
    if breakout_type == 'LOCAL_BREAK' and expansion_pct >= 30 and momentum_score >= 60:
        return {
            'is_prime': True,
            'reason': f'Local break with {expansion_pct:.0f}% expansion + momentum',
            'confidence': 'MEDIUM'
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # NOT PRIME: Doesn't meet any condition
    # ─────────────────────────────────────────────────────────────────────────
    return {
        'is_prime': False,
        'reason': f'No meaningful breakout ({breakout_type}, {expansion_pct:.0f}% exp)',
        'confidence': 'NONE'
    }


def analyze_chart_intelligence_with_prime(candles: List[Dict]) -> Dict:
    """
    Run all 3 intelligence layers:
    1. Breakout Expansion Recognition
    2. Prime Setup Condition (gate)
    3. Structure Quality Recognition
    
    Returns combined analysis with prime gate status.
    """
    # Layer 1: Breakout analysis
    breakout = analyze_breakout_expansion(candles)
    
    # Layer 2: Prime condition check
    prime = check_prime_setup_condition(breakout)
    
    # Layer 3: Structure quality (only if prime)
    if prime['is_prime']:
        structure = analyze_structure_quality(candles)
    else:
        structure = {
            'quality': 'SKIPPED',
            'score': 0,
            'directional_bias': 0,
            'chop_ratio': 0,
            'pullback_quality': 'NONE',
            'notes': 'Skipped - not prime'
        }
    
    # Combined intelligence score
    if prime['is_prime']:
        combined_score = (structure['score'] * 0.4) + (breakout['momentum_score'] * 0.6)
    else:
        combined_score = 0
    
    return {
        'breakout': breakout,
        'prime': prime,
        'structure': structure,
        'combined_score': round(combined_score),
        'should_evaluate_setup': prime['is_prime']
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: PULLBACK QUALITY RECOGNITION
# Scoring: CLEAN +6, USABLE +3, AGGRESSIVE -3, BAD -6
# ══════════════════════════════════════════════════════════════════════════════

def analyze_pullback_quality(candles: List[Dict], flip_zone_price: float = None, lookback: int = 30) -> Dict:
    """
    Evaluate the quality of the retrace into the flip zone.
    
    Scoring Impact (capped):
    - PULLBACK_CLEAN: +6 pts
    - PULLBACK_USABLE: +3 pts
    - PULLBACK_AGGRESSIVE: -3 pts
    - PULLBACK_BAD: -6 pts
    """
    if not candles or len(candles) < 15:
        return {
            'quality': 'PULLBACK_USABLE',
            'score_impact': 0,
            'retrace_slope': 0,
            'body_ratio': 0,
            'wick_ratio': 0,
            'volume_trend': 'NEUTRAL',
            'notes': 'Not enough candles'
        }
    
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    
    # Find the high (start of pullback)
    highs = [get_ohlcv(c)[1] for c in recent]
    high_idx = highs.index(max(highs))
    
    # Get pullback candles
    pullback_candles = recent[high_idx:] if high_idx < len(recent) - 3 else recent[-10:]
    if len(pullback_candles) < 3:
        pullback_candles = recent[-10:]
    
    # 1. RETRACE SLOPE
    first_close = get_ohlcv(pullback_candles[0])[3]
    last_close = get_ohlcv(pullback_candles[-1])[3]
    retrace_pct = ((first_close - last_close) / first_close * 100) if first_close > 0 else 0
    retrace_slope = retrace_pct / len(pullback_candles)
    
    # 2. BODY SIZE RATIO
    body_sizes = []
    ranges = []
    for c in pullback_candles:
        o, h, l, close, _ = get_ohlcv(c)
        body_sizes.append(abs(close - o))
        ranges.append(h - l)
    avg_body = sum(body_sizes) / len(body_sizes) if body_sizes else 0
    avg_range = sum(ranges) / len(ranges) if ranges else 1
    body_ratio = avg_body / avg_range if avg_range > 0 else 0
    
    # 3. WICK BEHAVIOR
    lower_wicks = 0
    upper_wicks = 0
    for c in pullback_candles:
        o, h, l, close, _ = get_ohlcv(c)
        lower_wicks += min(o, close) - l
        upper_wicks += h - max(o, close)
    total_wicks = lower_wicks + upper_wicks
    wick_ratio = lower_wicks / total_wicks if total_wicks > 0 else 0.5
    
    # 4. VOLUME TREND
    volumes = [get_ohlcv(c)[4] for c in pullback_candles]
    if len(volumes) >= 4 and sum(volumes) > 0:
        first_half = sum(volumes[:len(volumes)//2])
        second_half = sum(volumes[len(volumes)//2:])
        if second_half < first_half * 0.7:
            volume_trend = 'FADING'
        elif second_half > first_half * 1.3:
            volume_trend = 'EXPANDING'
        else:
            volume_trend = 'NEUTRAL'
    else:
        volume_trend = 'NEUTRAL'
    
    # 5. CALCULATE INTERNAL SCORE
    internal_score = 50
    if retrace_slope > 3: internal_score -= 20
    elif retrace_slope > 2: internal_score -= 10
    elif retrace_slope < 1: internal_score += 10
    
    if body_ratio < 0.4: internal_score += 15
    elif body_ratio > 0.7: internal_score -= 15
    
    if wick_ratio > 0.6: internal_score += 15
    elif wick_ratio < 0.3: internal_score -= 10
    
    if volume_trend == 'FADING': internal_score += 10
    elif volume_trend == 'EXPANDING': internal_score -= 10
    
    internal_score = max(0, min(100, internal_score))
    
    # 6. CLASSIFY & ASSIGN CAPPED SCORE IMPACT
    if internal_score >= 70:
        quality = 'PULLBACK_CLEAN'
        score_impact = 6
    elif internal_score >= 50:
        quality = 'PULLBACK_USABLE'
        score_impact = 3
    elif internal_score >= 30:
        quality = 'PULLBACK_AGGRESSIVE'
        score_impact = -3
    else:
        quality = 'PULLBACK_BAD'
        score_impact = -6
    
    notes_parts = []
    if retrace_slope < 1: notes_parts.append("Gentle drift")
    elif retrace_slope > 2: notes_parts.append("Steep drop")
    if wick_ratio > 0.6: notes_parts.append("Buying wicks")
    if volume_trend == 'FADING': notes_parts.append("Vol fading")
    
    return {
        'quality': quality,
        'score_impact': score_impact,
        'retrace_slope': round(retrace_slope, 2),
        'body_ratio': round(body_ratio, 2),
        'wick_ratio': round(wick_ratio, 2),
        'volume_trend': volume_trend,
        'notes': ' | '.join(notes_parts) if notes_parts else 'Standard pullback'
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 5: SETUP MATURITY DETECTION
# Scoring: 0 (Info/Timing only - NO score impact)
# ══════════════════════════════════════════════════════════════════════════════

def detect_setup_maturity(candles: List[Dict], flip_zone_price: float = 0, entry_buffer_pct: float = 5) -> Dict:
    """
    Timing context only - NO scoring impact.
    
    Classifications:
    - SETUP_FORMING: Retrace just started
    - SETUP_APPROACHING: Getting closer to zone
    - SETUP_READY: In entry zone, waiting for trigger
    - SETUP_TRIGGERED: Bounce started
    - SETUP_LATE: Already bounced, missed entry
    """
    if not candles or len(candles) < 5 or flip_zone_price <= 0:
        return {
            'maturity': 'SETUP_FORMING',
            'score_impact': 0,
            'distance_pct': 100,
            'is_in_zone': False,
            'bounce_started': False,
            'bounce_pct': 0,
            'recommendation': 'Insufficient data'
        }
    
    current_price = get_ohlcv(candles[-1])[3]
    recent_low = min(get_ohlcv(c)[2] for c in candles[-10:])
    
    # Distance from zone
    distance_pct = ((current_price - flip_zone_price) / flip_zone_price * 100) if flip_zone_price > 0 else 100
    
    # Zone boundaries
    zone_upper = flip_zone_price * (1 + entry_buffer_pct / 100)
    zone_lower = flip_zone_price * (1 - entry_buffer_pct / 100)
    is_in_zone = zone_lower <= current_price <= zone_upper
    is_below_zone = current_price < zone_lower
    
    # Bounce detection
    bounce_pct = ((current_price - recent_low) / recent_low * 100) if recent_low > 0 else 0
    bounce_started = bounce_pct > 3
    strong_bounce = bounce_pct > 10
    
    # Classify
    if is_below_zone and strong_bounce:
        maturity = 'SETUP_LATE'
        recommendation = 'Missed entry - wait for retest'
    elif is_in_zone and bounce_started:
        maturity = 'SETUP_TRIGGERED'
        recommendation = 'Entry window active'
    elif is_in_zone:
        maturity = 'SETUP_READY'
        recommendation = 'In zone - watch for trigger'
    elif distance_pct < 10:
        maturity = 'SETUP_APPROACHING'
        recommendation = 'Approaching - prepare entry'
    else:
        maturity = 'SETUP_FORMING'
        recommendation = 'Monitor retrace'
    
    return {
        'maturity': maturity,
        'score_impact': 0,  # NO scoring impact
        'distance_pct': round(distance_pct, 1),
        'is_in_zone': is_in_zone,
        'bounce_started': bounce_started,
        'bounce_pct': round(bounce_pct, 1),
        'recommendation': recommendation
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 6: MOMENTUM CONTINUATION / RSI BEHAVIOR
# Scoring: RUNNER +3, HEALTHY +2, NEUTRAL 0, WEAK -2
# ══════════════════════════════════════════════════════════════════════════════

def analyze_momentum_behavior(candles: List[Dict], rsi_values: List[float] = None) -> Dict:
    """
    RSI as context - light scoring layer.
    
    Scoring Impact (capped):
    - MOMENTUM_RUNNER: +3 pts
    - MOMENTUM_HEALTHY: +2 pts
    - MOMENTUM_NEUTRAL: 0 pts
    - MOMENTUM_WEAK: -2 pts
    """
    if not candles or len(candles) < 14:
        return {
            'classification': 'MOMENTUM_NEUTRAL',
            'score_impact': 0,
            'rsi_current': 50,
            'rsi_floor': 30,
            'floor_holding': True,
            'trend': 'FLAT',
            'notes': 'Insufficient data'
        }
    
    # Calculate RSI
    if rsi_values is None or len(rsi_values) < 5:
        rsi_values = calculate_rsi_series(candles)
    
    if not rsi_values or len(rsi_values) < 5:
        return {
            'classification': 'MOMENTUM_NEUTRAL',
            'score_impact': 0,
            'rsi_current': 50,
            'rsi_floor': 30,
            'floor_holding': True,
            'trend': 'FLAT',
            'notes': 'RSI calc failed'
        }
    
    rsi_current = rsi_values[-1]
    rsi_recent = rsi_values[-10:] if len(rsi_values) >= 10 else rsi_values
    rsi_floor = min(rsi_recent)
    
    # RSI trend
    mid = len(rsi_recent) // 2
    rsi_first = sum(rsi_recent[:mid]) / mid if mid > 0 else rsi_current
    rsi_second = sum(rsi_recent[mid:]) / (len(rsi_recent) - mid) if len(rsi_recent) > mid else rsi_current
    
    if rsi_second > rsi_first + 5:
        trend = 'UP'
    elif rsi_second < rsi_first - 5:
        trend = 'DOWN'
    else:
        trend = 'FLAT'
    
    floor_holding = rsi_floor > 35
    
    # Classify & assign capped score
    if rsi_current >= 60 and rsi_floor >= 50 and trend in ['UP', 'FLAT']:
        classification = 'MOMENTUM_RUNNER'
        score_impact = 3
        notes = 'Strong momentum - RSI above 50'
    elif rsi_current >= 45 and floor_holding:
        classification = 'MOMENTUM_HEALTHY'
        score_impact = 2
        notes = 'Healthy pullback'
    elif rsi_current < 35 or rsi_floor < 30:
        classification = 'MOMENTUM_WEAK'
        score_impact = -2
        notes = 'Momentum fading'
    else:
        classification = 'MOMENTUM_NEUTRAL'
        score_impact = 0
        notes = 'Neutral'
    
    return {
        'classification': classification,
        'score_impact': score_impact,
        'rsi_current': round(rsi_current, 1),
        'rsi_floor': round(rsi_floor, 1),
        'floor_holding': floor_holding,
        'trend': trend,
        'notes': notes
    }


def calculate_rsi_series(candles: List[Dict], period: int = 14) -> List[float]:
    """Calculate RSI series for candles."""
    if len(candles) < period + 1:
        return []
    
    closes = [get_ohlcv(c)[3] for c in candles]
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    if len(gains) < period:
        return []
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rsi = 100 - (100 / (1 + avg_gain / avg_loss))
        rsi_values.append(rsi)
    
    return rsi_values


# ══════════════════════════════════════════════════════════════════════════════
# COMBINED FULL INTELLIGENCE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_full_intelligence(candles: List[Dict], flip_zone_price: float = 0) -> Dict:
    """
    Run ALL 6 intelligence layers.
    
    Layers 1-3: Existing (Breakout, Prime, Structure)
    Layers 4-6: New (Pullback, Maturity, Momentum)
    
    Returns combined analysis with capped scoring bonuses.
    """
    # Existing layers
    breakout = analyze_breakout_expansion(candles)
    prime = check_prime_setup_condition(breakout)
    structure = analyze_structure_quality(candles) if prime['is_prime'] else {'quality': 'SKIPPED', 'score': 0}
    
    # New layers
    pullback = analyze_pullback_quality(candles, flip_zone_price)
    maturity = detect_setup_maturity(candles, flip_zone_price)
    momentum = analyze_momentum_behavior(candles)
    
    # Calculate total bonus (capped: -8 to +9)
    pullback_bonus = pullback['score_impact']  # -6 to +6
    momentum_bonus = momentum['score_impact']  # -2 to +3
    maturity_bonus = maturity['score_impact']  # Always 0
    
    total_intel_bonus = pullback_bonus + momentum_bonus + maturity_bonus
    
    return {
        # Existing
        'breakout': breakout,
        'prime': prime,
        'structure': structure,
        
        # New
        'pullback': pullback,
        'maturity': maturity,
        'momentum': momentum,
        
        # Capped bonuses
        'pullback_bonus': pullback_bonus,
        'momentum_bonus': momentum_bonus,
        'maturity_bonus': maturity_bonus,
        'total_intel_bonus': total_intel_bonus,
        
        # Gate status
        'should_evaluate_setup': prime['is_prime']
    }
