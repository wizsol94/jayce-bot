"""
786 + FLIP ZONE VALIDATOR (HUNTER MODE)

HUNTER MODE ALERT TIMING:
- Alert when price breaks BELOW 0.50
- AND flip zone aligns with 0.786
- AND price is moving toward the 0.786 + flip zone
- This is a loading/approach alert
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from setup_validators.hunter_mode import check_fib_break_with_mapping
except ImportError:
    check_fib_break_with_mapping = None

@dataclass
class ValidationLayer:
    layer_name: str
    passed: bool
    score: int
    reason: str
    weight: float = 1.0

@dataclass 
class ValidationResult:
    setup: str = "786"
    passed: bool = False
    final_score: int = 0
    final_grade: str = "C"
    layers: List[ValidationLayer] = field(default_factory=list)
    reasons_passed: List[str] = field(default_factory=list)
    reasons_failed: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    flashcard_type: str = "786"
    whale_conviction: bool = False
    alert_ready: bool = False
    stage: int = 0
    stage_label: str = ""
    hunter_mode: bool = True

def validate_786(candles: List[Dict], symbol: str, structure: Dict = None) -> ValidationResult:
    """Validate 786 + Flip Zone with HUNTER MODE."""
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
    
    passes_786_gate = structure.get('passes_786fz_gate', False)
    has_valid_breakout = structure.get('ath_breakout', False) or structure.get('major_high_break', False)
    
    if not passes_786_gate and not has_valid_breakout:
        result.reject_reason = "No valid breakout structure"
        logger.info(f"   [786-VAL] {symbol}: ❌ REJECTED - No valid breakout structure")
        return result
    
    range_size = swing_high - swing_low if swing_high > swing_low else 0
    fib_50 = swing_high - (range_size * 0.50)
    fib_786 = swing_high - (range_size * 0.786)
    
    # HUNTER MODE: Check if price broke 50 and approaching 786
    fib_break_data = {'fib_broken': False, 'flip_zone_aligned': False, 'ready_to_alert': False}
    if check_fib_break_with_mapping:
        fib_break_data = check_fib_break_with_mapping(structure, 0.50, 0.786)
    else:
        fib_break_data['fib_broken'] = current_price < fib_50
        for fz in flip_zones:
            fz_level = fz.get('level', 0) if isinstance(fz, dict) else 0
            if fz_level > 0 and abs(fz_level - fib_786) <= range_size * 0.05:
                fib_break_data['flip_zone_aligned'] = True
                break
        fib_break_data['approaching_target'] = fib_break_data['fib_broken'] and current_price > fib_786
        fib_break_data['ready_to_alert'] = fib_break_data['fib_broken'] and fib_break_data['flip_zone_aligned'] and fib_break_data['approaching_target']
    
    fib_broken = fib_break_data.get('fib_broken', False)
    flip_zone_aligned = fib_break_data.get('flip_zone_aligned', False)
    approaching = fib_break_data.get('approaching_target', False)
    hunter_ready = fib_break_data.get('ready_to_alert', False)
    
    # LAYER: Hunter Mode Approach
    result.layers.append(ValidationLayer(
        layer_name="hunter_approach",
        passed=hunter_ready,
        score=25 if hunter_ready else 10 if fib_broken else 0,
        reason=f"Broke 50: {'✓' if fib_broken else '✗'} | FZ at 786: {'✓' if flip_zone_aligned else '✗'} | Approaching: {'✓' if approaching else '✗'}",
        weight=1.5
    ))
    
    if hunter_ready:
        logger.info(f"   [786-VAL] hunter_approach: ✓ - Broke 50, approaching 786 with valid FZ ✓")
    
    # LAYER: Expansion (786 needs massive expansion >= 100%)
    expansion_passed = impulse_pct >= 100
    expansion_score = 25 if impulse_pct >= 200 else 20 if impulse_pct >= 150 else 15 if impulse_pct >= 100 else 5
    result.layers.append(ValidationLayer(
        layer_name="expansion",
        passed=expansion_passed,
        score=expansion_score,
        reason=f"Expansion {impulse_pct:.0f}% (need 100%)",
        weight=1.4
    ))
    
    # LAYER: Flip Zone at 786
    result.layers.append(ValidationLayer(
        layer_name="flip_zone",
        passed=flip_zone_aligned,
        score=20 if flip_zone_aligned else 0,
        reason=f"FZ aligned with 786: {'✓' if flip_zone_aligned else '✗'}",
        weight=1.4
    ))
    
    # LAYER: Retracement (Hunter Mode accepts early approach)
    if retracement_pct < 45:
        depth_passed = hunter_ready
        depth_score = 15 if hunter_ready else 5
        depth_reason = f"Early ({retracement_pct:.0f}%) - Hunter triggered"
    elif 45 <= retracement_pct < 62:
        depth_passed = True
        depth_score = 18
        depth_reason = f"Approaching 786 ({retracement_pct:.0f}%)"
    elif 62 <= retracement_pct <= 82:
        depth_passed = True
        depth_score = 20
        depth_reason = f"At 786 zone ({retracement_pct:.0f}%)"
    else:
        depth_passed = False
        depth_score = 0
        depth_reason = f"Below 786 ({retracement_pct:.0f}%)"
    
    result.layers.append(ValidationLayer(
        layer_name="pullback_depth",
        passed=depth_passed,
        score=depth_score,
        reason=depth_reason,
        weight=1.2
    ))
    
    # LAYER: Structure quality
    structure_passed = avg_body_ratio >= 0.45
    structure_score = 15 if avg_body_ratio >= 0.65 else 10 if avg_body_ratio >= 0.50 else 5
    result.layers.append(ValidationLayer(
        layer_name="structure",
        passed=structure_passed,
        score=structure_score,
        reason=f"Quality {avg_body_ratio:.0%}",
        weight=0.8
    ))
    
    # Whale (bonus)
    result.whale_conviction = whale_conviction
    whale_bonus = 5 if whale_conviction else 0
    
    # FINAL SCORE
    total_score = sum(layer.score * layer.weight for layer in result.layers) + whale_bonus
    result.final_score = min(100, int((total_score / 115) * 100))
    
    # Pass criteria
    hunter_valid = hunter_ready and expansion_passed
    zone_valid = depth_passed and flip_zone_aligned and expansion_passed
    result.passed = (hunter_valid or zone_valid) and result.final_score >= 65
    
    if result.final_score >= 90: result.final_grade = "A+"
    elif result.final_score >= 80: result.final_grade = "A"
    elif result.final_score >= 70: result.final_grade = "B+"
    elif result.final_score >= 60: result.final_grade = "B"
    else: result.final_grade = "C"
    
    result.alert_ready = result.passed
    
    if result.passed:
        if hunter_ready and retracement_pct < 60:
            result.stage = 1
            result.stage_label = "BROKE 50 - LOADING 786"
        elif retracement_pct < 72:
            result.stage = 2
            result.stage_label = "APPROACHING 786"
        else:
            result.stage = 3
            result.stage_label = "AT 786 ZONE"
    
    for layer in result.layers:
        if layer.passed:
            result.reasons_passed.append(layer.layer_name)
        else:
            result.reasons_failed.append(layer.layer_name)
    
    status = "✅ PASSED" if result.passed else "❌ REJECTED"
    mode = "[HUNTER]" if hunter_ready else "[ZONE]"
    logger.info(f"   [786-VAL] {symbol}: {status} {mode} Score={result.final_score} Grade={result.final_grade}")
    
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
