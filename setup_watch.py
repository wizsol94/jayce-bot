"""
WIZTHEORY SETUP WATCH v2.0
==========================
Alerts when structure breaks, signaling retrace has begun.

Triggers on BEARISH BOS after expansion - NOT distance-based.

WizTheory Process:
1. Valid impulse move detected
2. Fib levels calculated
3. Flip zone identified
4. Bearish Break of Structure occurs (retrace begins)
5. SETUP WATCH fires - "Price retrace beginning"
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Track recently alerted setups to avoid spam
WATCH_ALERTS_SENT = {}  # {token_address: timestamp}
WATCH_COOLDOWN_MINUTES = 60


def check_hunter_mode_timing(
    setup_type: str,
    current_price: float,
    fib_levels: Dict,
    candles: List[Dict],
    impulse_result: Dict
) -> Optional[Dict]:
    """
    HUNTER MODE: Setup-specific alert timing.
    
    Rules:
    - 382/50: Alert on first major rejection/exhaustion from expansion high
    - 618: Alert when price breaks below 382 level
    - 786: Alert when price breaks below 50 level
    - UNDER_FIB: Dynamic timing based on subtype urgency
    
    Returns alert_reason dict if timing is right, None otherwise.
    """
    
    fib_382 = fib_levels.get('382', 0)
    fib_50 = fib_levels.get('50', 0)
    fib_618 = fib_levels.get('618', 0)
    fib_786 = fib_levels.get('786', 0)
    
    impulse_data = impulse_result.get('impulse', {})
    expansion_high = impulse_data.get('breakout_high', 0)
    
    if setup_type in ['382', '50']:
        # Alert on first major rejection from expansion high
        # Check if price has pulled back 5-15% from high (exhaustion)
        if expansion_high <= 0:
            return None
        
        pullback_pct = ((expansion_high - current_price) / expansion_high) * 100
        
        if 5 <= pullback_pct <= 25:
            # Early rejection/exhaustion phase
            return {
                'trigger': 'REJECTION_FROM_HIGH',
                'reason': f'Price rejected {pullback_pct:.1f}% from expansion high',
                'urgency': 'HIGH' if pullback_pct >= 10 else 'EARLY'
            }
    
    elif setup_type == '618':
        # Alert when price breaks below 382 level
        if fib_382 <= 0:
            return None
        
        if current_price < fib_382:
            distance_below_382 = ((fib_382 - current_price) / fib_382) * 100
            return {
                'trigger': 'BROKE_382',
                'reason': f'Price broke below 382 ({distance_below_382:.1f}% below), heading to 618',
                'urgency': 'MODERATE'
            }
    
    elif setup_type == '786':
        # Alert when price breaks below 50 level
        if fib_50 <= 0:
            return None
        
        if current_price < fib_50:
            distance_below_50 = ((fib_50 - current_price) / fib_50) * 100
            return {
                'trigger': 'BROKE_50',
                'reason': f'Price broke below 50 ({distance_below_50:.1f}% below), heading to 786',
                'urgency': 'SLOWER'
            }
    
    elif setup_type == 'UNDER_FIB':
        # Under-Fib: Dynamic timing based on which fib is above destination
        # Determine subtype by checking which fib is closest above current price
        
        if current_price < fib_382 and current_price > fib_50:
            # Under-Fib 382 - FASTEST alert
            return {
                'trigger': 'UNDERFIB_382',
                'reason': 'Under-Fib 382 - destination zone approaching fast',
                'urgency': 'FASTEST'
            }
        elif current_price < fib_50 and current_price > fib_618:
            # Under-Fib 50 - EARLY alert
            return {
                'trigger': 'UNDERFIB_50',
                'reason': 'Under-Fib 50 - destination zone approaching',
                'urgency': 'EARLY'
            }
        elif current_price < fib_618 and current_price > fib_786:
            # Under-Fib 618 - MODERATE alert
            return {
                'trigger': 'UNDERFIB_618',
                'reason': 'Under-Fib 618 - destination zone in range',
                'urgency': 'MODERATE'
            }
        elif current_price < fib_786:
            # Under-Fib 786 - SLOWER alert
            return {
                'trigger': 'UNDERFIB_786',
                'reason': 'Under-Fib 786 - deep retrace to destination',
                'urgency': 'SLOWER'
            }
    
    return None



def detect_bearish_bos(candles: List[Dict], lookback: int = 20) -> Optional[Dict]:
    """
    Detect bearish break of structure.
    BOS = price breaks below last swing low, lower low forms.
    """
    if len(candles) < lookback:
        return None
    
    recent = candles[-lookback:]
    
    # Find swing lows in recent candles
    swing_lows = []
    for i in range(2, len(recent) - 2):
        low = float(recent[i].get('low') or recent[i].get('l') or 0)
        prev_low = float(recent[i-1].get('low') or recent[i-1].get('l') or 0)
        prev2_low = float(recent[i-2].get('low') or recent[i-2].get('l') or 0)
        next_low = float(recent[i+1].get('low') or recent[i+1].get('l') or 0)
        next2_low = float(recent[i+2].get('low') or recent[i+2].get('l') or 0)
        
        if low < prev_low and low < prev2_low and low < next_low and low < next2_low:
            swing_lows.append({'index': i, 'price': low})
    
    if len(swing_lows) < 2:
        return None
    
    # Check if most recent swing low is LOWER than previous (bearish BOS)
    last_swing = swing_lows[-1]
    prev_swing = swing_lows[-2]
    
    if last_swing['price'] < prev_swing['price']:
        # Bearish BOS confirmed - lower low formed
        return {
            'detected': True,
            'type': 'bearish',
            'broken_level': prev_swing['price'],
            'new_low': last_swing['price'],
            'index': last_swing['index']
        }
    
    return None


def check_setup_watch(
    symbol: str,
    token_address: str,
    current_price: float,
    impulse_result: Dict,
    candles: List[Dict],
    structure_result: Dict = None
) -> Optional[Dict]:
    """
    Check if token qualifies for SETUP WATCH alert.
    
    Triggers when:
    1. Valid impulse detected
    2. Flip zone identified
    3. Bearish BOS occurs (retrace beginning)
    """
    
    # Check cooldown
    if token_address in WATCH_ALERTS_SENT:
        last_alert = WATCH_ALERTS_SENT[token_address]
        if datetime.now() - last_alert < timedelta(minutes=WATCH_COOLDOWN_MINUTES):
            return None
    
    # Condition 1: Impulse detected with valid setup
    if not impulse_result.get('setup_detected', False):
        return None
    
    setup_type = impulse_result.get('setup_type')
    if not setup_type:
        return None
    
    # Condition 2: Get impulse data
    impulse_data = impulse_result.get('impulse', {})
    expansion_pct = impulse_data.get('expansion_pct', 0)
    impulse_score = impulse_data.get('score', 0)
    
    # Need decent impulse (minimum threshold)
    if impulse_score < 50 and expansion_pct < 25:
        return None
    
    # Condition 3: Get flip zone
    flip_zone = impulse_result.get('flip_zone', {})
    zone_origin = flip_zone.get('origin', 0)
    if zone_origin <= 0:
        return None
    
    # Condition 4: HUNTER MODE - Setup-specific timing
    fib_levels = impulse_result.get('fib_levels', {})
    
    hunter_timing = check_hunter_mode_timing(
        setup_type=setup_type,
        current_price=current_price,
        fib_levels=fib_levels,
        candles=candles,
        impulse_result=impulse_result
    )
    
    if not hunter_timing:
        # Fallback: Check for generic bearish BOS as early warning
        bos = detect_bearish_bos(candles)
        if not bos or not bos.get('detected'):
            if structure_result:
                bos_list = structure_result.get('bos', [])
                bearish_bos = [b for b in bos_list if b.get('direction') == 'bearish']
                if not bearish_bos:
                    return None
            else:
                return None
        # BOS detected but Hunter Mode timing not met - don't alert yet
        return None
    
    # Condition 5: Price should be above zone (retrace hasn't reached entry yet)
    if current_price <= 0 or zone_origin <= 0:
        return None
    
    if current_price < zone_origin * 0.90:
        # Already at/below zone - too late for watch (use 90% buffer)
        return None
    
    # All conditions met - create SETUP WATCH alert (Hunter Mode)
    target_fib = fib_levels.get(setup_type, zone_origin)
    
    alert_data = {
        'type': 'SETUP_WATCH',
        'symbol': symbol,
        'token_address': token_address,
        'setup_type': setup_type,
        'expansion_pct': round(expansion_pct, 1),
        'impulse_score': impulse_score,
        'zone_origin': zone_origin,
        'target_fib': target_fib,
        'current_price': current_price,
        'hunter_trigger': hunter_timing.get('trigger', 'UNKNOWN'),
        'hunter_reason': hunter_timing.get('reason', ''),
        'hunter_urgency': hunter_timing.get('urgency', 'NORMAL'),
        'retrace_status': 'HUNTER_MODE',
        'flip_zone_strength': flip_zone.get('strength', 'UNKNOWN'),
        'timestamp': datetime.now().isoformat()
    }
    
    # Mark as alerted
    WATCH_ALERTS_SENT[token_address] = datetime.now()
    
    return alert_data


def format_setup_watch_message(alert_data: Dict) -> str:
    """Format the SETUP WATCH Telegram message."""
    
    symbol = alert_data.get('symbol', '???')
    setup_type = alert_data.get('setup_type', '???')
    expansion = alert_data.get('expansion_pct', 0)
    impulse_score = alert_data.get('impulse_score', 0)
    zone_origin = alert_data.get('zone_origin', 0)
    target_fib = alert_data.get('target_fib', 0)
    current_price = alert_data.get('current_price', 0)
    bos_level = alert_data.get('bos_level', 0)
    zone_strength = alert_data.get('flip_zone_strength', '?')
    
    # Format prices
    def fmt_price(p):
        if p >= 1:
            return f"${p:,.4f}"
        elif p >= 0.001:
            return f"${p:.6f}"
        else:
            return f"${p:.10f}"
    
    # Get Hunter Mode fields
    hunter_trigger = alert_data.get('hunter_trigger', '')
    hunter_reason = alert_data.get('hunter_reason', '')
    hunter_urgency = alert_data.get('hunter_urgency', 'NORMAL')
    
    # Urgency emoji
    urgency_emoji = {
        'FASTEST': '🔴',
        'HIGH': '🟠', 
        'EARLY': '🟡',
        'MODERATE': '🟢',
        'SLOWER': '🔵',
        'NORMAL': '⚪'
    }.get(hunter_urgency, '⚪')
    
    message = f"""🎯 <b>HUNTER MODE ALERT</b>

<b>Token:</b> ${symbol}
<b>Setup:</b> {setup_type} + Flip Zone

{urgency_emoji} <b>Trigger:</b> {hunter_trigger}
<i>{hunter_reason}</i>

📊 <b>Impulse Data:</b>
- Expansion: {expansion:.0f}%
- Impulse Score: {impulse_score}/100
- Zone Strength: {zone_strength}

📍 <b>Levels:</b>
- Flip Zone: {fmt_price(zone_origin)}
- Entry Target: {fmt_price(target_fib)}
- Current Price: {fmt_price(current_price)}

⏳ <b>Urgency:</b> {hunter_urgency}
<i>Alert fired BEFORE entry zone — prepare for setup.</i>"""
    
    return message


def clear_old_alerts():
    """Clear alerts older than cooldown period."""
    global WATCH_ALERTS_SENT
    cutoff = datetime.now() - timedelta(minutes=WATCH_COOLDOWN_MINUTES)
    WATCH_ALERTS_SENT = {
        addr: ts for addr, ts in WATCH_ALERTS_SENT.items()
        if ts > cutoff
    }


if __name__ == '__main__':
    print("SETUP WATCH v2.0 - BOS-Based Trigger")
    print("=" * 50)
    print("Triggers when bearish BOS detected after expansion")
    print("NOT distance-based")
