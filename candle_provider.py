# RELIABILITY FIX APPLIED
"""
CANDLE PROVIDER v1.1
====================
Abstracted candle data fetching with:
- Primary: Birdeye API (uses TOKEN address)
- Fallback: GeckoTerminal (uses PAIR address)
- Caching with TTL to avoid re-fetching
- Rate limiting
- Graceful failures (never crash the cycle)
"""

import os
import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict


async def get_correct_pair_address(pair_address_lower: str) -> str:
    """
    DexScreener URLs use lowercase, but Birdeye needs correct case.
    Use DexScreener API to get the properly cased address.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address_lower}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            data = resp.json()
            if data.get('pairs'):
                return data['pairs'][0].get('pairAddress', pair_address_lower)
    except Exception as e:
        logger.debug(f"Could not get correct case for {pair_address_lower}: {e}")
    return pair_address_lower

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY', '')

# Cache settings
# Using selective cache from candle_cache.py
# Old global cache disabled - now uses priority-based caching
# Tier 1 (whale/breakout/active): ALWAYS fresh
# Tier 2/3 (quiet tokens): 90-120s cache max
from cache_tiers import (
    get_tiered_cache, store_tiered_cache, should_fetch_1m,
    assess_token_tier, get_tier_stats, cleanup_tiered_cache
)

from candle_cache import get_cached_candles as get_selective_cache, store_candles as store_selective_cache, should_use_cache, clear_expired_cache

CANDLE_CACHE: Dict[str, dict] = {}  # Legacy - kept for compatibility
# TIERED CACHE TTL
# Tier 1 (active edge): Uses fresh fetch, minimal cache
# Tier 2/3 (watchlist/background): Uses longer cache
CACHE_TTL_MINUTES = 30  # Default for most tokens (Tier 2/3)
CACHE_TTL_PRIORITY = 2  # For Tier 1 priority tokens  # Reduced from 5 - selective cache handles priority tokens

# Rate limiting
BIRDEYE_CALLS_TODAY = 0
BIRDEYE_DAILY_LIMIT = int(os.getenv('BIRDEYE_DAILY_CAP', '5000'))  # Configurable via .env

# Reliability state (added by reliability fix)
_BE_THRESH = {80: False, 90: False, 100: False}
_GECKO_COOLDOWN_UNTIL = None
_LAST_BE_CALL = 0.0
_BE_THROTTLE_SEC = 0.2
_GECKO_COOLDOWN_SECONDS = 60
_LAST_SUMMARY_DATE = None
_CALL_REASONS = {'birdeye_cap': 0, 'birdeye_non200': 0, 'gecko_429': 0,
                 'gecko_non200': 0, 'both_failed': 0}

def _send_owner_telegram(msg):
    try:
        import httpx as _hx
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        chat = os.getenv('HEARTBEAT_CHAT_ID', '') or os.getenv('OWNER_USER_ID', '')
        if not token or not chat:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        _hx.post(url, json={'chat_id': chat, 'text': msg}, timeout=8)
    except Exception as _e:
        logger.warning(f"Owner Telegram send failed: {_e}")

def _check_be_thresh():
    global _BE_THRESH
    if BIRDEYE_DAILY_LIMIT <= 0:
        return
    pct = (BIRDEYE_CALLS_TODAY / BIRDEYE_DAILY_LIMIT) * 100
    for t in (80, 90, 100):
        if pct >= t and not _BE_THRESH[t]:
            _BE_THRESH[t] = True
            msg = f"WARN Birdeye at {pct:.0f}% ({BIRDEYE_CALLS_TODAY}/{BIRDEYE_DAILY_LIMIT})"
            logger.info(f"[BIRDEYE-LIMIT] {msg}")
            if t >= 90:
                _send_owner_telegram(msg)

def _daily_rollover_check():
    global _BE_THRESH, _CALL_REASONS, _LAST_SUMMARY_DATE
    today = datetime.utcnow().date()
    if _LAST_SUMMARY_DATE is None:
        _LAST_SUMMARY_DATE = today
        return
    if today != _LAST_SUMMARY_DATE:
        try:
            summary = (
                f"CANDLE DAILY SUMMARY (UTC {_LAST_SUMMARY_DATE})\n"
                f"Birdeye: {PROVIDER_STATS.get('birdeye_success',0)} ok / "
                f"{PROVIDER_STATS.get('birdeye_fail',0)} fail "
                f"({BIRDEYE_CALLS_TODAY}/{BIRDEYE_DAILY_LIMIT})\n"
                f"Gecko: {PROVIDER_STATS.get('gecko_success',0)} ok / "
                f"{PROVIDER_STATS.get('gecko_fail',0)} fail\n"
                f"Cache hits: {PROVIDER_STATS.get('cache_hits',0)}\n"
                f"Skipped: {PROVIDER_STATS.get('skipped',0)}\n"
                f"Reasons: BE_cap={_CALL_REASONS['birdeye_cap']} "
                f"BE_non200={_CALL_REASONS['birdeye_non200']} "
                f"GK_429={_CALL_REASONS['gecko_429']} "
                f"both_failed={_CALL_REASONS['both_failed']}"
            )
            logger.info(f"[DAILY-SUMMARY] {summary}")
            _send_owner_telegram(summary)
        except Exception as _e:
            logger.warning(f"Daily summary error: {_e}")
        _BE_THRESH = {80: False, 90: False, 100: False}
        for k in _CALL_REASONS:
            _CALL_REASONS[k] = 0
        _LAST_SUMMARY_DATE = today
BIRDEYE_LAST_RESET = datetime.now().date()

# Stats
PROVIDER_STATS = {
    'birdeye_success': 0,
    'birdeye_fail': 0,
    'gecko_success': 0,
    'gecko_fail': 0,
    'cache_hits': 0,
    'skipped': 0
}


def reset_daily_limits():
    """Reset daily counters if new day"""
    global BIRDEYE_CALLS_TODAY, BIRDEYE_LAST_RESET
    today = datetime.now().date()
    if today > BIRDEYE_LAST_RESET:
        BIRDEYE_CALLS_TODAY = 0
        BIRDEYE_LAST_RESET = today
        logger.info("📊 Candle provider: Daily limits reset")


def get_cached_candles(address: str, token: dict = None) -> Optional[List[dict]]:
    """
    Check if we have fresh cached candles.
    Uses SELECTIVE caching - Tier 1 tokens always get fresh data.
    """
    # If we have token info, use selective cache
    if token:
        cached = get_selective_cache(token)
        if cached:
            PROVIDER_STATS['cache_hits'] += 1
            return cached
        return None
    
    # Fallback to basic cache for legacy calls
    cache_size = len(CANDLE_CACHE)
    in_cache = address in CANDLE_CACHE
    
    if in_cache:
        cached = CANDLE_CACHE[address]
        age = (datetime.now() - cached['fetched_at']).total_seconds() / 60
        if age < CACHE_TTL_MINUTES:
            PROVIDER_STATS['cache_hits'] += 1
            logger.info(f"Cache HIT: {address[:20]}... age={age:.1f}min")
            return cached['candles']
        else:
            logger.info(f"Cache EXPIRED: {address[:20]}... age={age:.1f}min > TTL={CACHE_TTL_MINUTES}")
    else:
        logger.info(f"Cache MISS: {address[:20]}... (cache has {cache_size} entries)")
    return None


def cache_candles(address: str, candles: List[dict], token: dict = None):
    """
    Store candles in cache.
    Uses SELECTIVE caching - only caches Tier 2/3 tokens.
    """
    # If we have token info, use selective cache
    if token:
        store_selective_cache(token, candles)
    
    # Also store in legacy cache
    CANDLE_CACHE[address] = {
        'candles': candles,
        'fetched_at': datetime.now()
    }
    # Prune old cache entries (keep last 500)
    if len(CANDLE_CACHE) > 500:
        oldest = sorted(CANDLE_CACHE.items(), key=lambda x: x[1]['fetched_at'])[:100]
        for addr, _ in oldest:
            del CANDLE_CACHE[addr]


async def fetch_candles_birdeye(token_address: str, symbol: str, pair_address: str = None) -> Optional[List[dict]]:
    """
    Fetch OHLCV from Birdeye API using TOKEN address.
    If only pair_address is provided, fetches the base token address from DexScreener.
    """
    # If we have a lowercase pair address, get the base token address from DexScreener
    if pair_address and (not token_address or token_address == pair_address):
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
                resp = await client.get(url, timeout=10)
                data = resp.json()
                if data.get('pairs'):
                    # Get the base token address (the actual token, not the LP)
                    token_address = data['pairs'][0].get('baseToken', {}).get('address')
                    logger.debug(f"📊 {symbol}: Got base token {token_address} from DexScreener")
        except Exception as e:
            logger.debug(f"📊 {symbol}: Could not get base token from DexScreener: {e}")
    global BIRDEYE_CALLS_TODAY
    
    reset_daily_limits()
    
    if not BIRDEYE_API_KEY:
        logger.debug(f"📊 {symbol}: No Birdeye API key")
        return None
    
    if BIRDEYE_CALLS_TODAY >= BIRDEYE_DAILY_LIMIT:
        _CALL_REASONS['birdeye_cap'] += 1
        _check_be_thresh()
        logger.info(f"BIRDEYE-CAP {symbol}: cap reached ({BIRDEYE_CALLS_TODAY}/{BIRDEYE_DAILY_LIMIT}) - falling back to Gecko")
        return None
    
    if not token_address or len(token_address) < 30:
        logger.debug(f"📊 {symbol}: Invalid token address")
        return None
    
    try:
        headers = {
            'X-API-KEY': BIRDEYE_API_KEY,
            'Accept': 'application/json'
        }
        
        # 5-minute candles, last 24 hours
        time_to = int(datetime.now().timestamp())
        time_from = time_to - 604800  # 7 days of candle history
        
        # Use TOKEN endpoint (not pair endpoint)
        url = f"https://public-api.birdeye.so/defi/ohlcv?address={token_address}&type=5m&time_from={time_from}&time_to={time_to}"
        
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        
        BIRDEYE_CALLS_TODAY += 1
        _check_be_thresh()
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', {}).get('items', [])
            
            if items and len(items) >= 10:
                candles = []
                for item in items:
                    candles.append({
                        'ts': int(item.get('unixTime', 0)),
                        'o': float(item.get('o', 0)),
                        'h': float(item.get('h', 0)),
                        'l': float(item.get('l', 0)),
                        'c': float(item.get('c', 0)),
                        'v': float(item.get('v', 0))
                    })
                candles.sort(key=lambda x: x['ts'])
                PROVIDER_STATS['birdeye_success'] += 1
                logger.info(f"📊 {symbol}: Birdeye ✓ ({len(candles)} candles) [{BIRDEYE_CALLS_TODAY}/{BIRDEYE_DAILY_LIMIT}]")
                return candles
            else:
                logger.debug(f"📊 {symbol}: Birdeye returned {len(items)} candles (need 10+)")
        else:
            _CALL_REASONS['birdeye_non200'] += 1
            logger.info(f"BIRDEYE-NON200 {symbol}: status={resp.status_code}")
        
        PROVIDER_STATS['birdeye_fail'] += 1
        return None
        
    except Exception as e:
        PROVIDER_STATS['birdeye_fail'] += 1
        logger.debug(f"📊 {symbol}: Birdeye error: {e}")
        return None


async def fetch_candles_geckoterminal(pair_address: str, symbol: str) -> Optional[List[dict]]:
    """
    Fallback: GeckoTerminal API (uses PAIR address).
    Often 404s for pump.fun pools but worth trying.
    """
    if not pair_address or len(pair_address) < 30:
        return None
    
    global _GECKO_COOLDOWN_UNTIL
    if _GECKO_COOLDOWN_UNTIL and datetime.now() < _GECKO_COOLDOWN_UNTIL:
        remaining = (_GECKO_COOLDOWN_UNTIL - datetime.now()).total_seconds()
        logger.debug(f"GECKO-COOLDOWN {symbol}: skipping ({remaining:.0f}s left)")
        PROVIDER_STATS['gecko_fail'] += 1
        return None
        
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pair_address}/ohlcv/minute?aggregate=5&limit=2016"
            )
        
        if resp.status_code == 429:
            _GECKO_COOLDOWN_UNTIL = datetime.now() + timedelta(seconds=_GECKO_COOLDOWN_SECONDS)
            _CALL_REASONS['gecko_429'] += 1
            logger.info(f"GECKO-429 {symbol}: rate-limited, cooling {_GECKO_COOLDOWN_SECONDS}s")
            PROVIDER_STATS['gecko_fail'] += 1
            return None
        
        if resp.status_code == 200:
            ohlcv = resp.json().get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            if len(ohlcv) >= 10:
                candles = sorted([
                    {'ts': int(c[0]), 'o': float(c[1]), 'h': float(c[2]), 'l': float(c[3]), 'c': float(c[4]), 'v': float(c[5])} 
                    for c in ohlcv
                ], key=lambda x: x['ts'])
                PROVIDER_STATS['gecko_success'] += 1
                logger.info(f"📊 {symbol}: GeckoTerminal ✓ ({len(candles)} candles)")
                return candles
        
        PROVIDER_STATS['gecko_fail'] += 1
        return None
        
    except Exception as e:
        PROVIDER_STATS['gecko_fail'] += 1
        return None


async def fetch_candles(pair_address: str, symbol: str, token_address: str = None) -> Optional[List[dict]]:
    """
    Main entry point: Fetch candles with caching and fallback.
    
    Order:
    1. Check cache (TTL 5 min)
    2. Try Birdeye with TOKEN address (primary)
    3. Try GeckoTerminal with PAIR address (fallback)
    4. Return None if all fail (graceful skip)
    """
    # ALWAYS use pair_address as cache key (stable identity)
    # token_address can vary or be None, but pair_address is always consistent
    cache_key = pair_address
    
    _daily_rollover_check()
    
    # Check cache first
    cached = get_cached_candles(cache_key)
    if cached:
        logger.info(f"📊 {symbol}: ✓ CACHE HIT ({len(cached)} candles)")
        return cached
    else:
        # Log cache miss with key for debugging
        logger.debug(f"📊 {symbol}: Cache miss (key: {cache_key[:20]}...)")
    
    # Try Birdeye with TOKEN address (primary)
    # Pass pair_address to get correct case from DexScreener API
    candles = await fetch_candles_birdeye(token_address or pair_address, symbol, pair_address)
    if candles:
        cache_candles(cache_key, candles)
        return candles
    
    # Small delay before fallback
    await asyncio.sleep(0.5)
    
    # Try GeckoTerminal with PAIR address (fallback)
    if pair_address:
        candles = await fetch_candles_geckoterminal(pair_address, symbol)
        if candles:
            cache_candles(cache_key, candles)
            return candles
    
    # All providers failed - log exact reason chain
    PROVIDER_STATS['skipped'] += 1
    _CALL_REASONS['both_failed'] += 1
    be_capped = BIRDEYE_CALLS_TODAY >= BIRDEYE_DAILY_LIMIT
    gk_cooling = _GECKO_COOLDOWN_UNTIL and datetime.now() < _GECKO_COOLDOWN_UNTIL
    parts = []
    if be_capped:
        parts.append(f"BE-CAP({BIRDEYE_CALLS_TODAY}/{BIRDEYE_DAILY_LIMIT})")
    if gk_cooling:
        parts.append("GK-COOLDOWN")
    if not parts:
        parts.append("both-empty")
    logger.info(f"NO-CANDLES {symbol}: {', '.join(parts)}")
    return None




# ══════════════════════════════════════════════════════════════════════════════
# DUAL TIMEFRAME FETCHING (1m + 5m)
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_candles_birdeye_1m(token_address: str, symbol: str, pair_address: str = None) -> Optional[List[dict]]:
    """
    Fetch 1-minute candles from Birdeye.
    Used for early detection + trigger timing (Hunter Mode).
    SAME structural standards as 5m - just faster.
    """
    global BIRDEYE_CALLS_TODAY
    
    if not token_address and not pair_address:
        return None
    
    reset_daily_limits()
    
    if BIRDEYE_CALLS_TODAY >= BIRDEYE_DAILY_LIMIT:
        logger.debug(f"📊 {symbol}: Birdeye daily limit reached")
        return None
    
    if pair_address and not token_address:
        token_address = await get_correct_pair_address(pair_address)
    
    if not BIRDEYE_API_KEY:
        return None
    
    try:
        headers = {
            'X-API-KEY': BIRDEYE_API_KEY,
            'Accept': 'application/json'
        }
        
        # 1-minute candles, last 2 hours (120 candles for new coins)
        time_to = int(datetime.now().timestamp())
        time_from = time_to - 7200  # 2 hours
        
        url = f"https://public-api.birdeye.so/defi/ohlcv?address={token_address}&type=1m&time_from={time_from}&time_to={time_to}"
        
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        
        BIRDEYE_CALLS_TODAY += 1
        _check_be_thresh()
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', {}).get('items', [])
            
            if items and len(items) >= 10:
                candles = []
                for item in items:
                    candles.append({
                        'ts': int(item.get('unixTime', 0)),
                        'o': float(item.get('o', 0)),
                        'h': float(item.get('h', 0)),
                        'l': float(item.get('l', 0)),
                        'c': float(item.get('c', 0)),
                        'v': float(item.get('v', 0))
                    })
                candles.sort(key=lambda x: x['ts'])
                logger.debug(f"📊 {symbol}: Birdeye 1m ✓ ({len(candles)} candles)")
                return candles
        
        return None
        
    except Exception as e:
        logger.debug(f"📊 {symbol}: Birdeye 1m error: {e}")
        return None


async def fetch_candles_dual(pair_address: str, symbol: str, token_address: str = None) -> dict:
    """
    Fetch BOTH 1m and 5m candles for dual-timeframe analysis.
    
    Returns dict with '5m', '1m', and 'primary' keys.
    """
    # Fetch 5m (primary structure) - uses existing cached system
    candles_5m = await fetch_candles(pair_address, symbol, token_address)
    
    # Fetch 1m (early detection) - no cache for freshness
    candles_1m = await fetch_candles_birdeye_1m(token_address or pair_address, symbol, pair_address)
    
    # Determine primary based on data quality
    primary = '5m'
    if candles_5m and len(candles_5m) >= 50:
        primary = '5m'
    elif candles_1m and len(candles_1m) >= 30:
        primary = '1m'
    
    return {
        '5m': candles_5m,
        '1m': candles_1m,
        'primary': primary
    }


def get_provider_stats() -> dict:
    """Get current provider statistics"""
    return {
        **PROVIDER_STATS,
        'birdeye_calls_today': BIRDEYE_CALLS_TODAY,
        'birdeye_limit': BIRDEYE_DAILY_LIMIT,
        'cache_size': len(CANDLE_CACHE)
    }


def log_provider_stats():
    """Log provider statistics"""
    stats = get_provider_stats()
    logger.info(f"📊 CANDLE PROVIDER STATS:")
    logger.info(f"   Birdeye: {stats['birdeye_success']} success, {stats['birdeye_fail']} fail ({stats['birdeye_calls_today']}/{stats['birdeye_limit']} today)")
    logger.info(f"   GeckoTerminal: {stats['gecko_success']} success, {stats['gecko_fail']} fail")
    logger.info(f"   Cache hits: {stats['cache_hits']} | Skipped: {stats['skipped']}")
