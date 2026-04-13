"""
RUNNER INTELLIGENCE LAYER v1.0

Purpose: Evaluate runner potential AFTER a valid WizTheory setup is detected.
This is a POST-DETECTION ANALYSIS LAYER only.

Does NOT modify:
- WizTheory setup detection
- DEX scanning pipeline
- Pattern matching engine
- Vision system
- Alert triggers

Pipeline: DEX Scan → Wiz Setup Detection → Runner Intelligence → Alert Output

Reference Patterns (from real runners):
- MOON: RSI HH's, entry protected, pullbacks holding ~50
- CALVIN: RSI 80+ breakout, pullbacks to 40, divergence exit at +900%
- HTTPS: RSI hitting 70 repeatedly, entry level never breaks
- Peepo: Multiple 70+HH, entry level protected, divergence exit
- Distorted: 75+HH → 80+HH staircase, HH+HL divergence = exit
- Snowball: Multiple 70+HH, entry support protected
"""

from typing import Dict, List, Tuple


def get_ohlcv(candle: Dict) -> Tuple[float, float, float, float, float]:
    """Extract OHLCV from candle dict."""
    if isinstance(candle, dict):
        o = float(candle.get('open', candle.get('o', 0)))
        h = float(candle.get('high', candle.get('h', 0)))
        l = float(candle.get('low', candle.get('l', 0)))
        c = float(candle.get('close', candle.get('c', 0)))
        v = float(candle.get('volume', candle.get('v', 0)))
        return o, h, l, c, v
    return 0, 0, 0, 0, 0


def calculate_rsi(candles: List[Dict], period: int = 14) -> List[float]:
    """Calculate RSI series for candles."""
    if len(candles) < period + 1:
        return []
    
    closes = [get_ohlcv(c)[3] for c in candles]
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    if len(gains) < period:
        return []
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rsi = 100 - (100 / (1 + avg_gain / avg_loss))
        rsi_values.append(rsi)
    
    return rsi_values


def find_peaks(values: List[float], min_distance: int = 3) -> List[Tuple[int, float]]:
    """Find local peaks in a series."""
    if len(values) < 3:
        return []
    
    peaks = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i-1] and values[i] > values[i+1]:
            if not peaks or (i - peaks[-1][0]) >= min_distance:
                peaks.append((i, values[i]))
    return peaks


def find_troughs(values: List[float], min_distance: int = 3) -> List[Tuple[int, float]]:
    """Find local troughs in a series."""
    if len(values) < 3:
        return []
    
    troughs = []
    for i in range(1, len(values) - 1):
        if values[i] < values[i-1] and values[i] < values[i+1]:
            if not troughs or (i - troughs[-1][0]) >= min_distance:
                troughs.append((i, values[i]))
    return troughs


def analyze_runner_intelligence(
    candles: List[Dict],
    entry_zone: float,
    rsi_values: List[float] = None
) -> Dict:
    """
    Analyze runner potential AFTER a valid WizTheory setup is detected.
    
    This is a POST-DETECTION layer only. Does not affect setup detection.
    
    Checks:
    1. RSI Breakout Signal (RSI >= 70 during impulse)
    2. Momentum Memory (RSI pullbacks hold above 40-45)
    3. RSI Higher High Continuation (staircase pattern)
    4. Entry Level Protection (support defended)
    5. Divergence Warning (price HH but RSI LH)
    
    Returns runner probability and formatted alert addition.
    """
    result = {
        'runner_probability': 'NONE',
        'momentum_detected': False,
        'momentum_memory': False,
        'rsi_staircase': False,
        'support_protected': False,
        'divergence_detected': False,
        'rsi_max': 0,
        'pullback_floor': 0,
        'entry_retests': 0,
        'signals': [],
        'warnings': [],
        'alert_addition': ''
    }
    
    if not candles or len(candles) < 25:
        return result
    
    # Calculate RSI if not provided
    if rsi_values is None or len(rsi_values) < 15:
        rsi_values = calculate_rsi(candles)
    
    if len(rsi_values) < 15:
        return result
    
    # ═══════════════════════════════════════════════════════════════════════
    # 1. RSI BREAKOUT SIGNAL
    # Check if RSI spiked above 70 during breakout impulse
    # ═══════════════════════════════════════════════════════════════════════
    rsi_max = max(rsi_values)
    result['rsi_max'] = round(rsi_max, 1)
    
    if rsi_max >= 70:
        result['momentum_detected'] = True
        result['signals'].append(f"RSI Momentum Breakout (>{int(rsi_max)})")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 2. MOMENTUM MEMORY CHECK
    # After RSI breaks 70, check if pullbacks hold above 40-45
    # ═══════════════════════════════════════════════════════════════════════
    if result['momentum_detected']:
        # Find where RSI first broke 70
        breakout_idx = None
        for i, rsi in enumerate(rsi_values):
            if rsi >= 70:
                breakout_idx = i
                break
        
        if breakout_idx is not None and breakout_idx < len(rsi_values) - 5:
            # Check pullbacks after breakout
            post_breakout_rsi = rsi_values[breakout_idx:]
            troughs = find_troughs(post_breakout_rsi)
            
            if troughs:
                pullback_floors = [t[1] for t in troughs]
                min_pullback = min(pullback_floors)
                result['pullback_floor'] = round(min_pullback, 1)
                
                # Momentum memory if pullbacks hold above 40
                if min_pullback >= 40:
                    result['momentum_memory'] = True
                    result['signals'].append(f"Momentum Memory (pullbacks >{int(min_pullback)})")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 3. RSI HIGHER HIGH CONTINUATION (Staircase)
    # Track RSI peaks - looking for equal or higher highs
    # ═══════════════════════════════════════════════════════════════════════
    rsi_peaks = find_peaks(rsi_values)
    
    if len(rsi_peaks) >= 2:
        # Filter peaks above 60 (meaningful peaks)
        strong_peaks = [(i, v) for i, v in rsi_peaks if v >= 60]
        
        if len(strong_peaks) >= 2:
            # Check for staircase (each peak >= 95% of previous - allowing small dips)
            staircase_count = 0
            for i in range(1, len(strong_peaks)):
                if strong_peaks[i][1] >= strong_peaks[i-1][1] * 0.95:
                    staircase_count += 1
            
            # Need at least 2 maintained/higher peaks for staircase
            if staircase_count >= 1:
                result['rsi_staircase'] = True
                result['signals'].append("RSI Staircase Continuation")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 4. ENTRY LEVEL PROTECTION
    # Check if price retests entry zone but no candle closes below
    # ═══════════════════════════════════════════════════════════════════════
    if entry_zone > 0:
        entry_buffer = entry_zone * 0.05  # 5% buffer
        entry_upper = entry_zone * 1.10   # 10% above entry
        entry_lower = entry_zone * 0.95   # 5% below entry
        
        retests = 0
        closes_below = 0
        
        for candle in candles[-30:]:  # Check last 30 candles
            o, h, l, c, v = get_ohlcv(candle)
            
            # Retest = low touches entry zone area
            if l <= entry_upper and l >= entry_lower:
                retests += 1
            
            # Close below entry = support broken
            if c < entry_zone * 0.98:  # 2% tolerance
                closes_below += 1
        
        result['entry_retests'] = retests
        
        # Support protected if 2+ retests with no closes below
        if retests >= 2 and closes_below == 0:
            result['support_protected'] = True
            result['signals'].append(f"Entry Support Protected ({retests} retests)")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 5. DIVERGENCE EXIT DETECTION
    # Price makes higher high but RSI makes lower high
    # ═══════════════════════════════════════════════════════════════════════
    price_highs = [get_ohlcv(c)[1] for c in candles]
    price_peaks = find_peaks(price_highs)
    
    if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
        # Get last two significant peaks
        last_price_peaks = price_peaks[-2:]
        
        # Find corresponding RSI values at those indices
        # Map candle indices to RSI indices (RSI starts after period)
        rsi_offset = len(candles) - len(rsi_values)
        
        last_rsi_peaks = rsi_peaks[-2:]
        
        # Check for divergence: price HH but RSI LH
        if len(last_price_peaks) >= 2 and len(last_rsi_peaks) >= 2:
            price_hh = last_price_peaks[-1][1] > last_price_peaks[-2][1]
            rsi_lh = last_rsi_peaks[-1][1] < last_rsi_peaks[-2][1] * 0.95
            
            if price_hh and rsi_lh:
                result['divergence_detected'] = True
                result['warnings'].append("Momentum Divergence Forming")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 6. CALCULATE RUNNER PROBABILITY
    # ═══════════════════════════════════════════════════════════════════════
    signals_count = sum([
        result['momentum_detected'],
        result['momentum_memory'],
        result['rsi_staircase'],
        result['support_protected']
    ])
    
    if signals_count == 4:
        result['runner_probability'] = 'HIGH'
    elif signals_count >= 3:
        result['runner_probability'] = 'MEDIUM'
    elif signals_count >= 2:
        result['runner_probability'] = 'LOW'
    else:
        result['runner_probability'] = 'NONE'
    
    # ═══════════════════════════════════════════════════════════════════════
    # 7. FORMAT ALERT ADDITION
    # ═══════════════════════════════════════════════════════════════════════
    if result['runner_probability'] in ['HIGH', 'MEDIUM']:
        alert_lines = ["🔥 <b>RUNNER INTELLIGENCE</b>"]
        
        for signal in result['signals']:
            alert_lines.append(f"  • {signal}")
        
        alert_lines.append(f"\n<b>Runner Probability:</b> {result['runner_probability']}")
        
        if result['divergence_detected']:
            alert_lines.append("\n⚠️ <b>Momentum Divergence Forming</b>")
            alert_lines.append("Possible Runner Exhaustion")
        
        result['alert_addition'] = '\n'.join(alert_lines)
    
    elif result['divergence_detected']:
        result['alert_addition'] = "⚠️ Momentum Divergence Forming\nPossible Runner Exhaustion"
    
    return result


def format_runner_log(result: Dict) -> str:
    """Format runner intelligence for logging."""
    if result['runner_probability'] == 'NONE':
        return ""
    
    parts = []
    if result['momentum_detected']:
        parts.append(f"RSI>{int(result['rsi_max'])}")
    if result['momentum_memory']:
        parts.append(f"Memory>{int(result['pullback_floor'])}")
    if result['rsi_staircase']:
        parts.append("Staircase")
    if result['support_protected']:
        parts.append(f"Protected({result['entry_retests']})")
    if result['divergence_detected']:
        parts.append("⚠️DIV")
    
    return f"🏃 RUNNER: {result['runner_probability']} | {' | '.join(parts)}"
