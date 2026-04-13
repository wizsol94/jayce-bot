#!/usr/bin/env python3
"""
PATCH: Scanner auto-fetches missing pair_address for whale tokens before scanning
"""

with open('/opt/jayce/scanner.py', 'r') as f:
    content = f.read()

old_code = '''    if whale_tokens:
        logger.info(f"[{ENVIRONMENT}]    🐋 {len(whale_tokens)} whale tokens to scan")
        
        for wt in whale_tokens:
            symbol = wt.get('symbol', '???')
            token_address = wt.get('token_address', '')
            pair_address = wt.get('pair_address', '')'''

new_code = '''    if whale_tokens:
        logger.info(f"[{ENVIRONMENT}]    🐋 {len(whale_tokens)} whale tokens to scan")
        
        for wt in whale_tokens:
            symbol = wt.get('symbol', '???')
            token_address = wt.get('token_address', '')
            pair_address = wt.get('pair_address', '')
            
            # AUTO-FETCH pair_address if missing
            if token_address and not pair_address:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(f'https://api.dexscreener.com/latest/dex/tokens/{token_address}')
                        if resp.status_code == 200:
                            pairs = resp.json().get('pairs', [])
                            sol_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                            if sol_pairs:
                                sol_pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                                pair_address = sol_pairs[0].get('pairAddress', '')
                                wt['pair_address'] = pair_address
                                # Update database
                                import sqlite3
                                conn = sqlite3.connect('/opt/jayce/data/queue.db')
                                conn.execute("UPDATE whale_watchlist SET pair_address = ? WHERE token_address = ?", (pair_address, token_address))
                                conn.commit()
                                conn.close()
                                logger.info(f"[{ENVIRONMENT}]       🔍 Auto-fetched pair for {symbol}")
                except Exception as e:
                    logger.warning(f"[{ENVIRONMENT}]       ⚠️ Could not fetch pair for {symbol}: {e}")
            
            if not pair_address:
                logger.info(f"[{ENVIRONMENT}]       ⏭️ {symbol}: No pair_address, skipping")
                continue'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('/opt/jayce/scanner.py', 'w') as f:
        f.write(content)
    print("✅ Patched scanner.py - Will auto-fetch missing pair_address for whale tokens")
else:
    print("❌ Could not find exact target code")
    print("   Trying alternative match...")
    
    # Try simpler match
    if "for wt in whale_tokens:" in content and "pair_address = wt.get('pair_address', '')" in content:
        # Find and show context
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "for wt in whale_tokens:" in line:
                print(f"   Found at line {i+1}")
                print(f"   Context: {lines[i:i+5]}")
                break
