"""
UNDER-FIB FLIP ZONE VALIDATOR (HUNTER MODE)

HUNTER MODE ALERT TIMING:
- Alert when price breaks the fib level above
- AND begins moving toward the untouched flip zone below
- Zone is the DESTINATION, fib is the GATE

This is destination-based: price traveling toward known target.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

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
    destination_zone: float = 0

def validate_under_fib(candles: List[Dict], symbol: str, structure: Dict = None) -> ValidationResult:
    """Validate Under-Fib Flip Zone with HUNTER MODE."""
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
    
    # Calculate all fib levels
    fibs = {
        '382': swing_high - (range_size * 0.382),
        '50': swing_high - (range_size * 0.50),
        '618': swing_high - (range_size * 0.618),
        '786': swing_high - (range_size * 0.786)
    }
    
    # HUNTER MODE: Find fresh flip zone BELOW a fib level
    fresh_zone_below_fib = False
    gate_fib_name = None
    destination_zone_level = 0
    zone_touches = 0
    
    for fz in flip_zones:
        if not isinstance(fz, dict):
            continue
        fz_level = fz.get('level', 0)
        touches = fz.get('touches', 0)
        is_fresh = fz.get('fresh', True)
        
        if fz_level <= 0 or not is_fresh:
            continue
        
        # Check if zone is below any fib
        for fib_name, fib_level in fibs.items():
            if fz_level < fib_level - (range_size * 0.03):
                # Zone is below this fib
                # Check if price has broken this fib (approaching zone)
                if current_price < fib_level:
                    fresh_zone_below_fib = True
                    gate_fib_name = fib_name
                    destination_zone_level = fz_level
                    zone_touches = touches
                    break
        if fresh_zone_below_fib:
            break
    
    result.gate_fib = gate_fib_name or ""
    result.destination_zone = destination_zone_level
    
    # LAYER: Flip Zone Below Fib
    result.layers.append(ValidationLayer(
        layer_name="flip_zone",
        passed=fresh_zone_below_fib,
        score=25 if fresh_zone_below_fib else 0,
        reason=f"Fresh zone below {gate_fib_name}: {'✓' if fresh_zone_below_fib else '✗'}",
        weight=1.4
    ))
    
    # LAYER: Zone Freshness
    zone_fresh = fresh_zone_below_fib and zone_touches <= 2
    result.layers.append(ValidationLayer(
        layer_name="zone_freshness",
        passed=zone_fresh,
        score=25 if zone_fresh else 10 if fresh_zone_below_fib else 0,
        reason=f"Zone touches: {zone_touches} ({'fresh' if zone_fresh else 'tested'})",
        weight=1.5
    ))
    
    if zone_fresh:
        logger.info(f"   [UFIB-VAL] zone_freshness: ✓ - Fresh untouched zone below {gate_fib_name} ✓")
    
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
    
    # LAYER: Alert Timing (price broke fib gate)
    price_broke_gate = False
    approaching_zone = False
    if gate_fib_name and gate_fib_name in fibs:
        gate_level = fibs[gate_fib_name]
        price_broke_gate = current_price < gate_level
        approaching_zone = price_broke_gate and current_price > destination_zone_level
    
    alert_ready = price_broke_gate and approaching_zone and fresh_zone_below_fib
    result.layers.append(ValidationLayer(
        layer_name="alert_timing",
        passed=alert_ready,
        score=20 if alert_ready else 10 if price_broke_gate else 0,
        reason=f"Broke {gate_fib_name}: {'✓' if price_broke_gate else '✗'} | Approaching zone: {'✓' if approaching_zone else '✗'}",
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
    
    # Pass criteria: Fresh zone + broke gate + expansion + approaching
    critical_passed = fresh_zone_below_fib and zone_fresh and expansion_passed and alert_ready
    result.passed = critical_passed and result.final_score >= 60
    
    if result.final_score >= 90: result.final_grade = "A+"
    elif result.final_score >= 80: result.final_grade = "A"
    elif result.final_score >= 70: result.final_grade = "B+"
    elif result.final_score >= 60: result.final_grade = "B"
    else: result.final_grade = "C"
    
    result.alert_ready = result.passed
    
    if result.passed:
        result.stage = 1
        result.stage_label = f"BROKE {gate_fib_name} - TARGETING ZONE"
    
    for layer in result.layers:
        if layer.passed:
            result.reasons_passed.append(layer.layer_name)
        else:
            result.reasons_failed.append(layer.layer_name)
    
    status = "✅ PASSED" if result.passed else "❌ REJECTED"
    logger.info(f"   [UFIB-VAL] {symbol}: {status} [HUNTER] Score={result.final_score} Grade={result.final_grade} Gate={gate_fib_name}")
    
    return result

def _compute_basic_structure(candles: List[Dict]) -> Dict:
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
