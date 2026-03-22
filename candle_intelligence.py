"""
CANDLE INTELLIGENCE v1.0
========================
Tags candles with market context labels for WizTheory grading.

Candle Types:
- EXPANSION: Strong directional move, large body, momentum
- REJECTION: Long wick showing price rejection (pin bars, hammers)
- COMPRESSION: Small body, low range, coiling energy
- SWEEP: Wick that takes liquidity then reverses
- EXHAUSTION: Large candle at end of move, signals reversal potential
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TaggedCandle:
    """Candle with intelligence tags"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    tags: List[str]
    body_percent: float  # Body as % of total range
    upper_wick_percent: float
    lower_wick_percent: float
    range_atr_ratio: float  # Range compared to ATR

def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    """Calculate Average True Range"""
    if len(candles) < period + 1:
        return 0.0
    
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].get('high', 0) or candles[i].get('h', 0)
        low = candles[i].get('low', 0) or candles[i].get('l', 0)
        prev_close = candles[i-1].get('close', 0) or candles[i-1].get('c', 0)
        
        if high and low and prev_close:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
    
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    
    return sum(trs[-period:]) / period

def tag_candle(candle: Dict, atr: float, prev_candles: List[Dict] = None) -> TaggedCandle:
    """
    Analyze a single candle and apply intelligence tags.
    """
    # Extract OHLCV
    o = candle.get('open', 0) or candle.get('o', 0)
    h = candle.get('high', 0) or candle.get('h', 0)
    l = candle.get('low', 0) or candle.get('l', 0)
    c = candle.get('close', 0) or candle.get('c', 0)
    v = candle.get('volume', 0) or candle.get('v', 0)
    ts = candle.get('timestamp', 0) or candle.get('t', 0)
    
    tags = []
    
    # Calculate candle metrics
    total_range = h - l if h > l else 0.0001
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    
    body_percent = (body / total_range) * 100 if total_range else 0
    upper_wick_percent = (upper_wick / total_range) * 100 if total_range else 0
    lower_wick_percent = (lower_wick / total_range) * 100 if total_range else 0
    range_atr_ratio = total_range / atr if atr > 0 else 1.0
    
    is_bullish = c > o
    is_bearish = c < o
    
    # ═══════════════════════════════════════════════════════════════════
    # TAG: EXPANSION
    # Large body candle (>70% body), range > 1.5x ATR, strong momentum
    # ═══════════════════════════════════════════════════════════════════
    if body_percent >= 70 and range_atr_ratio >= 1.5:
        if is_bullish:
            tags.append("EXPANSION_BULL")
        else:
            tags.append("EXPANSION_BEAR")
    
    # ═══════════════════════════════════════════════════════════════════
    # TAG: REJECTION
    # Long wick (>50% of range) showing rejection, small body
    # ═══════════════════════════════════════════════════════════════════
    if upper_wick_percent >= 50 and body_percent <= 40:
        tags.append("REJECTION_TOP")  # Bearish rejection
    
    if lower_wick_percent >= 50 and body_percent <= 40:
        tags.append("REJECTION_BOTTOM")  # Bullish rejection
    
    # ═══════════════════════════════════════════════════════════════════
    # TAG: COMPRESSION
    # Small range (<0.5x ATR), tight body - energy coiling
    # ═══════════════════════════════════════════════════════════════════
    if range_atr_ratio <= 0.5 and body_percent <= 50:
        tags.append("COMPRESSION")
    
    # ═══════════════════════════════════════════════════════════════════
    # TAG: SWEEP
    # Wick extends beyond recent high/low then closes back inside
    # Requires prev_candles context
    # ═══════════════════════════════════════════════════════════════════
    if prev_candles and len(prev_candles) >= 3:
        recent_highs = [pc.get('high', 0) or pc.get('h', 0) for pc in prev_candles[-5:]]
        recent_lows = [pc.get('low', 0) or pc.get('l', 0) for pc in prev_candles[-5:]]
        
        prev_high = max(recent_highs) if recent_highs else h
        prev_low = min(recent_lows) if recent_lows else l
        
        # Sweep high: wick goes above prev high, closes below
        if h > prev_high and c < prev_high and upper_wick_percent >= 30:
            tags.append("SWEEP_HIGH")
        
        # Sweep low: wick goes below prev low, closes above
        if l < prev_low and c > prev_low and lower_wick_percent >= 30:
            tags.append("SWEEP_LOW")
    
    # ═══════════════════════════════════════════════════════════════════
    # TAG: EXHAUSTION
    # Large candle (>2x ATR) at potential end of move
    # Often followed by reversal
    # ═══════════════════════════════════════════════════════════════════
    if range_atr_ratio >= 2.0 and body_percent >= 60:
        # Check if this could be exhaustion (extended move)
        if prev_candles and len(prev_candles) >= 5:
            # Count consecutive same-direction candles
            same_dir_count = 0
            for pc in reversed(prev_candles[-5:]):
                pc_o = pc.get('open', 0) or pc.get('o', 0)
                pc_c = pc.get('close', 0) or pc.get('c', 0)
                pc_bullish = pc_c > pc_o
                if pc_bullish == is_bullish:
                    same_dir_count += 1
                else:
                    break
            
            if same_dir_count >= 3:
                if is_bullish:
                    tags.append("EXHAUSTION_BULL")
                else:
                    tags.append("EXHAUSTION_BEAR")
    
    return TaggedCandle(
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        tags=tags,
        body_percent=round(body_percent, 1),
        upper_wick_percent=round(upper_wick_percent, 1),
        lower_wick_percent=round(lower_wick_percent, 1),
        range_atr_ratio=round(range_atr_ratio, 2)
    )

def analyze_candles(candles: List[Dict]) -> List[TaggedCandle]:
    """
    Analyze all candles and return tagged versions.
    """
    if not candles or len(candles) < 2:
        return []
    
    atr = calculate_atr(candles)
    tagged = []
    
    for i, candle in enumerate(candles):
        prev = candles[:i] if i > 0 else None
        tagged_candle = tag_candle(candle, atr, prev)
        tagged.append(tagged_candle)
    
    return tagged

def get_candle_summary(tagged_candles: List[TaggedCandle]) -> Dict:
    """
    Summarize candle intelligence for a token.
    """
    if not tagged_candles:
        return {'total': 0, 'tags': {}}
    
    tag_counts = {}
    for tc in tagged_candles:
        for tag in tc.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Recent bias (last 10 candles)
    recent = tagged_candles[-10:] if len(tagged_candles) >= 10 else tagged_candles
    recent_tags = []
    for tc in recent:
        recent_tags.extend(tc.tags)
    
    expansion_count = sum(1 for t in recent_tags if 'EXPANSION' in t)
    rejection_count = sum(1 for t in recent_tags if 'REJECTION' in t)
    compression_count = sum(1 for t in recent_tags if 'COMPRESSION' in t)
    sweep_count = sum(1 for t in recent_tags if 'SWEEP' in t)
    
    # Determine market character
    if expansion_count >= 3:
        character = "TRENDING"
    elif compression_count >= 3:
        character = "COILING"
    elif rejection_count >= 2:
        character = "INDECISION"
    else:
        character = "MIXED"
    
    return {
        'total_candles': len(tagged_candles),
        'tag_counts': tag_counts,
        'recent_character': character,
        'expansion_count': expansion_count,
        'rejection_count': rejection_count,
        'compression_count': compression_count,
        'sweep_count': sweep_count
    }

# ═══════════════════════════════════════════════════════════════════════════
# FLIP ZONE DETECTION (for WizTheory setups)
# ═══════════════════════════════════════════════════════════════════════════

def detect_flip_zones(tagged_candles: List[TaggedCandle], fib_levels: Dict) -> List[Dict]:
    """
    Detect flip zones near Fibonacci levels.
    A flip zone is where price rejected, swept, then reclaimed.
    """
    flip_zones = []
    
    if not tagged_candles or not fib_levels:
        return flip_zones
    
    for level_name, level_price in fib_levels.items():
        if not level_price:
            continue
            
        # Look for rejection or sweep near this level
        zone_tolerance = level_price * 0.02  # 2% tolerance
        
        touches = []
        for i, tc in enumerate(tagged_candles):
            # Check if candle interacted with this level
            if tc.low <= level_price + zone_tolerance and tc.high >= level_price - zone_tolerance:
                touch_type = None
                
                if 'REJECTION_BOTTOM' in tc.tags or 'SWEEP_LOW' in tc.tags:
                    touch_type = 'BULLISH_FLIP'
                elif 'REJECTION_TOP' in tc.tags or 'SWEEP_HIGH' in tc.tags:
                    touch_type = 'BEARISH_FLIP'
                
                if touch_type:
                    touches.append({
                        'index': i,
                        'candle': tc,
                        'type': touch_type,
                        'level': level_name
                    })
        
        if touches:
            flip_zones.append({
                'level': level_name,
                'price': level_price,
                'touches': touches,
                'quality': 'A' if len(touches) >= 2 else 'B'
            })
    
    return flip_zones

if __name__ == '__main__':
    # Test with sample data
    sample_candles = [
        {'o': 100, 'h': 105, 'l': 99, 'c': 104, 'v': 1000},
        {'o': 104, 'h': 110, 'l': 103, 'c': 109, 'v': 1500},
        {'o': 109, 'h': 112, 'l': 108, 'c': 108.5, 'v': 800},
        {'o': 108.5, 'h': 109, 'l': 105, 'c': 106, 'v': 1200},
        {'o': 106, 'h': 107, 'l': 102, 'c': 106.5, 'v': 2000},
    ]
    
    tagged = analyze_candles(sample_candles)
    for tc in tagged:
        print(f"Candle: O={tc.open} H={tc.high} L={tc.low} C={tc.close} | Tags: {tc.tags}")
    
    summary = get_candle_summary(tagged)
    print(f"\nSummary: {summary}")
