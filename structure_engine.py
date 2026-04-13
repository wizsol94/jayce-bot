"""
STRUCTURE ENGINE v1.0
=====================
Detects market structure for WizTheory setups.

Detects:
- Swing Highs / Swing Lows
- HH/HL (bullish) / LH/LL (bearish)
- Break of Structure (BOS)
- Liquidity sweeps
- Structure quality grade (A/B/C)
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class Swing:
    index: int
    price: float
    type: str  # 'high' or 'low'
    label: str  # 'HH', 'HL', 'LH', 'LL', or ''

@dataclass 
class StructureBreak:
    index: int
    price: float
    direction: str  # 'bullish' or 'bearish'
    broken_swing: Swing

@dataclass
class LiquiditySweep:
    index: int
    sweep_price: float
    close_price: float
    direction: str  # 'bull_sweep' (swept lows, closed above) or 'bear_sweep'
    swept_swing: Swing

def get_ohlcv(candle: dict) -> Tuple[float, float, float, float, float]:
    """Extract OHLCV from candle, handling both short and long key formats."""
    o = candle.get('open') or candle.get('o') or 0
    h = candle.get('high') or candle.get('h') or 0
    l = candle.get('low') or candle.get('l') or 0
    c = candle.get('close') or candle.get('c') or 0
    v = candle.get('volume') or candle.get('v') or 0
    return float(o), float(h), float(l), float(c), float(v)

def find_swings(candles: List[dict], lookback: int = 3) -> Tuple[List[Swing], List[Swing]]:
    """
    Find swing highs and swing lows.
    A swing high has lower highs on both sides.
    A swing low has higher lows on both sides.
    """
    swing_highs = []
    swing_lows = []
    
    if len(candles) < (lookback * 2 + 1):
        return swing_highs, swing_lows
    
    for i in range(lookback, len(candles) - lookback):
        _, h, l, _, _ = get_ohlcv(candles[i])
        
        is_swing_high = True
        is_swing_low = True
        
        for j in range(1, lookback + 1):
            _, h_before, l_before, _, _ = get_ohlcv(candles[i - j])
            _, h_after, l_after, _, _ = get_ohlcv(candles[i + j])
            
            if h <= h_before or h <= h_after:
                is_swing_high = False
            if l >= l_before or l >= l_after:
                is_swing_low = False
        
        if is_swing_high:
            swing_highs.append(Swing(index=i, price=h, type='high', label=''))
        if is_swing_low:
            swing_lows.append(Swing(index=i, price=l, type='low', label=''))
    
    return swing_highs, swing_lows

def label_swings(swing_highs: List[Swing], swing_lows: List[Swing]) -> Tuple[List[Swing], List[Swing]]:
    """
    Label swings as HH/LH for highs and HL/LL for lows.
    """
    # Label highs
    for i in range(1, len(swing_highs)):
        if swing_highs[i].price > swing_highs[i-1].price:
            swing_highs[i].label = 'HH'  # Higher High
        else:
            swing_highs[i].label = 'LH'  # Lower High
    
    # Label lows
    for i in range(1, len(swing_lows)):
        if swing_lows[i].price > swing_lows[i-1].price:
            swing_lows[i].label = 'HL'  # Higher Low
        else:
            swing_lows[i].label = 'LL'  # Lower Low
    
    return swing_highs, swing_lows

def detect_bos(candles: List[dict], swing_highs: List[Swing], swing_lows: List[Swing]) -> List[StructureBreak]:
    """
    Detect Break of Structure (BOS).
    Bullish BOS: Price breaks above a swing high
    Bearish BOS: Price breaks below a swing low
    """
    breaks = []
    
    # Check for bullish BOS (breaking swing highs)
    for sh in swing_highs:
        for i in range(sh.index + 1, len(candles)):
            _, h, _, c, _ = get_ohlcv(candles[i])
            if c > sh.price:  # Close above swing high = BOS
                breaks.append(StructureBreak(
                    index=i,
                    price=c,
                    direction='bullish',
                    broken_swing=sh
                ))
                break
    
    # Check for bearish BOS (breaking swing lows)
    for sl in swing_lows:
        for i in range(sl.index + 1, len(candles)):
            _, _, l, c, _ = get_ohlcv(candles[i])
            if c < sl.price:  # Close below swing low = BOS
                breaks.append(StructureBreak(
                    index=i,
                    price=c,
                    direction='bearish',
                    broken_swing=sl
                ))
                break
    
    return breaks

def detect_liquidity_sweeps(candles: List[dict], swing_highs: List[Swing], swing_lows: List[Swing]) -> List[LiquiditySweep]:
    """
    Detect liquidity sweeps.
    Bull sweep: Wick goes below swing low, but closes above it
    Bear sweep: Wick goes above swing high, but closes below it
    """
    sweeps = []
    
    # Check for bull sweeps (sweeping lows)
    for sl in swing_lows:
        for i in range(sl.index + 1, min(sl.index + 15, len(candles))):  # Check next 15 candles
            o, h, l, c, _ = get_ohlcv(candles[i])
            # Wick below swing low, but close above
            if l < sl.price and c > sl.price:
                sweeps.append(LiquiditySweep(
                    index=i,
                    sweep_price=l,
                    close_price=c,
                    direction='bull_sweep',
                    swept_swing=sl
                ))
                break
    
    # Check for bear sweeps (sweeping highs)
    for sh in swing_highs:
        for i in range(sh.index + 1, min(sh.index + 15, len(candles))):
            o, h, l, c, _ = get_ohlcv(candles[i])
            # Wick above swing high, but close below
            if h > sh.price and c < sh.price:
                sweeps.append(LiquiditySweep(
                    index=i,
                    sweep_price=h,
                    close_price=c,
                    direction='bear_sweep',
                    swept_swing=sh
                ))
                break
    
    return sweeps

def check_directional_bias(candles: List[dict], lookback: int = 20) -> Optional[str]:
    """
    FIX 1: Fallback for choppy meme coins.
    Check 20-candle directional bias when swing patterns are unclear.
    
    If recent candles show upward slope, return BULLISH_WEAK.
    This prevents valid setups from being marked RANGING.
    """
    if len(candles) < lookback:
        return None
    
    recent = candles[-lookback:]
    
    # Get closes
    closes = [float(c.get('close') or c.get('c') or 0) for c in recent]
    highs = [float(c.get('high') or c.get('h') or 0) for c in recent]
    lows = [float(c.get('low') or c.get('l') or 0) for c in recent]
    
    if not closes or closes[0] == 0:
        return None
    
    # Split into halves
    mid = lookback // 2
    first_half_avg = sum(closes[:mid]) / mid
    second_half_avg = sum(closes[mid:]) / (lookback - mid)
    
    first_half_high = max(highs[:mid])
    second_half_high = max(highs[mid:])
    first_half_low = min(lows[:mid])
    second_half_low = min(lows[mid:])
    
    # Calculate slope percentage
    slope_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100 if first_half_avg > 0 else 0
    
    # Upward bias: higher highs + positive slope + lows not breaking down
    if second_half_high > first_half_high and slope_pct > 2:
        # Allow slightly lower lows (choppy but trending)
        low_tolerance = first_half_low * 0.95
        if second_half_low >= low_tolerance:
            return 'BULLISH_WEAK'
    
    # Downward bias
    if second_half_high < first_half_high and slope_pct < -2:
        high_tolerance = first_half_high * 1.05
        if second_half_high <= high_tolerance:
            return 'BEARISH_WEAK'
    
    return None


def determine_trend(swing_highs: List[Swing], swing_lows: List[Swing]) -> str:
    """
    Determine overall trend based on swing structure.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 'UNKNOWN'
    
    # Count recent swing labels (last 4 of each)
    recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs
    recent_lows = swing_lows[-4:] if len(swing_lows) >= 4 else swing_lows
    
    hh_count = sum(1 for s in recent_highs if s.label == 'HH')
    lh_count = sum(1 for s in recent_highs if s.label == 'LH')
    hl_count = sum(1 for s in recent_lows if s.label == 'HL')
    ll_count = sum(1 for s in recent_lows if s.label == 'LL')
    
    bullish_score = hh_count + hl_count
    bearish_score = lh_count + ll_count
    
    if bullish_score >= 3 and bearish_score <= 1:
        return 'BULLISH'
    elif bearish_score >= 3 and bullish_score <= 1:
        return 'BEARISH'
    elif bullish_score > bearish_score:
        return 'BULLISH_WEAK'
    elif bearish_score > bullish_score:
        return 'BEARISH_WEAK'
    else:
        return 'RANGING'


def determine_trend_with_fallback(swing_highs: List[Swing], swing_lows: List[Swing], candles: List[dict]) -> str:
    """
    Determine trend with directional bias fallback.
    If swing pattern returns RANGING, check 20-candle directional bias.
    """
    trend = determine_trend(swing_highs, swing_lows)
    
    # If RANGING, try directional bias fallback for choppy meme coins
    if trend == 'RANGING' and candles:
        bias = check_directional_bias(candles)
        if bias:
            return bias
    
    return trend


def grade_structure(swing_highs: List[Swing], swing_lows: List[Swing], 
                    bos_list: List[StructureBreak], sweeps: List[LiquiditySweep],
                    trend: str) -> str:
    """
    Grade structure quality: A, B, or C.
    
    A = Clean trend with clear HH/HL or LH/LL, BOS confirmed
    B = Trend present but some choppiness
    C = Choppy, no clear structure
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 'C'
    
    # Check for clean structure
    recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs
    recent_lows = swing_lows[-4:] if len(swing_lows) >= 4 else swing_lows
    
    # Count consistent swings
    if trend in ['BULLISH', 'BULLISH_WEAK']:
        consistent_highs = sum(1 for s in recent_highs if s.label == 'HH')
        consistent_lows = sum(1 for s in recent_lows if s.label == 'HL')
    elif trend in ['BEARISH', 'BEARISH_WEAK']:
        consistent_highs = sum(1 for s in recent_highs if s.label == 'LH')
        consistent_lows = sum(1 for s in recent_lows if s.label == 'LL')
    else:
        return 'C'
    
    consistency = consistent_highs + consistent_lows
    has_bos = len(bos_list) > 0
    has_sweeps = len(sweeps) > 0
    
    # Grade A: Very clean structure
    if consistency >= 5 and has_bos:
        return 'A'
    
    # Grade B: Decent structure
    if consistency >= 3 or (consistency >= 2 and (has_bos or has_sweeps)):
        return 'B'
    
    # Grade C: Choppy
    return 'C'

def analyze_structure(candles: List[dict]) -> Dict:
    """
    Main entry point: Analyze market structure.
    Returns complete structure analysis.
    """
    result = {
        'swing_highs': [],
        'swing_lows': [],
        'trend': 'UNKNOWN',
        'bos': [],
        'liquidity_sweeps': [],
        'grade': 'C',
        'summary': ''
    }
    
    if not candles or len(candles) < 15:
        result['summary'] = 'Not enough candles for structure analysis'
        return result
    
    # Find swings
    swing_highs, swing_lows = find_swings(candles, lookback=3)
    
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        result['summary'] = 'Not enough swings detected'
        return result
    
    # Label swings (HH/HL/LH/LL)
    swing_highs, swing_lows = label_swings(swing_highs, swing_lows)
    
    # Detect BOS
    bos_list = detect_bos(candles, swing_highs, swing_lows)
    
    # Detect liquidity sweeps
    sweeps = detect_liquidity_sweeps(candles, swing_highs, swing_lows)
    
    # Determine trend (with directional bias fallback for choppy charts)
    trend = determine_trend_with_fallback(swing_highs, swing_lows, candles)
    
    # Grade structure
    grade = grade_structure(swing_highs, swing_lows, bos_list, sweeps, trend)
    
    # Build result
    result['swing_highs'] = [{'index': s.index, 'price': s.price, 'label': s.label} for s in swing_highs]
    result['swing_lows'] = [{'index': s.index, 'price': s.price, 'label': s.label} for s in swing_lows]
    result['trend'] = trend
    result['bos'] = [{'index': b.index, 'price': b.price, 'direction': b.direction} for b in bos_list]
    result['liquidity_sweeps'] = [{'index': s.index, 'direction': s.direction} for s in sweeps]
    result['grade'] = grade
    
    # Summary
    hh = sum(1 for s in swing_highs if s.label == 'HH')
    hl = sum(1 for s in swing_lows if s.label == 'HL')
    lh = sum(1 for s in swing_highs if s.label == 'LH')
    ll = sum(1 for s in swing_lows if s.label == 'LL')
    
    result['summary'] = f"Trend: {trend} | Grade: {grade} | HH:{hh} HL:{hl} LH:{lh} LL:{ll} | BOS:{len(bos_list)} Sweeps:{len(sweeps)}"
    
    return result

if __name__ == '__main__':
    # Test with sample uptrend data
    candles = []
    base = 100
    for i in range(50):
        # Simulate uptrend with pullbacks
        if i % 10 < 7:  # Impulse
            base += 2
        else:  # Pullback
            base -= 1
        candles.append({
            'o': base - 0.5,
            'h': base + 1,
            'l': base - 1,
            'c': base + 0.5,
            'v': 1000
        })
    
    result = analyze_structure(candles)
    print(f"Structure Analysis:")
    print(f"  {result['summary']}")
    print(f"  Swing Highs: {len(result['swing_highs'])}")
    print(f"  Swing Lows: {len(result['swing_lows'])}")
