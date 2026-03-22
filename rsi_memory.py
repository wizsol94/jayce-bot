"""
RSI MOMENTUM MEMORY v2.0
========================
Two RSI modes for WizTheory setups:

MODE 1: RSI MEMORY (Pullback Analysis)
- Bullish continuation if RSI holds 40-50 floor during pullback
- Momentum weak/dead if RSI loses floor and cannot reclaim

MODE 2: RSI EXPANSION (Breakout/Runner Analysis)
- Breakout Pressure: RSI 70+ while pressing resistance
- Runner Mode: RSI 75-90 with confirmed breakout
- NOT treated as bearish - used as strength confirmation

Outputs:
- RSI_MEMORY_INTACT: true/false
- RSI_BREAKOUT_PRESSURE: true/false  
- RSI_RUNNER_MODE: true/false
"""

from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def get_ohlcv(candle: dict) -> Tuple[float, float, float, float, float]:
    """Extract OHLCV from candle."""
    o = candle.get('open') or candle.get('o') or 0
    h = candle.get('high') or candle.get('h') or 0
    l = candle.get('low') or candle.get('l') or 0
    c = candle.get('close') or candle.get('c') or 0
    v = candle.get('volume') or candle.get('v') or 0
    return float(o), float(h), float(l), float(c), float(v)

def calculate_rsi(candles: List[dict], period: int = 14) -> List[float]:
    """Calculate RSI values for all candles."""
    closes = [get_ohlcv(c)[3] for c in candles]
    
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
        
        rsi_values.append(round(rsi, 2))
    
    return rsi_values

# ══════════════════════════════════════════════════════════════════════════════
# MODE 1: RSI MEMORY (Pullback Analysis)
# ══════════════════════════════════════════════════════════════════════════════

def check_rsi_memory(rsi_values: List[float], trend: str = 'BULLISH') -> Dict:
    """
    Check if RSI momentum memory is intact during pullback.
    
    Bullish: RSI should hold 40-50 floor during pullbacks
    Bearish: RSI should hold 50-60 ceiling during pullbacks
    """
    result = {
        'RSI_MEMORY_INTACT': False,
        'floor': 0,
        'ceiling': 100,
        'current': 0,
        'state': 'UNKNOWN',
        'grade': 'C',
        'reason': ''
    }
    
    if len(rsi_values) < 10:
        result['reason'] = 'Not enough RSI data'
        return result
    
    recent = rsi_values[-20:] if len(rsi_values) >= 20 else rsi_values
    current = rsi_values[-1]
    floor = min(recent)
    ceiling = max(recent)
    
    result['current'] = current
    result['floor'] = floor
    result['ceiling'] = ceiling
    
    if trend in ['BULLISH', 'BULLISH_WEAK']:
        # Bullish memory: floor should hold above 35-40
        if floor >= 45:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'STRONG_MEMORY'
            result['grade'] = 'A'
            result['reason'] = f'Floor at {floor:.0f} - strong momentum memory'
        elif floor >= 38:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'MEMORY_HOLDING'
            result['grade'] = 'B'
            result['reason'] = f'Floor at {floor:.0f} - memory intact'
        elif floor >= 30 and current >= 45:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'RECOVERING'
            result['grade'] = 'B'
            result['reason'] = f'Dipped to {floor:.0f}, recovering to {current:.0f}'
        else:
            result['RSI_MEMORY_INTACT'] = False
            result['state'] = 'MEMORY_LOST'
            result['grade'] = 'C'
            result['reason'] = f'Floor broke at {floor:.0f} - momentum lost'
            
    elif trend in ['BEARISH', 'BEARISH_WEAK']:
        # Bearish memory: ceiling should hold below 60-65
        if ceiling <= 55:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'STRONG_MEMORY'
            result['grade'] = 'A'
            result['reason'] = f'Ceiling at {ceiling:.0f} - strong bearish memory'
        elif ceiling <= 62:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'MEMORY_HOLDING'
            result['grade'] = 'B'
            result['reason'] = f'Ceiling at {ceiling:.0f} - memory intact'
        else:
            result['RSI_MEMORY_INTACT'] = False
            result['state'] = 'MEMORY_LOST'
            result['grade'] = 'C'
            result['reason'] = f'Ceiling broke at {ceiling:.0f}'
    else:
        # Neutral - just check if not completely dead
        if floor >= 35:
            result['RSI_MEMORY_INTACT'] = True
            result['state'] = 'NEUTRAL_OK'
            result['grade'] = 'B'
            result['reason'] = f'RSI floor {floor:.0f} holding'
        else:
            result['RSI_MEMORY_INTACT'] = False
            result['state'] = 'WEAK'
            result['grade'] = 'C'
            result['reason'] = f'RSI floor weak at {floor:.0f}'
    
    return result

# ══════════════════════════════════════════════════════════════════════════════
# MODE 2: RSI EXPANSION (Breakout/Runner Analysis)
# ══════════════════════════════════════════════════════════════════════════════

def find_local_high(candles: List[dict], lookback: int = 20) -> float:
    """Find local high (resistance) in recent candles."""
    if len(candles) < lookback:
        lookback = len(candles)
    
    recent = candles[-lookback:]
    return max(get_ohlcv(c)[1] for c in recent)  # max high

def find_prior_high(candles: List[dict], lookback: int = 50) -> float:
    """Find prior high (potential ATH or major resistance)."""
    if len(candles) < lookback:
        lookback = len(candles)
    
    # Look at older candles (skip most recent 10)
    if len(candles) > 15:
        older = candles[:-10]
        return max(get_ohlcv(c)[1] for c in older[-lookback:])
    else:
        return max(get_ohlcv(c)[1] for c in candles)

def check_volume_support(candles: List[dict], lookback: int = 10) -> bool:
    """Check if recent volume supports the move."""
    if len(candles) < lookback + 5:
        return False
    
    recent_vol = sum(get_ohlcv(c)[4] for c in candles[-lookback:]) / lookback
    prior_vol = sum(get_ohlcv(c)[4] for c in candles[-(lookback+10):-lookback]) / 10
    
    # Volume should be at least 1.2x prior average
    return recent_vol >= prior_vol * 1.2

def check_rsi_expansion(candles: List[dict], rsi_values: List[float], structure_grade: str = 'B') -> Dict:
    """
    Check for RSI expansion / breakout conditions.
    
    RSI 70+ near resistance = BREAKOUT_PRESSURE
    RSI 75-90 with breakout confirmed = RUNNER_MODE
    
    This is STRENGTH confirmation, not bearish signal.
    """
    result = {
        'RSI_BREAKOUT_PRESSURE': False,
        'RSI_RUNNER_MODE': False,
        'current_rsi': 0,
        'price_vs_resistance': 'below',
        'volume_supported': False,
        'expansion_grade': 'C',
        'reason': ''
    }
    
    if len(rsi_values) < 5 or len(candles) < 20:
        result['reason'] = 'Not enough data'
        return result
    
    current_rsi = rsi_values[-1]
    result['current_rsi'] = current_rsi
    
    # Get price levels
    current_price = get_ohlcv(candles[-1])[3]  # close
    local_high = find_local_high(candles, lookback=15)
    prior_high = find_prior_high(candles, lookback=40)
    
    # Check volume support
    volume_supported = check_volume_support(candles)
    result['volume_supported'] = volume_supported
    
    # Calculate distance from resistance
    resistance = max(local_high, prior_high)
    distance_pct = ((resistance - current_price) / resistance) * 100 if resistance > 0 else 0
    
    # Price position relative to resistance
    if current_price >= resistance * 0.995:  # Within 0.5% or above
        result['price_vs_resistance'] = 'at_or_above'
    elif current_price >= resistance * 0.97:  # Within 3%
        result['price_vs_resistance'] = 'pressing'
    elif current_price >= resistance * 0.93:  # Within 7%
        result['price_vs_resistance'] = 'approaching'
    else:
        result['price_vs_resistance'] = 'below'
    
    # ══════════════════════════════════════════════════════════════════════
    # BREAKOUT PRESSURE: RSI 70+ while pressing resistance
    # ══════════════════════════════════════════════════════════════════════
    if current_rsi >= 70 and result['price_vs_resistance'] in ['pressing', 'at_or_above']:
        result['RSI_BREAKOUT_PRESSURE'] = True
        result['reason'] = f'RSI {current_rsi:.0f} with price {result["price_vs_resistance"]} resistance'
        
        # Higher grade if volume confirms
        if volume_supported and structure_grade in ['A', 'B']:
            result['expansion_grade'] = 'A'
        else:
            result['expansion_grade'] = 'B'
    
    # ══════════════════════════════════════════════════════════════════════
    # RUNNER MODE: RSI 75-90 with confirmed breakout
    # ══════════════════════════════════════════════════════════════════════
    if current_rsi >= 75 and result['price_vs_resistance'] == 'at_or_above':
        # Confirm breakout: check if we closed above prior highs
        recent_closes = [get_ohlcv(c)[3] for c in candles[-5:]]
        breakout_confirmed = all(c >= prior_high * 0.98 for c in recent_closes[-3:])
        
        if breakout_confirmed:
            result['RSI_RUNNER_MODE'] = True
            result['RSI_BREAKOUT_PRESSURE'] = True  # Runner implies breakout pressure
            result['reason'] = f'RUNNER: RSI {current_rsi:.0f}, breakout confirmed, price above resistance'
            
            # Grade based on RSI strength and volume
            if current_rsi >= 80 and volume_supported and structure_grade == 'A':
                result['expansion_grade'] = 'A+'
            elif current_rsi >= 75 and volume_supported:
                result['expansion_grade'] = 'A'
            else:
                result['expansion_grade'] = 'B'
    
    # If no expansion conditions met
    if not result['RSI_BREAKOUT_PRESSURE'] and not result['RSI_RUNNER_MODE']:
        if current_rsi >= 65:
            result['reason'] = f'RSI {current_rsi:.0f} elevated but not at resistance yet'
            result['expansion_grade'] = 'C'
        else:
            result['reason'] = f'RSI {current_rsi:.0f} - no expansion signal'
            result['expansion_grade'] = 'C'
    
    return result

# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT: Full RSI Analysis
# ══════════════════════════════════════════════════════════════════════════════

def analyze_rsi_full(candles: List[dict], trend: str = 'BULLISH', structure_grade: str = 'B') -> Dict:
    """
    Complete RSI analysis combining both modes.
    
    Returns:
    - RSI_MEMORY_INTACT: Pullback holding momentum floor
    - RSI_BREAKOUT_PRESSURE: RSI 70+ pressing resistance
    - RSI_RUNNER_MODE: RSI 75-90 with confirmed breakout
    - Combined grade for setup scoring
    """
    result = {
        'RSI_MEMORY_INTACT': False,
        'RSI_BREAKOUT_PRESSURE': False,
        'RSI_RUNNER_MODE': False,
        'current_rsi': 0,
        'floor': 0,
        'ceiling': 100,
        'memory_grade': 'C',
        'expansion_grade': 'C',
        'combined_grade': 'C',
        'mode': 'UNKNOWN',
        'summary': ''
    }
    
    if not candles or len(candles) < 25:
        result['summary'] = 'Not enough candle data'
        return result
    
    # Calculate RSI
    rsi_values = calculate_rsi(candles)
    
    if len(rsi_values) < 10:
        result['summary'] = 'Not enough RSI data'
        return result
    
    current_rsi = rsi_values[-1]
    result['current_rsi'] = current_rsi
    
    # ══════════════════════════════════════════════════════════════════════
    # MODE 1: Check RSI Memory
    # ══════════════════════════════════════════════════════════════════════
    memory_result = check_rsi_memory(rsi_values, trend)
    result['RSI_MEMORY_INTACT'] = memory_result['RSI_MEMORY_INTACT']
    result['floor'] = memory_result['floor']
    result['ceiling'] = memory_result['ceiling']
    result['memory_grade'] = memory_result['grade']
    
    # ══════════════════════════════════════════════════════════════════════
    # MODE 2: Check RSI Expansion (only if RSI is elevated)
    # ══════════════════════════════════════════════════════════════════════
    if current_rsi >= 60:
        expansion_result = check_rsi_expansion(candles, rsi_values, structure_grade)
        result['RSI_BREAKOUT_PRESSURE'] = expansion_result['RSI_BREAKOUT_PRESSURE']
        result['RSI_RUNNER_MODE'] = expansion_result['RSI_RUNNER_MODE']
        result['expansion_grade'] = expansion_result['expansion_grade']
    
    # ══════════════════════════════════════════════════════════════════════
    # Determine active mode and combined grade
    # ══════════════════════════════════════════════════════════════════════
    if result['RSI_RUNNER_MODE']:
        result['mode'] = 'RUNNER'
        result['combined_grade'] = result['expansion_grade']
    elif result['RSI_BREAKOUT_PRESSURE']:
        result['mode'] = 'BREAKOUT_PRESSURE'
        result['combined_grade'] = result['expansion_grade']
    elif result['RSI_MEMORY_INTACT']:
        result['mode'] = 'PULLBACK_MEMORY'
        result['combined_grade'] = result['memory_grade']
    else:
        result['mode'] = 'WEAK'
        result['combined_grade'] = 'C'
    
    # Build summary
    flags = []
    if result['RSI_MEMORY_INTACT']:
        flags.append('MEM✓')
    if result['RSI_BREAKOUT_PRESSURE']:
        flags.append('BKOUT✓')
    if result['RSI_RUNNER_MODE']:
        flags.append('RUNNER✓')
    
    flag_str = ' '.join(flags) if flags else 'NONE'
    result['summary'] = f"RSI:{current_rsi:.0f} | Mode:{result['mode']} | {flag_str} | Grade:{result['combined_grade']}"
    
    return result

# Backward compatible simple function
def analyze_rsi(candles: List[dict]) -> Dict:
    """Simple RSI analysis for backward compatibility."""
    result = analyze_rsi_full(candles)
    return {
        'current': result['current_rsi'],
        'floor': result['floor'],
        'ceiling': result['ceiling'],
        'state': result['mode'],
        'grade': result['combined_grade'],
        'RSI_MEMORY_INTACT': result['RSI_MEMORY_INTACT'],
        'RSI_BREAKOUT_PRESSURE': result['RSI_BREAKOUT_PRESSURE'],
        'RSI_RUNNER_MODE': result['RSI_RUNNER_MODE']
    }

if __name__ == '__main__':
    print("=" * 60)
    print("TEST 1: Bullish pullback (memory should hold)")
    print("=" * 60)
    candles1 = []
    base = 100
    for i in range(60):
        if i < 40:
            base += 1.2 if i % 5 < 4 else -0.3
        else:
            base -= 0.4 if i % 3 < 2 else 0.2
        candles1.append({'o': base-0.3, 'h': base+0.5, 'l': base-0.5, 'c': base+0.2, 'v': 1000})
    
    result1 = analyze_rsi_full(candles1, trend='BULLISH')
    print(f"  {result1['summary']}")
    print(f"  Memory Intact: {result1['RSI_MEMORY_INTACT']}")
    print()
    
    print("=" * 60)
    print("TEST 2: Breakout scenario (RSI expansion)")
    print("=" * 60)
    candles2 = []
    base = 100
    for i in range(60):
        if i < 30:
            base += 0.5  # Gradual rise
        elif i < 50:
            base += 2.5  # Strong breakout
        else:
            base += 1.0  # Continuation
        candles2.append({'o': base-0.2, 'h': base+1.5, 'l': base-0.3, 'c': base+1.2, 'v': 2000 + i*50})
    
    result2 = analyze_rsi_full(candles2, trend='BULLISH', structure_grade='A')
    print(f"  {result2['summary']}")
    print(f"  Breakout Pressure: {result2['RSI_BREAKOUT_PRESSURE']}")
    print(f"  Runner Mode: {result2['RSI_RUNNER_MODE']}")
