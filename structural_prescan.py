"""
STRUCTURAL PRE-SCAN v1.0

Lightweight structural analysis on ALL validated tokens.
Ranks by setup-shape, not just volume/price change.

3 BUCKETS:
- DEEP_SCAN_NOW: High probability setup forming/active/triggered
- MONITOR: Setup potentially forming, watch closely
- REJECT: No setup characteristics

RANKING FACTORS:
1. Meaningful breakout structure (ATH, major high, local high)
2. Strong recent expansion (impulse move)
3. Clean market structure
4. Controlled pullback behavior
5. Proximity to Wiz Theory levels (382, 50, 618, 786, Under-Fib)
6. Volume quality
7. Candle quality / rejection quality
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ScanBucket(Enum):
    DEEP_SCAN_NOW = "DEEP_SCAN_NOW"
    MONITOR = "MONITOR"
    REJECT = "REJECT"


@dataclass
class PrescanResult:
    symbol: str
    pair_address: str
    bucket: ScanBucket
    score: float
    reasons: List[str]
    
    # Individual scores
    breakout_score: float = 0
    expansion_score: float = 0
    structure_score: float = 0
    pullback_score: float = 0
    fib_proximity_score: float = 0
    volume_score: float = 0
    candle_quality_score: float = 0


def calculate_fib_levels(high: float, low: float) -> Dict[str, float]:
    """Calculate Fibonacci retracement levels."""
    diff = high - low
    return {
        '236': high - (diff * 0.236),
        '382': high - (diff * 0.382),
        '50': high - (diff * 0.5),
        '618': high - (diff * 0.618),
        '786': high - (diff * 0.786),
    }


def analyze_breakout_structure(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze breakout quality.
    Returns score (0-100) and reasons.
    
    Checks for:
    - ATH break (strongest)
    - Major high break
    - Local high break
    - Expansion from base
    """
    if len(candles) < 20:
        return 0, ["Insufficient candles"]
    
    reasons = []
    score = 0
    
    closes = [c['close'] for c in candles]
    highs = [c['high'] for c in candles]
    
    current_price = closes[-1]
    all_time_high = max(highs)
    recent_high_20 = max(highs[-20:])
    recent_high_50 = max(highs[-50:]) if len(highs) >= 50 else max(highs)
    
    # ATH break or near ATH (strongest signal)
    if current_price >= all_time_high * 0.95:
        score += 40
        if current_price >= all_time_high:
            reasons.append("ATH_BREAK")
        else:
            reasons.append("NEAR_ATH")
    
    # Major high break (last 50 candles)
    elif current_price >= recent_high_50 * 0.95:
        score += 30
        reasons.append("MAJOR_HIGH_BREAK")
    
    # Local high break (last 20 candles)
    elif current_price >= recent_high_20 * 0.95:
        score += 20
        reasons.append("LOCAL_HIGH_BREAK")
    
    # Check for expansion from consolidation
    if len(candles) >= 30:
        # Look for tight range followed by expansion
        range_20_ago = max(highs[-30:-10]) - min([c['low'] for c in candles[-30:-10]])
        recent_range = max(highs[-10:]) - min([c['low'] for c in candles[-10:]])
        
        if recent_range > range_20_ago * 1.5:
            score += 15
            reasons.append("EXPANSION_FROM_BASE")
    
    return min(score, 100), reasons


def analyze_expansion(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze recent expansion/impulse quality.
    """
    if len(candles) < 10:
        return 0, []
    
    reasons = []
    score = 0
    
    # Calculate recent move
    recent_candles = candles[-10:]
    start_price = recent_candles[0]['open']
    end_price = recent_candles[-1]['close']
    
    if start_price == 0:
        return 0, []
    
    move_pct = ((end_price - start_price) / start_price) * 100
    
    # Strong expansion
    if move_pct >= 50:
        score += 35
        reasons.append("STRONG_EXPANSION_50%+")
    elif move_pct >= 30:
        score += 25
        reasons.append("GOOD_EXPANSION_30%+")
    elif move_pct >= 15:
        score += 15
        reasons.append("MODERATE_EXPANSION_15%+")
    
    # Check for consecutive bullish candles (impulse)
    bullish_streak = 0
    for c in recent_candles:
        if c['close'] > c['open']:
            bullish_streak += 1
        else:
            bullish_streak = 0
    
    if bullish_streak >= 4:
        score += 20
        reasons.append(f"IMPULSE_{bullish_streak}_CANDLES")
    
    return min(score, 100), reasons


def analyze_market_structure(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze overall market structure cleanliness.
    """
    if len(candles) < 20:
        return 0, []
    
    reasons = []
    score = 50  # Start neutral
    
    closes = [c['close'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    
    # Check for higher highs and higher lows (bullish structure)
    hh_count = 0
    hl_count = 0
    
    for i in range(5, len(candles), 5):
        chunk = candles[i-5:i]
        prev_chunk = candles[i-10:i-5] if i >= 10 else candles[0:5]
        
        if max([c['high'] for c in chunk]) > max([c['high'] for c in prev_chunk]):
            hh_count += 1
        if min([c['low'] for c in chunk]) > min([c['low'] for c in prev_chunk]):
            hl_count += 1
    
    if hh_count >= 2 and hl_count >= 2:
        score += 30
        reasons.append("CLEAN_HH_HL_STRUCTURE")
    elif hh_count >= 1 and hl_count >= 1:
        score += 15
        reasons.append("FORMING_STRUCTURE")
    
    # Penalize choppy action (too many direction changes)
    direction_changes = 0
    for i in range(1, len(closes)):
        if (closes[i] > closes[i-1]) != (closes[i-1] > closes[i-2] if i >= 2 else True):
            direction_changes += 1
    
    chop_ratio = direction_changes / len(closes)
    if chop_ratio > 0.6:
        score -= 20
        reasons.append("CHOPPY_STRUCTURE")
    
    return max(0, min(score, 100)), reasons


def analyze_pullback(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze pullback quality and control.
    """
    if len(candles) < 20:
        return 0, []
    
    reasons = []
    score = 0
    
    # Find recent high and measure pullback
    highs = [c['high'] for c in candles]
    closes = [c['close'] for c in candles]
    
    recent_high_idx = highs.index(max(highs[-30:])) if len(highs) >= 30 else highs.index(max(highs))
    recent_high = highs[recent_high_idx]
    current_price = closes[-1]
    
    if recent_high == 0:
        return 0, []
    
    pullback_pct = ((recent_high - current_price) / recent_high) * 100
    
    # Controlled pullback (not too deep, not too shallow)
    if 10 <= pullback_pct <= 50:
        score += 30
        reasons.append(f"CONTROLLED_PULLBACK_{pullback_pct:.0f}%")
        
        # Extra points for landing near fib levels
        if 35 <= pullback_pct <= 42:
            score += 20
            reasons.append("NEAR_382_LEVEL")
        elif 47 <= pullback_pct <= 53:
            score += 20
            reasons.append("NEAR_50_LEVEL")
        elif 58 <= pullback_pct <= 65:
            score += 20
            reasons.append("NEAR_618_LEVEL")
        elif 75 <= pullback_pct <= 82:
            score += 15
            reasons.append("NEAR_786_LEVEL")
    
    # Check pullback candle quality (smaller bodies = controlled)
    if recent_high_idx < len(candles) - 3:
        pullback_candles = candles[recent_high_idx:]
        avg_body_size = sum(abs(c['close'] - c['open']) for c in pullback_candles) / len(pullback_candles)
        avg_range = sum(c['high'] - c['low'] for c in pullback_candles) / len(pullback_candles)
        
        if avg_range > 0:
            body_ratio = avg_body_size / avg_range
            if body_ratio < 0.5:
                score += 15
                reasons.append("SMALL_BODY_PULLBACK")
    
    return min(score, 100), reasons


def analyze_fib_proximity(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze proximity to and respect of Wiz Theory fib levels.
    """
    if len(candles) < 20:
        return 0, []
    
    reasons = []
    score = 0
    
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    
    swing_high = max(highs)
    swing_low = min(lows)
    current_price = candles[-1]['close']
    
    fibs = calculate_fib_levels(swing_high, swing_low)
    
    # Check proximity to each fib level
    for level_name, level_price in fibs.items():
        if level_price == 0:
            continue
        
        distance_pct = abs((current_price - level_price) / level_price) * 100
        
        if distance_pct <= 3:  # Within 3% of fib level
            score += 30
            reasons.append(f"AT_{level_name}_LEVEL")
        elif distance_pct <= 7:  # Within 7%
            score += 15
            reasons.append(f"NEAR_{level_name}_LEVEL")
    
    # Check for fib level respect (bounce or rejection)
    recent_lows = [c['low'] for c in candles[-10:]]
    recent_low = min(recent_lows)
    
    for level_name, level_price in fibs.items():
        if level_price == 0:
            continue
        
        # Did price respect this level?
        if abs((recent_low - level_price) / level_price) * 100 <= 5:
            if current_price > recent_low * 1.03:  # Bounced at least 3%
                score += 20
                reasons.append(f"BOUNCE_FROM_{level_name}")
    
    return min(score, 100), reasons


def analyze_volume_quality(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze volume patterns.
    """
    if len(candles) < 20 or 'volume' not in candles[0]:
        return 50, ["NO_VOLUME_DATA"]  # Neutral if no volume
    
    reasons = []
    score = 50  # Start neutral
    
    volumes = [c.get('volume', 0) for c in candles]
    recent_vol = sum(volumes[-5:]) / 5 if volumes[-5:] else 0
    older_vol = sum(volumes[-20:-5]) / 15 if len(volumes) >= 20 else sum(volumes) / len(volumes)
    
    if older_vol == 0:
        return 50, []
    
    vol_ratio = recent_vol / older_vol
    
    # Volume expansion on move
    if vol_ratio >= 2:
        score += 30
        reasons.append("VOLUME_EXPANSION_2X+")
    elif vol_ratio >= 1.5:
        score += 20
        reasons.append("VOLUME_EXPANSION_1.5X+")
    
    # Volume decreasing on pullback (healthy)
    last_3_vol = volumes[-3:]
    if len(last_3_vol) >= 3:
        if last_3_vol[-1] < last_3_vol[0]:
            score += 15
            reasons.append("VOLUME_DECLINING_PULLBACK")
    
    return min(score, 100), reasons


def analyze_candle_quality(candles: List[Dict]) -> Tuple[float, List[str]]:
    """
    Analyze candle quality and rejection wicks.
    """
    if len(candles) < 10:
        return 0, []
    
    reasons = []
    score = 50  # Start neutral
    
    recent = candles[-10:]
    
    # Look for rejection wicks (long lower wicks = buyers)
    rejection_count = 0
    for c in recent:
        body = abs(c['close'] - c['open'])
        lower_wick = min(c['close'], c['open']) - c['low']
        upper_wick = c['high'] - max(c['close'], c['open'])
        total_range = c['high'] - c['low']
        
        if total_range > 0:
            # Strong lower wick rejection
            if lower_wick > body * 1.5 and lower_wick > upper_wick:
                rejection_count += 1
    
    if rejection_count >= 2:
        score += 25
        reasons.append(f"REJECTION_WICKS_{rejection_count}")
    
    # Look for strong bullish candles
    strong_bullish = 0
    for c in recent:
        body = c['close'] - c['open']
        total_range = c['high'] - c['low']
        
        if total_range > 0 and body > 0:
            body_ratio = body / total_range
            if body_ratio > 0.7:  # Strong body, small wicks
                strong_bullish += 1
    
    if strong_bullish >= 3:
        score += 20
        reasons.append(f"STRONG_BULLISH_CANDLES_{strong_bullish}")
    
    return min(score, 100), reasons


def structural_prescan(symbol: str, pair_address: str, candles: List[Dict]) -> PrescanResult:
    """
    Run full structural pre-scan on a token.
    Returns bucket assignment and detailed scores.
    """
    if not candles or len(candles) < 15:
        return PrescanResult(
            symbol=symbol,
            pair_address=pair_address,
            bucket=ScanBucket.REJECT,
            score=0,
            reasons=["INSUFFICIENT_DATA"]
        )
    
    # Run all analyses
    breakout_score, breakout_reasons = analyze_breakout_structure(candles)
    expansion_score, expansion_reasons = analyze_expansion(candles)
    structure_score, structure_reasons = analyze_market_structure(candles)
    pullback_score, pullback_reasons = analyze_pullback(candles)
    fib_score, fib_reasons = analyze_fib_proximity(candles)
    volume_score, volume_reasons = analyze_volume_quality(candles)
    candle_score, candle_reasons = analyze_candle_quality(candles)
    
    # Weighted total score
    total_score = (
        breakout_score * 0.20 +      # 20% - Breakout structure
        expansion_score * 0.15 +      # 15% - Recent expansion
        structure_score * 0.15 +      # 15% - Market structure
        pullback_score * 0.20 +       # 20% - Pullback quality
        fib_score * 0.15 +            # 15% - Fib proximity
        volume_score * 0.08 +         # 8% - Volume quality
        candle_score * 0.07           # 7% - Candle quality
    )
    
    # Combine all reasons
    all_reasons = (
        breakout_reasons + expansion_reasons + structure_reasons +
        pullback_reasons + fib_reasons + volume_reasons + candle_reasons
    )
    
    # Determine bucket
    if total_score >= 25:
        bucket = ScanBucket.DEEP_SCAN_NOW
    elif total_score >= 15:
        bucket = ScanBucket.MONITOR
    else:
        bucket = ScanBucket.REJECT
    
    # Bonus: If at a key fib level with good structure, bump to DEEP_SCAN
    if bucket == ScanBucket.MONITOR:
        if any('AT_' in r and '_LEVEL' in r for r in fib_reasons):
            if structure_score >= 50:
                bucket = ScanBucket.DEEP_SCAN_NOW
                all_reasons.append("BUMP_FIB_LEVEL_READY")
    
    return PrescanResult(
        symbol=symbol,
        pair_address=pair_address,
        bucket=bucket,
        score=total_score,
        reasons=all_reasons,
        breakout_score=breakout_score,
        expansion_score=expansion_score,
        structure_score=structure_score,
        pullback_score=pullback_score,
        fib_proximity_score=fib_score,
        volume_score=volume_score,
        candle_quality_score=candle_score
    )


async def run_prescan_batch(tokens: List[Dict], fetch_candles_func) -> Dict[str, List[PrescanResult]]:
    """
    Run structural prescan on all tokens.
    Returns dict with 3 bucket lists.
    """
    results = {
        'DEEP_SCAN_NOW': [],
        'MONITOR': [],
        'REJECT': []
    }
    
    logger.info(f"[PRESCAN] Running structural prescan on {len(tokens)} tokens...")
    
    for token in tokens:
        symbol = token.get('symbol', '???')
        pair_address = token.get('pair_address', '')
        
        try:
            # Fetch lightweight candles (fewer candles for prescan)
            candles = await fetch_candles_func(pair_address, limit=50)
            
            if not candles:
                results['REJECT'].append(PrescanResult(
                    symbol=symbol,
                    pair_address=pair_address,
                    bucket=ScanBucket.REJECT,
                    score=0,
                    reasons=["NO_CANDLE_DATA"]
                ))
                continue
            
            # Run prescan
            result = structural_prescan(symbol, pair_address, candles)
            results[result.bucket.value].append(result)
            
            # Log ALL scores for debugging
            logger.info(f"[PRESCAN] {symbol}: {result.bucket.value} — Score: {result.score:.0f} — B:{result.breakout_score:.0f} E:{result.expansion_score:.0f} S:{result.structure_score:.0f} P:{result.pullback_score:.0f} F:{result.fib_proximity_score:.0f}")
            
        except Exception as e:
            logger.debug(f"[PRESCAN] Error on {symbol}: {e}")
            results['REJECT'].append(PrescanResult(
                symbol=symbol,
                pair_address=pair_address,
                bucket=ScanBucket.REJECT,
                score=0,
                reasons=[f"ERROR: {str(e)[:50]}"]
            ))
    
    # Sort by score within each bucket
    for bucket in results:
        results[bucket].sort(key=lambda x: x.score, reverse=True)
    
    logger.info(f"[PRESCAN] Results: DEEP_SCAN={len(results['DEEP_SCAN_NOW'])} | MONITOR={len(results['MONITOR'])} | REJECT={len(results['REJECT'])}")
    
    return results

def quick_filter(tokens):
    """Compatibility function - returns all tokens since prescan handles filtering."""
    return tokens

