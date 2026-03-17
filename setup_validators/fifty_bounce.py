"""
50 + FLIP ZONE VALIDATOR (HUNTER MODE)

HUNTER MODE ALERT TIMING:
- Alert on FIRST major rejection/exhaustion from expansion high (SAME as 382)
- Do NOT wait for price to reach 0.50
- Trigger while retrace is beginning
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from setup_validators.hunter_mode import detect_expansion_exhaustion
except ImportError:
    detect_expansion_exhaustion = None

@dataclass
class ValidationResult:
    layer_name: str
    passed: bool
    score: int
    reason: str
    details: Dict = field(default_factory=dict)

@dataclass  
class FiftyBounceResult:
    symbol: str = ""
    is_valid: bool = False
    final_score: int = 0
    final_grade: str = "C"
    layers: List[ValidationResult] = field(default_factory=list)
    rejection_reason: str = None
    stage: int = 0
    stage_name: str = ""
    hunter_mode: bool = True
    impulse_high: float = 0
    impulse_low: float = 0
    fib_50: float = 0
    current_retracement: float = 0

def validate_50_bounce(candles: List[Dict], symbol: str, structure: Dict = None) -> FiftyBounceResult:
    """Validate 50 + Flip Zone with HUNTER MODE."""
    result = FiftyBounceResult(symbol=symbol)
    
    if not candles or len(candles) < 50:
        result.rejection_reason = "Insufficient candles"
        return result
    
    if structure is None:
        structure = _build_structure(candles)
    
    impulse_pct = structure.get('impulse_pct', 0)
    retracement_pct = structure.get('retracement_pct', 0)
    swing_high = structure.get('swing_high', 0)
    swing_low = structure.get('swing_low', 0)
    current_price = structure.get('current_price', 0)
    flip_zones = structure.get('flip_zones', [])
    avg_body_ratio = structure.get('avg_body_ratio', 0.5)
    
    passes_50_gate = structure.get('passes_50fz_gate', False)
    has_valid_breakout = structure.get('ath_breakout', False) or structure.get('major_high_break', False)
    
    if not passes_50_gate and not has_valid_breakout:
        result.rejection_reason = "No valid breakout structure"
        logger.info(f"   [50-VAL] {symbol}: ❌ REJECTED - No valid breakout structure")
        return result
    
    range_size = swing_high - swing_low if swing_high > swing_low else 0
    fib_50 = swing_high - (range_size * 0.50)
    result.fib_50 = fib_50
    result.impulse_high = swing_high
    result.impulse_low = swing_low
    result.current_retracement = retracement_pct
    
    # HUNTER MODE: EXHAUSTION DETECTION
    exhaustion_data = {'exhaustion_detected': False, 'exhaustion_score': 0}
    if detect_expansion_exhaustion:
        exhaustion_data = detect_expansion_exhaustion(candles, structure)
    
    exhaustion_detected = exhaustion_data.get('exhaustion_detected', False)
    exhaustion_score = exhaustion_data.get('exhaustion_score', 0)
    pullback_started = exhaustion_data.get('pullback_started', False)
    
    result.layers.append(ValidationResult(
        layer_name="exhaustion",
        passed=exhaustion_detected,
        score=exhaustion_score // 4,
        reason=f"Exhaustion: {exhaustion_data.get('exhaustion_type', 'none')} ({exhaustion_score}%)"
    ))
    
    if exhaustion_detected:
        logger.info(f"   [50-VAL] exhaustion: ✓ {exhaustion_score} - {exhaustion_data.get('exhaustion_type')} ✓")
    
    # IMPULSE CHECK
    impulse_passed = impulse_pct >= 48
    if impulse_pct >= 80:
        impulse_score = 25
    elif impulse_pct >= 60:
        impulse_score = 20
    elif impulse_pct >= 48:
        impulse_score = 15
    else:
        impulse_score = 0
    
    result.layers.append(ValidationResult(
        layer_name="impulse",
        passed=impulse_passed,
        score=impulse_score,
        reason=f"{impulse_pct:.0f}%"
    ))
    logger.info(f"   [50-VAL] impulse: {'✓' if impulse_passed else '✗'} {impulse_score} - {impulse_pct:.0f}%" + (" ✓" if impulse_passed else " < 48%"))
    
    # STRUCTURE QUALITY
    clean_quality = avg_body_ratio * 100
    clean_passed = clean_quality >= 50
    clean_score = 20 if clean_quality >= 70 else 15 if clean_quality >= 55 else 10 if clean_quality >= 50 else 5
    
    result.layers.append(ValidationResult(
        layer_name="clean_impulse",
        passed=clean_passed,
        score=clean_score,
        reason=f"Quality: {clean_quality:.0f}%"
    ))
    logger.info(f"   [50-VAL] clean_impulse: {'✓' if clean_passed else '✗'} {clean_score} - Quality: {clean_quality:.0f}%")
    
    # PULLBACK STARTED
    pullback_layer = exhaustion_detected or pullback_started or retracement_pct >= 10
    if exhaustion_detected:
        pullback_score = 25
        pullback_reason = "Exhaustion triggered ✓"
    elif pullback_started or retracement_pct >= 15:
        pullback_score = 20
        pullback_reason = "Structure broken ✓"
    else:
        pullback_score = 5
        pullback_reason = "Waiting for break"
    
    result.layers.append(ValidationResult(
        layer_name="pullback_started",
        passed=pullback_layer,
        score=pullback_score,
        reason=pullback_reason
    ))
    logger.info(f"   [50-VAL] pullback_started: {'✓' if pullback_layer else '✗'} {pullback_score} - {pullback_reason}")
    
    # CONTROLLED PULLBACK
    recent_candles = candles[-10:] if len(candles) >= 10 else candles
    red_candles = sum(1 for c in recent_candles if float(c.get('c', 0) or 0) < float(c.get('o', 0) or 0))
    control_pct = (1 - (red_candles / len(recent_candles))) * 100
    controlled_passed = control_pct >= 40 or exhaustion_detected
    control_score = 20 if control_pct >= 70 else 15 if control_pct >= 50 else 10 if control_pct >= 40 else 5
    
    result.layers.append(ValidationResult(
        layer_name="controlled_pullback",
        passed=controlled_passed,
        score=control_score,
        reason=f"Control: {control_pct:.0f}%"
    ))
    logger.info(f"   [50-VAL] controlled_pullback: {'✓' if controlled_passed else '✗'} {control_score} - Control: {control_pct:.0f}%")
    
    # FLIP ZONE
    flip_zone_detected = False
    flip_zone_type = "none"
    if flip_zones:
        for fz in flip_zones:
            fz_level = fz.get('level', 0) if isinstance(fz, dict) else 0
            touches = fz.get('touches', 0) if isinstance(fz, dict) else 0
            if fib_50 > 0 and fz_level > 0:
                distance_pct = abs(fz_level - fib_50) / fib_50 * 100
                if distance_pct < 8:
                    flip_zone_detected = True
                    flip_zone_type = "multi_touch" if touches >= 2 else "single"
                    break
    
    fz_score = 25 if flip_zone_detected and flip_zone_type == "multi_touch" else 20 if flip_zone_detected else 10
    result.layers.append(ValidationResult(
        layer_name="flip_zone",
        passed=flip_zone_detected,
        score=fz_score,
        reason=f"FZ at 0.50 ({flip_zone_type})"
    ))
    logger.info(f"   [50-VAL] flip_zone: {'✓' if flip_zone_detected else '✗'} {fz_score} - FZ at 0.50 ({flip_zone_type})")
    
    # FINAL SCORE
    total_score = sum(layer.score for layer in result.layers)
    result.final_score = min(100, int((total_score / 115) * 100))
    
    hunter_valid = exhaustion_detected and impulse_passed and flip_zone_detected
    zone_valid = pullback_layer and impulse_passed and flip_zone_detected and controlled_passed
    result.is_valid = (hunter_valid or zone_valid) and result.final_score >= 55
    
    if result.final_score >= 90: result.final_grade = "A+"
    elif result.final_score >= 80: result.final_grade = "A"
    elif result.final_score >= 70: result.final_grade = "B+"
    elif result.final_score >= 60: result.final_grade = "B"
    else: result.final_grade = "C"
    
    if result.is_valid:
        if exhaustion_detected and retracement_pct < 25:
            result.stage = 1
            result.stage_name = "EXHAUSTION ALERT"
        elif retracement_pct < 40:
            result.stage = 2
            result.stage_name = "APPROACHING 50"
        else:
            result.stage = 3
            result.stage_name = "AT 50 ZONE"
    
    status = "✅ VALID" if result.is_valid else "❌ INVALID"
    mode = "[HUNTER]" if exhaustion_detected else "[ZONE]"
    logger.info(f"   [50-VAL] {symbol}: {status} {mode} Score={result.final_score} Grade={result.final_grade}")
    
    return result

def _build_structure(candles: List[Dict]) -> Dict:
    if not candles or len(candles) < 50:
        return {}
    try:
        highs = [float(c.get('h', 0) or 0) for c in candles if float(c.get('h', 0) or 0) > 0]
        lows = [float(c.get('l', 0) or 0) for c in candles if float(c.get('l', 0) or 0) > 0]
        closes = [float(c.get('c', 0) or 0) for c in candles if float(c.get('c', 0) or 0) > 0]
        
        swing_high = max(highs[-100:]) if len(highs) >= 100 else max(highs)
        swing_low = min(lows[-150:]) if len(lows) >= 150 else min(lows)
        current_price = closes[-1]
        
        swing_high_idx = len(candles) - 1
        for i, c in enumerate(candles):
            if float(c.get('h', 0) or 0) == swing_high:
                swing_high_idx = i
                break
        
        impulse_pct = ((swing_high - swing_low) / swing_low) * 100 if swing_low > 0 else 0
        range_size = swing_high - swing_low
        retracement_pct = ((swing_high - current_price) / range_size) * 100 if range_size > 0 else 0
        
        body_ratios = []
        for c in candles[-30:]:
            o, h, l, cl = float(c.get('o', 0) or 0), float(c.get('h', 0) or 0), float(c.get('l', 0) or 0), float(c.get('c', 0) or 0)
            candle_range = h - l if h > l else 0.0001
            body_ratios.append(abs(cl - o) / candle_range)
        avg_body_ratio = sum(body_ratios) / len(body_ratios) if body_ratios else 0.5
        
        return {
            'impulse_pct': impulse_pct,
            'retracement_pct': retracement_pct,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'swing_high_idx': swing_high_idx,
            'current_price': current_price,
            'avg_body_ratio': avg_body_ratio,
            'flip_zones': [],
            'ath_breakout': True
        }
    except:
        return {}
