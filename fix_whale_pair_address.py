#!/usr/bin/env python3
"""
FIX: Whale Watchlist Missing Pair Addresses
============================================
1. Backfill all existing whale tokens with missing pair_address
2. Patch receiver.py to auto-fetch pair_address on insert
3. Patch scanner.py to fetch pair_address if missing before scan
"""

import sqlite3
import asyncio
import httpx

QUEUE_DB = '/opt/jayce/data/queue.db'

async def fetch_pair_address(token_address: str) -> str:
    """Fetch pair_address from DexScreener using token address."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f'https://api.dexscreener.com/latest/dex/tokens/{token_address}')
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get('pairs', [])
                # Get the most liquid Solana pair
                sol_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                if sol_pairs:
                    # Sort by liquidity
                    sol_pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                    return sol_pairs[0].get('pairAddress', '')
    except Exception as e:
        print(f"   Error fetching pair for {token_address[:16]}...: {e}")
    return ''

async def backfill_pair_addresses():
    """Backfill missing pair_addresses for all whale tokens."""
    print("="*60)
    print("BACKFILLING WHALE WATCHLIST PAIR ADDRESSES")
    print("="*60)
    
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    
    # Get all tokens with missing pair_address
    c.execute("""
        SELECT id, token_address, symbol 
        FROM whale_watchlist 
        WHERE (pair_address = '' OR pair_address IS NULL) AND expired = 0
    """)
    missing = c.fetchall()
    
    print(f"\nFound {len(missing)} whale tokens with missing pair_address\n")
    
    fixed = 0
    for row in missing:
        id, token_address, symbol = row
        print(f"   {symbol}: Fetching pair_address...", end=" ")
        
        pair_address = await fetch_pair_address(token_address)
        
        if pair_address:
            c.execute("UPDATE whale_watchlist SET pair_address = ? WHERE id = ?", (pair_address, id))
            print(f"✅ {pair_address[:20]}...")
            fixed += 1
        else:
            print("❌ Not found")
        
        await asyncio.sleep(0.3)  # Rate limit
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"COMPLETE: Fixed {fixed}/{len(missing)} whale tokens")
    print("="*60)

# Run backfill
asyncio.run(backfill_pair_addresses())
