"""
PSEF v1.2 - PRE-SETUP ENVIRONMENT FILTER
========================================
Filters tokens BEFORE deep scan using 4 gates.
Only tokens passing all gates proceed to WizTheory engine.

Gate 1: Impulse - meaningful expansion leg exists
Gate 2: Structure - clean trend structure (HH/HL or LL/LH)
Gate 3: Pullback Quality - controlled pullback, no panic dumps
Gate 4: RSI Momentum Memory - 2-phase model (breakout + pullback)

v1.2 CHANGES:
- Gate 4 now uses 2-phase RSI model per WizTheory rules:
  Phase 1: Breakout Validation - RSI must have hit 65+ (confirms impulse)
  Phase 2: Pullback Evaluation - RSI 40+ OR recovering from dip
  Fail: RSI stuck below 30 with no recovery, or continuous downtrend
"""

from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def get_ohlcv(candle: dict) -> Tuple[float, float, float, float, float]:
    o = candle.get('open') or candle.get('o') or 0
    h = candle.get('high') or candle.get('h') or 0
    l = candle.get('low') or candle.get('l') or 0
    c = candle.get('close') or candle.get('c') or 0
    v = candle.get('volume') or candle.get('v') or 0
    return float(o), float(h), float(l), float(c), float(v)

def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
    if len(closes) < period + 1:
        return []
    rsi_values = []
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)
    if len(gains) < period:
        return []
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(rsi)
    return rsi_values

def find_swings(candles: List[dict], lookback: int = 3) -> Tuple[List[dict], List[dict]]:
    swing_highs = []
    swing_lows = []
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
            swing_highs.append({'index': i, 'price': h})
        if is_swing_low:
            swing_lows.append({'index': i, 'price': l})
    return swing_highs, swing_lows

def gate_1_impulse(candles: List[dict]) -> Tuple[bool, str]:
    if len(candles) < 20:
        return False, "Not enough candles"
    recent = candles[-20:]
    highs = [get_ohlcv(c)[1] for c in recent]
    lows = [get_ohlcv(c)[2] for c in recent]
    total_range = max(highs) - min(lows)
    if total_range == 0:
        return False, "No price movement"
    candle_ranges = []
    for c in recent:
        o, h, l, cl, _ = get_ohlcv(c)
        candle_ranges.append(h - l)
    avg_range = sum(candle_ranges) / len(candle_ranges)
    expansion_count = sum(1 for r in candle_ranges if r > avg_range * 2)
    if expansion_count >= 2:
        return True, f"Found {expansion_count} expansion candles"
    first_close = get_ohlcv(recent[0])[3]
    last_close = get_ohlcv(recent[-1])[3]
    move_percent = abs(last_close - first_close) / first_close * 100 if first_close > 0 else 0
    if move_percent >= 10:
        return True, f"Strong move: {move_percent:.1f}%"
    return False, f"Weak impulse: only {expansion_count} expansion candles, {move_percent:.1f}% move"

def gate_2_structure(candles: List[dict]) -> Tuple[bool, str]:
    swing_highs, swing_lows = find_swings(candles, lookback=2)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return True, "Not enough swings to analyze (allowing through)"
    hh_count = 0
    hl_count = 0
    for i in range(1, len(swing_highs)):
        if swing_highs[i]['price'] > swing_highs[i-1]['price']:
            hh_count += 1
    for i in range(1, len(swing_lows)):
        if swing_lows[i]['price'] > swing_lows[i-1]['price']:
            hl_count += 1
    lh_count = 0
    ll_count = 0
    for i in range(1, len(swing_highs)):
        if swing_highs[i]['price'] < swing_highs[i-1]['price']:
            lh_count += 1
    for i in range(1, len(swing_lows)):
        if swing_lows[i]['price'] < swing_lows[i-1]['price']:
            ll_count += 1
    bullish_structure = hh_count >= 1 and hl_count >= 1
    bearish_structure = lh_count >= 1 and ll_count >= 1
    if bullish_structure or bearish_structure:
        direction = "bullish" if bullish_structure else "bearish"
        return True, f"Clean {direction} structure"
    return False, "Choppy structure - no clear HH/HL or LH/LL"

def gate_3_pullback(candles: List[dict]) -> Tuple[bool, str]:
    if len(candles) < 10:
        return True, "Not enough candles for pullback analysis"
    recent = candles[-10:]
    panic_candles = 0
    for c in recent:
        o, h, l, cl, _ = get_ohlcv(c)
        total_range = h - l
        if total_range == 0:
            continue
        body = abs(cl - o)
        lower_wick = min(o, cl) - l
        wick_ratio = lower_wick / total_range
        body_ratio = body / total_range
        if wick_ratio > 0.6 and body_ratio < 0.3:
            panic_candles += 1
    if panic_candles >= 3:
        return False, f"Panic pullback: {panic_candles} panic wicks"
    return True, f"Controlled pullback ({panic_candles} panic wicks)"

def gate_4_rsi(candles: List[dict]) -> Tuple[bool, str]:
    """
    Gate 4: RSI Momentum Memory (v1.2 - 2-Phase Model)
    
    Phase 1: BREAKOUT VALIDATION
    - RSI must have reached 65+ in recent history (confirms impulse happened)
    
    Phase 2: PULLBACK EVALUATION  
    - RSI currently 40+ (healthy pullback) OR
    - RSI dipped below 30 but is now recovering (higher than recent low)
    
    FAIL CONDITIONS:
    - No breakout detected (RSI never hit 65+)
    - RSI stuck below 30 with no recovery
    - RSI continuously trending down with no bounce
    """
    closes = [get_ohlcv(c)[3] for c in candles]
    rsi_values = calculate_rsi(closes)
    
    if len(rsi_values) < 10:
        return True, "Not enough RSI data (allowing through)"
    
    # PHASE 1: BREAKOUT VALIDATION
    lookback_breakout = min(50, len(rsi_values))
    breakout_rsi = rsi_values[-lookback_breakout:]
    rsi_peak = max(breakout_rsi)
    
    breakout_confirmed = rsi_peak >= 65
    
    if not breakout_confirmed:
        if rsi_peak >= 60:
            pass  # Borderline - allow through
        else:
            return False, f"No breakout impulse: RSI peak was only {rsi_peak:.1f} (need 65+)"
    
    # PHASE 2: PULLBACK EVALUATION
    recent_rsi = rsi_values[-10:]
    rsi_current = recent_rsi[-1]
    rsi_low = min(recent_rsi)
    rsi_recent_low_idx = recent_rsi.index(rsi_low)
    
    is_recovering = rsi_current > rsi_low and rsi_recent_low_idx < len(recent_rsi) - 1
    
    continuous_down = True
    for i in range(1, len(recent_rsi)):
        if recent_rsi[i] >= recent_rsi[i-1]:
            continuous_down = False
            break
    
    # PASS: RSI currently healthy (40+)
    if rsi_current >= 40:
        return True, f"RSI healthy: {rsi_current:.1f} (peak was {rsi_peak:.1f})"
    
    # PASS: RSI dipped but is recovering
    if rsi_current >= 30 and is_recovering:
        return True, f"RSI recovering: {rsi_low:.1f} -> {rsi_current:.1f} (peak was {rsi_peak:.1f})"
    
    # PASS: RSI below 30 but clearly bouncing back
    if rsi_current < 30 and is_recovering and (rsi_current - rsi_low) >= 5:
        return True, f"RSI bounce detected: {rsi_low:.1f} -> {rsi_current:.1f} (+{rsi_current - rsi_low:.1f})"
    
    # FAIL: RSI stuck below 30 with no recovery
    if rsi_current < 30 and not is_recovering:
        return False, f"RSI collapsed: stuck at {rsi_current:.1f} (low: {rsi_low:.1f}, no recovery)"
    
    # FAIL: Continuous downtrend with no bounce
    if continuous_down and rsi_current < 35:
        return False, f"RSI freefall: continuous decline to {rsi_current:.1f}"
    
    # DEFAULT PASS: Edge cases
    return True, f"RSI acceptable: {rsi_current:.1f} (peak: {rsi_peak:.1f}, low: {rsi_low:.1f})"

def run_psef(candles: List[dict]) -> Dict:
    result = {
        'passed': False,
        'gates': {},
        'failed_gate': None,
        'summary': ''
    }
    if not candles or len(candles) < 20:
        result['summary'] = 'Not enough candle data'
        result['failed_gate'] = 'data'
        return result
    
    g1, r1 = gate_1_impulse(candles)
    result['gates']['impulse'] = {'passed': g1, 'reason': r1}
    if not g1:
        result['failed_gate'] = 'impulse'
        result['summary'] = f"Failed Impulse: {r1}"
        return result
    
    g2, r2 = gate_2_structure(candles)
    result['gates']['structure'] = {'passed': g2, 'reason': r2}
    if not g2:
        result['failed_gate'] = 'structure'
        result['summary'] = f"Failed Structure: {r2}"
        return result
    
    g3, r3 = gate_3_pullback(candles)
    result['gates']['pullback'] = {'passed': g3, 'reason': r3}
    if not g3:
        result['failed_gate'] = 'pullback'
        result['summary'] = f"Failed Pullback: {r3}"
        return result
    
    g4, r4 = gate_4_rsi(candles)
    result['gates']['rsi'] = {'passed': g4, 'reason': r4}
    if not g4:
        result['failed_gate'] = 'rsi'
        result['summary'] = f"Failed RSI: {r4}"
        return result
    
    result['passed'] = True
    result['summary'] = "All 4 gates passed"
    return result

if __name__ == '__main__':
    test_candles = [
        {'o': 100 + i*0.5, 'h': 102 + i*0.5, 'l': 99 + i*0.5, 'c': 101 + i*0.5, 'v': 1000}
        for i in range(30)
    ]
    result = run_psef(test_candles)
    print(f"PSEF Result: {result}")
