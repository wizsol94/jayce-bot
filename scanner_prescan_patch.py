"""
This script patches the scanner to use structural prescan instead of light filter.
"""

import re

with open('/opt/jayce/scanner.py', 'r') as f:
    content = f.read()

# Find and replace the light scoring section
# We'll replace from "# Score tokens using lightweight metrics" to "candidates = all_candidates[:20]"

old_section_start = "# Score tokens using lightweight metrics (NO candles needed)"
old_section_end = "# Take top 20 (watchlist competes with new discoveries)\n    candidates = all_candidates[:20]"

new_section = '''# ══════════════════════════════════════════════════════════════
    # STRUCTURAL PRESCAN - Analyze ALL tokens for setup shape
    # Replaces old volume/price-based light filter
    # ══════════════════════════════════════════════════════════════
    logger.info(f"[{ENVIRONMENT}] 🔬 STRUCTURAL PRESCAN: Analyzing {len(tokens)} tokens for setup shape...")
    
    # Define lightweight candle fetch for prescan (fewer candles, faster)
    async def fetch_prescan_candles(pair_address: str, limit: int = 50):
        """Fetch limited candles for prescan analysis."""
        try:
            # Use birdeye for candles
            candles = await fetch_candles_birdeye(pair_address, interval="5m", limit=limit)
            return candles
        except Exception as e:
            logger.debug(f"Prescan candle fetch failed for {pair_address}: {e}")
            return []
    
    # Run structural prescan on all validated tokens
    from structural_prescan import run_prescan_batch, ScanBucket
    
    prescan_results = await run_prescan_batch(tokens, fetch_prescan_candles)
    
    deep_scan_tokens = prescan_results.get('DEEP_SCAN_NOW', [])
    monitor_tokens = prescan_results.get('MONITOR', [])
    reject_tokens = prescan_results.get('REJECT', [])
    
    logger.info(f"[{ENVIRONMENT}]    📊 Prescan Results:")
    logger.info(f"[{ENVIRONMENT}]       🎯 DEEP_SCAN_NOW: {len(deep_scan_tokens)} tokens")
    logger.info(f"[{ENVIRONMENT}]       👁️  MONITOR: {len(monitor_tokens)} tokens")
    logger.info(f"[{ENVIRONMENT}]       ❌ REJECT: {len(reject_tokens)} tokens")
    
    # Log top DEEP_SCAN candidates
    for result in deep_scan_tokens[:5]:
        reasons_str = ', '.join(result.reasons[:3]) if result.reasons else 'N/A'
        logger.info(f"[{ENVIRONMENT}]       → {result.symbol}: Score {result.score:.0f} | {reasons_str}")
    
    # Convert prescan results to candidate format
    scored_tokens = []
    
    # DEEP_SCAN_NOW tokens get priority
    for result in deep_scan_tokens:
        token_data = next((t for t in tokens if t.get('pair_address') == result.pair_address), None)
        if token_data:
            scored_tokens.append({
                'token': token_data,
                'light_score': result.score + 50,  # Bonus for being DEEP_SCAN
                'prescan_bucket': 'DEEP_SCAN_NOW',
                'prescan_reasons': result.reasons,
                'breakout_score': result.breakout_score,
                'fib_proximity': result.fib_proximity_score
            })
    
    # MONITOR tokens can fill remaining slots
    for result in monitor_tokens:
        token_data = next((t for t in tokens if t.get('pair_address') == result.pair_address), None)
        if token_data:
            scored_tokens.append({
                'token': token_data,
                'light_score': result.score,
                'prescan_bucket': 'MONITOR',
                'prescan_reasons': result.reasons,
                'breakout_score': result.breakout_score,
                'fib_proximity': result.fib_proximity_score
            })
    
    # Sort by score
    scored_tokens.sort(key=lambda x: x['light_score'], reverse=True)
    
    # Merge watchlist tokens into candidate pool
    watchlist_candidates = []
    watchlist_addresses = set()
    for entry in watchlist_entries:
        watchlist_addresses.add(entry['pair_address'])
        boosted_score = entry['last_score'] + 30  # Bonus for being on watchlist
        watchlist_candidates.append({
            'token': entry['token_data'],
            'light_score': boosted_score,
            'from_watchlist': True,
            'watchlist_setup': entry['potential_setup'],
            'evaluations': entry['evaluations'],
            'prescan_bucket': 'WATCHLIST'
        })
    
    # Remove duplicates
    new_candidates = [s for s in scored_tokens if s['token'].get('pair_address') not in watchlist_addresses]
    
    # Combine and sort
    all_candidates = watchlist_candidates + new_candidates
    all_candidates.sort(key=lambda x: x['light_score'], reverse=True)
    
    # Take top candidates (more than before since prescan is smarter)
    # Deep scan all DEEP_SCAN_NOW + top MONITOR tokens
    max_deep_scan = 30  # Increased from 20
    candidates = all_candidates[:max_deep_scan]'''

# Find the section to replace
if old_section_start in content and old_section_end in content:
    # Find start and end positions
    start_idx = content.find(old_section_start)
    end_idx = content.find(old_section_end) + len(old_section_end)
    
    # Replace the section
    content = content[:start_idx] + new_section + content[end_idx:]
    
    with open('/opt/jayce/scanner.py', 'w') as f:
        f.write(content)
    
    print("✅ Scanner patched with structural prescan!")
    print("")
    print("Changes made:")
    print("  • Replaced light filter with structural prescan")
    print("  • Now analyzes ALL tokens for setup shape")
    print("  • 3 buckets: DEEP_SCAN_NOW, MONITOR, REJECT")
    print("  • Prioritizes: breakout structure, fib proximity, pullback quality")
    print("  • Increased deep scan limit to 30 tokens")
else:
    print("❌ Could not find the section to replace")
    print(f"Found start: {old_section_start in content}")
    print(f"Found end: {old_section_end in content}")
