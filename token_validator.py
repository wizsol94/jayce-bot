"""
TOKEN VALIDATOR v2.0

Strict validation layer to ensure ALL tokens match DexScreener UI filters.
Now includes PROFILE check.

Filters:
- Chain: Solana ONLY
- DEX: PumpFun + PumpSwap ONLY  
- Min Liquidity: $10,000
- Min Market Cap: $100,000
- Min Age: 1 hour (3600 seconds)
- Profile: MUST HAVE (websites or socials)
"""

import httpx
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Filter constants
ALLOWED_CHAIN = "solana"
ALLOWED_DEXES = {"pumpfun", "pumpswap", "pump.fun", "pump-fun", "raydium"}
MIN_LIQUIDITY = 10000
MIN_MARKET_CAP = 100000
MIN_AGE_SECONDS = 3600  # 1 hour


async def fetch_token_details(pair_address: str) -> Optional[Dict]:
    """Fetch token details from DexScreener API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get('pairs', []) or data.get('pair', [])
                if pairs:
                    return pairs[0] if isinstance(pairs, list) else pairs
    except Exception as e:
        logger.debug(f"Failed to fetch {pair_address}: {e}")
    return None


def validate_token(token_data: Dict) -> Tuple[bool, str]:
    """
    Validate a token against all required filters.
    
    Returns:
        (passed: bool, reason: str)
    """
    # Check chain
    chain = token_data.get('chainId', '').lower()
    if chain != ALLOWED_CHAIN:
        return False, f"CHAIN:{chain}"
    
    # Check DEX
    dex = token_data.get('dexId', '').lower()
    if dex not in ALLOWED_DEXES:
        return False, f"DEX:{dex}"
    
    # Check liquidity
    liquidity = float(token_data.get('liquidity', {}).get('usd', 0) or 0)
    if liquidity < MIN_LIQUIDITY:
        return False, f"LIQ:${liquidity:,.0f} (need ${MIN_LIQUIDITY:,})"
    
    # Check market cap
    market_cap = float(token_data.get('marketCap', 0) or token_data.get('fdv', 0) or 0)
    if market_cap < MIN_MARKET_CAP:
        return False, f"MC:${market_cap:,.0f} (need ${MIN_MARKET_CAP:,})"
    
    # Check age (pairCreatedAt is in milliseconds)
    created_at = token_data.get('pairCreatedAt', 0)
    if created_at:
        age_seconds = (datetime.now().timestamp() * 1000 - created_at) / 1000
        if age_seconds < MIN_AGE_SECONDS:
            age_minutes = age_seconds / 60
            return False, f"AGE:{age_minutes:.0f}min (need 60min)"
    
    # Check PROFILE - must have websites OR socials
    info = token_data.get('info', {})
    websites = info.get('websites', [])
    socials = info.get('socials', [])
    
    has_profile = bool(websites) or bool(socials)
    
    if not has_profile:
        return False, "NO_PROFILE"
    
    # All checks passed
    return True, "OK"


async def validate_tokens_batch(tokens: List[Dict], source: str) -> List[Dict]:
    """
    Validate a batch of tokens and return only those that pass all filters.
    """
    validated = []
    failed_count = 0
    no_profile_count = 0
    
    logger.info(f"[VALIDATOR] Validating {len(tokens)} tokens from {source}")
    
    for token in tokens:
        symbol = token.get('symbol', '???')
        pair_address = token.get('pair_address', '')
        
        if not pair_address or len(pair_address) < 30:
            logger.debug(f"[VALIDATOR] ❌ {symbol} | NO_ADDRESS")
            failed_count += 1
            continue
        
        # Fetch full token details from API
        details = await fetch_token_details(pair_address)
        
        if not details:
            # If we can't fetch details, skip the token (be strict)
            logger.debug(f"[VALIDATOR] ❌ {symbol} | FETCH_FAILED")
            failed_count += 1
            continue
        
        # Validate against filters
        passed, reason = validate_token(details)
        
        if passed:
            # Enrich token with validated data
            token['validated'] = True
            token['liquidity'] = float(details.get('liquidity', {}).get('usd', 0) or 0)
            token['market_cap'] = float(details.get('marketCap', 0) or 0)
            token['dex'] = details.get('dexId', '')
            validated.append(token)
        else:
            failed_count += 1
            if "NO_PROFILE" in reason:
                no_profile_count += 1
            logger.info(f"[VALIDATOR] ❌ {symbol} | {source} | {reason}")
    
    logger.info(f"[VALIDATOR] {source}: {len(validated)}/{len(tokens)} passed ({failed_count} filtered, {no_profile_count} no profile)")
    
    return validated


def validate_token_sync(token_data: Dict) -> Tuple[bool, str]:
    """Synchronous version for simple validation without API fetch."""
    return validate_token(token_data)


def quick_filter(tokens: List[Dict]) -> List[Dict]:
    """Quick filter using data already in token dict."""
    filtered = []
    for t in tokens:
        mc = t.get('market_cap', 0) or t.get('marketCap', 0)
        liq = t.get('liquidity', 0)
        dex = t.get('dex', '').lower()
        
        if mc and mc < MIN_MARKET_CAP:
            continue
        if liq and liq < MIN_LIQUIDITY:
            continue
        if dex and dex not in ALLOWED_DEXES:
            continue
        
        filtered.append(t)
    
    return filtered
