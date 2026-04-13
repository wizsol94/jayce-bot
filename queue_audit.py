"""
QUEUE & TOKEN PERSISTENCE AUDIT
================================
Analyzes why tokens are not being rescanned for cache to work.
"""

import sys
sys.path.insert(0, '/opt/jayce')

from datetime import datetime, timedelta
import re
from collections import defaultdict

# Read all logs from today
with open('/opt/jayce/logs/scanner.log', 'r') as f:
    logs = f.readlines()

print("=" * 70)
print("QUEUE & TOKEN PERSISTENCE AUDIT")
print("=" * 70)

# Extract all token fetches with timestamps and addresses
fetch_data = []
for line in logs:
    # Match Birdeye success logs
    match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*📊 ([^:]+): Birdeye ✓', line)
    if match:
        timestamp_str = match.group(1)
        symbol = match.group(2).strip()
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            fetch_data.append({'time': timestamp, 'symbol': symbol})
        except:
            pass

# Also extract pair addresses from HTTP logs
address_fetches = defaultdict(list)
for line in logs:
    match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*address=([A-Za-z0-9]+)&type=5m', line)
    if match:
        timestamp_str = match.group(1)
        address = match.group(2)
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            address_fetches[address].append(timestamp)
        except:
            pass

print(f"\nTotal fetches in log: {len(fetch_data)}")
print(f"Unique addresses fetched: {len(address_fetches)}")

# 1. TOKEN RESCAN FREQUENCY
print("\n" + "=" * 50)
print("1. TOKEN RESCAN FREQUENCY (by address)")
print("=" * 50)

# Calculate time span
if address_fetches:
    all_times = [t for times in address_fetches.values() for t in times]
    if all_times:
        time_span = (max(all_times) - min(all_times)).total_seconds() / 3600
        print(f"Log time span: {time_span:.1f} hours")

# Count rescans
rescan_counts = {addr: len(times) for addr, times in address_fetches.items()}
sorted_rescans = sorted(rescan_counts.items(), key=lambda x: x[1], reverse=True)

print(f"\nTokens scanned only ONCE: {sum(1 for c in rescan_counts.values() if c == 1)}")
print(f"Tokens scanned 2-3 times: {sum(1 for c in rescan_counts.values() if 2 <= c <= 3)}")
print(f"Tokens scanned 4+ times: {sum(1 for c in rescan_counts.values() if c >= 4)}")

print("\nMost frequently rescanned (top 10):")
for addr, count in sorted_rescans[:10]:
    # Get time span for this token
    times = sorted(address_fetches[addr])
    if len(times) > 1:
        span = (times[-1] - times[0]).total_seconds() / 60
        print(f"  {addr[:20]}...: {count}x over {span:.0f} min")
    else:
        print(f"  {addr[:20]}...: {count}x")

# 2. RESCAN WINDOWS
print("\n" + "=" * 50)
print("2. RESCANS BY TIME WINDOW")
print("=" * 50)

def count_rescans_in_window(address_fetches, window_minutes):
    """Count tokens that were rescanned within the given window."""
    rescanned = 0
    for addr, times in address_fetches.items():
        times = sorted(times)
        for i in range(1, len(times)):
            if (times[i] - times[i-1]).total_seconds() / 60 <= window_minutes:
                rescanned += 1
                break
    return rescanned

print(f"Tokens rescanned within 30 min: {count_rescans_in_window(address_fetches, 30)}")
print(f"Tokens rescanned within 1 hour: {count_rescans_in_window(address_fetches, 60)}")
print(f"Tokens rescanned within 4 hours: {count_rescans_in_window(address_fetches, 240)}")

# 3. CYCLE-BY-CYCLE OVERLAP
print("\n" + "=" * 50)
print("3. CYCLE-BY-CYCLE TOKEN OVERLAP")
print("=" * 50)

# Group fetches by cycle (assuming ~2-3 min cycles)
cycles = []
current_cycle = []
last_time = None

for addr, times in sorted(address_fetches.items(), key=lambda x: min(x[1])):
    for t in times:
        if last_time is None or (t - last_time).total_seconds() < 120:
            current_cycle.append(addr)
        else:
            if current_cycle:
                cycles.append(set(current_cycle))
            current_cycle = [addr]
        last_time = t

if current_cycle:
    cycles.append(set(current_cycle))

print(f"Detected cycles: {len(cycles)}")

if len(cycles) >= 2:
    # Check overlap between consecutive cycles
    overlaps = []
    for i in range(1, min(len(cycles), 10)):
        overlap = len(cycles[i] & cycles[i-1])
        total = len(cycles[i] | cycles[i-1])
        overlap_pct = overlap / total * 100 if total > 0 else 0
        overlaps.append(overlap_pct)
        print(f"Cycle {i-1} → {i}: {overlap}/{total} tokens overlap ({overlap_pct:.0f}%)")
    
    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
    print(f"\nAverage cycle overlap: {avg_overlap:.0f}%")
    
    if avg_overlap < 30:
        print("⚠️ LOW OVERLAP - tokens are churning too fast!")
    elif avg_overlap < 60:
        print("⚠️ MODERATE OVERLAP - some persistence but high churn")
    else:
        print("✅ GOOD OVERLAP - tokens persisting between cycles")

# 4. SOURCE ANALYSIS
print("\n" + "=" * 50)
print("4. TOKEN SOURCE ANALYSIS")
print("=" * 50)

sources = defaultdict(int)
for line in logs:
    if 'TOP=' in line:
        match = re.search(r'TOP=(\d+).*5M=(\d+).*1H=(\d+).*Raw=(\d+)', line)
        if match:
            sources['TOP'] += int(match.group(1))
            sources['5M'] += int(match.group(2))
            sources['1H'] += int(match.group(3))
            sources['Raw'] += int(match.group(4))

if sources:
    print("Token sources (cumulative):")
    for src, count in sources.items():
        print(f"  {src}: {count}")
else:
    # Check for other source indicators
    trending_count = sum(1 for l in logs if 'trending' in l.lower())
    watchlist_count = sum(1 for l in logs if 'watchlist' in l.lower())
    print(f"Trending mentions: {trending_count}")
    print(f"Watchlist mentions: {watchlist_count}")

# 5. WATCHLIST PERSISTENCE
print("\n" + "=" * 50)
print("5. WATCHLIST / QUEUE PERSISTENCE")
print("=" * 50)

# Check for watchlist-related logs
watchlist_logs = [l for l in logs if 'watchlist' in l.lower() or 'retained' in l.lower() or 'queue' in l.lower()]
print(f"Watchlist/queue related log entries: {len(watchlist_logs)}")

# Check for token retention patterns
retained = [l for l in logs if 'retained' in l.lower() or 'Retained' in l]
dropped = [l for l in logs if 'dropped' in l.lower() or 'removed' in l.lower()]
print(f"'Retained' mentions: {len(retained)}")
print(f"'Dropped/removed' mentions: {len(dropped)}")

# 6. DUPLICATE DETECTION
print("\n" + "=" * 50)
print("6. DUPLICATE HANDLING")
print("=" * 50)

# Check for dedup logs
dedup_logs = [l for l in logs if 'dedup' in l.lower() or 'duplicate' in l.lower()]
print(f"Dedup-related log entries: {len(dedup_logs)}")
for log in dedup_logs[-5:]:
    print(f"  {log.strip()[:80]}...")

# 7. KEY FINDING: Single-scan tokens
print("\n" + "=" * 50)
print("7. CRITICAL: SINGLE-SCAN TOKEN ANALYSIS")
print("=" * 50)

single_scan = [addr for addr, times in address_fetches.items() if len(times) == 1]
multi_scan = [addr for addr, times in address_fetches.items() if len(times) > 1]

print(f"Tokens scanned only ONCE: {len(single_scan)} ({len(single_scan)/len(address_fetches)*100:.0f}%)")
print(f"Tokens scanned MULTIPLE times: {len(multi_scan)} ({len(multi_scan)/len(address_fetches)*100:.0f}%)")

if len(single_scan) / len(address_fetches) > 0.7:
    print("\n⚠️ CRITICAL: 70%+ tokens are scanned only once!")
    print("   This means NO persistence - cache cannot help.")
    print("   Tokens are being replaced every cycle instead of retained.")

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)
print("""
If most tokens are scanned only once:
1. Check if watchlist/retained queue is being used
2. Check if source feeds overwhelm persistent tokens
3. Check if tokens are deduped by pair_address (not symbol)
4. Implement token retention across cycles
5. Prioritize rescanning known-structure tokens over new discoveries
""")

