# UNDERFIB PROPAGATION APPLIED
# PEAK RSI PATCH APPLIED
# SETUP CLASSIFIER REWRITE APPLIED
# BAND FIRST FIX APPLIED
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

# Tier 1.C.13: Per-run cooldown block tracker (audit 6.E)
# Module-level state. Reset at start of each run_detection() call.
# Scanner reads via get_last_run_cooldown_blocks() after each call.
# Captures cooldown blocks even when run_detection returns None (all engines blocked).
_LAST_RUN_COOLDOWN_BLOCKS: Dict[str, int] = {}


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


def get_last_run_cooldown_blocks() -> Dict[str, int]:
    """
    Returns a copy of the cooldown-block tracker from the last run_detection() call.
    Tier 1.C.13: Per-engine cooldown block counter (audit 6.E).
    Scanner.py reads this after each run_detection() to aggregate into DAILY_METRICS.
    Returns a COPY — mutations don't affect the tracker.
    Captures even when run_detection returns None (all engines blocked case).
    """
    return dict(_LAST_RUN_COOLDOWN_BLOCKS)



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
    
    # ═══════════════════════════════════════════════════════════════
    # BREAKOUT PEAK RSI (strength signature for WizTheory setups)
    # ═══════════════════════════════════════════════════════════════
    # Tracks the highest RSI hit during the impulse expansion phase
    # (from swing_low through swing_high).
    #
    # WizTheory interpretation: 70-90 typical for valid setups.
    # High peak RSI = real momentum entered move, retraces to FZ
    # likely to push back to high or higher.
    #
    # This is a CONFIRMATION FIELD only — not a gate, not scored.
    # Displayed in alerts so trader can interpret breakout strength.
    # ═══════════════════════════════════════════════════════════════
    breakout_peak_rsi = 0
    try:
        if swing_high_idx > swing_low_idx and swing_high_idx > 14:
            # Walk from swing_low_idx to swing_high_idx, compute RSI at each candle.
            # Take the max — that's the peak RSI during the expansion.
            for i in range(max(swing_low_idx, 14), swing_high_idx + 1):
                rsi_at_i = calculate_rsi(closes[:i+1])
                if rsi_at_i > breakout_peak_rsi:
                    breakout_peak_rsi = rsi_at_i
    except Exception:
        # Graceful failure — alert will show N/A
        breakout_peak_rsi = 0
    
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
        'breakout_peak_rsi': breakout_peak_rsi,
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
    Wiz Theory Setup Classifier (REWRITE)

    Priority hierarchy:
      1. Flip zone alignment with fib level (PRIMARY identity)
      2. Deepest wick retrace depth (confirms or emits mixed-depth warning)
      3. Body acceptance retrace (further confirmation)
      4. Boundary rule: prefer deeper fib only when FZ center genuinely closer
      5. 382 special: wick-origin / left-side rejection / thin FZ allowed

    Confidence (0-100, logging only):
      - retrace alignment: 0-50
      - FZ structure validity: 0-30
      - body acceptance agreement: 0-20

    Preserves OLD return contract:
      recommended_setup, flip_zone_range, fib_overlaps, confidence, reason, debug
    Adds new fields:
      retrace_pct, body_retrace_pct, primary_path, wick_origin_detected,
      left_side_rejection_detected, body_acceptance_match, boundary,
      mixed_depth_warning
    """
    result = {
        'recommended_setup': None,
        'flip_zone_range': None,
        'fib_overlaps': {},
        'confidence': 0,
        'reason': 'No flip zone detected',
        'debug': [],
        # new fields
        'retrace_pct': 0.0,
        'body_retrace_pct': 0.0,
        'primary_path': None,
        'wick_origin_detected': False,
        'left_side_rejection_detected': False,
        'body_acceptance_match': False,
        'boundary': False,
        'mixed_depth_warning': False,
    }

    if not candles or len(candles) < 20:
        return result

    swing_high = structure.get('swing_high', 0)
    swing_low = structure.get('swing_low', 0)
    fib_range = swing_high - swing_low

    if fib_range <= 0 or swing_low <= 0:
        return result

    # ───────── fib levels (wick-based, per master rules)
    fib_levels = {
        '382': swing_high - (fib_range * 0.382),
        '50':  swing_high - (fib_range * 0.50),
        '618': swing_high - (fib_range * 0.618),
        '786': swing_high - (fib_range * 0.786),
    }

    # ───────── official Wiz Theory retrace bands
    #   382: 30-40%
    #   50:  40-55%
    #   618: 50-60%
    #   786: 70-80%
    # Boundary rule: deeper fib preferred only when FZ center genuinely closer

    result['debug'].append(
        f"Swing: low={swing_low:.8f} high={swing_high:.8f} range={fib_range:.8f}"
    )

    # ═════════════════════════════════════════════════════════════════
    # STEP 1: Deepest wick retrace (structural truth)
    # ═════════════════════════════════════════════════════════════════
    deepest_wick = min(float(c.get('l') or c.get('low') or swing_high) for c in candles[-50:])
    wick_retrace_pct = ((swing_high - deepest_wick) / fib_range) * 100 if fib_range > 0 else 0
    wick_retrace_pct = max(0.0, min(100.0, wick_retrace_pct))
    result['retrace_pct'] = round(wick_retrace_pct, 1)
    result['debug'].append(f"Deepest wick retrace: {wick_retrace_pct:.1f}%")

    # ═════════════════════════════════════════════════════════════════
    # STEP 2: Detect FZ range from body-percentile (still useful signal)
    # ═════════════════════════════════════════════════════════════════
    recent = candles[-40:]
    body_closes = []
    for c in recent:
        close = float(c.get('close') or c.get('c') or 0)
        if 0 < close < swing_high:
            body_closes.append(close)

    fz_center = None
    fz_low = fz_high = None
    body_retrace_pct = 0.0

    if len(body_closes) >= 5:
        body_closes_sorted = sorted(body_closes)
        p25 = body_closes_sorted[int(len(body_closes_sorted) * 0.25)]
        p75 = body_closes_sorted[int(len(body_closes_sorted) * 0.75)]
        buf = (p75 - p25) * 0.15
        fz_low = p25 - buf
        fz_high = p75 + buf
        fz_center = (fz_low + fz_high) / 2.0
        result['flip_zone_range'] = (fz_low, fz_high)
        body_retrace_pct = ((swing_high - fz_center) / fib_range) * 100 if fib_range > 0 else 0
        body_retrace_pct = max(0.0, min(100.0, body_retrace_pct))
        result['body_retrace_pct'] = round(body_retrace_pct, 1)
        result['debug'].append(
            f"FZ from bodies: {fz_low:.8f}-{fz_high:.8f}, center={fz_center:.8f} ({body_retrace_pct:.1f}% retrace)"
        )
    else:
        result['debug'].append("FZ from bodies: insufficient data, will rely on wick retrace")

    # ═════════════════════════════════════════════════════════════════
    # STEP 3: Classify by BAND MEMBERSHIP (PRIMARY) — official Wiz Theory ranges
    # ═════════════════════════════════════════════════════════════════
    classify_retrace_pct = body_retrace_pct if fz_center is not None else wick_retrace_pct

    # Official Wiz Theory bands
    bands = {
        '382': (30.0, 40.0),
        '50':  (40.0, 55.0),
        '618': (50.0, 60.0),
        '786': (70.0, 80.0),
    }
    fib_order = ['382', '50', '618', '786']

    # Distances kept for tie-breaking + confidence (NOT primary identity)
    distances = {
        '382': abs(classify_retrace_pct - 38.2),
        '50':  abs(classify_retrace_pct - 50.0),
        '618': abs(classify_retrace_pct - 61.8),
        '786': abs(classify_retrace_pct - 78.6),
    }
    result['debug'].append(
        f"Classify-retrace: {classify_retrace_pct:.1f}% (from {'FZ center' if fz_center is not None else 'wick'})"
    )
    result['debug'].append(
        "Distances: " + " | ".join(f"{k}:{v:.1f}pts" for k, v in distances.items())
    )

    # Find which bands the retrace sits inside
    matching = [name for name, (lo, hi) in bands.items() if lo <= classify_retrace_pct <= hi]

    if len(matching) == 1:
        # Clean single-band membership — definitive
        primary = matching[0]
        result['debug'].append(f"Band membership: {primary} (single band, clean)")
    elif len(matching) >= 2:
        # Genuine band overlap (e.g. 50-55% retrace lives in both 50 and 618)
        result['boundary'] = True
        primary = max(matching, key=lambda x: fib_order.index(x))  # deeper wins
        result['debug'].append(
            f"BAND OVERLAP {matching} — picking deeper: {primary}"
        )
    else:
        # Retrace outside all bands (e.g. <30%, 60-70% gap, >80%)
        # Fall back to nearest fib by distance
        primary = min(distances, key=distances.get)
        result['debug'].append(
            f"No band match — nearest fib by distance: {primary} ({distances[primary]:.1f}pts away)"
        )

    primary_dist = distances[primary]

    # ═════════════════════════════════════════════════════════════════
    # STEP 4: Edge-of-band boundary check — upgrade to deeper if FZ aligns
    # ═════════════════════════════════════════════════════════════════
    # If retrace sits within 2% of the UPPER edge of its band AND FZ alignment
    # clearly favors the deeper adjacent band, upgrade to deeper.
    if not result['boundary']:
        primary_band = bands.get(primary)
        if primary_band:
            band_lo, band_hi = primary_band
            distance_to_upper_edge = abs(classify_retrace_pct - band_hi)
            if distance_to_upper_edge <= 2.0:
                # Find the next deeper band
                cur_idx = fib_order.index(primary)
                if cur_idx + 1 < len(fib_order):
                    deeper = fib_order[cur_idx + 1]
                    if distances[deeper] < distances[primary]:
                        result['boundary'] = True
                        result['debug'].append(
                            f"EDGE-BOUNDARY: {primary} retrace {classify_retrace_pct:.1f}% within 2pts of "
                            f"upper edge ({band_hi}%) AND FZ closer to {deeper} ({distances[deeper]:.1f}pts vs "
                            f"{distances[primary]:.1f}pts) — upgrading to {deeper}"
                        )
                        primary = deeper
                        primary_dist = distances[primary]

    result['recommended_setup'] = primary

    # ═════════════════════════════════════════════════════════════════
    # STEP 5: Mixed-depth warning (wick vs FZ alignment disagree)
    # ═════════════════════════════════════════════════════════════════
    band_for = {
        '382': (30, 40),
        '50':  (40, 55),
        '618': (50, 60),
        '786': (70, 80),
    }
    band_low, band_high = band_for[primary]
    wick_in_band = (band_low <= wick_retrace_pct <= band_high)
    if not wick_in_band and fz_center is not None:
        result['mixed_depth_warning'] = True
        result['debug'].append(
            f"WARN mixed-depth: wick={wick_retrace_pct:.1f}% outside {primary} band ({band_low}-{band_high}%), "
            f"but FZ aligns with {primary}"
        )

    # ═════════════════════════════════════════════════════════════════
    # STEP 6: 382 special path — wick-origin / left-side rejection
    # ═════════════════════════════════════════════════════════════════
    fib_382 = fib_levels['382']
    tol_382 = fib_382 * 0.03  # ±3%
    wick_origin = False
    left_side_rejection = False

    # Current pullback wick check (last 40 candles)
    for i, c in enumerate(candles[-40:]):
        c_low = float(c.get('l') or c.get('low') or 0)
        if abs(c_low - fib_382) <= tol_382:
            # confirm breakout: next 10 candles, price moves >=5% above wick low
            idx_global = len(candles) - 40 + i
            future = candles[idx_global+1: idx_global+11]
            if future:
                max_high = max(float(fc.get('h') or fc.get('high') or 0) for fc in future)
                if c_low > 0 and (max_high - c_low) / c_low >= 0.05:
                    wick_origin = True
                    break

    # Left-side rejection: earlier candles wicked at 0.382 and price later respected it
    if not wick_origin and len(candles) > 50:
        earlier = candles[:-40]
        for c in earlier[-30:]:  # look at the 30 candles just before the current 40
            c_high = float(c.get('h') or c.get('high') or 0)
            c_low = float(c.get('l') or c.get('low') or 0)
            if (abs(c_high - fib_382) <= tol_382) or (abs(c_low - fib_382) <= tol_382):
                left_side_rejection = True
                break

    result['wick_origin_detected'] = wick_origin
    result['left_side_rejection_detected'] = left_side_rejection
    if primary == '382':
        result['primary_path'] = 'wick_origin' if (wick_origin or left_side_rejection) else 'thin_fz_only'
    else:
        result['primary_path'] = 'thick_fz'

    if primary == '382' and (wick_origin or left_side_rejection):
        result['debug'].append(
            f"382 path: wick_origin={wick_origin} left_side_rejection={left_side_rejection}"
        )

    # ═════════════════════════════════════════════════════════════════
    # STEP 7: Body acceptance agreement check
    # ═════════════════════════════════════════════════════════════════
    body_match = False
    if fz_center is not None:
        body_band = band_for[primary]
        body_match = (body_band[0] <= body_retrace_pct <= body_band[1])
    result['body_acceptance_match'] = body_match
    if fz_center is not None and not body_match:
        result['debug'].append(
            f"WARN body acceptance disagrees: body_retrace={body_retrace_pct:.1f}% outside {primary} band"
        )

    # ═════════════════════════════════════════════════════════════════
    # STEP 8: Confidence (logging only, not used to silence alerts)
    # ═════════════════════════════════════════════════════════════════
    # Component A: retrace alignment (0-50)
    align_score = max(0, 50 - int(primary_dist * 2.5))
    align_score = min(50, align_score)

    # Component B: FZ structure validity (0-30)
    fz_score = 0
    if primary == '382':
        if wick_origin or left_side_rejection:
            fz_score = 30
        elif fz_center is not None:
            fz_score = 15
    else:
        if fz_center is not None:
            fz_score = 30

    # Component C: body acceptance agreement (0-20)
    body_score = 20 if body_match else (10 if fz_center is not None else 0)

    confidence = align_score + fz_score + body_score
    result['confidence'] = min(100, confidence)
    result['debug'].append(
        f"Confidence={result['confidence']} (align={align_score}, fz={fz_score}, body={body_score})"
    )

    # ═════════════════════════════════════════════════════════════════
    # STEP 9: Populate fib_overlaps for downstream logging compatibility
    # ═════════════════════════════════════════════════════════════════
    for fib_name in ['382', '50', '618', '786']:
        d = distances[fib_name]
        pseudo_overlap = max(0, 100 - int(d * 4))
        result['fib_overlaps'][fib_name] = {
            'overlap_pct': pseudo_overlap,
            'fib_zone': None,
            'fib_level': fib_levels[fib_name],
        }

    # ═════════════════════════════════════════════════════════════════
    # STEP 10: Build human-readable reason
    # ═════════════════════════════════════════════════════════════════
    parts = []
    parts.append(f"FZ aligns with {primary} (dist {primary_dist:.1f}pts)")
    parts.append(f"wick retrace {wick_retrace_pct:.1f}%")
    if fz_center is not None:
        parts.append(f"body retrace {body_retrace_pct:.1f}%")
    if result['mixed_depth_warning']:
        parts.append("MIXED-DEPTH (wick vs FZ disagree)")
    if result['boundary']:
        parts.append("BOUNDARY-DEEPER-PICKED")
    if primary == '382':
        if wick_origin: parts.append("382 wick-origin ✓")
        if left_side_rejection: parts.append("382 left-side-rejection ✓")
    result['reason'] = " | ".join(parts)

    return result


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
    
    # Tier 1.C.13: Reset per-run cooldown block tracker (audit 6.E)
    global _LAST_RUN_COOLDOWN_BLOCKS
    _LAST_RUN_COOLDOWN_BLOCKS = {}
    
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
            # Tier 1.C.13: Track cooldown blocks per-engine (audit 6.E)
            _LAST_RUN_COOLDOWN_BLOCKS[engine_id] = _LAST_RUN_COOLDOWN_BLOCKS.get(engine_id, 0) + 1
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
                # Capture Under-Fib specific fields for downstream propagation
                _ufib_destination_zone = float(getattr(validation, 'destination_zone', 0) or 0)
                _ufib_gate_fib = str(getattr(validation, 'gate_fib', fib_above) or fib_above)
                _ufib_subtype = str(getattr(validation, 'underfib_subtype', '') or f"Under-Fib {fib_above}")
                logger.info(f"   ✅ {symbol}: Under-Fib (below {fib_above}) Stage {validation.stage} [{validation.stage_label}]")
                logger.info(f"   [UFIB-PROP] destination_zone={_ufib_destination_zone:.10f} gate={_ufib_gate_fib} subtype={_ufib_subtype}")
                
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
            # Under-Fib propagation (only meaningful when engine_id == 'underfib')
            'underfib_destination_zone': locals().get('_ufib_destination_zone', 0.0),
            'underfib_gate_fib': locals().get('_ufib_gate_fib', ''),
            'underfib_subtype': locals().get('_ufib_subtype', ''),
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
