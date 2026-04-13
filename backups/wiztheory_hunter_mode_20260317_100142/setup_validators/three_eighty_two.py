"""
382 + FLIP ZONE VALIDATOR (HUNTER MODE)

CORE CONCEPT: Breakout → Exhaustion → Early Alert → Continuation

HUNTER MODE ALERT TIMING:
- Alert on FIRST major rejection/exhaustion from expansion high
- Do NOT wait for price to reach 0.382
- This is the fastest setup → must be early
- If expansion continues, re-fib and re-evaluate mapping

Sequence:
1. Prior resistance zone (2+ touches/rejections)
2. Breakout above that zone (expansion >= 30%)
3. EXHAUSTION DETECTED (rejection wick, bearish candle, volume spike)
4. Alert fires IMMEDIATELY on exhaustion
5. Price expected to pull back to flip zone at 382 level

This validator uses shared analysis + Hunter Mode exhaustion detection.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Import Hunter Mode functions
try:
    from setup_validators.hunter_mode import detect_expansion_exhaustion, get_current_fib_alignment
except ImportError:
    detect_expansion_exhaustion = None
    get_current_fib_alignment = None


@dataclass
class ValidationLayer:
    layer_name: str
    passed: bool
    score: int
    reason: str
    weight: float = 1.0


@dataclass 
class ValidationResult:
    setup: str = "382"
    passed: bool = False
    final_score: int = 0
    final_grade: str = "C"
    layers: List[ValidationLayer] = field(default_factory=list)
    reasons_passed: List[str] = field(default_factory=list)
    reasons_failed: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    flashcard_type: str = "382"
    whale_conviction: bool = False
    alert_ready: bool = False
    stage: int = 0
    stage_label: str = ""
    hunter_mode: bool = True  # Always Hunter Mode


def validate_382(candles: List[Dict], symbol: str, structure: Dict = None) -> ValidationResult:
    """
    Validate 382 + Flip Zone setup with HUNTER MODE.
    
    HUNTER MODE: Alert on exhaustion, not arrival at zone.
    """
    result = ValidationResult()
    
    if structure is None:
        structure = _compute_basic_structure(candles)
    
    if not structure:
        result.reject_reason = "No structure data available"
        return result
    
    # ═══════════════════════════════════════════════════════════════
    # EXTRACT SHARED ANALYSIS
    # ═══════════════════════════════════════════════════════════════
    impulse_pct = structure.get('impulse_pct', 0)
    retracement_pct = structure.get('retracement_pct', 0)
    current_price = structure.get('current_price', 0)
    rsi = structure.get('rsi', 50)
    swing_high = structure.get('swing_high', 0)
    swing_low = structure.get('swing_low', 0)
    avg_body_ratio = structure.get('avg_body_ratio', 0.5)
    volume_expanding = structure.get('volume_expanding', False)
    volume_contracting = structure.get('volume_contracting', False)
    flip_zones = structure.get('flip_zones', [])
    fib_levels = structure.get('fib_levels', {})
    
    # ═══════════════════════════════════════════════════════════════
    # GATE CHECK: Must pass hybrid intake gate
    # ═══════════════════════════════════════════════════════════════
    passes_382_gate = structure.get('passes_382fz_gate', False)
    has_valid_breakout = structure.get('ath_breakout', False) or structure.get('major_high_break', False)
    
    if not passes_382_gate and not has_valid_breakout:
        result.reject_reason = "No valid breakout structure (hybrid gate failed)"
        result.reasons_failed.append("NO_BREAKOUT")
        logger.info(f"   [382-VAL] {symbol}: ❌ REJECTED - No valid breakout structure")
        return result
    
    ath_breakout = has_valid_breakout
    whale_conviction = structure.get('whale_conviction', False)
    
    # Calculate fib levels
    range_size = swing_high - swing_low if swing_high > swing_low else 0
    fib_382_level = fib_levels.get('382', swing_high - (range_size * 0.382))
    
    # ═══════════════════════════════════════════════════════════════
    # HUNTER MODE: EXHAUSTION DETECTION (PRIMARY TRIGGER)
    # ═══════════════════════════════════════════════════════════════
    exhaustion_data = {'exhaustion_detected': False, 'exhaustion_score': 0}
    if detect_expansion_exhaustion:
        exhaustion_data = detect_expansion_exhaustion(candles, structure)
    
    exhaustion_detected = exhaustion_data.get('exhaustion_detected', False)
    exhaustion_score = exhaustion_data.get('exhaustion_score', 0)
    pullback_started = exhaustion_data.get('pullback_started', False)
    
    result.layers.append(ValidationLayer(
        layer_name="exhaustion",
        passed=exhaustion_detected,
        score=exhaustion_score // 4,  # Normalize to 0-25
        reason=f"Exhaustion: {exhaustion_data.get('exhaustion_type', 'none')} ({exhaustion_score}%)",
        weight=1.5  # High weight for Hunter Mode
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: FLIP ZONE DETECTION
    # ═══════════════════════════════════════════════════════════════
    flip_zone_detected = False
    flip_zone_score = 0
    
    if flip_zones and len(flip_zones) > 0:
        for fz in flip_zones:
            fz_level = fz.get('level', 0) if isinstance(fz, dict) else 0
            touches = fz.get('touches', 0) if isinstance(fz, dict) else 0
            
            if fib_382_level > 0 and fz_level > 0:
                distance_pct = abs(fz_level - fib_382_level) / fib_382_level * 100
                if distance_pct < 8 and touches >= 2:  # 8% tolerance for early detection
                    flip_zone_detected = True
                    break
    
    if not flip_zone_detected:
        flip_zone_detected = _detect_flip_zone_from_candles(candles, fib_382_level)
    
    if flip_zone_detected:
        flip_zone_score = 20
        flip_zone_reason = "Flip zone detected at 382 level"
    else:
        flip_zone_score = 0
        flip_zone_reason = "No clear flip zone at 382"
    
    result.layers.append(ValidationLayer(
        layer_name="flip_zone",
        passed=flip_zone_detected,
        score=flip_zone_score,
        reason=flip_zone_reason,
        weight=1.3
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: EXPANSION (>= 30%)
    # ═══════════════════════════════════════════════════════════════
    expansion_passed = impulse_pct >= 30
    
    if impulse_pct >= 60:
        expansion_score = 20
    elif impulse_pct >= 45:
        expansion_score = 15
    elif impulse_pct >= 30:
        expansion_score = 12
    else:
        expansion_score = 0
    
    if ath_breakout:
        expansion_score += 5
    
    result.layers.append(ValidationLayer(
        layer_name="expansion",
        passed=expansion_passed,
        score=expansion_score,
        reason=f"Expansion {impulse_pct:.0f}%" + (" + ATH" if ath_breakout else ""),
        weight=1.2
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 3: RETRACEMENT DEPTH (HUNTER MODE: Accept early stages)
    # Alert can fire BEFORE reaching 382, so accept 0-42%
    # ═══════════════════════════════════════════════════════════════
    
    # Hunter Mode: Accept early retracement OR at-zone
    if retracement_pct < 15:
        # Very early - just exhausted, minimal pullback
        depth_passed = exhaustion_detected  # OK if exhaustion detected
        depth_score = 10 if exhaustion_detected else 0
        depth_reason = f"Early stage ({retracement_pct:.1f}%) - Exhaustion triggered"
    elif 15 <= retracement_pct < 30:
        # Approaching zone
        depth_passed = True
        depth_score = 15
        depth_reason = f"Approaching 382 ({retracement_pct:.1f}%)"
    elif 30 <= retracement_pct <= 42:
        # In the zone
        depth_passed = True
        depth_score = 20
        depth_reason = f"At 382 zone ({retracement_pct:.1f}%)"
    else:
        # Below zone
        depth_passed = False
        depth_score = 0
        depth_reason = f"Below 382 zone ({retracement_pct:.1f}%)"
    
    result.layers.append(ValidationLayer(
        layer_name="pullback_depth",
        passed=depth_passed,
        score=depth_score,
        reason=depth_reason,
        weight=1.1
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 4: STRUCTURE QUALITY
    # ═══════════════════════════════════════════════════════════════
    structure_quality = avg_body_ratio
    structure_passed = structure_quality >= 0.45
    
    if structure_quality >= 0.70:
        structure_score = 15
    elif structure_quality >= 0.55:
        structure_score = 10
    elif structure_quality >= 0.45:
        structure_score = 7
    else:
        structure_score = 0
    
    result.layers.append(ValidationLayer(
        layer_name="structure",
        passed=structure_passed,
        score=structure_score,
        reason=f"Structure quality {structure_quality:.0%}",
        weight=0.9
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 5: VOLUME BEHAVIOR
    # ═══════════════════════════════════════════════════════════════
    if volume_contracting:
        volume_passed = True
        volume_score = 15
        volume_reason = "Volume declining (healthy pullback)"
    elif volume_expanding:
        volume_passed = False
        volume_score = 5
        volume_reason = "Volume expanding (watch for distribution)"
    else:
        volume_passed = True
        volume_score = 10
        volume_reason = "Volume neutral"
    
    result.layers.append(ValidationLayer(
        layer_name="volume",
        passed=volume_passed,
        score=volume_score,
        reason=volume_reason,
        weight=0.8
    ))
    
    # ═══════════════════════════════════════════════════════════════
    # WHALE CONVICTION (Bonus)
    # ═══════════════════════════════════════════════════════════════
    result.whale_conviction = whale_conviction
    whale_bonus = 5 if whale_conviction else 0
    
    # ═══════════════════════════════════════════════════════════════
    # CALCULATE FINAL SCORE AND GRADE
    # ═══════════════════════════════════════════════════════════════
    
    # Hunter Mode critical: exhaustion OR depth + flip zone + expansion
    hunter_triggered = exhaustion_detected and expansion_passed
    zone_triggered = depth_passed and flip_zone_detected and expansion_passed
    
    critical_passed = hunter_triggered or zone_triggered
    
    # Calculate weighted score
    total_score = sum(layer.score * layer.weight for layer in result.layers)
    total_score += whale_bonus
    
    max_possible = 120  # Approximate max
    result.final_score = int((total_score / max_possible) * 100)
    result.final_score = min(100, result.final_score)
    
    passed_layers = sum(1 for layer in result.layers if layer.passed)
    
    result.passed = (
        critical_passed and
        passed_layers >= 3 and
        result.final_score >= 60
    )
    
    # Grade
    if result.final_score >= 90:
        result.final_grade = "A+"
    elif result.final_score >= 80:
        result.final_grade = "A"
    elif result.final_score >= 70:
        result.final_grade = "B+"
    elif result.final_score >= 60:
        result.final_grade = "B"
    else:
        result.final_grade = "C"
    
    result.alert_ready = result.passed
    
    # Stage labeling for Hunter Mode
    if result.passed:
        if exhaustion_detected and retracement_pct < 20:
            result.stage = 1
            result.stage_label = "EXHAUSTION ALERT"
        elif retracement_pct < 30:
            result.stage = 2
            result.stage_label = "APPROACHING 382"
        else:
            result.stage = 3
            result.stage_label = "AT 382 ZONE"
    
    # Populate reasons
    for layer in result.layers:
        if layer.passed:
            result.reasons_passed.append(layer.layer_name)
        else:
            result.reasons_failed.append(layer.layer_name)
    
    status = "✅ PASSED" if result.passed else "❌ REJECTED"
    mode = "[HUNTER]" if exhaustion_detected else "[ZONE]"
    logger.info(f"   [382-VAL] {symbol}: {status} {mode} Score={result.final_score} Grade={result.final_grade} Stage={result.stage_label}")
    
    return result


def _detect_flip_zone_from_candles(candles: List[Dict], fib_382_level: float) -> bool:
    """Detect flip zone from candle data."""
    if not candles or len(candles) < 50 or fib_382_level <= 0:
        return False
    
    try:
        tolerance = fib_382_level * 0.03
        split_point = int(len(candles) * 0.6)
        prior_candles = candles[:split_point]
        
        touches = 0
        for c in prior_candles:
            high = float(c.get('h', 0) or 0)
            close = float(c.get('c', 0) or 0)
            if abs(high - fib_382_level) <= tolerance and close < fib_382_level:
                touches += 1
        
        return touches >= 2
    except:
        return False


def _compute_basic_structure(candles: List[Dict]) -> Dict:
    """Fallback structure computation."""
    if not candles or len(candles) < 50:
        return {}
    
    try:
        highs = [float(c.get('h', 0) or 0) for c in candles if float(c.get('h', 0) or 0) > 0]
        lows = [float(c.get('l', 0) or 0) for c in candles if float(c.get('l', 0) or 0) > 0]
        closes = [float(c.get('c', 0) or 0) for c in candles if float(c.get('c', 0) or 0) > 0]
        
        if len(highs) < 50:
            return {}
        
        swing_high = max(highs[-100:]) if len(highs) >= 100 else max(highs)
        swing_low = min(lows[-150:]) if len(lows) >= 150 else min(lows)
        current_price = closes[-1]
        
        # Find swing high index
        swing_high_idx = len(candles) - 1
        for i, c in enumerate(candles):
            if float(c.get('h', 0) or 0) == swing_high:
                swing_high_idx = i
                break
        
        impulse_pct = ((swing_high - swing_low) / swing_low) * 100 if swing_low > 0 else 0
        range_size = swing_high - swing_low
        retracement_pct = ((swing_high - current_price) / range_size) * 100 if range_size > 0 else 0
        
        return {
            'impulse_pct': impulse_pct,
            'retracement_pct': retracement_pct,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'swing_high_idx': swing_high_idx,
            'current_price': current_price,
            'fib_levels': {'382': swing_high - (range_size * 0.382)},
            'avg_body_ratio': 0.6,
            'volume_contracting': True,
            'volume_expanding': False,
            'flip_zones': [],
            'rsi': 50,
            'candle_count': len(candles),
            'whale_conviction': False
        }
    except:
        return {}
