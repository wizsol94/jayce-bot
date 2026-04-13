"""
WIZTHEORY IMPULSE DETECTOR v1.0
===============================
Detects impulse legs using WizTheory logic - NOT generic TA.

Process:
1. Detect left rejection level (flip zone origin)
2. Detect breakout/reclaim above zone
3. Measure expansion from zone origin to breakout high
4. Apply fib across expansion move
5. Identify which fib level aligns with flip zone
6. Validate expansion thresholds per setup
7. Monitor retrace behavior

Setup Classification:
- 382: Zone aligns with 0.382, expansion 30%+
- 50: Zone aligns with 0.50, expansion 50%+
- 618: Zone aligns with 0.618, expansion 60%+
- 786: Zone aligns with 0.786, expansion 100%+
- Under-Fib: Zone = origin, expansion 60%+
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS - WIZTHEORY RULES
# ══════════════════════════════════════════════════════════════════════════════

FIB_TOLERANCE = 0.10

MIN_EXPANSION = {
    '382': 28,  # Tolerance: was 30
    '50': 48,   # Tolerance: was 50
    '618': 58,  # Tolerance: was 60
    '786': 95,  # Tolerance: was 100
    'UNDER_FIB': 58  # Tolerance: was 60
}

FIB_LEVELS = {
    '382': 0.382,
    '50': 0.50,
    '618': 0.618,
    '786': 0.786
}

RSI_BREAKOUT_MIN = 65
RSI_RETRACE_FLOOR = 40
MIN_REJECTION_WICK_RATIO = 0.3
MIN_ZONE_TESTS = 1


@dataclass
class FlipZone:
    origin_price: float
    origin_index: int
    rejection_count: int
    zone_strength: str
    reclaimed: bool
    reclaim_index: int
    reclaim_price: float


@dataclass 
class ImpulseLeg:
    zone_origin: float
    breakout_high: float
    expansion_low: float
    expansion_pct: float
    breakout_index: int
    high_index: int
    impulse_score: int
    valid: bool


@dataclass
class WizSetup:
    setup_type: str
    flip_zone: FlipZone
    impulse: ImpulseLeg
    fib_levels: Dict[str, float]
    fib_alignment_pct: float
    expansion_valid: bool
    setup_valid: bool
    grade: str


def get_ohlcv(candle: dict) -> Tuple[float, float, float, float, float]:
    o = float(candle.get('open') or candle.get('o') or 0)
    h = float(candle.get('high') or candle.get('h') or 0)
    l = float(candle.get('low') or candle.get('l') or 0)
    c = float(candle.get('close') or candle.get('c') or 0)
    v = float(candle.get('volume') or candle.get('v') or 0)
    return o, h, l, c, v


def calculate_rsi(candles: List[dict], period: int = 14) -> List[float]:
    closes = [get_ohlcv(c)[3] for c in candles]
    if len(closes) < period + 1:
        return []
    
    rsi_values = []
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)
    
    if len(gains) < period:
        return []
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(round(rsi, 2))
    
    return rsi_values


def is_breakout_candle(candle: dict, zone_level: float, avg_volume: float) -> Tuple[bool, int]:
    o, h, l, c, v = get_ohlcv(candle)
    candle_range = h - l
    
    if candle_range == 0:
        return False, 0
    
    score = 0
    
    if c <= zone_level:
        return False, 0
    
    score += 20
    
    body = abs(c - o)
    body_ratio = body / candle_range
    if body_ratio >= 0.6:
        score += 25
    elif body_ratio >= 0.4:
        score += 15
    else:
        score += 5
    
    if c > o:
        score += 15
    
    if avg_volume > 0:
        if v > avg_volume * 1.5:
            score += 20
        elif v > avg_volume * 1.2:
            score += 10
    
    expansion_above = ((c - zone_level) / zone_level) * 100
    if expansion_above >= 5:
        score += 20
    elif expansion_above >= 2:
        score += 10
    
    return score >= 50, score


def validate_real_breakout(candles: List[dict], breakout_idx: int) -> bool:
    """
    Validate that a breakout occurred above the previous high.
    Requirements:
    1. Price must close above the previous significant high
    2. The high being broken must have been resistance (rejected at least once)
    """
    if breakout_idx < 15 or breakout_idx >= len(candles):
        return False
    
    breakout_candle = candles[breakout_idx]
    _, breakout_high, _, breakout_close, _ = get_ohlcv(breakout_candle)
    
    # Look for previous high that was broken
    lookback_candles = candles[max(0, breakout_idx - 30):breakout_idx]
    if len(lookback_candles) < 10:
        return False
    
    # Find the highest high before this candle
    prev_highs = []
    for c in lookback_candles:
        _, h, _, _, _ = get_ohlcv(c)
        prev_highs.append(h)
    
    if not prev_highs:
        return False
    
    prev_high = max(prev_highs)
    
    # Breakout must CLOSE above previous high (not just wick)
    if breakout_close < prev_high * 0.98:  # 2% tolerance
        return False
    
    # The previous high must have been tested/rejected at least once
    rejection_count = 0
    for c in lookback_candles:
        _, c_high, _, c_close, _ = get_ohlcv(c)
        # Rejection = price approached but closed below
        if c_high >= prev_high * 0.95 and c_close < prev_high * 0.98:
            rejection_count += 1
    
    # Need at least 1 rejection to confirm it was resistance
    return rejection_count >= 1


def find_real_breakout_anchor(candles: List[dict], lookback: int = 100) -> Optional[dict]:
    """
    Find CONFIRMED breakout above ATH/major resistance.
    
    STRICT REQUIREMENTS:
    1. Identify ATH or major resistance zone
    2. Require BODY CLOSE above resistance (not just wick)
    3. Require multiple closes above (confirmation)
    4. Require meaningful expansion beyond breakout (not tiny drift)
    
    Returns breakout info or None if no valid breakout.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if len(candles) < 30:
        logger.debug("    [BREAKOUT] Not enough candles")
        return None
    
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    offset = len(candles) - len(recent)
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: Find ATH / Major Resistance Zone
    # ══════════════════════════════════════════════════════════════════════
    
    # Find the highest high in first 70% of data (the resistance to break)
    resistance_search_end = int(len(recent) * 0.7)
    if resistance_search_end < 10:
        resistance_search_end = min(len(recent) - 5, 30)
    
    resistance_high = 0
    resistance_idx = 0
    
    for i in range(0, resistance_search_end):
        _, h, _, _, _ = get_ohlcv(recent[i])
        if h > resistance_high:
            resistance_high = h
            resistance_idx = i
    
    if resistance_high == 0:
        logger.debug("    [BREAKOUT] No resistance zone found")
        return None
    
    # Create resistance zone (allow 2% tolerance)
    resistance_zone_top = resistance_high
    resistance_zone_bottom = resistance_high * 0.98
    
    logger.info(f"    [BREAKOUT] Resistance zone: {resistance_zone_bottom:.10f} - {resistance_zone_top:.10f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: Check for CONFIRMED breakout above resistance
    # ══════════════════════════════════════════════════════════════════════
    
    # Look for candles AFTER the resistance that closed above it
    breakout_candles = []
    first_breakout_idx = None
    breakout_high = 0
    breakout_high_idx = 0
    
    for i in range(resistance_idx + 1, len(recent)):
        o, h, l, c, _ = get_ohlcv(recent[i])
        
        # Body close above resistance (not just wick)
        body_top = max(o, c)
        body_bottom = min(o, c)
        
        if body_bottom > resistance_zone_bottom:  # Body is above resistance
            breakout_candles.append(i)
            if first_breakout_idx is None:
                first_breakout_idx = i
        
        if h > breakout_high:
            breakout_high = h
            breakout_high_idx = i
    
    # Require at least 2 body closes above resistance
    MIN_BREAKOUT_CLOSES = 2
    if len(breakout_candles) < MIN_BREAKOUT_CLOSES:
        logger.info(f"    [BREAKOUT] ❌ Only {len(breakout_candles)} closes above resistance (need {MIN_BREAKOUT_CLOSES})")
        return None
    
    logger.info(f"    [BREAKOUT] ✓ {len(breakout_candles)} candles closed above resistance")
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 3: Check for MEANINGFUL expansion beyond breakout
    # ══════════════════════════════════════════════════════════════════════
    
    # Calculate expansion beyond resistance
    expansion_pct = ((breakout_high - resistance_high) / resistance_high) * 100
    
    # Require at least 15% expansion beyond the breakout level
    MIN_EXPANSION_BEYOND_BREAKOUT = 15
    if expansion_pct < MIN_EXPANSION_BEYOND_BREAKOUT:
        logger.info(f"    [BREAKOUT] ❌ Expansion only {expansion_pct:.1f}% beyond resistance (need {MIN_EXPANSION_BEYOND_BREAKOUT}%)")
        return None
    
    logger.info(f"    [BREAKOUT] ✓ Expanded {expansion_pct:.1f}% beyond resistance")
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 4: Verify this is a REAL breakout (not just ranging above)
    # ══════════════════════════════════════════════════════════════════════
    
    # The breakout high should be significantly above resistance
    # AND price should have shown impulsive movement
    
    # Check if the move from resistance to high was impulsive (not slow drift)
    candles_to_high = breakout_high_idx - first_breakout_idx if first_breakout_idx else 0
    
    # If it took too many candles to reach the high, it might be slow drift
    if candles_to_high > 30 and expansion_pct < 30:
        logger.info(f"    [BREAKOUT] ⚠️ Slow drift detected ({candles_to_high} candles for {expansion_pct:.1f}%)")
        # Don't reject, but note it
    
    logger.info(f"    [BREAKOUT] ✅ CONFIRMED breakout above ATH")
    logger.info(f"    [BREAKOUT]    Resistance: {resistance_high:.10f}")
    logger.info(f"    [BREAKOUT]    Breakout high: {breakout_high:.10f}")
    logger.info(f"    [BREAKOUT]    Expansion: {expansion_pct:.1f}%")
    logger.info(f"    [BREAKOUT]    Closes above: {len(breakout_candles)}")
    
    return {
        'breakout_idx': first_breakout_idx + offset if first_breakout_idx else breakout_high_idx + offset,
        'breakout_high': breakout_high,
        'broken_resistance': resistance_high,
        'flip_zone_level': resistance_high,
        'expansion_beyond_breakout': expansion_pct,
        'breakout_closes': len(breakout_candles),
        'confirmed': True
    }


def detect_flip_zone_origin(candles: List[dict], lookback: int = 50) -> Optional[FlipZone]:
    if len(candles) < lookback:
        lookback = len(candles)
    
    resistance_levels = []
    
    for i in range(len(candles) - lookback, len(candles) - 5):
        o, h, l, c, v = get_ohlcv(candles[i])
        upper_wick = h - max(o, c)
        candle_range = h - l
        
        if candle_range > 0:
            wick_ratio = upper_wick / candle_range
            
            if wick_ratio >= MIN_REJECTION_WICK_RATIO:
                resistance_levels.append({
                    'level': h,
                    'index': i,
                    'wick_ratio': wick_ratio
                })
    
    if not resistance_levels:
        return None
    
    grouped_levels = []
    used = set()
    
    for i, level1 in enumerate(resistance_levels):
        if i in used:
            continue
        
        group = [level1]
        used.add(i)
        
        for j, level2 in enumerate(resistance_levels):
            if j in used:
                continue
            
            diff_pct = abs(level1['level'] - level2['level']) / level1['level']
            if diff_pct <= 0.02:
                group.append(level2)
                used.add(j)
        
        grouped_levels.append(group)
    
    best_zone = None
    best_score = 0
    
    for group in grouped_levels:
        rejection_count = len(group)
        avg_level = sum(g['level'] for g in group) / len(group)
        first_index = min(g['index'] for g in group)
        
        if rejection_count >= 3:
            strength = 'STRONG'
            score = 100
        elif rejection_count >= 2:
            strength = 'MEDIUM'
            score = 70
        else:
            if group[0]['wick_ratio'] >= 0.5:
                strength = 'MEDIUM'
                score = 60
            else:
                strength = 'WEAK'
                score = 30
        
        if score > best_score:
            best_score = score
            best_zone = FlipZone(
                origin_price=avg_level,
                origin_index=first_index,
                rejection_count=rejection_count,
                zone_strength=strength,
                reclaimed=False,
                reclaim_index=-1,
                reclaim_price=0
            )
    
    return best_zone


def detect_breakout(candles: List[dict], flip_zone: FlipZone) -> Optional[FlipZone]:
    if not flip_zone:
        return None
    
    zone_level = flip_zone.origin_price
    start_idx = flip_zone.origin_index + 1
    
    volumes = [get_ohlcv(c)[4] for c in candles[max(0, start_idx-20):start_idx]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    
    for i in range(start_idx, len(candles)):
        candle = candles[i]
        
        is_breakout, quality = is_breakout_candle(candle, zone_level, avg_volume)
        
        if is_breakout:
            o, h, l, c, v = get_ohlcv(candle)
            
            flip_zone.reclaimed = True
            flip_zone.reclaim_index = i
            flip_zone.reclaim_price = c
            
            return flip_zone
    
    return None


def measure_expansion(candles: List[dict], flip_zone: FlipZone) -> Optional[ImpulseLeg]:
    if not flip_zone or not flip_zone.reclaimed:
        return None
    
    zone_origin = flip_zone.origin_price
    breakout_idx = flip_zone.reclaim_index
    
    breakout_high = 0
    high_index = breakout_idx
    
    for i in range(breakout_idx, len(candles)):
        o, h, l, c, v = get_ohlcv(candles[i])
        if h > breakout_high:
            breakout_high = h
            high_index = i
    
    if breakout_high == 0:
        return None
    
    search_start = max(0, flip_zone.origin_index - 30)
    expansion_low = zone_origin
    
    for i in range(search_start, flip_zone.origin_index + 1):
        o, h, l, c, v = get_ohlcv(candles[i])
        if l < expansion_low:
            expansion_low = l
    
    if zone_origin == 0:
        return None
    
    expansion_pct = ((breakout_high - zone_origin) / zone_origin) * 100
    
    impulse_score = calculate_impulse_score(candles, flip_zone, breakout_high, expansion_pct)
    
    return ImpulseLeg(
        zone_origin=zone_origin,
        breakout_high=breakout_high,
        expansion_low=expansion_low,
        expansion_pct=round(expansion_pct, 2),
        breakout_index=breakout_idx,
        high_index=high_index,
        impulse_score=impulse_score,
        valid=impulse_score >= 40
    )


def calculate_impulse_score(candles: List[dict], flip_zone: FlipZone, breakout_high: float, expansion_pct: float) -> int:
    score = 0
    
    if expansion_pct >= 100:
        score += 25
    elif expansion_pct >= 60:
        score += 20
    elif expansion_pct >= 40:
        score += 15
    elif expansion_pct >= 25:
        score += 10
    else:
        score += 5
    
    breakout_candle = candles[flip_zone.reclaim_index]
    o, h, l, c, v = get_ohlcv(breakout_candle)
    candle_range = h - l
    if candle_range > 0:
        body = abs(c - o)
        body_ratio = body / candle_range
        if body_ratio >= 0.7:
            score += 20
        elif body_ratio >= 0.5:
            score += 15
        elif body_ratio >= 0.3:
            score += 10
        else:
            score += 5
    
    volumes = [get_ohlcv(c)[4] for c in candles[max(0, flip_zone.reclaim_index-20):flip_zone.reclaim_index]]
    avg_vol = sum(volumes) / len(volumes) if volumes else 0
    if avg_vol > 0:
        vol_ratio = v / avg_vol
        if vol_ratio >= 2.0:
            score += 20
        elif vol_ratio >= 1.5:
            score += 15
        elif vol_ratio >= 1.2:
            score += 10
        else:
            score += 5
    
    rsi_values = calculate_rsi(candles[:flip_zone.reclaim_index + 1])
    if rsi_values:
        breakout_rsi = rsi_values[-1]
        if breakout_rsi >= 70:
            score += 15
        elif breakout_rsi >= 65:
            score += 12
        elif breakout_rsi >= 60:
            score += 8
        else:
            score += 4
    
    if flip_zone.zone_strength == 'STRONG':
        score += 20
    elif flip_zone.zone_strength == 'MEDIUM':
        score += 12
    else:
        score += 5
    
    return min(score, 100)



def analyze_body_acceptance(candles: List[dict], fib_levels: Dict[str, float], flip_zone_origin: float) -> Dict:
    """
    Analyze where candle BODIES are accepting/reclaiming within the fib structure.
    
    Fib anchors remain wick-based (low wick → high wick).
    This function determines which fib zone has the strongest BODY acceptance.
    
    Returns:
        - best_body_zone: The fib level where bodies are accepting (382, 50, 618, etc.)
        - body_acceptance_score: How clean the body acceptance is (0-100)
        - zone_details: Debug info about each zone
    """
    result = {
        'best_body_zone': None,
        'body_acceptance_score': 0,
        'zone_details': {},
        'debug': []
    }
    
    if not candles or len(candles) < 10:
        return result
    
    # Get recent candles for body analysis (last 20 candles of retrace)
    recent = candles[-20:]
    
    # Define zone ranges (fib level ± tolerance for body acceptance)
    zone_tolerance = 0.03  # 3% zone width for body acceptance
    
    zone_scores = {}
    
    for setup_type, fib_price in fib_levels.items():
        if fib_price <= 0 or setup_type == 'UNDER_FIB':
            continue
            
        zone_top = fib_price * (1 + zone_tolerance)
        zone_bottom = fib_price * (1 - zone_tolerance)
        
        # Count body interactions with this zone
        body_closes_in_zone = 0
        body_opens_in_zone = 0
        body_reclaims = 0  # Closed below then closed back above
        body_rejections = 0  # Wicked into but body stayed out
        total_body_touches = 0
        
        prev_close = None
        
        for candle in recent:
            o = float(candle.get('open') or candle.get('o') or 0)
            h = float(candle.get('high') or candle.get('h') or 0)
            l = float(candle.get('low') or candle.get('l') or 0)
            c = float(candle.get('close') or candle.get('c') or 0)
            
            body_top = max(o, c)
            body_bottom = min(o, c)
            
            # Body closes inside zone
            if zone_bottom <= c <= zone_top:
                body_closes_in_zone += 1
                total_body_touches += 1
            
            # Body opens inside zone
            if zone_bottom <= o <= zone_top:
                body_opens_in_zone += 1
            
            # Body reclaim: previous close below zone, current close inside or above
            if prev_close and prev_close < zone_bottom and c >= zone_bottom:
                body_reclaims += 1
            
            # Wick rejection: wick touched zone but body stayed above
            if l <= zone_top and body_bottom > zone_top:
                body_rejections += 1
            
            prev_close = c
        
        # Calculate acceptance score for this zone
        # Higher score = more body acceptance at this level
        acceptance_score = 0
        
        # Body closes in zone (strongest signal)
        acceptance_score += body_closes_in_zone * 15
        
        # Body reclaims (very strong - shows zone is being defended)
        acceptance_score += body_reclaims * 25
        
        # Body opens in zone (continuation inside zone)
        acceptance_score += body_opens_in_zone * 10
        
        # Wick rejections (zone acting as support/resistance)
        acceptance_score += body_rejections * 5
        
        # Check if flip zone origin aligns with this fib level
        origin_alignment = abs(flip_zone_origin - fib_price) / fib_price if fib_price > 0 else 999
        if origin_alignment <= 0.05:  # Within 5%
            acceptance_score += 20  # Bonus for flip zone alignment
        
        zone_scores[setup_type] = {
            'score': acceptance_score,
            'body_closes': body_closes_in_zone,
            'body_reclaims': body_reclaims,
            'body_opens': body_opens_in_zone,
            'wick_rejections': body_rejections,
            'fib_price': fib_price,
            'origin_alignment': round(origin_alignment * 100, 1)
        }
        
        result['debug'].append(
            f"{setup_type}: score={acceptance_score} closes={body_closes_in_zone} "
            f"reclaims={body_reclaims} origin_align={origin_alignment*100:.1f}%"
        )
    
    # Find best body acceptance zone
    if zone_scores:
        best_zone = max(zone_scores.items(), key=lambda x: x[1]['score'])
        if best_zone[1]['score'] > 0:
            result['best_body_zone'] = best_zone[0]
            result['body_acceptance_score'] = best_zone[1]['score']
    
    result['zone_details'] = zone_scores
    
    return result


def apply_fib_and_classify(impulse: ImpulseLeg, flip_zone: FlipZone, candles: List[dict] = None) -> Optional[WizSetup]:
    if not impulse or not flip_zone:
        return None
    
    fib_range = impulse.breakout_high - impulse.expansion_low
    
    fib_levels = {
        '382': impulse.breakout_high - (fib_range * 0.382),
        '50': impulse.breakout_high - (fib_range * 0.50),
        '618': impulse.breakout_high - (fib_range * 0.618),
        '786': impulse.breakout_high - (fib_range * 0.786),
        'UNDER_FIB': impulse.expansion_low
    }
    
    zone_origin = flip_zone.origin_price
    
    best_match = None
    best_alignment = 999
    
    # Step 1: Traditional wick-based alignment check
    for setup_type, fib_price in fib_levels.items():
        if fib_price == 0:
            continue
        
        alignment_pct = abs(zone_origin - fib_price) / fib_price
        
        if alignment_pct <= FIB_TOLERANCE and alignment_pct < best_alignment:
            best_alignment = alignment_pct
            best_match = setup_type
    
    # Step 2: Body acceptance analysis (may override wick-based classification)
    # This checks where candle BODIES are actually accepting/reclaiming
    body_analysis = analyze_body_acceptance(candles if candles else [], fib_levels, zone_origin)
    
    body_zone = body_analysis.get('best_body_zone')
    body_score = body_analysis.get('body_acceptance_score', 0)
    
    # Log debug info
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"    [FIB-CLASS] Wick-based match: {best_match} (align: {best_alignment*100:.1f}%)")
    logger.info(f"    [FIB-CLASS] Body acceptance zone: {body_zone} (score: {body_score})")
    for debug_line in body_analysis.get('debug', []):
        logger.debug(f"    [FIB-CLASS] {debug_line}")
    
    # Override classification if body acceptance strongly favors a different zone
    if body_zone and body_score >= 30:  # Minimum threshold for body-based override
        if body_zone != best_match:
            # Check if body zone also has reasonable wick alignment
            body_zone_fib = fib_levels.get(body_zone, 0)
            if body_zone_fib > 0:
                body_zone_alignment = abs(zone_origin - body_zone_fib) / body_zone_fib
                # Allow body-based override if alignment is within extended tolerance
                if body_zone_alignment <= FIB_TOLERANCE * 1.5:
                    logger.info(f"    [FIB-CLASS] ✅ OVERRIDE: {best_match} → {body_zone} (body acceptance stronger)")
                    best_match = body_zone
                    best_alignment = body_zone_alignment
    
    if not best_match:
        return None
    
    min_expansion = MIN_EXPANSION.get(best_match, 30)
    expansion_valid = impulse.expansion_pct >= min_expansion
    
    if expansion_valid and impulse.impulse_score >= 75 and flip_zone.zone_strength == 'STRONG':
        grade = 'A'
    elif expansion_valid and impulse.impulse_score >= 50:
        grade = 'B'
    else:
        grade = 'C'
    
    setup_valid = expansion_valid and impulse.valid
    
    return WizSetup(
        setup_type=best_match,
        flip_zone=flip_zone,
        impulse=impulse,
        fib_levels=fib_levels,
        fib_alignment_pct=round(best_alignment * 100, 2),
        expansion_valid=expansion_valid,
        setup_valid=setup_valid,
        grade=grade
    )


def analyze_retrace(candles: List[dict], setup: WizSetup) -> Dict:
    result = {
        'retrace_quality': 'UNKNOWN',
        'at_entry_zone': False,
        'rejection_forming': False,
        'rsi_holding': False,
        'rsi_curling': False,
        'setup_failing': False,
        'failure_reason': None,
        'entry_score': 0
    }
    
    if not setup or not setup.setup_valid:
        return result
    
    recent = candles[-10:] if len(candles) >= 10 else candles
    
    target_fib = setup.fib_levels.get(setup.setup_type, setup.flip_zone.origin_price)
    zone_origin = setup.flip_zone.origin_price
    
    current_close = get_ohlcv(candles[-1])[3]
    
    distance_to_fib = abs(current_close - target_fib) / target_fib
    result['at_entry_zone'] = distance_to_fib <= 0.05
    
    rejection_count = 0
    small_body_count = 0
    
    for candle in recent[-5:]:
        o, h, l, c, v = get_ohlcv(candle)
        candle_range = h - l
        
        if candle_range > 0:
            body = abs(c - o)
            lower_wick = min(o, c) - l
            
            if body / candle_range < 0.4:
                small_body_count += 1
            
            if lower_wick / candle_range >= 0.3:
                rejection_count += 1
    
    result['rejection_forming'] = rejection_count >= 2 or small_body_count >= 3
    
    rsi_values = calculate_rsi(candles)
    if len(rsi_values) >= 5:
        current_rsi = rsi_values[-1]
        prev_rsi = rsi_values[-3]
        min_recent_rsi = min(rsi_values[-5:])
        
        result['rsi_holding'] = min_recent_rsi >= RSI_RETRACE_FLOOR
        result['rsi_curling'] = current_rsi > prev_rsi and current_rsi >= 45
    
    if current_close < zone_origin * 0.95:
        result['setup_failing'] = True
        result['failure_reason'] = 'Closed below flip zone'
    
    bearish_count = 0
    for candle in recent[-3:]:
        o, h, l, c, v = get_ohlcv(candle)
        body = abs(c - o)
        candle_range = h - l
        if c < o and candle_range > 0 and body / candle_range >= 0.6:
            bearish_count += 1
    
    if bearish_count >= 2:
        result['setup_failing'] = True
        result['failure_reason'] = 'Strong selling pressure'
    
    if rsi_values and rsi_values[-1] < 30:
        result['setup_failing'] = True
        result['failure_reason'] = 'RSI collapsed'
    
    entry_score = 0
    if result['at_entry_zone']:
        entry_score += 30
    if result['rejection_forming']:
        entry_score += 25
    if result['rsi_holding']:
        entry_score += 25
    if result['rsi_curling']:
        entry_score += 20
    if result['setup_failing']:
        entry_score = max(0, entry_score - 50)
    
    result['entry_score'] = entry_score
    
    if entry_score >= 80:
        result['retrace_quality'] = 'EXCELLENT'
    elif entry_score >= 60:
        result['retrace_quality'] = 'GOOD'
    elif entry_score >= 40:
        result['retrace_quality'] = 'FAIR'
    else:
        result['retrace_quality'] = 'POOR'
    
    return result



# ══════════════════════════════════════════════════════════════════════════════
# BREAKOUT FRESHNESS FILTER
# Ensures we only trade ACTIVE breakouts, not stale/dead moves
# ══════════════════════════════════════════════════════════════════════════════

def check_breakout_freshness(candles: List[dict], impulse, flip_zone) -> Dict:
    """
    Check if a breakout is still fresh/active or stale/dead.
    
    Uses TWO conditions together:
    1. How recent is the expansion high (candle age)
    2. How far is current price below that high (% drawdown)
    
    Returns:
        {
            'status': 'FRESH' | 'AGING' | 'STALE',
            'high_age': int,  # candles since high
            'pct_below_high': float,  # how far below high
            'reason': str,
            'has_recent_reclaim': bool  # structure still active
        }
    """
    result = {
        'status': 'FRESH',
        'high_age': 0,
        'pct_below_high': 0,
        'reason': 'Breakout is active',
        'has_recent_reclaim': False
    }
    
    if not candles or not impulse:
        return result
    
    # Get current price
    current_price = float(candles[-1].get('c') or candles[-1].get('close') or 0)
    if current_price <= 0:
        return result
    
    # Get expansion high info
    breakout_high = impulse.breakout_high
    high_index = impulse.high_index
    total_candles = len(candles)
    
    # Calculate metrics
    high_age = total_candles - 1 - high_index  # How many candles ago was the high
    pct_below_high = ((breakout_high - current_price) / breakout_high) * 100 if breakout_high > 0 else 0
    
    result['high_age'] = high_age
    result['pct_below_high'] = round(pct_below_high, 1)
    
    # Check for recent body acceptance / reclaim near flip zone
    # This indicates the move might be reviving
    has_recent_reclaim = False
    zone_price = flip_zone.origin_price if flip_zone else 0
    
    if zone_price > 0:
        # Check last 10 candles for body acceptance near zone
        zone_tolerance = zone_price * 0.05  # 5% tolerance
        recent_candles = candles[-10:]
        bodies_near_zone = 0
        
        for c in recent_candles:
            o = float(c.get('o') or c.get('open') or 0)
            close = float(c.get('c') or c.get('close') or 0)
            body_mid = (o + close) / 2
            
            if abs(body_mid - zone_price) <= zone_tolerance:
                bodies_near_zone += 1
        
        has_recent_reclaim = bodies_near_zone >= 3
        result['has_recent_reclaim'] = has_recent_reclaim
    
    # ══════════════════════════════════════════════════════════════════════════
    # FRESHNESS RULES (both conditions must be met for STALE)
    # ══════════════════════════════════════════════════════════════════════════
    
    # Standard setups (382, 50, 618): tighter thresholds
    # These are shallower pullbacks - if price dumped 50%+, the move is likely dead
    STANDARD_AGE_THRESHOLD = 30  # candles
    STANDARD_DRAWDOWN_THRESHOLD = 45  # percent
    
    # Deep pullback setups (786, Under-Fib): looser thresholds  
    # These naturally pull back deeper, so allow more room
    DEEP_AGE_THRESHOLD = 45  # candles
    DEEP_DRAWDOWN_THRESHOLD = 65  # percent
    
    # Determine which thresholds to use based on current price position
    # If price is very deep (below 618), use deep thresholds
    fib_618_level = breakout_high - (breakout_high - flip_zone.origin_price) * 0.618 if flip_zone else 0
    is_deep_pullback = current_price < fib_618_level if fib_618_level > 0 else pct_below_high > 50
    
    if is_deep_pullback:
        age_threshold = DEEP_AGE_THRESHOLD
        drawdown_threshold = DEEP_DRAWDOWN_THRESHOLD
        setup_context = "deep pullback"
    else:
        age_threshold = STANDARD_AGE_THRESHOLD
        drawdown_threshold = STANDARD_DRAWDOWN_THRESHOLD
        setup_context = "standard"
    
    # Apply freshness logic
    is_old = high_age > age_threshold
    is_deep_dump = pct_below_high > drawdown_threshold
    
    # STALE: Both conditions met AND no recent reclaim activity
    if is_old and is_deep_dump and not has_recent_reclaim:
        result['status'] = 'STALE'
        result['reason'] = f"High is {high_age} candles old + {pct_below_high:.0f}% below ({setup_context})"
        return result
    
    # AGING: One condition met, or both met but has recent reclaim
    if is_old or is_deep_dump:
        if has_recent_reclaim:
            result['status'] = 'AGING'
            result['reason'] = f"Old/deep but has recent zone reclaim activity"
        elif is_old:
            result['status'] = 'AGING'
            result['reason'] = f"High is {high_age} candles old (threshold: {age_threshold})"
        else:
            result['status'] = 'AGING'
            result['reason'] = f"Price {pct_below_high:.0f}% below high (threshold: {drawdown_threshold}%)"
        return result
    
    # FRESH: Neither condition met
    result['status'] = 'FRESH'
    result['reason'] = f"High is recent ({high_age} candles) and price healthy ({pct_below_high:.0f}% below)"
    return result


def detect_wiztheory_setup(candles: List[dict], symbol: str = "???") -> Dict:
    result = {
        'setup_detected': False,
        'setup_type': None,
        'flip_zone': None,
        'impulse': None,
        'fib_levels': None,
        'retrace': None,
        'grade': 'C',
        'impulse_score': 0,
        'expansion_pct': 0,
        'summary': ''
    }
    
    if not candles or len(candles) < 30:
        result['summary'] = 'Not enough candles'
        return result
    
    # BREAKOUT VALIDATION (REQUIRED)
    # Must have historical breakout with 30%+ expansion
    from breakout_validator import validate_breakout
    breakout_result = validate_breakout(candles, symbol)
    if not breakout_result['valid']:
        result['summary'] = f"No valid breakout: {breakout_result['reason']}"
        return result
    
    # Store breakout info for impulse calculation
    result['breakout_level'] = breakout_result['breakout_level']
    result['expansion_from_breakout'] = breakout_result['expansion_pct']
    
    flip_zone = detect_flip_zone_origin(candles)
    if not flip_zone:
        result['summary'] = 'No flip zone detected'
        return result
    
    flip_zone = detect_breakout(candles, flip_zone)
    if not flip_zone or not flip_zone.reclaimed:
        result['summary'] = 'No breakout detected'
        return result
    
    impulse = measure_expansion(candles, flip_zone)
    if not impulse:
        result['summary'] = 'Could not measure expansion'
        return result
    
    # ══════════════════════════════════════════════════════════════════════════
    # BREAKOUT FRESHNESS CHECK
    # Reject stale/dead breakouts where the move already happened and dumped
    # ══════════════════════════════════════════════════════════════════════════
    freshness = check_breakout_freshness(candles, impulse, flip_zone)
    result['freshness'] = freshness
    
    if freshness['status'] == 'STALE':
        result['summary'] = f"Stale breakout: {freshness['reason']}"
        logger.info(f"    [FRESHNESS] ❌ STALE: {freshness['reason']}")
        logger.info(f"    [FRESHNESS]    High age: {freshness['high_age']} candles | Below high: {freshness['pct_below_high']:.1f}%")
        return result
    elif freshness['status'] == 'AGING':
        logger.info(f"    [FRESHNESS] ⚠️ AGING: {freshness['reason']}")
        logger.info(f"    [FRESHNESS]    High age: {freshness['high_age']} candles | Below high: {freshness['pct_below_high']:.1f}%")
    else:
        logger.debug(f"    [FRESHNESS] ✅ FRESH: {freshness['reason']}")
    
    setup = apply_fib_and_classify(impulse, flip_zone, candles)
    if not setup:
        result['summary'] = 'No fib alignment found'
        return result
    
    retrace = analyze_retrace(candles, setup)
    
    result['setup_detected'] = setup.setup_valid
    result['setup_type'] = setup.setup_type
    result['flip_zone'] = {
        'origin': flip_zone.origin_price,
        'strength': flip_zone.zone_strength,
        'rejections': flip_zone.rejection_count,
        'reclaim_price': flip_zone.reclaim_price
    }
    result['impulse'] = {
        'zone_origin': impulse.zone_origin,
        'breakout_high': impulse.breakout_high,
        'expansion_low': impulse.expansion_low,
        'expansion_pct': impulse.expansion_pct,
        'score': impulse.impulse_score
    }
    result['fib_levels'] = setup.fib_levels
    result['retrace'] = retrace
    result['grade'] = setup.grade
    result['impulse_score'] = impulse.impulse_score
    result['expansion_pct'] = impulse.expansion_pct
    
    if setup.setup_valid:
        result['summary'] = f"{setup.setup_type} Setup | Exp: {impulse.expansion_pct:.0f}% | Score: {impulse.impulse_score} | {setup.grade}"
    else:
        if not setup.expansion_valid:
            result['summary'] = f"{setup.setup_type} - Expansion too small ({impulse.expansion_pct:.0f}% < {MIN_EXPANSION[setup.setup_type]}%)"
        else:
            result['summary'] = f"{setup.setup_type} - Invalid (score: {impulse.impulse_score})"
    
    return result


if __name__ == '__main__':
    print("WizTheory Impulse Detector v1.0 - Test")
    print("=" * 50)
    
    candles = []
    price = 100
    
    for i in range(15):
        price += 1.5
        candles.append({'o': price - 0.5, 'h': price + 1, 'l': price - 1, 'c': price, 'v': 1000})
    
    resistance = price + 2
    for i in range(5):
        candles.append({'o': price, 'h': resistance + 1, 'l': price - 1, 'c': price - 0.5, 'v': 1200})
        price -= 0.5
    
    for i in range(10):
        price -= 1
        candles.append({'o': price + 0.5, 'h': price + 1, 'l': price - 0.5, 'c': price, 'v': 800})
    
    for i in range(15):
        price += 3
        candles.append({'o': price - 2, 'h': price + 1, 'l': price - 2.5, 'c': price, 'v': 2000 + i * 100})
    
    for i in range(10):
        price -= 1.5
        candles.append({'o': price + 1, 'h': price + 1.5, 'l': price - 0.5, 'c': price + 0.3, 'v': 900})
    
    result = detect_wiztheory_setup(candles)
    
    print(f"Setup Detected: {result['setup_detected']}")
    print(f"Setup Type: {result['setup_type']}")
    print(f"Summary: {result['summary']}")
    print(f"Grade: {result['grade']}")
