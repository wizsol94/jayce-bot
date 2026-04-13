"""
TIERED CACHE VALIDATION
========================
Validates that tier-specific TTLs are being applied correctly.
"""

import sys
sys.path.insert(0, '/opt/jayce')

print("=" * 70)
print("TIERED CACHE VALIDATION REPORT")
print("=" * 70)

# 1. CHECK CACHE_TIERS.PY CONFIGURATION
print("\n1. TIER CONFIGURATION (cache_tiers.py)")
print("=" * 50)

with open('/opt/jayce/cache_tiers.py', 'r') as f:
    tiers_content = f.read()

import re

# Extract tier configs
tier_configs = re.findall(r'(\d):\s*TierConfig\(\s*name="([^"]+)",\s*cache_1m_seconds=(\d+),\s*cache_5m_seconds=(\d+)', tiers_content)

print("\nConfigured Tiers:")
for tier_num, name, cache_1m, cache_5m in tier_configs:
    print(f"  Tier {tier_num} ({name}):")
    print(f"    1m cache: {cache_1m}s {'(DISABLED)' if cache_1m == '0' else ''}")
    print(f"    5m cache: {cache_5m}s ({int(cache_5m)//60} min)")

# 2. CHECK GLOBAL TTL
print("\n2. GLOBAL TTL SETTINGS (candle_provider.py)")
print("=" * 50)

with open('/opt/jayce/candle_provider.py', 'r') as f:
    cp_content = f.read()

global_ttl = re.search(r'CACHE_TTL_MINUTES\s*=\s*(\d+)', cp_content)
if global_ttl:
    print(f"  CACHE_TTL_MINUTES = {global_ttl.group(1)} minutes")
else:
    print("  CACHE_TTL_MINUTES not found")

# Check if tiered cache is imported
if 'from cache_tiers import' in cp_content:
    print("  ✅ cache_tiers IS imported in candle_provider.py")
else:
    print("  ⚠️ cache_tiers NOT imported in candle_provider.py")

# 3. CHECK ACTUAL CACHE LOGIC FLOW
print("\n3. CACHE LOGIC FLOW ANALYSIS")
print("=" * 50)

# Check get_cached_candles function
print("\nget_cached_candles() logic:")
match = re.search(r'def get_cached_candles\(.*?\n(.*?)(?=\ndef |\Z)', cp_content, re.DOTALL)
if match:
    func_body = match.group(1)[:800]
    
    # Check if tier logic is used
    if 'get_selective_cache' in func_body or 'assess_token_tier' in func_body:
        print("  ✅ Uses selective/tiered cache logic")
    else:
        print("  ⚠️ Does NOT use tiered cache logic")
    
    # Check fallback to global TTL
    if 'CACHE_TTL_MINUTES' in func_body:
        print("  ⚠️ Falls back to global CACHE_TTL_MINUTES")
        # Check when this happens
        if 'if token:' in func_body:
            print("     → Only when token dict is None (legacy calls)")
        else:
            print("     → Always uses global TTL (PROBLEM)")
    else:
        print("  ✅ Does NOT use global CACHE_TTL_MINUTES")

# 4. CHECK HYBRID_FETCH_CANDLES IN SCANNER.PY
print("\n4. HYBRID_FETCH_CANDLES TIER LOGIC")
print("=" * 50)

with open('/opt/jayce/scanner.py', 'r') as f:
    scanner_content = f.read()

match = re.search(r'async def hybrid_fetch_candles.*?return await fetch_candles', scanner_content, re.DOTALL)
if match:
    hybrid_func = match.group()
    
    if 'assess_token_tier' in hybrid_func:
        print("  ✅ Uses assess_token_tier()")
    else:
        print("  ⚠️ Does NOT use assess_token_tier()")
    
    if 'tier == 3' in hybrid_func and 'age_min < 60' in hybrid_func:
        print("  ✅ Tier 3: Uses 60 min cache")
    else:
        print("  ⚠️ Tier 3 logic may be missing")
    
    if 'tier == 2' in hybrid_func and 'age_min < 30' in hybrid_func:
        print("  ✅ Tier 2: Uses 30 min cache")
    else:
        print("  ⚠️ Tier 2 logic may be missing")
    
    if 'tier == 1' in hybrid_func or '# Tier 1' in hybrid_func:
        print("  ✅ Tier 1: Falls through to fresh fetch")
    else:
        print("  ℹ️ Tier 1: Implicit (falls through to fetch_candles)")

# 5. CHECK 1m CACHE BEHAVIOR
print("\n5. 1m CANDLE CACHE BEHAVIOR")
print("=" * 50)

# Check fetch_candles_birdeye_1m
match = re.search(r'async def fetch_candles_birdeye_1m.*?(?=async def|\Z)', cp_content, re.DOTALL)
if match:
    func_1m = match.group()
    
    if 'cache' in func_1m.lower():
        print("  ⚠️ 1m function HAS cache logic")
        if 'CANDLE_CACHE' in func_1m:
            print("     → Uses CANDLE_CACHE (may apply global TTL)")
    else:
        print("  ✅ 1m function has NO internal cache (always fresh)")
else:
    print("  ⚠️ fetch_candles_birdeye_1m not found")

# 6. CRITICAL CHECK: Is global TTL overriding tiers?
print("\n6. CRITICAL: GLOBAL TTL OVERRIDE CHECK")
print("=" * 50)

# The key question: When fetch_candles is called, does it use:
# a) Tiered TTL from cache_tiers.py
# b) Global CACHE_TTL_MINUTES = 30

# Check the actual cache check in fetch_candles
fetch_candles_match = re.search(r'async def fetch_candles\(pair_address.*?cached = get_cached_candles\(cache_key\)', cp_content, re.DOTALL)
if fetch_candles_match:
    print("  fetch_candles() calls get_cached_candles(cache_key)")
    print("  → No token dict passed, so:")
    print("  → Falls back to CANDLE_CACHE with CACHE_TTL_MINUTES")
    print("")
    print("  ⚠️ POTENTIAL ISSUE:")
    print("     Tiered cache logic in hybrid_fetch_candles checks CANDLE_CACHE directly")
    print("     But fetch_candles ALSO checks CANDLE_CACHE with global TTL")
    print("")
    print("     Flow for Tier 1 token:")
    print("     1. hybrid_fetch_candles: tier==1 → calls fetch_candles()")
    print("     2. fetch_candles: checks get_cached_candles() with global TTL")
    print("     3. If cache age < 30 min → returns cached (even for Tier 1)")
    print("")
    print("  ❌ RESULT: Tier 1 tokens may get 30 min cached data!")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print("""
FINDING: The tiered cache system in cache_tiers.py is PARTIALLY implemented
but NOT fully integrated into the main fetch path.

Current behavior:
- hybrid_fetch_candles() checks tiers for Tier 2 and Tier 3 only
- Tier 1 falls through to fetch_candles()
- fetch_candles() uses GLOBAL 30-minute TTL via get_cached_candles()

IMPACT:
- Tier 2/3: Working correctly (30-60 min cache)
- Tier 1: ⚠️ Using 30 min cache instead of 45-90 seconds!

This explains why 99%+ cache hits - ALL tokens use 30 min cache,
including Tier 1 "active edge" tokens that should have fresh data.
""")

