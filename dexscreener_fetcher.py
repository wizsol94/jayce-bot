"""
DEXSCREENER FETCHER v2.0 - MAXED OUT
=====================================
More search terms, relaxed profile filter (icon OR socials)
"""
import asyncio
import httpx
import logging
from datetime import datetime
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

ALLOWED_DEXES = {'pumpfun', 'pumpswap'}
MIN_LIQUIDITY = 10000
MIN_MARKET_CAP = 100000
MIN_AGE_HOURS = 1
VOL_5M_LIMIT = 50
VOL_1H_LIMIT = 50

# MAXED search terms - covers most active Solana memes
SEARCH_TERMS_5M = ['pump', 'bonk', 'wojak', 'pepe', 'doge', 'cat', 'dog', 'moon', 'elon', 'trump', 'biden', 'ai', 'gpt', 'meme', 'sol', 'inu', 'shib', 'frog', 'chad', 'based']
SEARCH_TERMS_1H = ['coin', 'token', 'crypto', 'ape', 'monkey', 'bear', 'bull', 'gold', 'diamond', 'rocket', 'mars', 'baby', 'mini', 'mega', 'super', 'king', 'queen', 'lord', 'god', 'devil']

def has_profile(pair: dict) -> bool:
    info = pair.get('info', {})
    if not info:
        return False
    # Relaxed: icon OR socials (not both required)
    has_icon = bool(info.get('imageUrl'))
    has_socials = bool(info.get('socials'))
    has_websites = bool(info.get('websites'))
    return has_icon or has_socials or has_websites

def passes_filters(pair: dict) -> bool:
    if pair.get('chainId') != 'solana':
        return False
    dex_id = pair.get('dexId', '').lower()
    if dex_id not in ALLOWED_DEXES:
        return False
    labels = [l.lower() for l in pair.get('labels', [])]
    if 'clmm' in labels or 'cpmm' in labels:
        return False
    if 'clmm' in pair.get('pairAddress', '').lower():
        return False
    liquidity = pair.get('liquidity', {}).get('usd', 0) or 0
    if liquidity < MIN_LIQUIDITY:
        return False
    market_cap = pair.get('marketCap', 0) or pair.get('fdv', 0) or 0
    if market_cap < MIN_MARKET_CAP:
        return False
    pair_created = pair.get('pairCreatedAt')
    if pair_created:
        try:
            created_time = datetime.fromtimestamp(pair_created / 1000)
            age_hours = (datetime.now() - created_time).total_seconds() / 3600
            if age_hours < MIN_AGE_HOURS:
                return False
        except:
            pass
    if not has_profile(pair):
        return False
    return True

def extract_token_data(pair: dict, source: str, rank: int) -> dict:
    base_token = pair.get('baseToken', {})
    return {
        'symbol': base_token.get('symbol', '???')[:20],
        'pair_address': pair.get('pairAddress', ''),
        'address': base_token.get('address', ''),
        'source': source,
        'rank': rank,
        'url': f"https://dexscreener.com/solana/{pair.get('pairAddress', '')}",
        'dex': pair.get('dexId', ''),
        'market_cap': pair.get('marketCap', 0) or pair.get('fdv', 0) or 0,
        'liquidity': pair.get('liquidity', {}).get('usd', 0) or 0,
        'volume_5m': pair.get('volume', {}).get('m5', 0) or 0,
        'volume_1h': pair.get('volume', {}).get('h1', 0) or 0,
        'price_change_1h': pair.get('priceChange', {}).get('h1', 0) or 0,
        'price_change_24h': pair.get('priceChange', {}).get('h24', 0) or 0,
    }

async def fetch_volume_movers() -> Tuple[List[dict], Dict[str, int]]:
    all_tokens = {}
    source_counts = {'VOL_5M': 0, 'VOL_1H': 0}
    stats = {'raw_5m': 0, 'raw_1h': 0, 'filtered_5m': 0, 'filtered_1h': 0}
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 5M Volume - all search terms
        logger.info("DexScreener: Fetching 5M volume (20 search terms)...")
        all_5m_pairs = []
        for term in SEARCH_TERMS_5M:
            try:
                resp = await client.get(f'https://api.dexscreener.com/latest/dex/search?q={term}', headers=headers)
                if resp.status_code == 200:
                    pairs = resp.json().get('pairs', [])
                    all_5m_pairs.extend(pairs)
                await asyncio.sleep(0.12)
            except:
                pass
        
        stats['raw_5m'] = len(all_5m_pairs)
        pairs_sorted = sorted(all_5m_pairs, key=lambda p: p.get('volume', {}).get('m5', 0) or 0, reverse=True)
        rank = 0
        for pair in pairs_sorted:
            if source_counts['VOL_5M'] >= VOL_5M_LIMIT:
                break
            if not passes_filters(pair):
                stats['filtered_5m'] += 1
                continue
            addr = pair.get('baseToken', {}).get('address', '')
            if not addr or addr in all_tokens:
                continue
            rank += 1
            all_tokens[addr] = extract_token_data(pair, 'VOL_5M', rank)
            source_counts['VOL_5M'] += 1
        logger.info(f"DexScreener: 5M raw={stats['raw_5m']} filtered={stats['filtered_5m']} final={source_counts['VOL_5M']}")
        
        await asyncio.sleep(0.3)
        
        # 1H Volume - different search terms
        logger.info("DexScreener: Fetching 1H volume (20 search terms)...")
        all_1h_pairs = []
        for term in SEARCH_TERMS_1H:
            try:
                resp = await client.get(f'https://api.dexscreener.com/latest/dex/search?q={term}', headers=headers)
                if resp.status_code == 200:
                    pairs = resp.json().get('pairs', [])
                    all_1h_pairs.extend(pairs)
                await asyncio.sleep(0.12)
            except:
                pass
        
        stats['raw_1h'] = len(all_1h_pairs)
        pairs_sorted = sorted(all_1h_pairs, key=lambda p: p.get('volume', {}).get('h1', 0) or 0, reverse=True)
        rank = 0
        for pair in pairs_sorted:
            if source_counts['VOL_1H'] >= VOL_1H_LIMIT:
                break
            if not passes_filters(pair):
                stats['filtered_1h'] += 1
                continue
            addr = pair.get('baseToken', {}).get('address', '')
            if not addr or addr in all_tokens:
                continue
            rank += 1
            all_tokens[addr] = extract_token_data(pair, 'VOL_1H', rank)
            source_counts['VOL_1H'] += 1
        logger.info(f"DexScreener: 1H raw={stats['raw_1h']} filtered={stats['filtered_1h']} final={source_counts['VOL_1H']}")
    
    tokens = list(all_tokens.values())
    logger.info(f"DexScreener TOTAL: {len(tokens)} tokens (5M:{source_counts['VOL_5M']} + 1H:{source_counts['VOL_1H']})")
    return tokens, source_counts

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    async def test():
        tokens, counts = await fetch_volume_movers()
        print(f"\nRESULTS: {len(tokens)} tokens | 5M: {counts['VOL_5M']} | 1H: {counts['VOL_1H']}")
        print("\n5M tokens:")
        for t in [x for x in tokens if x['source']=='VOL_5M'][:10]:
            print(f"  {t['symbol']:12} | MC: ${t['market_cap']:>12,.0f}")
        print("\n1H tokens:")
        for t in [x for x in tokens if x['source']=='VOL_1H'][:10]:
            print(f"  {t['symbol']:12} | MC: ${t['market_cap']:>12,.0f}")
    asyncio.run(test())
