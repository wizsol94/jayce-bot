"""
QUIET MOVERS SOURCE v1.0 — SUPPLEMENTAL DISCOVERY
==================================================
Phase 1 of intake upgrade.

PURPOSE: Catch tokens showing momentum that aren't on the main ranked page yet.
This is SUPPLEMENTAL to the main DEX scan, NOT a replacement.

GUARDRAILS (LOCKED):
- Solana only
- PumpFun + PumpSwap only (NO Raydium, NO Meteora, NO Orca)
- Age >= 1 hour (for quiet movers only)
- MC >= $100,000
- Liquidity >= $10,000
- Momentum: +20-200% in 1h OR +25-300% in 6h

NOTE: This does NOT affect the main DEX ranked-page scan which has NO age limit.
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# GUARDRAILS (LOCKED - DO NOT MODIFY WITHOUT APPROVAL)
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_DEXES = {'pumpfun', 'pumpswap'}  # NO Raydium, NO Meteora, NO Orca
MIN_MARKET_CAP = 100_000
MIN_LIQUIDITY = 10_000
MIN_AGE_HOURS = 1  # For quiet movers only

# Momentum thresholds
MIN_GAIN_1H = 20
MAX_GAIN_1H = 200
MIN_GAIN_6H = 25
MAX_GAIN_6H = 300

# Dead chart filters
MIN_VOLUME_24H = 3_000
MIN_TRANSACTIONS_24H = 30


def _validate_quiet_mover(pair: dict) -> Tuple[bool, str]:
    """Validate pair against quiet mover guardrails. Returns (valid, reason)."""
    
    # Chain
    if pair.get('chainId') != 'solana':
        return False, 'not_solana'
    
    # DEX — STRICT: only pumpfun and pumpswap
    dex = pair.get('dexId', '').lower()
    if dex not in ALLOWED_DEXES:
        return False, f'bad_dex_{dex}'
    
    # Market cap
    mc = float(pair.get('marketCap', 0) or 0)
    if mc < MIN_MARKET_CAP:
        return False, 'mc_low'
    
    # Liquidity
    liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
    if liq < MIN_LIQUIDITY:
        return False, 'liq_low'
    
    # Age (quiet movers only — main scan has no age limit)
    created_at = pair.get('pairCreatedAt')
    if created_at:
        try:
            age_hours = (datetime.now().timestamp() * 1000 - created_at) / (1000 * 60 * 60)
            if age_hours < MIN_AGE_HOURS:
                return False, 'too_young'
        except:
            pass
    
    # Momentum check
    pc = pair.get('priceChange', {})
    h1 = float(pc.get('h1', 0) or 0)
    h6 = float(pc.get('h6', 0) or 0)
    h24 = float(pc.get('h24', 0) or 0)
    
    has_momentum = (
        (MIN_GAIN_1H <= h1 <= MAX_GAIN_1H) or
        (MIN_GAIN_6H <= h6 <= MAX_GAIN_6H) or
        (h24 >= 50 and h1 >= 10)
    )
    
    if not has_momentum:
        return False, 'no_momentum'
    
    # Volume
    vol = float(pair.get('volume', {}).get('h24', 0) or 0)
    if vol < MIN_VOLUME_24H:
        return False, 'vol_low'
    
    # Transactions
    txns = pair.get('txns', {}).get('h24', {})
    total_txns = (txns.get('buys', 0) or 0) + (txns.get('sells', 0) or 0)
    if total_txns < MIN_TRANSACTIONS_24H:
        return False, 'txns_low'
    
    return True, 'valid'


async def fetch_quiet_movers(existing_tokens: Set[str] = None) -> Tuple[List[dict], dict]:
    """
    Fetch quiet movers — tokens with momentum not on main ranked page.
    
    Returns: (tokens_list, stats_dict)
    """
    existing_tokens = existing_tokens or set()
    tokens = []
    seen = set()
    stats = {'checked': 0, 'passed': 0, 'rejected': {}}
    
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    
    async with httpx.AsyncClient(timeout=30) as client:
        
        # Search terms to find PumpFun/PumpSwap tokens
        terms = ['pump', 'pumpswap', 'sol', 'meme', 'pepe', 'dog', 'cat', 'ai', 'wojak', 'chad', 'frog', 'trump', 'elon', 'doge']
        
        for term in terms:
            try:
                resp = await client.get(
                    f'https://api.dexscreener.com/latest/dex/search?q={term}',
                    headers=headers
                )
                if resp.status_code != 200:
                    continue
                
                for pair in resp.json().get('pairs', []):
                    token_addr = pair.get('baseToken', {}).get('address', '')
                    
                    if not token_addr or token_addr in existing_tokens or token_addr in seen:
                        continue
                    
                    stats['checked'] += 1
                    valid, reason = _validate_quiet_mover(pair)
                    
                    if not valid:
                        stats['rejected'][reason] = stats['rejected'].get(reason, 0) + 1
                        continue
                    
                    tokens.append({
                        'address': token_addr,
                        'pair_address': pair.get('pairAddress', ''),
                        'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                        'source': 'QUIET_MOVERS',
                        'dex': pair.get('dexId', ''),
                        'market_cap': float(pair.get('marketCap', 0) or 0),
                        'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                        'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                        'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                    })
                    seen.add(token_addr)
                    stats['passed'] += 1
                
                await asyncio.sleep(0.15)
            except Exception as e:
                logger.debug(f"Search error ({term}): {e}")
        
        # Also check token profiles for new activity
        try:
            resp = await client.get(
                'https://api.dexscreener.com/token-profiles/latest/v1',
                headers=headers
            )
            if resp.status_code == 200:
                for item in (resp.json() if isinstance(resp.json(), list) else []):
                    if item.get('chainId') != 'solana':
                        continue
                    
                    token_addr = item.get('tokenAddress', '')
                    if not token_addr or token_addr in existing_tokens or token_addr in seen:
                        continue
                    
                    # Get pair data
                    try:
                        pr = await client.get(
                            f'https://api.dexscreener.com/latest/dex/tokens/{token_addr}',
                            headers=headers
                        )
                        if pr.status_code != 200:
                            continue
                        
                        pairs = pr.json().get('pairs', [])
                        pair = next((p for p in pairs if p.get('dexId', '').lower() in ALLOWED_DEXES), None)
                        
                        if not pair:
                            continue
                        
                        stats['checked'] += 1
                        valid, reason = _validate_quiet_mover(pair)
                        
                        if not valid:
                            stats['rejected'][reason] = stats['rejected'].get(reason, 0) + 1
                            continue
                        
                        tokens.append({
                            'address': token_addr,
                            'pair_address': pair.get('pairAddress', ''),
                            'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                            'source': 'QUIET_MOVERS',
                            'dex': pair.get('dexId', ''),
                            'market_cap': float(pair.get('marketCap', 0) or 0),
                            'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                            'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                            'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                            'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                        })
                        seen.add(token_addr)
                        stats['passed'] += 1
                        
                        await asyncio.sleep(0.1)
                    except:
                        continue
        except Exception as e:
            logger.debug(f"Profiles error: {e}")
    
    logger.info(f"🔍 Quiet Movers: checked={stats['checked']} found={stats['passed']}")
    return tokens, stats


async def test():
    """Test quiet movers discovery."""
    print("=" * 60)
    print("QUIET MOVERS TEST — Supplemental Discovery")
    print("=" * 60)
    print(f"\nGuardrails (LOCKED):")
    print(f"  DEXes allowed: {ALLOWED_DEXES}")
    print(f"  MC >= ${MIN_MARKET_CAP:,}")
    print(f"  Liq >= ${MIN_LIQUIDITY:,}")
    print(f"  Age >= {MIN_AGE_HOURS}h")
    print(f"  Momentum: +{MIN_GAIN_1H}-{MAX_GAIN_1H}% (1h) or +{MIN_GAIN_6H}-{MAX_GAIN_6H}% (6h)")
    print()
    
    tokens, stats = await fetch_quiet_movers()
    
    print(f"Results:")
    print(f"  Checked: {stats['checked']}")
    print(f"  Passed: {stats['passed']}")
    
    if tokens:
        print(f"\nQuiet movers found ({len(tokens)}):")
        for t in sorted(tokens, key=lambda x: -x['price_change_1h'])[:15]:
            print(f"  {t['symbol'][:12]:<12} +{t['price_change_1h']:>5.0f}% | MC ${t['market_cap']:>10,.0f} | {t['dex']}")
    
    if stats['rejected']:
        print(f"\nRejected (top reasons):")
        for reason, count in sorted(stats['rejected'].items(), key=lambda x: -x[1])[:6]:
            print(f"  {reason}: {count}")


if __name__ == '__main__':
    asyncio.run(test())
