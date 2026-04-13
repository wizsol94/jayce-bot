"""
WHALE CONVICTION SYSTEM v1.0
============================
2-Layer whale detection system:

LAYER 1 - Whale Presence (Holdings Check)
- TRUE if any tracked wallet currently holds the token

LAYER 2 - Whale Conviction (Holdings + Strength)
- TRUE only if:
  - Whale Presence = TRUE
  - AND breakout/expansion confirmed (using existing metrics)

Tracked Whales:
- GET RICH WHALE: CNudZYFgpbT26fidsiNrWfHeGTBMMeVWqruZXsEkcUPc
- GAKE: DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm
- GAKE ALT: EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt
- ANSEM: AVAZvHLR2PcWpDcf8BXY4rVxNHYRBytycHkcB5z5QNXYm
- FRANKDEGOD: 498g1rVnFcnjBjpfw1xyqA1WvgQXUU8RWuELjxkjAayQ
- TRADERPOW ALT: DwtF6KdjB9xgzKhCvcxKQLGU1NezdFFdVo8tLzSb7C8W
"""

import os
import logging
import httpx
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Tracked whale wallets
TRACKED_WHALES = {
    "CNudZYFgpbT26fidsiNrWfHeGTBMMeVWqruZXsEkcUPc": "GET RICH WHALE",
    "DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm": "GAKE",
    "EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt": "GAKE ALT",
    "AVAZvHLR2PcWpDcf8BXY4rVxNHYRBytycHkcB5z5QNXYm": "ANSEM",
    "498g1rVnFcnjBjpfw1xyqA1WvgQXUU8RWuELjxkjAayQ": "FRANKDEGOD",
    "DwtF6KdjB9xgzKhCvcxKQLGU1NezdFFdVo8tLzSb7C8W": "TRADERPOW ALT",
}

BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
BIRDEYE_WALLET_URL = "https://public-api.birdeye.so/v1/wallet/token_list"

# Cache to avoid repeated API calls (wallet -> {tokens: set, timestamp})
WALLET_HOLDINGS_CACHE: Dict[str, dict] = {}
CACHE_TTL_MINUTES = 5  # Refresh holdings every 5 minutes

# Conviction strength thresholds (using existing metrics)
MIN_EXPANSION_FOR_CONVICTION = 30  # 30% expansion minimum
MIN_BREAKOUT_FOR_CONVICTION = 20   # 20% breakout minimum


async def get_wallet_holdings(wallet_address: str) -> set:
    """
    Fetch current token holdings for a wallet from Birdeye.
    Returns set of token addresses held by this wallet.
    Uses caching to minimize API calls.
    """
    now = datetime.now()
    
    # Check cache
    if wallet_address in WALLET_HOLDINGS_CACHE:
        cached = WALLET_HOLDINGS_CACHE[wallet_address]
        cache_age = (now - cached['timestamp']).total_seconds() / 60
        if cache_age < CACHE_TTL_MINUTES:
            return cached['tokens']
    
    # Fetch from Birdeye
    tokens = set()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BIRDEYE_WALLET_URL,
                params={"wallet": wallet_address},
                headers={"X-API-KEY": BIRDEYE_API_KEY}
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and 'data' in data:
                    items = data['data'].get('items', [])
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                
                for item in items:
                    addr = item.get('address', '')
                    balance = float(item.get('uiAmount', 0) or 0)
                    # Only count if balance > 0
                    if addr and balance > 0:
                        tokens.add(addr)
                
                logger.debug(f"[WHALE] {TRACKED_WHALES.get(wallet_address, wallet_address[:8])}: {len(tokens)} tokens held")
            else:
                logger.warning(f"[WHALE] Birdeye wallet API error: {resp.status_code}")
    except Exception as e:
        logger.warning(f"[WHALE] Holdings fetch error for {wallet_address[:8]}: {e}")
    
    # Update cache
    WALLET_HOLDINGS_CACHE[wallet_address] = {
        'tokens': tokens,
        'timestamp': now
    }
    
    return tokens


async def check_whale_presence(token_address: str) -> Dict:
    """
    LAYER 1: Check if any tracked whale currently holds this token.
    
    Returns:
        {
            'detected': bool,
            'holding_wallets': [{'wallet': str, 'name': str}, ...]
        }
    """
    holding_wallets = []
    
    for wallet, name in TRACKED_WHALES.items():
        try:
            holdings = await get_wallet_holdings(wallet)
            if token_address in holdings:
                holding_wallets.append({
                    'wallet': wallet,
                    'name': name
                })
        except Exception as e:
            logger.debug(f"[WHALE] Error checking {name}: {e}")
    
    return {
        'detected': len(holding_wallets) > 0,
        'holding_wallets': holding_wallets
    }


def check_strength_confirmed(engine_result: dict, impulse_result: dict = None) -> Dict:
    """
    Check if breakout/expansion strength is confirmed.
    Uses EXISTING metrics from engine/impulse detection.
    
    Returns:
        {
            'confirmed': bool,
            'expansion_pct': float,
            'breakout_pct': float,
            'reason': str
        }
    """
    expansion_pct = 0
    breakout_pct = 0
    
    # Get expansion from engine result
    if engine_result:
        expansion_pct = engine_result.get('impulse_pct', 0) or engine_result.get('expansion_pct', 0)
        breakout_pct = engine_result.get('breakout_pct', 0)
    
    # Get from impulse result if available
    if impulse_result:
        impulse_data = impulse_result.get('impulse', {})
        if not expansion_pct:
            expansion_pct = impulse_data.get('expansion_pct', 0)
        if not breakout_pct:
            breakout_pct = impulse_data.get('breakout_pct', 0)
    
    # Check thresholds
    has_expansion = expansion_pct >= MIN_EXPANSION_FOR_CONVICTION
    has_breakout = breakout_pct >= MIN_BREAKOUT_FOR_CONVICTION
    
    confirmed = has_expansion or has_breakout
    
    if confirmed:
        if has_expansion and has_breakout:
            reason = f"Expansion {expansion_pct:.0f}% + Breakout {breakout_pct:.0f}%"
        elif has_expansion:
            reason = f"Expansion {expansion_pct:.0f}%"
        else:
            reason = f"Breakout {breakout_pct:.0f}%"
    else:
        reason = f"Weak (Exp: {expansion_pct:.0f}%, BO: {breakout_pct:.0f}%)"
    
    return {
        'confirmed': confirmed,
        'expansion_pct': expansion_pct,
        'breakout_pct': breakout_pct,
        'reason': reason
    }


async def get_whale_conviction(
    token_address: str,
    engine_result: dict = None,
    impulse_result: dict = None
) -> Dict:
    """
    FULL WHALE CONVICTION CHECK (2-Layer System)
    
    Layer 1: Whale Presence (holdings)
    Layer 2: Whale Conviction (holdings + strength)
    
    Returns:
        {
            'whale_detected': bool,        # Layer 1 result
            'whale_conviction': bool,      # Layer 2 result
            'holding_wallets': list,       # Which whales hold it
            'strength_confirmed': bool,    # Breakout/expansion met
            'strength_reason': str,        # Why strength passed/failed
            'conviction_summary': str      # Human readable summary
        }
    """
    # Layer 1: Check holdings
    presence = await check_whale_presence(token_address)
    whale_detected = presence['detected']
    holding_wallets = presence['holding_wallets']
    
    # Layer 2: Check strength (only if whale detected)
    if whale_detected:
        strength = check_strength_confirmed(engine_result, impulse_result)
        strength_confirmed = strength['confirmed']
        strength_reason = strength['reason']
        
        # Conviction = Holdings + Strength
        whale_conviction = strength_confirmed
        
        if whale_conviction:
            wallet_names = [w['name'] for w in holding_wallets]
            conviction_summary = f"🐋 {', '.join(wallet_names)} holding + {strength_reason}"
        else:
            wallet_names = [w['name'] for w in holding_wallets]
            conviction_summary = f"🐋 {', '.join(wallet_names)} holding but {strength_reason}"
    else:
        strength_confirmed = False
        strength_reason = "N/A"
        whale_conviction = False
        conviction_summary = "No tracked whales holding"
    
    return {
        'whale_detected': whale_detected,
        'whale_conviction': whale_conviction,
        'holding_wallets': holding_wallets,
        'strength_confirmed': strength_confirmed,
        'strength_reason': strength_reason,
        'conviction_summary': conviction_summary
    }


def format_whale_for_alert(conviction_result: dict) -> tuple:
    """
    Format whale info for alert display.
    
    Returns:
        (whale_detected_text, whale_conviction_text)
    """
    if conviction_result['whale_detected']:
        names = [w['name'] for w in conviction_result['holding_wallets']]
        detected_text = f"Yes ({', '.join(names)})"
    else:
        detected_text = "No"
    
    if conviction_result['whale_conviction']:
        conviction_text = f"Yes ✅"
    else:
        conviction_text = "No"
    
    return detected_text, conviction_text
