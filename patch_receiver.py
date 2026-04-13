#!/usr/bin/env python3
"""
PATCH: Auto-fetch pair_address when whale token is added
"""

# Read receiver.py
with open('/opt/jayce/receiver.py', 'r') as f:
    content = f.read()

# Find the whale endpoint and add auto-fetch logic
old_code = '''    token_address = data.get('token_address', '')
    pair_address = data.get('pair_address', '')
    symbol = data.get('symbol', '???')
    whale_wallet = data.get('whale_wallet', '')
    buy_amount_sol = data.get('buy_amount_sol', 0)
    
    if not token_address and not pair_address:
        return jsonify({'error': 'Need token_address or pair_address'}), 400'''

new_code = '''    token_address = data.get('token_address', '')
    pair_address = data.get('pair_address', '')
    symbol = data.get('symbol', '???')
    whale_wallet = data.get('whale_wallet', '')
    buy_amount_sol = data.get('buy_amount_sol', 0)
    
    if not token_address and not pair_address:
        return jsonify({'error': 'Need token_address or pair_address'}), 400
    
    # AUTO-FETCH pair_address if missing
    if token_address and not pair_address:
        try:
            import httpx
            resp = httpx.get(f'https://api.dexscreener.com/latest/dex/tokens/{token_address}', timeout=10)
            if resp.status_code == 200:
                pairs = resp.json().get('pairs', [])
                sol_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                if sol_pairs:
                    sol_pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                    pair_address = sol_pairs[0].get('pairAddress', '')
                    print(f"   🔍 Auto-fetched pair_address for {symbol}: {pair_address[:20]}...")
        except Exception as e:
            print(f"   ⚠️ Could not auto-fetch pair_address: {e}")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('/opt/jayce/receiver.py', 'w') as f:
        f.write(content)
    print("✅ Patched receiver.py - Will auto-fetch pair_address for new whale tokens")
else:
    print("❌ Could not find target code in receiver.py")
    print("   Manual patch may be needed")
