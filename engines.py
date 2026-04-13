"""
WIZTHEORY DETECTION ENGINES v4.0
================================
5 calibrated fib + flip zone engines for Jayce Scanner.
All parameters locked from 50-chart calibration.

Engines:
- .382 + Flip Zone (30-40% retracement)
- .50 + Flip Zone (40-55% retracement)
- .618 + Flip Zone (50-65% retracement)
- .786 + Flip Zone (70-80% retracement)
- Under-Fib Flip Zone (80-100% retracement)
"""

import os
import logging
from flashcard_analysis import analyze_flashcard_similarity, apply_grade_boost, format_flashcard_note
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — LOCKED FROM CALIBRATION
# ══════════════════════════════════════════════════════════════════════════════

STRICT_MODE = os.getenv('STRICT_MODE', 'true').lower() == 'true'

ENGINE_PARAMS = {
    '382': {
        'name': '382 + Flip Zone',
        'retracement_min': 30,
        'retracement_max': 40,
        'impulse_min': 30,
        'entry_buffer_min': 3,
        'entry_buffer_max': 6,
        'invalidation_fib': 0.50,
        'cooldown_hours': 4,
        'whale_required': False,
        'grade_threshold': 70,
        'description': 'Aggressive continuation. Structure rules everything.',
    },
    '50': {
        'name': '50 + Flip Zone',
        'retracement_min': 40,
        'retracement_max': 55,
        'impulse_min': 50,
        'entry_buffer_min': 4,
        'entry_buffer_max': 7,
        'invalidation_fib': 0.618,
        'cooldown_hours': 6,
        'whale_required': False,
        'grade_threshold': 70,
        'description': 'Balanced accumulation. The "half-back" zone.',
    },
    '618': {
        'name': '618 + Flip Zone',
        'retracement_min': 50,
        'retracement_max': 65,
        'impulse_min': 60,
        'entry_buffer_min': 5,
        'entry_buffer_max': 7,
        'invalidation_fib': 0.786,
        'cooldown_hours': 6,
        'whale_required': False,  # NEVER required per WizTheory rules
        'grade_threshold': 70,
        'description': 'Golden ratio. Where value meets conviction.',
    },
    '786': {
        'name': '786 + Flip Zone',
        'retracement_min': 70,
        'retracement_max': 80,
        'impulse_min': 100,
        'entry_buffer_min': 6,
        'entry_buffer_max': 9,
        'invalidation_fib': 0.786,
        'cooldown_hours': 8,
        'whale_required': False,  # NEVER required per WizTheory rules
        'grade_threshold': 75,
        'description': 'Final defense. Maximum pain = maximum R:R.',
    },
    'underfib': {
        'name': 'Under-Fib Flip Zone',
        'retracement_min': 55,  # Only 618/786 territory (removed under-382/under-50)
        'retracement_max': 85,
        'impulse_min': 60,
        'entry_buffer_min': 5,
        'entry_buffer_max': 9,
        'invalidation_fib': 0.90,  # Below flip zone
        'cooldown_hours': 6,
        'whale_required': False,  # Preferred but not required
        'grade_threshold': 70,
        'description': 'Flip zone below fib level. Price breaks fib to reach zone.',
    },
}

# Apply strict mode multipliers
if STRICT_MODE:
    for e in ENGINE_PARAMS.values():
        e['impulse_min'] = int(e['impulse_min'] * 1.2)
        e['grade_threshold'] = min(e['grade_threshold'] + 5, 90)


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE COOLDOWNS — Per-token, per-engine tracking
# ══════════════════════════════════════════════════════════════════════════════

ENGINE_COOLDOWNS: Dict[str, datetime] = {}


def get_cooldown_key(token_address: str, engine_id: str) -> str:
    # Use token-only cooldown to allow setup evolution (382 → 618 → 786)
    # Per WizTheory: These are ONE evolving structure, not separate setups
    return f"{token_address}:STRUCTURE"


def is_engine_on_cooldown(token_address: str, engine_id: str) -> bool:
    """Check if token structure is on cooldown (allows setup evolution)."""
    key = get_cooldown_key(token_address, engine_id)
    if key not in ENGINE_COOLDOWNS:
        return False
    
    # Use a single cooldown for structure (not per-engine)
    # This allows 382 → 618 → 786 evolution without spam
    cooldown_hours = 4  # Single cooldown period for all setup types
    cooldown_end = ENGINE_COOLDOWNS[key] + timedelta(hours=cooldown_hours)
    
    if datetime.now() < cooldown_end:
        return True
    
    # Expired
    del ENGINE_COOLDOWNS[key]
    return False


def set_engine_cooldown(token_address: str, engine_id: str):
    """Set cooldown for token structure (allows setup evolution)."""
    key = get_cooldown_key(token_address, engine_id)
    ENGINE_COOLDOWNS[key] = datetime.now()


def cleanup_engine_cooldowns():
    """Remove expired cooldowns."""
    now = datetime.now()
    max_cooldown = timedelta(hours=24)
    expired = [k for k, v in ENGINE_COOLDOWNS.items() if now - v > max_cooldown]
    for key in expired:
        del ENGINE_COOLDOWNS[key]
    if expired:
        logger.info(f"🧹 Cleaned {len(expired)} expired engine cooldowns")


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURE ANALYSIS — Core detection logic
# ══════════════════════════════════════════════════════════════════════════════

def calculate_fib_levels(low: float, high: float) -> Dict[str, float]:
    """Calculate fibonacci retracement levels."""
    if high <= low:
        return {}
    range_size = high - low
    return {
        '0': high,
        '236': high - (range_size * 0.236),
        '382': high - (range_size * 0.382),
        '50': high - (range_size * 0.50),
        '618': high - (range_size * 0.618),
        '786': high - (range_size * 0.786),
        '886': high - (range_size * 0.886),
        '100': low,
    }


def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculate RSI from close prices."""
    if len(closes) < period + 1:
        return 50.0  # Neutral default
    
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = changes[-period:]
    
    gains = [c if c > 0 else 0 for c in recent]
    losses = [-c if c < 0 else 0 for c in recent]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def detect_flip_zones(candles: List[dict], fib_levels: Dict[str, float]) -> List[dict]:
    """
    Detect flip zones — areas where price broke through resistance
    and is now testing as support.
    """
    flip_zones = []
    
    if len(candles) < 10:
        return flip_zones
    
    # Get price range
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    total_range = max(highs) - min(lows)
    
    if total_range <= 0:
        return flip_zones
    
    zone_size = total_range * 0.03  # 3% zones
    
    # Check each fib level for flip zone characteristics
    for fib_name, fib_price in fib_levels.items():
        if fib_name in ['0', '100']:
            continue
        
        # Count touches near this level
        touches = 0
        rejections = 0
        
        for i, c in enumerate(candles):
            # Check if price touched this zone
            zone_top = fib_price + zone_size
            zone_bot = fib_price - zone_size
            
            if c['l'] <= zone_top and c['h'] >= zone_bot:
                touches += 1
                
                # Check for rejection (wick into zone, close outside)
                if c['l'] < zone_bot and c['c'] > zone_bot:
                    rejections += 1
                elif c['h'] > zone_top and c['c'] < zone_top:
                    rejections += 1
        
        if touches >= 2:
            flip_zones.append({
                'fib_level': fib_name,
                'level': fib_price,  # FIXED: was 'price', validators expect 'level'
                'price': fib_price,  # Keep for backwards compat
                'zone_top': fib_price + zone_size,
                'zone_bottom': fib_price - zone_size,  # FIXED: was 'zone_bot'
                'zone_bot': fib_price - zone_size,  # Keep for backwards compat
                'touches': touches,
                'rejections': rejections,
                'fresh': True,  # Added: validators check this
            })
    
    return flip_zones


def analyze_structure(candles: List[dict]) -> Optional[dict]:
    """
    Analyze candle data to extract structure metrics.
    Returns swing points, fib levels, retracement %, impulse %, etc.
    """
    if not candles or len(candles) < 10:
        return None
    
    # Extract OHLCV
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    closes = [c['c'] for c in candles]
    opens = [c['o'] for c in candles]
    volumes = [c['v'] for c in candles if c.get('v', 0) > 0]
    
    # Find swing points
    swing_high = max(highs)
    swing_high_idx = highs.index(swing_high)
    swing_low = min(lows)
    swing_low_idx = lows.index(swing_low)
    
    current_price = closes[-1]
    
    if swing_high <= swing_low:
        return None
    
    # Determine impulse direction (we want UP impulse, then pullback)
    # Swing low should come BEFORE swing high for valid setup
    if swing_low_idx > swing_high_idx:
        # This is a downtrend structure, not what we want
        # But check if there's a mini-impulse after the low
        recent_high = max(highs[swing_low_idx:]) if swing_low_idx < len(highs) - 1 else swing_high
        if recent_high > swing_low * 1.1:  # At least 10% bounce
            swing_high = recent_high
            swing_high_idx = highs.index(recent_high)
        else:
            return None
    
    # Calculate impulse
    impulse_range = swing_high - swing_low
    impulse_pct = (impulse_range / swing_low) * 100 if swing_low > 0 else 0
    
    # Calculate retracement from high
    pullback = swing_high - current_price
    retracement_pct = (pullback / impulse_range) * 100 if impulse_range > 0 else 0
    
    # Ensure retracement is positive (price below high)
    if retracement_pct < 0:
        retracement_pct = 0
    
    # Fib levels
    fib_levels = calculate_fib_levels(swing_low, swing_high)
    
    # Flip zones
    flip_zones = detect_flip_zones(candles, fib_levels)
    
    # Volume metrics
    if len(volumes) >= 4:
        avg_volume = sum(volumes) / len(volumes)
        recent_volume = volumes[-1] if volumes else 0
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Volume trend
        first_half = sum(volumes[:len(volumes)//2]) / max(1, len(volumes)//2)
        second_half = sum(volumes[len(volumes)//2:]) / max(1, len(volumes) - len(volumes)//2)
        volume_expanding = second_half > first_half * 1.1
        volume_contracting = second_half < first_half * 0.9
    else:
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        recent_volume = volumes[-1] if volumes else 0
        volume_ratio = 1.0
        volume_expanding = False
        volume_contracting = False
    
    # RSI
    rsi = calculate_rsi(closes)
    
    # RSI divergence check (price lower low, RSI higher low)
    rsi_divergence = False
    if len(closes) >= 20:
        # Compare last 10 candles RSI trend vs price trend
        early_rsi = calculate_rsi(closes[:-10])
        late_rsi = rsi
        early_low = min(lows[:-10]) if len(lows) > 10 else swing_low
        late_low = min(lows[-10:])
        
        # Bullish divergence: price made lower low but RSI made higher low
        if late_low < early_low and late_rsi > early_rsi:
            rsi_divergence = True
    
    # Candle quality metrics
    green_candles = sum(1 for c in candles if c['c'] > c['o'])
    red_candles = len(candles) - green_candles
    
    # Body to range ratio (clean vs choppy)
    body_ratios = []
    for c in candles:
        candle_range = c['h'] - c['l']
        if candle_range > 0:
            body = abs(c['c'] - c['o'])
            body_ratios.append(body / candle_range)
    avg_body_ratio = sum(body_ratios) / len(body_ratios) if body_ratios else 0.5
    
    return {
        'swing_high': swing_high,
        'swing_high_idx': swing_high_idx,
        'swing_low': swing_low,
        'swing_low_idx': swing_low_idx,
        'current_price': current_price,
        'impulse_range': impulse_range,
        'impulse_pct': impulse_pct,
        'retracement_pct': retracement_pct,
        'fib_levels': fib_levels,
        'flip_zones': flip_zones,
        'avg_volume': avg_volume,
        'recent_volume': recent_volume,
        'volume_ratio': volume_ratio,
        'volume_expanding': volume_expanding,
        'volume_contracting': volume_contracting,
        'rsi': rsi,
        'rsi_divergence': rsi_divergence,
        'green_candles': green_candles,
        'red_candles': red_candles,
        'avg_body_ratio': avg_body_ratio,
        'candle_count': len(candles),
    }


# ══════════════════════════════════════════════════════════════════════════════
# WHALE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def check_whale_activity(token: dict, structure: dict) -> bool:
    """
    Check for whale activity signals.
    Based on volume patterns and market cap ratios.
    """
    # High volume relative to market cap
    mc = token.get('market_cap', 0) or token.get('fdv', 0)
    vol = token.get('volume_24h', 0)
    
    if mc > 0 and vol > 0:
        vol_to_mc = vol / mc
        if vol_to_mc > 0.3:  # >30% of MC traded in 24h
            logger.debug(f"🐋 Whale signal: Vol/MC ratio = {vol_to_mc:.2f}")
            return True
    
    # High volume ratio in current structure
    if structure and structure.get('volume_ratio', 0) > 2.0:
        logger.debug(f"🐋 Whale signal: Volume ratio = {structure['volume_ratio']:.2f}")
        return True
    
    # Volume expanding during pullback (accumulation)
    if structure and structure.get('volume_expanding') and structure.get('rsi', 50) < 40:
        logger.debug("🐋 Whale signal: Volume expanding on pullback with low RSI")
        return True
    
    return False


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE SCORING
# ══════════════════════════════════════════════════════════════════════════════

def calculate_engine_score(engine_id: str, structure: dict, has_whale: bool) -> int:
    """
    Calculate confidence score for engine detection.
    Score range: 0-100
    """
    score = 50  # Base score
    params = ENGINE_PARAMS.get(engine_id, {})
    
    # ─────────────────────────────────────────────────
    # IMPULSE QUALITY (+0 to +15)
    # ─────────────────────────────────────────────────
    impulse_pct = structure.get('impulse_pct', 0)
    if impulse_pct >= 150:
        score += 15
    elif impulse_pct >= 100:
        score += 12
    elif impulse_pct >= 70:
        score += 8
    elif impulse_pct >= 50:
        score += 5
    
    # ─────────────────────────────────────────────────
    # VOLUME QUALITY (+0 to +10)
    # ─────────────────────────────────────────────────
    if structure.get('volume_expanding'):
        score += 10
    elif structure.get('volume_ratio', 1) >= 1.5:
        score += 7
    elif structure.get('volume_ratio', 1) >= 1.2:
        score += 4
    
    # ─────────────────────────────────────────────────
    # RSI STATE (+0 to +10)
    # ─────────────────────────────────────────────────
    rsi = structure.get('rsi', 50)
    if rsi < 25:
        score += 10  # Deeply oversold
    elif rsi < 35:
        score += 7
    elif rsi < 45:
        score += 4
    
    # ─────────────────────────────────────────────────
    # RSI DIVERGENCE (+10)
    # ─────────────────────────────────────────────────
    if structure.get('rsi_divergence'):
        score += 10
    
    # ─────────────────────────────────────────────────
    # WHALE ACTIVITY (+10)
    # ─────────────────────────────────────────────────
    if has_whale:
        score += 10
    
    # ─────────────────────────────────────────────────
    # FLIP ZONE QUALITY (+0 to +10)
    # ─────────────────────────────────────────────────
    flip_zones = structure.get('flip_zones', [])
    if flip_zones:
        best_zone = max(flip_zones, key=lambda z: z.get('rejections', 0))
        rejections = best_zone.get('rejections', 0)
        if rejections >= 5:
            score += 10
        elif rejections >= 3:
            score += 7
        elif rejections >= 2:
            score += 4
    
    # ─────────────────────────────────────────────────
    # STRUCTURE QUALITY (+0 to +5)
    # ─────────────────────────────────────────────────
    body_ratio = structure.get('avg_body_ratio', 0.5)
    if body_ratio >= 0.6:  # Clean candles
        score += 5
    elif body_ratio >= 0.4:
        score += 2
    
    # ─────────────────────────────────────────────────
    # ENGINE-SPECIFIC BONUSES
    # ─────────────────────────────────────────────────
    ret_pct = structure.get('retracement_pct', 0)
    
    if engine_id == '382':
        # Speed bonus for .382 (fast pullback)
        if structure.get('volume_expanding'):
            score += 3
    
    elif engine_id == '50':
        # Balanced pullback bonus
        if structure.get('volume_contracting'):
            score += 3
    
    elif engine_id == '618':
        # Golden ratio precision bonus
        if 60 <= ret_pct <= 65:
            score += 5
        # Extra points for confluence
        if has_whale and structure.get('rsi_divergence'):
            score += 3
    
    elif engine_id == '786':
        # Violent mode detection
        if structure.get('volume_contracting') and rsi < 30:
            score += 8  # Compression before expansion
            logger.info("🔥 .786 VIOLENT MODE detected")
    
    elif engine_id == 'underfib':
        # Micro accumulation bonus
        if structure.get('volume_contracting') and rsi > 25:
            score += 5
        # Recovery signal
        if rsi > 35 and structure.get('rsi_divergence'):
            score += 5
    
    return min(score, 100)


def score_to_grade(score: int) -> str:
    """Convert score to letter grade."""
    if score >= 85:
        return 'A+'
    elif score >= 75:
        return 'A'
    elif score >= 65:
        return 'B'
    elif score >= 55:
        return 'C'
    else:
        return 'D'


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE DETECTION
# ══════════════════════════════════════════════════════════════════════════════


def determine_setup_by_body_acceptance(candles: List[dict], structure: dict) -> dict:
    """
    Determine the real tradeable setup type by analyzing where candle BODIES are accepting.
    
    KEY RULE: "Setup type = which fib zone the flip zone MOSTLY OCCUPIES"
    
    1. Detect flip zone as a RANGE (not single price) where bodies are accepting
    2. Map that range against fib levels (382 / 50 / 618 / 786)
    3. Classify by which fib zone contains the majority of acceptance
    
    Retrace % is informational only, NOT the classifier.
    """
    result = {
        'recommended_setup': None,
        'flip_zone_range': None,
        'fib_overlaps': {},
        'confidence': 0,
        'reason': 'No flip zone detected',
        'debug': []
    }
    
    if not candles or len(candles) < 20:
        return result
    
    # Get swing high/low from structure (wick-based, per master fib rules)
    swing_high = structure.get('swing_high', 0)
    swing_low = structure.get('swing_low', 0)
    fib_range = swing_high - swing_low
    
    if fib_range <= 0 or swing_low <= 0:
        return result
    
    # Calculate fib levels (wick-based)
    fib_levels = {
        '382': swing_high - (fib_range * 0.382),
        '50': swing_high - (fib_range * 0.50),
        '618': swing_high - (fib_range * 0.618),
        '786': swing_high - (fib_range * 0.786),
    }
    
    # Define fib ZONES (each fib level has a range around it)
    # These ranges define where each setup "owns" the price action
    fib_zones = {
        '382': (swing_high - (fib_range * 0.45), swing_high - (fib_range * 0.30)),  # 30-45%
        '50': (swing_high - (fib_range * 0.58), swing_high - (fib_range * 0.42)),   # 42-58%
        '618': (swing_high - (fib_range * 0.70), swing_high - (fib_range * 0.55)),  # 55-70%
        '786': (swing_high - (fib_range * 0.85), swing_high - (fib_range * 0.70)),  # 70-85%
    }
    
    result['debug'].append(f"Swing: low={swing_low:.8f} high={swing_high:.8f} range={fib_range:.8f}")
    for fib_name, fib_price in fib_levels.items():
        zone = fib_zones[fib_name]
        result['debug'].append(f"Fib {fib_name}: {fib_price:.8f} (zone: {zone[1]:.8f} - {zone[0]:.8f})")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Detect Flip Zone as a RANGE where bodies are accepting
    # ═══════════════════════════════════════════════════════════════════
    recent = candles[-40:]  # Look at recent retrace candles
    
    # Collect all body close prices in the retrace zone
    body_closes = []
    body_ranges = []  # (body_low, body_high) for each candle
    
    for c in recent:
        o = float(c.get('open') or c.get('o') or 0)
        h = float(c.get('high') or c.get('h') or 0)
        l = float(c.get('low') or c.get('l') or 0)
        close = float(c.get('close') or c.get('c') or 0)
        
        if close <= 0:
            continue
        
        body_low = min(o, close)
        body_high = max(o, close)
        
        # Only include candles that are in the retrace zone (below swing high)
        if close < swing_high:
            body_closes.append(close)
            body_ranges.append((body_low, body_high))
    
    if len(body_closes) < 5:
        result['reason'] = 'Not enough retrace candles'
        return result
    
    # Find the flip zone range: where most body closes are clustering
    # Use percentiles to find the acceptance band
    body_closes_sorted = sorted(body_closes)
    
    # Flip zone = 25th to 75th percentile of body closes (middle 50%)
    p25_idx = int(len(body_closes_sorted) * 0.25)
    p75_idx = int(len(body_closes_sorted) * 0.75)
    
    flip_zone_low = body_closes_sorted[p25_idx]
    flip_zone_high = body_closes_sorted[p75_idx]
    
    # Expand slightly to capture the full acceptance band
    flip_zone_buffer = (flip_zone_high - flip_zone_low) * 0.15
    flip_zone_low -= flip_zone_buffer
    flip_zone_high += flip_zone_buffer
    
    result['flip_zone_range'] = (flip_zone_low, flip_zone_high)
    result['debug'].append(f"Flip Zone Range: {flip_zone_low:.8f} - {flip_zone_high:.8f}")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Calculate overlap of flip zone with each fib zone
    # ═══════════════════════════════════════════════════════════════════
    
    def calculate_overlap(range1, range2):
        """Calculate overlap percentage between two ranges."""
        overlap_low = max(range1[0], range2[0])
        overlap_high = min(range1[1], range2[1])
        
        if overlap_high <= overlap_low:
            return 0.0  # No overlap
        
        overlap_size = overlap_high - overlap_low
        range1_size = range1[1] - range1[0]
        
        if range1_size <= 0:
            return 0.0
        
        return (overlap_size / range1_size) * 100
    
    flip_zone = (flip_zone_low, flip_zone_high)
    
    for fib_name, fib_zone in fib_zones.items():
        # fib_zone is (lower_price, upper_price) but we need (low, high) order
        fib_zone_ordered = (min(fib_zone), max(fib_zone))
        overlap_pct = calculate_overlap(flip_zone, fib_zone_ordered)
        
        result['fib_overlaps'][fib_name] = {
            'overlap_pct': round(overlap_pct, 1),
            'fib_zone': fib_zone_ordered,
            'fib_level': fib_levels[fib_name]
        }
        
        result['debug'].append(f"Overlap with {fib_name}: {overlap_pct:.1f}%")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Classify by which fib zone has the MOST overlap
    # ═══════════════════════════════════════════════════════════════════
    
    best_overlap = 0
    best_setup = None
    
    for fib_name, data in result['fib_overlaps'].items():
        if data['overlap_pct'] > best_overlap:
            best_overlap = data['overlap_pct']
            best_setup = fib_name
    
    if best_setup and best_overlap >= 20:  # At least 20% overlap required
        result['recommended_setup'] = best_setup
        result['confidence'] = min(100, int(best_overlap))
        result['reason'] = f"Flip zone ({flip_zone_low:.8f} - {flip_zone_high:.8f}) has {best_overlap:.0f}% overlap with {best_setup} zone"
        
        # Find runner-up
        overlaps_sorted = sorted(result['fib_overlaps'].items(), key=lambda x: x[1]['overlap_pct'], reverse=True)
        if len(overlaps_sorted) > 1 and overlaps_sorted[1][1]['overlap_pct'] > 0:
            result['runner_up'] = {
                'zone': overlaps_sorted[1][0],
                'overlap': overlaps_sorted[1][1]['overlap_pct']
            }
    else:
        result['reason'] = f"No significant fib zone overlap (best: {best_setup} at {best_overlap:.0f}%)"
    
    return result




# ══════════════════════════════════════════════════════════════════════════════
# BREAKOUT ELIGIBILITY CHECK
# Ensures we only run validators on charts that have CONFIRMED breakout + expansion
# ══════════════════════════════════════════════════════════════════════════════

def check_breakout_eligibility(candles: List[dict], symbol: str) -> dict:
    """
    Check if chart has a CONFIRMED breakout that already happened.
    
    KEY INSIGHT: We're looking for setups where:
    1. There WAS a resistance level
    2. Price BROKE above it (in the past)
    3. Price EXPANDED beyond the breakout
    4. Price is NOW retracing back toward flip zone (this is the ENTRY opportunity)
    
    We do NOT require current price to be above ATH - that would miss all retrace entries!
    """
    logger.info(f"   [BREAKOUT] {symbol}: Checking breakout eligibility ({len(candles) if candles else 0} candles)")
    
    result = {
        'eligible': False,
        'reason': 'Unknown',
        'breakout_high': 0,
        'resistance_level': 0,
        'expansion_pct': 0,
        'closes_above': 0
    }
    
    if not candles or len(candles) < 30:
        result['reason'] = 'Not enough candles'
        return result
    
    # Use last 100 candles for analysis
    lookback = min(100, len(candles))
    recent = candles[-lookback:]
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: Find the ATH (highest high in the data)
    # This is the EXPANSION HIGH - the peak of the impulse move
    # ══════════════════════════════════════════════════════════════════════
    ath_price = 0
    ath_idx = 0
    
    for i in range(len(recent)):
        h = float(recent[i].get('h') or recent[i].get('high') or 0)
        if h > ath_price:
            ath_price = h
            ath_idx = i
    
    if ath_price == 0:
        result['reason'] = 'No ATH found'
        return result
    
    result['breakout_high'] = ath_price
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: Find the resistance that was BROKEN before the ATH
    # Look for the highest high BEFORE the ATH that was then exceeded
    # ══════════════════════════════════════════════════════════════════════
    
    # Need at least 5 candles before ATH to identify resistance
    if ath_idx < 5:
        result['reason'] = 'ATH too early in data - no prior resistance visible'
        return result
    
    # Find highest high before the ATH (this is the resistance that was broken)
    resistance_high = 0
    resistance_idx = 0
    
    for i in range(0, ath_idx):
        h = float(recent[i].get('h') or recent[i].get('high') or 0)
        if h > resistance_high:
            resistance_high = h
            resistance_idx = i
    
    if resistance_high == 0:
        result['reason'] = 'No resistance found before ATH'
        return result
    
    result['resistance_level'] = resistance_high
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 3: Verify the breakout - ATH must be meaningfully above resistance
    # ══════════════════════════════════════════════════════════════════════
    
    expansion_pct = ((ath_price - resistance_high) / resistance_high) * 100 if resistance_high > 0 else 0
    result['expansion_pct'] = expansion_pct
    
    # Require at least 15% expansion beyond the resistance
    MIN_EXPANSION = 15
    if expansion_pct < MIN_EXPANSION:
        result['reason'] = f'Expansion only {expansion_pct:.1f}% above resistance (need {MIN_EXPANSION}%)'
        logger.info(f"   [BREAKOUT] {symbol}: ❌ {result['reason']}")
        return result
    
    logger.info(f"   [BREAKOUT] {symbol}: ✓ Expanded {expansion_pct:.1f}% above prior resistance")
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 4: Count candles that closed above the old resistance
    # This confirms the breakout was real, not just a wick
    # ══════════════════════════════════════════════════════════════════════
    
    breakout_candles = 0
    
    for i in range(resistance_idx + 1, len(recent)):
        o = float(recent[i].get('o') or recent[i].get('open') or 0)
        c = float(recent[i].get('c') or recent[i].get('close') or 0)
        body_bottom = min(o, c)
        
        # Body closed above resistance zone (within 2%)
        if body_bottom > resistance_high * 0.98:
            breakout_candles += 1
    
    result['closes_above'] = breakout_candles
    
    # Require at least 2 candles with bodies above resistance
    MIN_BREAKOUT_CLOSES = 2
    if breakout_candles < MIN_BREAKOUT_CLOSES:
        result['reason'] = f'Only {breakout_candles} closes above resistance (need {MIN_BREAKOUT_CLOSES})'
        logger.info(f"   [BREAKOUT] {symbol}: ❌ {result['reason']}")
        return result
    
    logger.info(f"   [BREAKOUT] {symbol}: ✓ {breakout_candles} candles closed above resistance")
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 5: Check freshness - reject if ATH is too old AND price dumped
    # ══════════════════════════════════════════════════════════════════════
    
    current_price = float(recent[-1].get('c') or recent[-1].get('close') or 0)
    candles_since_ath = len(recent) - 1 - ath_idx
    pct_below_ath = ((ath_price - current_price) / ath_price) * 100 if ath_price > 0 else 0
    
    # Stale breakout check: ATH is old AND price crashed
    STALE_AGE = 40  # candles
    STALE_DUMP = 60  # percent below ATH
    
    if candles_since_ath > STALE_AGE and pct_below_ath > STALE_DUMP:
        result['reason'] = f'Stale breakout: ATH {candles_since_ath} candles ago, price {pct_below_ath:.0f}% below'
        logger.info(f"   [BREAKOUT] {symbol}: ❌ {result['reason']}")
        return result
    
    # ══════════════════════════════════════════════════════════════════════
    # BREAKOUT CONFIRMED - Chart is eligible for setup classification
    # ══════════════════════════════════════════════════════════════════════
    result['eligible'] = True
    result['reason'] = f'Breakout confirmed: {expansion_pct:.0f}% expansion, {breakout_candles} closes above'
    
    logger.info(f"   [BREAKOUT] {symbol}: ✅ ELIGIBLE for setup classification")
    logger.info(f"   [BREAKOUT]    Prior resistance: {resistance_high:.10f}")
    logger.info(f"   [BREAKOUT]    Breakout ATH: {ath_price:.10f}")
    logger.info(f"   [BREAKOUT]    Expansion: {expansion_pct:.1f}%")
    logger.info(f"   [BREAKOUT]    Closes above: {breakout_candles}")
    logger.info(f"   [BREAKOUT]    Current: {pct_below_ath:.1f}% below ATH ({candles_since_ath} candles ago)")
    
    return result



def run_detection(token: dict, candles: List[dict]) -> Optional[dict]:
    """
    Run all 5 WizTheory engines on the token.
    Returns the best matching engine result or None.
    
    This is the main entry point — call this from scanner.py
    """
    symbol = token.get('symbol', '???')
    address = token.get('address', '')
    
    # Analyze structure
    structure = analyze_structure(candles)
    if not structure:
        logger.debug(f"❌ {symbol}: Could not analyze structure")
        return None
    
    # Add gate info from hybrid intake to structure
    structure['passes_382fz_gate'] = token.get('passes_382fz_gate', False)
    structure['passes_618fz_gate'] = token.get('passes_618fz_gate', False)
    structure['passes_786fz_gate'] = token.get('passes_786fz_gate', False)
    structure['passes_underfib_gate'] = token.get('passes_underfib_gate', False)
    structure['passes_50fz_gate'] = token.get('passes_50fz_gate', False)
    structure['ath_breakout'] = token.get('ath_breakout', False)
    structure['major_high_break'] = token.get('major_high_break', False)
    
    ret_pct = structure['retracement_pct']
    impulse_pct = structure['impulse_pct']
    current_price = structure['current_price']
    fib_levels = structure['fib_levels']
    
    logger.info(f"📊 {symbol}: Impulse={impulse_pct:.0f}% Retrace={ret_pct:.0f}% RSI={structure['rsi']:.0f}")
    
    # Check whale activity
    has_whale = check_whale_activity(token, structure)
    if has_whale:
        logger.info(f"🐋 {symbol}: Whale activity detected")
    
    # ═══════════════════════════════════════════════════════════════════
    # PRE-ROUTING: Body Acceptance Analysis
    # Determines the REAL tradeable setup based on where bodies are accepting
    # ═══════════════════════════════════════════════════════════════════
    body_routing = determine_setup_by_body_acceptance(candles, structure)
    recommended_setup = body_routing.get('recommended_setup')
    body_retrace = body_routing.get('body_retrace_pct')
    
    if recommended_setup:
        flip_range = body_routing.get('flip_zone_range')
        flip_str = f"{flip_range[0]:.8f} - {flip_range[1]:.8f}" if flip_range else "N/A"
        
        logger.info(f"   [FLIP-ZONE] Wick retrace: {ret_pct:.1f}% (context only)")
        logger.info(f"   [FLIP-ZONE] Flip zone range: {flip_str}")
        logger.info(f"   [FLIP-ZONE] ✅ CLASSIFIED AS: {recommended_setup} + Flip Zone")
        
        # Show overlap percentages for each fib zone
        for fib_name, data in body_routing.get('fib_overlaps', {}).items():
            marker = "→" if fib_name == recommended_setup else " "
            logger.info(f"   [FLIP-ZONE] {marker} {fib_name}: {data['overlap_pct']:.0f}% overlap")
        
        logger.info(f"   [FLIP-ZONE] Reason: {body_routing.get('reason')}")
    
    # Test each engine
    results = []
    
    # If body acceptance strongly recommends a setup, prioritize it
    engine_order = list(ENGINE_PARAMS.keys())
    if recommended_setup and recommended_setup in engine_order:
        # Move recommended setup to front of list
        engine_order.remove(recommended_setup)
        engine_order.insert(0, recommended_setup)
    
    for engine_id in engine_order:
        params = ENGINE_PARAMS[engine_id]
        # Skip if on cooldown
        if is_engine_on_cooldown(address, engine_id):
            continue
        
        engine_name = params['name']
        ret_min = params['retracement_min']
        ret_max = params['retracement_max']
        impulse_min = params['impulse_min']
        whale_required = params['whale_required']
        inv_fib = params['invalidation_fib']
        grade_threshold = params['grade_threshold']
        
        # ─────────────────────────────────────────────────
        # CHECK 1: Retracement range (with body acceptance override)
        # ─────────────────────────────────────────────────
        wick_in_range = (ret_min <= ret_pct <= ret_max)
        body_recommended = (engine_id == recommended_setup and body_routing.get('confidence', 0) >= 50)
        
        # Allow through if: wick says yes, OR body acceptance strongly recommends this setup
        if not wick_in_range and not body_recommended:
            continue
        
        # Log when body acceptance overrides wick routing
        if not wick_in_range and body_recommended:
            logger.info(f"   [BODY-ROUTE] ✅ OVERRIDE: {engine_id} allowed (wick: {ret_pct:.1f}% out of {ret_min}-{ret_max}%, but body acceptance strong)")
        
        # ─────────────────────────────────────────────────
        # CHECK 2: Impulse minimum
        # ─────────────────────────────────────────────────
        if impulse_pct < impulse_min:
            logger.debug(f"   {engine_name}: Impulse {impulse_pct:.0f}% < min {impulse_min}%")
            continue
        
        # ─────────────────────────────────────────────────
        # CHECK 3: Invalidation (not below key fib)
        # ─────────────────────────────────────────────────
        if inv_fib < 1.0:
            inv_key = str(int(inv_fib * 1000))
            inv_price = fib_levels.get(inv_key, structure['swing_low'])
            if current_price < inv_price:
                logger.debug(f"   {engine_name}: Price ${current_price:.8f} below invalidation ${inv_price:.8f}")
                continue
        elif engine_id == 'underfib':
            # Under-fib: flip zone is below fib, so deeper pullbacks are expected
            # Only reject if completely broken structure (below swing low)
            if current_price < structure['swing_low'] * 0.90:
                logger.debug(f"   {engine_name}: Structure broken - below swing low")
                continue
        
        # ─────────────────────────────────────────────────
        # CHECK 4: Whale/conviction requirement
        # ─────────────────────────────────────────────────
        if whale_required and not has_whale:
            # .618 can pass with strong impulse OR flip zone rejections
            if engine_id == '618':
                flip_zones = structure.get('flip_zones', [])
                best_rejections = max([z.get('rejections', 0) for z in flip_zones]) if flip_zones else 0
                if impulse_pct >= 100 or best_rejections >= 5:
                    pass  # Override whale requirement
                else:
                    logger.debug(f"   {engine_name}: Whale required but not detected")
                    continue
            # .786 has stricter requirements
            elif engine_id == '786':
                if impulse_pct >= 150 and structure['rsi'] < 35:
                    pass  # Violent mode override
                else:
                    logger.debug(f"   {engine_name}: Whale REQUIRED for .786")
                    continue
            else:
                continue
        
        # ─────────────────────────────────────────────────
        # CHECK 5: Under-fib specific requirements
        # ─────────────────────────────────────────────────
        if engine_id == 'underfib':
            # Under-Fib needs price to break fib and approach flip zone
            # RSI can be low - that's expected at these levels
            pass  # Let validator handle the logic
        
        # ─────────────────────────────────────────────────
        # PASSED ALL CHECKS — Calculate score
        # ─────────────────────────────────────────────────
        
        # ═══════════════════════════════════════════════════
        # 50 BOUNCE VALIDATOR - Quality gate for 50 setups
        # ═══════════════════════════════════════════════════
        if engine_id == '50':
            # Check 50FZ gate (ATH/major high break required)
            passes_gate = token.get('passes_50fz_gate', True)
            if not passes_gate:
                logger.info(f"   ⛔ {symbol}: 50+FZ GATE - No ATH/major high break")
                continue
            
            try:
                from setup_validators.fifty_bounce import validate_50_bounce
                validation = validate_50_bounce(candles, symbol)
                
                # Log all layer results for debugging
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"   [50-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                if not validation.is_valid:
                    logger.info(f"   ❌ {symbol}: 50+FZ REJECTED - {validation.rejection_reason}")
                    continue
                
                # Log stage and all layer results
                logger.info(f"   ✅ {symbol}: 50+FZ Stage {validation.stage} [{validation.stage_name}]")
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"      [50-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                # Use validator score and grade
                score = validation.final_score
                grade = validation.final_grade
                
                # ═══════════════════════════════════════════════════
                # STAGE 5: FLASHCARD ANALYSIS (confidence boost only)
                # ═══════════════════════════════════════════════════
                flashcard_match = None
                try:
                    current_setup = {
                        'impulse_pct': structure.get('impulse_pct', 0),
                        'retracement_pct': structure.get('retracement_pct', 0),
                        'structure_quality': 'clean' if validation.final_score >= 75 else 'moderate',
                        'pullback_type': 'controlled',
                        'has_flip_zone': any(l.layer_name == 'flip_zone' and l.passed for l in validation.layers),
                        'candle_quality': sum(1 for l in validation.layers if 'candle' in l.layer_name.lower() and l.passed) * 25
                    }
                    
                    flashcard_match = analyze_flashcard_similarity(engine_id, current_setup, candles)
                    
                    if flashcard_match:
                        logger.info(f"   📚 {symbol}: Flashcard {flashcard_match.similarity_score:.0f}% match to {flashcard_match.best_match_name}")
                        
                        # Apply grade boost if high similarity
                        if flashcard_match.grade_boost > 0:
                            old_grade = grade
                            grade = apply_grade_boost(grade, flashcard_match.grade_boost)
                            if grade != old_grade:
                                logger.info(f"   📚 {symbol}: Grade boosted {old_grade} → {grade}")
                except Exception as e:
                    logger.debug(f"   Flashcard analysis error: {e}")
                
                # Add stage info to result for Telegram formatting
                # Stage 1 = "SETUP FORMING", Stage 2 = "ENTRY CONFIRMATION"
            except Exception as e:
                logger.warning(f"   50 validator error: {e}")
                score = calculate_engine_score(engine_id, structure, has_whale)
                grade = score_to_grade(score)
        
        # ═══════════════════════════════════════════════════
        # 382 VALIDATOR - Fast momentum continuation
        # ═══════════════════════════════════════════════════
        elif engine_id == '382':
            try:
                from setup_validators.three_eighty_two import validate_382
                
                # Pass shared structure to validator
                validation = validate_382(candles, symbol, structure)
                
                # Log layer results
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"   [382-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                if not validation.passed:
                    reject = validation.reject_reason or "Failed validation"
                    logger.info(f"   ❌ {symbol}: 382+FZ REJECTED - {reject}")
                    continue
                
                # Log success
                logger.info(f"   ✅ {symbol}: 382+FZ Stage {validation.stage} [{validation.stage_label}]")
                
                # Use validator score and grade
                score = validation.final_score
                grade = validation.final_grade
                
                # Flashcard analysis
                flashcard_match = None
                try:
                    current_setup = {
                        'impulse_pct': structure.get('impulse_pct', 0),
                        'retracement_pct': structure.get('retracement_pct', 0),
                        'structure_quality': 'clean' if validation.final_score >= 75 else 'moderate',
                        'pullback_type': 'controlled',
                        'has_flip_zone': any(l.layer_name == 'flip_zone' and l.passed for l in validation.layers),
                        'candle_quality': 70
                    }
                    
                    flashcard_match = analyze_flashcard_similarity(engine_id, current_setup, candles)
                    
                    if flashcard_match:
                        logger.info(f"   📚 {symbol}: Flashcard {flashcard_match.similarity_score:.0f}% match to {flashcard_match.best_match_name}")
                        
                        if flashcard_match.grade_boost > 0:
                            old_grade = grade
                            grade = apply_grade_boost(grade, flashcard_match.grade_boost)
                            if grade != old_grade:
                                logger.info(f"   📚 {symbol}: Grade boosted {old_grade} → {grade}")
                except Exception as e:
                    logger.debug(f"   Flashcard analysis error: {e}")
                
            except Exception as e:
                logger.warning(f"   382 validator error: {e}")
                score = calculate_engine_score(engine_id, structure, has_whale)
                grade = score_to_grade(score)
        
        # ═══════════════════════════════════════════════════
        # 618 VALIDATOR - Deep continuation pullback
        # ═══════════════════════════════════════════════════
        elif engine_id == '618':
            try:
                from setup_validators.six_eighteen import validate_618
                
                # Pass shared structure to validator
                validation = validate_618(candles, symbol, structure)
                
                # Log layer results
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"   [618-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                if not validation.passed:
                    reject = validation.reject_reason or "Failed validation"
                    logger.info(f"   ❌ {symbol}: 618+FZ REJECTED - {reject}")
                    continue
                
                # Log success
                logger.info(f"   ✅ {symbol}: 618+FZ Stage {validation.stage} [{validation.stage_label}]")
                
                # Use validator score and grade
                score = validation.final_score
                grade = validation.final_grade
                
                # Flashcard analysis
                flashcard_match = None
                try:
                    current_setup = {
                        'impulse_pct': structure.get('impulse_pct', 0),
                        'retracement_pct': structure.get('retracement_pct', 0),
                        'structure_quality': 'clean' if validation.final_score >= 75 else 'moderate',
                        'pullback_type': 'controlled',
                        'has_flip_zone': any(l.layer_name == 'flip_zone' and l.passed for l in validation.layers),
                        'candle_quality': 70
                    }
                    
                    flashcard_match = analyze_flashcard_similarity(engine_id, current_setup, candles)
                    
                    if flashcard_match:
                        logger.info(f"   📚 {symbol}: Flashcard {flashcard_match.similarity_score:.0f}% match to {flashcard_match.best_match_name}")
                        
                        if flashcard_match.grade_boost > 0:
                            old_grade = grade
                            grade = apply_grade_boost(grade, flashcard_match.grade_boost)
                            if grade != old_grade:
                                logger.info(f"   📚 {symbol}: Grade boosted {old_grade} → {grade}")
                except Exception as e:
                    logger.debug(f"   Flashcard analysis error: {e}")
                
            except Exception as e:
                logger.warning(f"   618 validator error: {e}")
                score = calculate_engine_score(engine_id, structure, has_whale)
                grade = score_to_grade(score)
        
        # ═══════════════════════════════════════════════════════════════
        # 786 VALIDATOR - Pain zone continuation (last line of defense)
        # ═══════════════════════════════════════════════════════════════
        elif engine_id == '786':
            try:
                from setup_validators.seven_eighty_six import validate_786
                
                validation = validate_786(candles, symbol, structure)
                
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"   [786-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                if not validation.passed:
                    reject = validation.reject_reason or "Failed validation"
                    logger.info(f"   ❌ {symbol}: 786+FZ REJECTED - {reject}")
                    continue
                
                logger.info(f"   ✅ {symbol}: 786+FZ Stage {validation.stage} [{validation.stage_label}]")
                
                score = validation.final_score
                grade = validation.final_grade
                
                # Flashcard analysis
                flashcard_match = None
                try:
                    current_setup = {
                        'impulse_pct': structure.get('impulse_pct', 0),
                        'retracement_pct': structure.get('retracement_pct', 0),
                        'structure_quality': 'clean' if validation.final_score >= 75 else 'moderate',
                        'pullback_type': 'deep',
                        'has_flip_zone': any(l.layer_name == 'resistance_zone' and l.passed for l in validation.layers),
                        'candle_quality': 70
                    }
                    
                    flashcard_match = analyze_flashcard_similarity(engine_id, current_setup, candles)
                    
                    if flashcard_match:
                        logger.info(f"   📚 {symbol}: Flashcard {flashcard_match.similarity_score:.0f}% match to {flashcard_match.best_match_name}")
                        
                        if flashcard_match.grade_boost > 0:
                            old_grade = grade
                            grade = apply_grade_boost(grade, flashcard_match.grade_boost)
                            if grade != old_grade:
                                logger.info(f"   📚 {symbol}: Grade boosted {old_grade} → {grade}")
                except Exception as e:
                    logger.debug(f"   Flashcard analysis error: {e}")
                
            except Exception as e:
                logger.warning(f"   786 validator error: {e}")
                score = calculate_engine_score(engine_id, structure, has_whale)
                grade = score_to_grade(score)
        
        # ═══════════════════════════════════════════════════════════════
        # UNDER-FIB VALIDATOR - Flip zone below fib level
        # ═══════════════════════════════════════════════════════════════
        elif engine_id == 'underfib':
            try:
                from setup_validators.under_fib import validate_under_fib
                
                validation = validate_under_fib(candles, symbol, structure)
                
                for layer in validation.layers:
                    status = "✓" if layer.passed else "✗"
                    logger.info(f"   [UFIB-VAL] {layer.layer_name}: {status} {layer.score} - {layer.reason}")
                
                if not validation.passed:
                    reject = validation.reject_reason or "Failed validation"
                    logger.info(f"   ❌ {symbol}: Under-Fib REJECTED - {reject}")
                    continue
                
                fib_above = validation.fib_level_above
                logger.info(f"   ✅ {symbol}: Under-Fib (below {fib_above}) Stage {validation.stage} [{validation.stage_label}]")
                
                score = validation.final_score
                grade = validation.final_grade
                
                # Flashcard analysis
                flashcard_match = None
                try:
                    current_setup = {
                        'impulse_pct': structure.get('impulse_pct', 0),
                        'retracement_pct': structure.get('retracement_pct', 0),
                        'structure_quality': 'clean' if validation.final_score >= 75 else 'moderate',
                        'pullback_type': 'under_fib',
                        'has_flip_zone': True,
                        'candle_quality': 70
                    }
                    
                    flashcard_match = analyze_flashcard_similarity(engine_id, current_setup, candles)
                    
                    if flashcard_match:
                        logger.info(f"   📚 {symbol}: Flashcard {flashcard_match.similarity_score:.0f}% match to {flashcard_match.best_match_name}")
                        
                        if flashcard_match.grade_boost > 0:
                            old_grade = grade
                            grade = apply_grade_boost(grade, flashcard_match.grade_boost)
                            if grade != old_grade:
                                logger.info(f"   📚 {symbol}: Grade boosted {old_grade} → {grade}")
                except Exception as e:
                    logger.debug(f"   Flashcard analysis error: {e}")
                
            except Exception as e:
                logger.warning(f"   Under-Fib validator error: {e}")
                score = calculate_engine_score(engine_id, structure, has_whale)
                grade = score_to_grade(score)
        
        else:
            score = calculate_engine_score(engine_id, structure, has_whale)
            grade = score_to_grade(score)
        
        # Check grade threshold
        if score < grade_threshold:
            logger.debug(f"   {engine_name}: Score {score} below threshold {grade_threshold}")
            continue
        
        # ─────────────────────────────────────────────────
        # CALCULATE ENTRY ZONE
        # ─────────────────────────────────────────────────
        buffer_min = params['entry_buffer_min']
        buffer_max = params['entry_buffer_max']
        buffer_pct = (buffer_min + buffer_max) / 2 / 100
        
        if engine_id == 'underfib':
            # Entry on structure break above current
            entry_price = current_price * 1.02
            entry_range_low = current_price
            entry_range_high = current_price * 1.05
        else:
            fib_key = engine_id if engine_id in fib_levels else '618'
            fib_price = fib_levels.get(fib_key, current_price)
            entry_price = fib_price * (1 + buffer_pct)
            entry_range_low = fib_price
            entry_range_high = fib_price * (1 + (buffer_max / 100))
        
        # ─────────────────────────────────────────────────
        # CALCULATE INVALIDATION
        # ─────────────────────────────────────────────────
        if inv_fib < 1.0:
            inv_key = str(int(inv_fib * 1000))
            invalidation_price = fib_levels.get(inv_key, structure['swing_low'])
            invalidation_text = f"Close below .{inv_key} (${invalidation_price:.8f})"
        else:
            invalidation_price = structure['swing_low']
            invalidation_text = f"HTF breakdown below ${invalidation_price:.8f}"
        
        # ─────────────────────────────────────────────────
        # BUILD RESULT
        # ─────────────────────────────────────────────────
        result = {
            'triggered': True,
            'engine_id': engine_id,
            'engine_name': engine_name,
            'score': score,
            'grade': grade,
            'retracement_pct': ret_pct,
            'impulse_pct': impulse_pct,
            'entry_price': entry_price,
            'entry_range': f"${entry_range_low:.8f} - ${entry_range_high:.8f}",
            'invalidation_price': invalidation_price,
            'invalidation_text': invalidation_text,
            'has_whale': has_whale,
            'rsi': structure['rsi'],
            'rsi_divergence': structure.get('rsi_divergence', False),
            'volume_expanding': structure.get('volume_expanding', False),
            'volume_contracting': structure.get('volume_contracting', False),
            'volume_ratio': structure.get('volume_ratio', 1.0),
            'fib_levels': fib_levels,
            'flip_zones': structure.get('flip_zones', []),
            'swing_high': structure['swing_high'],
            'swing_low': structure['swing_low'],
            'description': params['description'],
        }
        
        results.append(result)
        logger.info(f"✅ {symbol}: {engine_name} TRIGGERED — Score: {score} Grade: {grade}")
    
    if not results:
        return None
    
    # Return best scoring engine
    best = max(results, key=lambda x: x['score'])
    
    # Set cooldown for triggered engine
    set_engine_cooldown(address, best['engine_id'])
    
    return best


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS FOR INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def get_engine_names() -> List[str]:
    """Get list of all engine names."""
    return [p['name'] for p in ENGINE_PARAMS.values()]


def get_engine_by_id(engine_id: str) -> Optional[dict]:
    """Get engine parameters by ID."""
    return ENGINE_PARAMS.get(engine_id)


def format_engine_result_text(result: dict) -> str:
    """Format engine result for display in alerts."""
    if not result:
        return ""
    
    whale_emoji = '🐋' if result.get('has_whale') else ''
    div_emoji = '📈' if result.get('rsi_divergence') else ''
    
    lines = [
        f"🎯 <b>{result['engine_name']}</b> {whale_emoji}{div_emoji}",
        f"<b>Grade:</b> {result['grade']} ({result['score']}/100)",
        f"<b>Impulse:</b> {result['impulse_pct']:.0f}% | <b>Retrace:</b> {result['retracement_pct']:.0f}%",
        f"<b>RSI:</b> {result['rsi']:.0f}",
        f"",
        f"<b>Entry Zone:</b> {result['entry_range']}",
        f"<b>Invalidation:</b> {result['invalidation_text']}",
    ]
    
    if result.get('rsi_divergence'):
        lines.append("<i>📈 Bullish RSI divergence detected</i>")
    
    if result.get('volume_expanding'):
        lines.append("<i>📊 Volume expanding (accumulation)</i>")
    elif result.get('volume_contracting'):
        lines.append("<i>📊 Volume contracting (compression)</i>")
    
    return "\n".join(lines)
