"""
UNDER-FIB FLIP ZONE VALIDATOR (HUNTER MODE) v2.0

HUNTER MODE ALERT TIMING:
- Alert when price breaks the fib level above (GATE)
- AND begins moving toward the flip zone below (DESTINATION)
- Zone is the DESTINATION, fib is the GATE

DESTINATION-FIRST LOGIC:
1. Find valid flip zone first
2. Identify which fib is directly ABOVE it (that's the gate)
3. Track price relative to gate and destination

UNDER-FIB SUBTYPES:
- Under-Fib 382: Zone below .382, gate at .382
- Under-Fib 50: Zone below .50, gate at .50  
- Under-Fib 618: Zone below .618, gate at .618
- Under-Fib 786: Zone below .786, gate at .786

FRESHNESS RULE (CRITICAL):
- Pre-breakout touches are ALLOWED (zone establishment)
- Only POST-breakout touches determine freshness
- Zone is fresh if untested AFTER the breakout
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class ValidationLayer:
    layer_name: str
    passed: bool
    score: int
    reason: str
    weight: float = 1.0

@dataclass 
class ValidationResult:
    setup: str = "underfib"
    passed: bool = False
    final_score: int = 0
    final_grade: str = "C"
    layers: List[ValidationLayer] = field(default_factory=list)
    reasons_passed: List[str] = field(default_factory=list)
    reasons_failed: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    flashcard_type: str = "underfib"
    whale_conviction: bool = False
    alert_ready: bool = False
    stage: int = 0
    stage_label: str = ""
    hunter_mode: bool = True
    gate_fib: str = ""
    fib_level_above: str = ""  # Alias for gate_fib
    destination_zone: float = 0
    underfib_subtype: str = ""  # "Under-Fib 382", "Under-Fib 50", etc.


def _find_breakout_index(candles: List[Dict], swing_high: float) -> int:
    """
    Find the index where the breakout to swing high occurred.
    This is the candle that first closed above 90% of the swing high.
    """
    if not candles or swing_high <= 0:
        return -1
    
    breakout_threshold = swing_high * 0.90
    
    for i, c in enumerate(candles):
        close = float(c.get('c', 0) or 0)
        if close >= breakout_threshold:
            return i
    
    return -1


def _count_post_breakout_zone_touches(
    candles: List[Dict], 
    breakout_idx: int, 
    zone_level: float, 
    zone_tolerance: float
) -> Tuple[int, bool]:
    """
    Count how many times price interacted with the zone AFTER breakout.
    
    Returns:
        (touch_count, is_fresh)
        - is_fresh = True if zone has 0-1 post-breakout touches
    """
    if breakout_idx < 0 or breakout_idx >= len(candles):
        return (0, True)
    
    post_breakout_candles = candles[breakout_idx:]
    zone_top = zone_level + zone_tolerance
    zone_bottom = zone_level - zone_tolerance
    
    touch_count = 0
    
    for c in post_breakout_candles:
        low = float(c.get('l', 0) or 0)
        high = float(c.get('h', 0) or 0)
        
        # Touch = price entered the zone
        if low <= zone_top and high >= zone_bottom:
            touch_count += 1
    
    # Fresh = 0-1 post-breakout touches (first touch is the entry opportunity)
    is_fresh = touch_count <= 1
    
    return (touch_count, is_fresh)


def _find_destination_zone(
    flip_zones: List[Dict], 
    fibs: Dict[str, float], 
    current_price: float,
    range_size: float
) -> Tuple[Optional[Dict], str, float]:
    """
    DESTINATION-FIRST LOGIC:
    1. Find flip zones that are BELOW a fib level
    2. Identify which fib is directly above (the gate)
    3. Return the best destination zone
    
    Returns:
        (zone_dict, gate_fib_name, zone_level)
    """
    # Sort fibs by level descending (382 highest, 786 lowest)
    fib_order = ['382', '50', '618', '786']
    
    best_zone = None
    best_gate = None
    best_level = 0
    
    for fz in flip_zones:
        if not isinstance(fz, dict):
            continue
        
        fz_level = fz.get('level', 0)
        if fz_level <= 0:
            continue
        
        # Find which fib is directly ABOVE this zone
        for fib_name in fib_order:
            fib_level = fibs.get(fib_name, 0)
            
            # Zone must be meaningfully below the fib (at least 3% of range)
            if fz_level < fib_level - (range_size * 0.03):
                # This fib is above the zone - it's the gate
                # Check if price has broken or is near this gate
                if current_price < fib_level * 1.02:  # Within 2% of gate or below
                    best_zone = fz
                    best_gate = fib_name
                    best_level = fz_level
                    break
        
        if best_zone:
            break
    
    return (best_zone, best_gate or "", best_level)


def _check_alert_timing(
    current_price: float,
    gate_level: float,
    destination_zone: float,
    zone_tolerance: float
) -> Tuple[bool, bool, bool, str]:
    """
    Check alert timing state.
    
    Returns:
        (price_broke_gate, is_approaching, is_first_touch, state_label)
    
    States:
    - APPROACHING: Price broke gate, moving toward zone, hasn't touched yet
    - FIRST_TOUCH: Price just entered zone for first time
    - REACTING: Price bounced from zone (too late for alert)
    """
    zone_top = destination_zone + zone_tolerance
    zone_bottom = destination_zone - zone_tolerance
    
    price_broke_gate = current_price < gate_level
    
    # Check position relative to zone
    if current_price > zone_top:
        # Above zone - approaching
        is_approaching = price_broke_gate
        is_first_touch = False
        state = "APPROACHING" if is_approaching else "ABOVE_GATE"
    elif current_price >= zone_bottom:
        # Inside zone - first touch window
        is_approaching = False
        is_first_touch = True
        state = "FIRST_TOUCH"
    else:
        # Below zone - either deep in zone or bounced
        # Still valid if just slightly below (within 2x tolerance)
        if current_price >= zone_bottom - zone_tolerance:
            is_approaching = False
            is_first_touch = True
            state = "IN_ZONE"
        else:
            is_approaching = False
            is_first_touch = False
            state = "BELOW_ZONE"
    
    return (price_broke_gate, is_approaching, is_first_touch, state)


def validate_under_fib(candles: List[Dict], symbol: str, structure: Dict = None) -> ValidationResult:
    """Validate Under-Fib Flip Zone with HUNTER MODE v2.0."""
    result = ValidationResult()
    
    if structure is None:
        structure = _compute_basic_structure(candles)
    
    if not structure:
        result.reject_reason = "No structure data available"
        return result
    
    impulse_pct = structure.get('impulse_pct', 0)
    retracement_pct = structure.get('retracement_pct', 0)
    current_price = structure.get('current_price', 0)
    swing_high = structure.get('swing_high', 0)
    swing_low = structure.get('swing_low', 0)
    flip_zones = structure.get('flip_zones', [])
    avg_body_ratio = structure.get('avg_body_ratio', 0.5)
    whale_conviction = structure.get('whale_conviction', False)
    
    passes_underfib_gate = structure.get('passes_underfib_gate', False)
    has_valid_breakout = structure.get('ath_breakout', False) or structure.get('major_high_break', False)
    
    if not passes_underfib_gate and not has_valid_breakout:
        result.reject_reason = "No valid breakout structure"
        logger.info(f"   [UFIB-VAL] {symbol}: ❌ REJECTED - No valid breakout structure")
        return result
    
    range_size = swing_high - swing_low if swing_high > swing_low else 0
    zone_tolerance = range_size * 0.03  # 3% tolerance for zone boundaries
    
    # Calculate all fib levels
    fibs = {
        '382': swing_high - (range_size * 0.382),
        '50': swing_high - (range_size * 0.50),
        '618': swing_high - (range_size * 0.618),
        '786': swing_high - (range_size * 0.786)
    }
    
    # ═══════════════════════════════════════════════════════════════
    # DESTINATION-FIRST: Find the target zone and its gate
    # ═══════════════════════════════════════════════════════════════
    dest_zone, gate_fib_name, destination_zone_level = _find_destination_zone(
        flip_zones, fibs, current_price, range_size
    )
    
    fresh_zone_below_fib = dest_zone is not None and destination_zone_level > 0
    zone_touches_total = dest_zone.get('touches', 0) if dest_zone else 0
    
    result.gate_fib = gate_fib_name
    result.fib_level_above = gate_fib_name
    result.destination_zone = destination_zone_level
    result.underfib_subtype = f"Under-Fib {gate_fib_name}" if gate_fib_name else ""
    
    # ═══════════════════════════════════════════════════════════════
    # ZONE FRESHNESS: Count only POST-BREAKOUT touches
    # ═══════════════════════════════════════════════════════════════
    breakout_idx = _find_breakout_index(candles, swing_high)
    post_breakout_touches, zone_is_fresh = _count_post_breakout_zone_touches(
        candles, breakout_idx, destination_zone_level, zone_tolerance
    )
    
    # LAYER: Flip Zone Below Fib
    result.layers.append(ValidationLayer(
        layer_name="flip_zone",
        passed=fresh_zone_below_fib,
        score=25 if fresh_zone_below_fib else 0,
        reason=f"Zone below {gate_fib_name}: {'✓' if fresh_zone_below_fib else '✗'} ({result.underfib_subtype})",
        weight=1.4
    ))
    
    # LAYER: Zone Freshness (POST-BREAKOUT only)
    result.layers.append(ValidationLayer(
        layer_name="zone_freshness",
        passed=zone_is_fresh,
        score=25 if zone_is_fresh else 10 if fresh_zone_below_fib else 0,
        reason=f"Post-breakout touches: {post_breakout_touches} ({'fresh' if zone_is_fresh else 'tested'}) [pre-BO: {zone_touches_total - post_breakout_touches}]",
        weight=1.5
    ))
    
    if zone_is_fresh and fresh_zone_below_fib:
        logger.info(f"   [UFIB-VAL] zone_freshness: ✓ - Fresh zone (post-BO touches: {post_breakout_touches})")
    
    # LAYER: Expansion
    expansion_passed = impulse_pct >= 60
    expansion_score = 20 if impulse_pct >= 100 else 15 if impulse_pct >= 80 else 12 if impulse_pct >= 60 else 0
    result.layers.append(ValidationLayer(
        layer_name="expansion",
        passed=expansion_passed,
        score=expansion_score,
        reason=f"Expansion {impulse_pct:.0f}% (need 60%)",
        weight=1.3
    ))
    
    # LAYER: Pullback Depth
    depth_passed = retracement_pct >= 40
    depth_score = 20 if retracement_pct >= 50 else 15 if retracement_pct >= 40 else 5
    result.layers.append(ValidationLayer(
        layer_name="pullback_depth",
        passed=depth_passed,
        score=depth_score,
        reason=f"Pullback {retracement_pct:.0f}% (need 40%)",
        weight=1.1
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # ALERT TIMING: Approach OR First-Touch window
    # ═══════════════════════════════════════════════════════════════
    price_broke_gate = False
    is_approaching = False
    is_first_touch = False
    timing_state = "UNKNOWN"
    
    if gate_fib_name and gate_fib_name in fibs:
        gate_level = fibs[gate_fib_name]
        price_broke_gate, is_approaching, is_first_touch, timing_state = _check_alert_timing(
            current_price, gate_level, destination_zone_level, zone_tolerance
        )
    
    # Alert is ready if:
    # - Price broke gate AND (approaching OR first touch)
    # - Zone is fresh
    alert_timing_passed = price_broke_gate and (is_approaching or is_first_touch)
    alert_ready = alert_timing_passed and zone_is_fresh and fresh_zone_below_fib
    
    result.layers.append(ValidationLayer(
        layer_name="alert_timing",
        passed=alert_timing_passed,
        score=20 if alert_timing_passed else 10 if price_broke_gate else 0,
        reason=f"Gate {gate_fib_name}: {'✓' if price_broke_gate else '✗'} | State: {timing_state}",
        weight=1.3
    ))
    
    # LAYER: Structure
    structure_passed = avg_body_ratio >= 0.45
    structure_score = 12 if avg_body_ratio >= 0.60 else 8 if avg_body_ratio >= 0.45 else 4
    result.layers.append(ValidationLayer(
        layer_name="structure",
        passed=structure_passed,
        score=structure_score,
        reason=f"Quality {avg_body_ratio:.0%}",
        weight=0.9
    ))
    
    # Whale (bonus)
    result.whale_conviction = whale_conviction
    whale_bonus = 5 if whale_conviction else 0
    
    # FINAL SCORE
    total_score = sum(layer.score * layer.weight for layer in result.layers) + whale_bonus
    result.final_score = min(100, int((total_score / 130) * 100))
    
    # Pass criteria: Zone exists + fresh + expansion + alert timing
    critical_passed = fresh_zone_below_fib and zone_is_fresh and expansion_passed and alert_timing_passed
    result.passed = critical_passed and result.final_score >= 60
    
    if result.final_score >= 90: result.final_grade = "A+"
    elif result.final_score >= 80: result.final_grade = "A"
    elif result.final_score >= 70: result.final_grade = "B+"
    elif result.final_score >= 60: result.final_grade = "B"
    else: result.final_grade = "C"
    
    result.alert_ready = result.passed
    
    if result.passed:
        result.stage = 1
        result.stage_label = f"{result.underfib_subtype} - {timing_state}"
    
    for layer in result.layers:
        if layer.passed:
            result.reasons_passed.append(layer.layer_name)
        else:
            result.reasons_failed.append(layer.layer_name)
    
    status = "✅ PASSED" if result.passed else "❌ REJECTED"
    logger.info(f"   [UFIB-VAL] {symbol}: {status} [HUNTER] Score={result.final_score} Grade={result.final_grade} {result.underfib_subtype}")
    
    return result


def _compute_basic_structure(candles: List[Dict]) -> Dict:
    """Fallback structure computation if none provided."""
    if not candles or len(candles) < 50:
        return {}
    try:
        highs = [float(c.get('h', 0) or 0) for c in candles if float(c.get('h', 0) or 0) > 0]
        lows = [float(c.get('l', 0) or 0) for c in candles if float(c.get('l', 0) or 0) > 0]
        closes = [float(c.get('c', 0) or 0) for c in candles if float(c.get('c', 0) or 0) > 0]
        
        swing_high = max(highs[-100:]) if len(highs) >= 100 else max(highs)
        swing_low = min(lows[-150:]) if len(lows) >= 150 else min(lows)
        current_price = closes[-1]
        
        impulse_pct = ((swing_high - swing_low) / swing_low) * 100 if swing_low > 0 else 0
        range_size = swing_high - swing_low
        retracement_pct = ((swing_high - current_price) / range_size) * 100 if range_size > 0 else 0
        
        return {
            'impulse_pct': impulse_pct,
            'retracement_pct': retracement_pct,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'current_price': current_price,
            'avg_body_ratio': 0.6,
            'flip_zones': [],
            'whale_conviction': False
        }
    except:
        return {}
