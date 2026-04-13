"""
CACHE KEY IDENTITY AUDIT
=========================
Verifies cache key construction and identifies mismatches.
"""

import sys
sys.path.insert(0, '/opt/jayce')

import re
from collections import defaultdict

print("=" * 70)
print("CACHE KEY IDENTITY AUDIT")
print("=" * 70)

# 1. ANALYZE CACHE KEY CONSTRUCTION IN CODE
print("\n1. CACHE KEY CONSTRUCTION (from code)")
print("=" * 50)

with open('/opt/jayce/candle_provider.py', 'r') as f:
    cp_content = f.read()

# Find all cache_key assignments
cache_key_patterns = re.findall(r'cache_key\s*=\s*[^\n]+', cp_content)
print("Cache key assignments found:")
for pattern in cache_key_patterns:
    print(f"  {pattern}")

# Find get_cached_candles calls
get_cache_calls = re.findall(r'get_cached_candles\([^)]+\)', cp_content)
print("\nget_cached_candles() calls:")
for call in get_cache_calls:
    print(f"  {call}")

# Find cache_candles calls
cache_calls = re.findall(r'cache_candles\([^)]+\)', cp_content)
print("\ncache_candles() calls:")
for call in cache_calls:
    print(f"  {call}")

# 2. CHECK FETCH_CANDLES FUNCTION
print("\n2. FETCH_CANDLES CACHE KEY LOGIC")
print("=" * 50)

# Extract fetch_candles function
match = re.search(r'async def fetch_candles\(pair_address.*?(?=async def|\Z)', cp_content, re.DOTALL)
if match:
    func = match.group()[:1000]
    print("fetch_candles signature and cache logic:")
    # Find cache_key line
    for line in func.split('\n'):
        if 'cache_key' in line or 'token_address' in line or 'pair_address' in line:
            print(f"  {line.strip()}")

# 3. CHECK SCANNER.PY FETCH PATHS
print("\n3. SCANNER.PY FETCH PATHS")
print("=" * 50)

with open('/opt/jayce/scanner.py', 'r') as f:
    scanner_content = f.read()

# Find all fetch_candles calls
fetch_calls = re.findall(r'fetch_candles\([^)]+\)', scanner_content)
print(f"fetch_candles() calls in scanner.py: {len(fetch_calls)}")
for call in set(fetch_calls):
    print(f"  {call}")

# Find hybrid_fetch_candles
match = re.search(r'async def hybrid_fetch_candles.*?(?=\n    # Run hybrid|\Z)', scanner_content, re.DOTALL)
if match:
    print("\nhybrid_fetch_candles function:")
    for line in match.group().split('\n')[:20]:
        print(f"  {line}")

# 4. ANALYZE ACTUAL LOG DATA FOR KEY MISMATCHES
print("\n4. ACTUAL CACHE KEY ANALYSIS FROM LOGS")
print("=" * 50)

with open('/opt/jayce/logs/scanner.log', 'r') as f:
    logs = f.readlines()

# Extract cache miss keys
cache_miss_keys = []
for line in logs:
    match = re.search(r'Cache MISS: ([A-Za-z0-9]+)', line)
    if match:
        cache_miss_keys.append(match.group(1))

# Extract Birdeye fetch addresses
birdeye_addresses = []
for line in logs:
    match = re.search(r'address=([A-Za-z0-9]+)&type=5m', line)
    if match:
        birdeye_addresses.append(match.group(1))

print(f"Cache miss keys logged: {len(cache_miss_keys)}")
print(f"Birdeye addresses fetched: {len(birdeye_addresses)}")

# Check if cache keys match birdeye addresses
# Get recent samples
recent_misses = cache_miss_keys[-50:] if cache_miss_keys else []
recent_fetches = birdeye_addresses[-50:] if birdeye_addresses else []

print(f"\nRecent cache miss keys (sample):")
for key in recent_misses[:5]:
    print(f"  {key}")

print(f"\nRecent Birdeye addresses (sample):")
for addr in recent_fetches[:5]:
    print(f"  {addr}")

# Check for case sensitivity issues
print("\n5. CASE SENSITIVITY CHECK")
print("=" * 50)

lower_keys = [k for k in cache_miss_keys if k[0].islower()]
upper_keys = [k for k in cache_miss_keys if k[0].isupper()]
print(f"Cache keys starting lowercase: {len(lower_keys)}")
print(f"Cache keys starting uppercase: {len(upper_keys)}")

lower_addrs = [a for a in birdeye_addresses if a[0].islower()]
upper_addrs = [a for a in birdeye_addresses if a[0].isupper()]
print(f"Birdeye addresses starting lowercase: {len(lower_addrs)}")
print(f"Birdeye addresses starting uppercase: {len(upper_addrs)}")

# Check if same token appears with different cases
print("\n6. SAME TOKEN DIFFERENT KEYS CHECK")
print("=" * 50)

# Group by lowercased key to find case mismatches
key_variants = defaultdict(set)
for key in cache_miss_keys:
    key_variants[key.lower()].add(key)

mismatches = {k: v for k, v in key_variants.items() if len(v) > 1}
print(f"Tokens with multiple key variants: {len(mismatches)}")
for key, variants in list(mismatches.items())[:5]:
    print(f"  {key}: {variants}")

# 7. CHECK FETCH PARAMETER ORDER
print("\n7. FETCH PARAMETER ANALYSIS")
print("=" * 50)

# Check what parameters are passed to fetch_candles
# From scanner.py: fetch_candles(pair_address, symbol, token_address)
# The cache key is: token_address or pair_address

# Find actual call patterns
print("Checking if token_address and pair_address are swapped...")

# Look for calls where first param might be token vs pair
call_patterns = re.findall(r'fetch_candles\(([^,]+),\s*([^,]+),\s*([^)]+)\)', scanner_content)
print(f"Found {len(call_patterns)} fetch_candles calls with 3 params:")
for p1, p2, p3 in call_patterns[:5]:
    print(f"  fetch_candles({p1.strip()}, {p2.strip()}, {p3.strip()})")

# 8. SUMMARY
print("\n" + "=" * 70)
print("CACHE KEY IDENTITY FINDINGS")
print("=" * 70)

issues = []

if len(mismatches) > 0:
    issues.append(f"CASE MISMATCH: {len(mismatches)} tokens have multiple key variants")

if len(lower_keys) > 0 and len(upper_keys) > 0:
    issues.append(f"MIXED CASE: Keys are both lower ({len(lower_keys)}) and upper ({len(upper_keys)})")

# Check if cache key uses token_address but fetch uses pair_address
if 'token_address or pair_address' in cp_content:
    issues.append("FALLBACK LOGIC: cache_key = token_address OR pair_address - may cause inconsistency")

if issues:
    print("⚠️ ISSUES FOUND:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("No obvious key mismatches found in static analysis")

print("\n" + "=" * 70)
print("NEXT STEPS")
print("=" * 70)
print("""
To fix cache key mismatches:
1. Normalize all cache keys to same case (lowercase)
2. Use pair_address as PRIMARY key (most stable)
3. Ensure token_address fallback doesn't create different keys
4. Verify all fetch paths use consistent parameter order
""")

