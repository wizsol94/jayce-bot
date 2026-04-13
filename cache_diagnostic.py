"""
CACHE DIAGNOSTIC TOOL
=====================
Analyzes cache behavior to identify inefficiencies.
"""

import sys
sys.path.insert(0, '/opt/jayce')

from datetime import datetime
import re

# Read recent logs
with open('/opt/jayce/logs/scanner.log', 'r') as f:
    logs = f.readlines()

# Filter to last hour
recent_logs = [l for l in logs if '2026-03-24 01:' in l or '2026-03-24 00:5' in l]

print("=" * 70)
print("CACHE DIAGNOSTIC REPORT")
print("=" * 70)

# 1. CACHE KEY ANALYSIS
print("\n1. CACHE KEY STRUCTURE")
print("-" * 50)

# Check candle_provider.py for cache key logic
with open('/opt/jayce/candle_provider.py', 'r') as f:
    cp_content = f.read()

# Find cache key usage
if 'cache_key = token_address or pair_address' in cp_content:
    print("5m Cache Key: token_address OR pair_address (fallback)")
else:
    print("5m Cache Key: UNKNOWN - needs inspection")

# Check 1m cache
if 'fetch_candles_birdeye_1m' in cp_content:
    # Extract 1m function
    match = re.search(r'async def fetch_candles_birdeye_1m.*?(?=async def|\Z)', cp_content, re.DOTALL)
    if match:
        func_code = match.group()
        if 'cache' in func_code.lower():
            print("1m Cache: Has caching logic")
        else:
            print("1m Cache: ⚠️ NO CACHING - always fresh fetch!")
    else:
        print("1m Cache: Could not parse function")

print("\n2. CACHE HIT/MISS ANALYSIS")
print("-" * 50)

# Count Birdeye calls vs cache hits
birdeye_calls = [l for l in recent_logs if 'Birdeye ✓' in l]
cache_hits = [l for l in recent_logs if 'Cache hit' in l or 'cache hit' in l.lower()]

print(f"Birdeye API calls (last hour): {len(birdeye_calls)}")
print(f"Cache hits logged: {len(cache_hits)}")
if len(birdeye_calls) > 0:
    hit_rate = len(cache_hits) / (len(cache_hits) + len(birdeye_calls)) * 100 if cache_hits else 0
    print(f"Apparent hit rate: {hit_rate:.1f}%")
    if len(cache_hits) == 0:
        print("⚠️ NO CACHE HITS LOGGED - cache may not be working or not logging")

print("\n3. TOKEN FETCH FREQUENCY")
print("-" * 50)

# Extract token symbols from Birdeye calls
token_fetches = {}
for line in birdeye_calls:
    match = re.search(r'📊 ([^:]+): Birdeye', line)
    if match:
        symbol = match.group(1).strip()
        token_fetches[symbol] = token_fetches.get(symbol, 0) + 1

# Sort by frequency
sorted_tokens = sorted(token_fetches.items(), key=lambda x: x[1], reverse=True)

print("Most frequently fetched tokens:")
for symbol, count in sorted_tokens[:15]:
    status = "⚠️ OVER-FETCHED" if count > 3 else "OK"
    print(f"  {symbol}: {count} times {status}")

total_fetches = sum(token_fetches.values())
unique_tokens = len(token_fetches)
print(f"\nTotal fetches: {total_fetches}")
print(f"Unique tokens: {unique_tokens}")
if unique_tokens > 0:
    avg_fetches = total_fetches / unique_tokens
    print(f"Avg fetches per token: {avg_fetches:.1f}")
    if avg_fetches > 2:
        print("⚠️ HIGH - tokens being re-fetched too often")

print("\n4. 1m vs 5m FETCH BREAKDOWN")
print("-" * 50)

# Check HTTP logs for 1m vs 5m
http_1m = [l for l in recent_logs if 'type=1m' in l]
http_5m = [l for l in recent_logs if 'type=5m' in l]

print(f"5m API calls: {len(http_5m)}")
print(f"1m API calls: {len(http_1m)}")

if len(http_1m) > 0:
    ratio = len(http_1m) / len(http_5m) * 100 if http_5m else 0
    print(f"1m/5m ratio: {ratio:.1f}%")

print("\n5. DUPLICATE FETCH DETECTION")
print("-" * 50)

# Check for same token fetched within 1 minute
from collections import defaultdict
fetch_times = defaultdict(list)

for line in birdeye_calls:
    match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*📊 ([^:]+): Birdeye', line)
    if match:
        timestamp_str = match.group(1)
        symbol = match.group(2).strip()
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            fetch_times[symbol].append(timestamp)
        except:
            pass

duplicates = 0
for symbol, times in fetch_times.items():
    times.sort()
    for i in range(1, len(times)):
        diff = (times[i] - times[i-1]).total_seconds()
        if diff < 120:  # Same token fetched within 2 min
            duplicates += 1
            if duplicates <= 5:
                print(f"  {symbol}: fetched again after {diff:.0f}s")

print(f"\nTotal near-duplicate fetches (<2min apart): {duplicates}")
if duplicates > 10:
    print("⚠️ HIGH DUPLICATE RATE - cache is not preventing re-fetches")

print("\n6. FETCH PATH ANALYSIS")
print("-" * 50)

# Check where fetches originate
stage3_fetches = len([l for l in recent_logs if 'Stage 3: Fetching' in l])
engine_fetches = len([l for l in recent_logs if 'screenshot_chart' in l or 'Engine' in l])

print(f"Stage 3 (hybrid intake) fetch batches: {stage3_fetches}")
print(f"Engine analysis fetches: {engine_fetches}")

# Check for multiple fetch paths
print("\nFetch code paths:")
print("  - hybrid_intake.py Stage 3 → fetch_candles_func")
print("  - scanner.py engine analysis → fetch_candles")
print("  - scanner.py screenshot_chart → candle data")

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

issues = []

if len(cache_hits) == 0:
    issues.append("Cache hits not being logged - add visibility")
    
if avg_fetches > 2:
    issues.append(f"Tokens fetched {avg_fetches:.1f}x avg - cache TTL or key issue")
    
if duplicates > 10:
    issues.append("Many duplicate fetches within 2 min - cache not working")
    
if len(http_1m) > len(http_5m) * 0.3:
    issues.append("1m calls are high - selective 1m may not be working")

if issues:
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}")
else:
    print("No major issues detected")

