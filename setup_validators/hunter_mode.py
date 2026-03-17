"""
HUNTER MODE - Early Alert Detection System

Core functions for detecting:
1. Expansion exhaustion (for 382/50 early alerts)
2. Fib level breaks with flip zone mapping (for 618/786 approach alerts)
3. Dynamic re-fib support

HUNTER MODE PRINCIPLE:
Alert on INTENT to pull back, not arrival at entry zone.
Give trader time to prepare limit orders.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def detect_expansion_exhaustion(candles: List[Dict], structure: Dict) -> Dict:
    """
    Detect first major rejection/exhaustion from expansion high.
    
    Signs of exhaustion:
    1. Long upper wick at/near swing high (rejection)
    2. Bearish candle after new high
    3. Volume spike at top (distribution)
    4. RSI divergence (lower high on RSI while price makes higher high)
    5. Failed breakout attempt (wick above, close below)
    
    Returns:
        {
            'exhaustion_detected': bool,
            'exhaustion_type': str,  # 'rejection_wick', 'bearish_reversal', 'volume_spike', 'rsi_divergence'
            'exhaustion_score': int,  # 0-100
            'candles_since_high': int,
            'pullback_started': bool
        }
    """
    result = {
        'exhaustion_detected': False,
        'exhaustion_type': None,
        'exhaustion_score': 0,
        'candles_since_high': 0,
        'pullback_started': False
    }
    
    if not candles or len(candles) < 10:
        return result
    
    try:
        swing_high = structure.get('swing_high', 0)
        swing_high_idx = structure.get('swing_high_idx', len(candles) - 1)
        current_price = structure.get('current_price', 0)
        rsi = structure.get('rsi', 50)
        
        if swing_high <= 0:
            return result
        
        # How many candles since the high?
        candles_since_high = len(candles) - 1 - swing_high_idx
        result['candles_since_high'] = candles_since_high
        
        # Get candles around the high
        high_candle_idx = min(swing_high_idx, len(candles) - 1)
        high_candle = candles[high_candle_idx]
        
        high_open = float(high_candle.get('o', 0) or 0)
        high_close = float(high_candle.get('c', 0) or 0)
        high_high = float(high_candle.get('h', 0) or 0)
        high_low = float(high_candle.get('l', 0) or 0)
        high_volume = float(high_candle.get('v', 0) or 0)
        
        body = abs(high_close - high_open)
        upper_wick = high_high - max(high_open, high_close)
        lower_wick = min(high_open, high_close) - high_low
        candle_range = high_high - high_low if high_high > high_low else 0.0001
        
        exhaustion_signals = []
        exhaustion_score = 0
        
        # ─────────────────────────────────────────────────
        # SIGNAL 1: Rejection wick (upper wick > body)
        # ─────────────────────────────────────────────────
        if candle_range > 0 and upper_wick > body * 1.5:
            exhaustion_signals.append('rejection_wick')
            exhaustion_score += 25
            
        # ─────────────────────────────────────────────────
        # SIGNAL 2: Bearish candle at high (close < open)
        # ─────────────────────────────────────────────────
        if high_close < high_open:
            exhaustion_signals.append('bearish_at_high')
            exhaustion_score += 20
            
        # ─────────────────────────────────────────────────
        # SIGNAL 3: Volume spike at top
        # ─────────────────────────────────────────────────
        if high_candle_idx >= 5:
            prior_volumes = [float(c.get('v', 0) or 0) for c in candles[high_candle_idx-5:high_candle_idx]]
            avg_prior_vol = sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0
            if avg_prior_vol > 0 and high_volume > avg_prior_vol * 2:
                exhaustion_signals.append('volume_spike')
                exhaustion_score += 20
                
        # ─────────────────────────────────────────────────
        # SIGNAL 4: Price now below high (pullback started)
        # ─────────────────────────────────────────────────
        if current_price < swing_high * 0.97:  # 3% below high
            result['pullback_started'] = True
            exhaustion_score += 15
            
        # ─────────────────────────────────────────────────
        # SIGNAL 5: RSI showing exhaustion (above 70 at high)
        # ─────────────────────────────────────────────────
        if rsi < 60 and structure.get('rsi_at_high', rsi) > 70:
            exhaustion_signals.append('rsi_divergence')
            exhaustion_score += 15
            
        # ─────────────────────────────────────────────────
        # SIGNAL 6: Multiple red candles after high
        # ─────────────────────────────────────────────────
        if candles_since_high >= 2 and high_candle_idx + 2 < len(candles):
            post_high_candles = candles[high_candle_idx+1:high_candle_idx+4]
            red_count = sum(1 for c in post_high_candles 
                          if float(c.get('c', 0) or 0) < float(c.get('o', 0) or 0))
            if red_count >= 2:
                exhaustion_signals.append('consecutive_red')
                exhaustion_score += 15
        
        # Determine if exhaustion is detected
        result['exhaustion_score'] = min(100, exhaustion_score)
        result['exhaustion_detected'] = exhaustion_score >= 40
        result['exhaustion_type'] = exhaustion_signals[0] if exhaustion_signals else None
        
        if result['exhaustion_detected']:
            logger.debug(f"   [HUNTER] Exhaustion detected: {exhaustion_signals}, score={exhaustion_score}")
        
    except Exception as e:
        logger.debug(f"   [HUNTER] Exhaustion detection error: {e}")
    
    return result


def check_fib_break_with_mapping(structure: Dict, break_fib: float, target_fib: float) -> Dict:
    """
    Check if price has broken below a fib level AND the flip zone aligns with target fib.
    
    Used for:
    - 618 alerts: break_fib=0.382, target_fib=0.618
    - 786 alerts: break_fib=0.50, target_fib=0.786
    
    Returns:
        {
            'fib_broken': bool,
            'flip_zone_aligned': bool,
            'approaching_target': bool,
            'ready_to_alert': bool
        }
    """
    result = {
        'fib_broken': False,
        'flip_zone_aligned': False,
        'approaching_target': False,
        'ready_to_alert': False
    }
    
    try:
        current_price = structure.get('current_price', 0)
        swing_high = structure.get('swing_high', 0)
        swing_low = structure.get('swing_low', 0)
        flip_zones = structure.get('flip_zones', [])
        fib_levels = structure.get('fib_levels', {})
        
        if swing_high <= swing_low or current_price <= 0:
            return result
        
        range_size = swing_high - swing_low
        
        # Calculate fib levels
        break_level = swing_high - (range_size * break_fib)
        target_level = swing_high - (range_size * target_fib)
        
        # Check if price has broken below the break fib
        result['fib_broken'] = current_price < break_level
        
        # Check if flip zone aligns with target fib (within 5%)
        tolerance = range_size * 0.05
        
        for fz in flip_zones:
            if isinstance(fz, dict):
                fz_level = fz.get('level', 0)
                if fz_level > 0 and abs(fz_level - target_level) <= tolerance:
                    result['flip_zone_aligned'] = True
                    break
        
        # Check if price is moving toward target (between break and target)
        if result['fib_broken'] and current_price > target_level:
            result['approaching_target'] = True
        
        # Ready to alert if all conditions met
        result['ready_to_alert'] = (
            result['fib_broken'] and 
            result['flip_zone_aligned'] and 
            result['approaching_target']
        )
        
        if result['ready_to_alert']:
            logger.debug(f"   [HUNTER] Fib break alert ready: broke {break_fib}, targeting {target_fib}")
            
    except Exception as e:
        logger.debug(f"   [HUNTER] Fib break check error: {e}")
    
    return result


def get_current_fib_alignment(structure: Dict) -> Dict:
    """
    Determine which fib level the flip zone currently aligns with.
    Used for dynamic re-fib and setup classification.
    
    Returns:
        {
            'aligned_fib': str,  # '382', '50', '618', '786', 'underfib', or None
            'flip_zone_level': float,
            'alignment_quality': float  # 0-1, how close the alignment is
        }
    """
    result = {
        'aligned_fib': None,
        'flip_zone_level': 0,
        'alignment_quality': 0
    }
    
    try:
        swing_high = structure.get('swing_high', 0)
        swing_low = structure.get('swing_low', 0)
        flip_zones = structure.get('flip_zones', [])
        
        if swing_high <= swing_low or not flip_zones:
            return result
        
        range_size = swing_high - swing_low
        
        # Fib levels and their names
        fib_map = {
            '382': swing_high - (range_size * 0.382),
            '50': swing_high - (range_size * 0.50),
            '618': swing_high - (range_size * 0.618),
            '786': swing_high - (range_size * 0.786)
        }
        
        # Find the primary flip zone (highest touch count or most recent)
        primary_fz = None
        for fz in flip_zones:
            if isinstance(fz, dict):
                if primary_fz is None or fz.get('touches', 0) > primary_fz.get('touches', 0):
                    primary_fz = fz
        
        if not primary_fz:
            return result
        
        fz_level = primary_fz.get('level', 0)
        result['flip_zone_level'] = fz_level
        
        # Check alignment with each fib level
        best_alignment = None
        best_quality = 0
        tolerance = range_size * 0.05  # 5% tolerance
        
        for fib_name, fib_level in fib_map.items():
            distance = abs(fz_level - fib_level)
            if distance <= tolerance:
                quality = 1 - (distance / tolerance)
                if quality > best_quality:
                    best_quality = quality
                    best_alignment = fib_name
        
        # Check for under-fib (zone is below nearest fib)
        if not best_alignment:
            for fib_name, fib_level in fib_map.items():
                if fz_level < fib_level - tolerance:
                    result['aligned_fib'] = 'underfib'
                    result['alignment_quality'] = 0.8
                    return result
        
        result['aligned_fib'] = best_alignment
        result['alignment_quality'] = best_quality
        
    except Exception as e:
        logger.debug(f"   [HUNTER] Fib alignment check error: {e}")
    
    return result


def should_allow_reclassification_alert(
    current_setup: str, 
    new_setup: str, 
    flip_zone_id: str,
    cooldown_tracker: Dict
) -> bool:
    """
    Check if a reclassification alert should be allowed.
    
    Valid reclassifications (same flip zone, expansion grew):
    382 → 50 → 618 → 786
    
    Returns True if alert should fire.
    """
    # Setup progression order
    progression = ['382', '50', '618', '786']
    
    try:
        current_idx = progression.index(current_setup) if current_setup in progression else -1
        new_idx = progression.index(new_setup) if new_setup in progression else -1
        
        # Valid if moving to deeper fib (higher index)
        if new_idx > current_idx:
            logger.info(f"   [HUNTER] Reclassification allowed: {current_setup} → {new_setup}")
            return True
            
    except ValueError:
        pass
    
    return False
