"""
PRE-ALERT SYSTEM v1.0
=====================
Early warning system for setups that are FORMING but not yet confirmed.

Detects when price is approaching a valid fib zone.
Does NOT require RSI conditions.
Visually distinct from full alerts.

States:
- APPROACHING: Price 10-15% from zone
- TESTING: Price 5-10% from zone
- WEAK_REACTION: Price touched zone, weak bounce
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cooldown tracking
PRE_ALERT_COOLDOWNS: Dict[str, Dict[str, datetime]] = {}
COOLDOWN_MINUTES = 60

@dataclass
class PreAlertResult:
    should_alert: bool = False
    state: str = ""
    setup_type: str = ""
    distance_pct: float = 0
    zone_price: float = 0
    current_price: float = 0
    message: str = ""


def get_fib_zones(fib_levels: dict) -> List[Tuple[str, float, float, float]]:
    """
    Get fib zones with their ranges.
    Returns list of (name, level_price, zone_top, zone_bottom)
    """
    zones = []
    
    fib_382 = fib_levels.get('382', 0)
    fib_50 = fib_levels.get('50', 0)
    fib_618 = fib_levels.get('618', 0)
    fib_786 = fib_levels.get('786', 0)
    
    if fib_382 > 0:
        tolerance = fib_382 * 0.03
        zones.append(('382', fib_382, fib_382 + tolerance, fib_382 - tolerance))
    
    if fib_50 > 0:
        tolerance = fib_50 * 0.03
        zones.append(('50', fib_50, fib_50 + tolerance, fib_50 - tolerance))
    
    if fib_618 > 0:
        tolerance = fib_618 * 0.03
        zones.append(('618', fib_618, fib_618 + tolerance, fib_618 - tolerance))
    
    if fib_786 > 0:
        tolerance = fib_786 * 0.03
        zones.append(('786', fib_786, fib_786 + tolerance, fib_786 - tolerance))
    
    return zones


def check_cooldown(token_address: str, state: str) -> bool:
    """Check if we're in cooldown for this token/state combo."""
    key = f"{token_address}:{state}"
    if token_address in PRE_ALERT_COOLDOWNS:
        if state in PRE_ALERT_COOLDOWNS[token_address]:
            last_alert = PRE_ALERT_COOLDOWNS[token_address][state]
            if datetime.now() - last_alert < timedelta(minutes=COOLDOWN_MINUTES):
                return True
    return False


def set_cooldown(token_address: str, state: str):
    """Set cooldown for this token/state."""
    if token_address not in PRE_ALERT_COOLDOWNS:
        PRE_ALERT_COOLDOWNS[token_address] = {}
    PRE_ALERT_COOLDOWNS[token_address][state] = datetime.now()


def check_pre_alert(
    token_address: str,
    symbol: str,
    current_price: float,
    fib_levels: dict,
    psef_passed: bool,
    already_alerted: bool = False
) -> PreAlertResult:
    """
    Check if token qualifies for a pre-alert.
    
    Requirements:
    - Token passed PSEF (valid environment)
    - Price is approaching a valid fib zone
    - Not already fully alerted
    - Not in cooldown
    
    NO RSI requirement.
    """
    result = PreAlertResult()
    
    # Must pass PSEF
    if not psef_passed:
        return result
    
    # Skip if already got full alert
    if already_alerted:
        return result
    
    if current_price <= 0:
        return result
    
    zones = get_fib_zones(fib_levels)
    if not zones:
        return result
    
    # Find closest zone BELOW current price (price approaching from above)
    best_zone = None
    best_distance = float('inf')
    
    for zone_name, zone_level, zone_top, zone_bottom in zones:
        if zone_level <= 0:
            continue
        
        # Calculate distance as percentage
        if current_price > zone_level:
            # Price above zone - approaching
            distance_pct = ((current_price - zone_level) / zone_level) * 100
            
            if distance_pct < best_distance and distance_pct <= 15:
                best_distance = distance_pct
                best_zone = (zone_name, zone_level, zone_top, zone_bottom, distance_pct)
        
        elif zone_bottom <= current_price <= zone_top:
            # Price IN the zone - testing
            best_distance = 0
            best_zone = (zone_name, zone_level, zone_top, zone_bottom, 0)
            break
    
    if not best_zone:
        return result
    
    zone_name, zone_level, zone_top, zone_bottom, distance_pct = best_zone
    
    # Determine state
    if distance_pct == 0:
        state = "TESTING"
    elif distance_pct <= 5:
        state = "TESTING"
    elif distance_pct <= 10:
        state = "APPROACHING"
    elif distance_pct <= 15:
        state = "APPROACHING"
    else:
        return result
    
    # Check cooldown
    if check_cooldown(token_address, state):
        return result
    
    # Build result
    result.should_alert = True
    result.state = state
    result.setup_type = f"{zone_name} + Flip Zone"
    result.distance_pct = distance_pct
    result.zone_price = zone_level
    result.current_price = current_price
    
    # Set cooldown
    set_cooldown(token_address, state)
    
    return result


def format_pre_alert_message(
    symbol: str,
    token_address: str,
    result: PreAlertResult,
    rsi: float = 0
) -> str:
    """
    Format pre-alert for Telegram.
    Visually distinct from full alerts.
    """
    state_emoji = {
        "APPROACHING": "🔜",
        "TESTING": "🎯",
        "WEAK_REACTION": "⚡"
    }
    
    emoji = state_emoji.get(result.state, "👁️")
    
    # RSI info (optional, not required)
    rsi_text = f"📊 RSI: {rsi:.0f}" if rsi > 0 else ""
    
    message = f"""👁️ SETUP FORMING: ${symbol}
━━━━━━━━━━━━━━━━━━━━
📐 Type: {result.setup_type}
{emoji} State: {result.state}
📏 Distance: {result.distance_pct:.1f}% to zone
💰 Zone: ${result.zone_price:.8f}
📍 Price: ${result.current_price:.8f}
{rsi_text}

🔗 CA: {token_address}"""
    
    return message.strip()


def clear_expired_cooldowns():
    """Clean up old cooldowns."""
    now = datetime.now()
    expired_tokens = []
    
    for token_address, states in PRE_ALERT_COOLDOWNS.items():
        expired_states = []
        for state, timestamp in states.items():
            if now - timestamp > timedelta(minutes=COOLDOWN_MINUTES * 2):
                expired_states.append(state)
        
        for state in expired_states:
            del PRE_ALERT_COOLDOWNS[token_address][state]
        
        if not PRE_ALERT_COOLDOWNS[token_address]:
            expired_tokens.append(token_address)
    
    for token in expired_tokens:
        del PRE_ALERT_COOLDOWNS[token]
