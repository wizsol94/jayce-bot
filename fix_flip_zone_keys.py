#!/usr/bin/env python3
"""
FIX: Flip Zone Key Mismatch
===========================
Changes 'price' to 'level' in engines.py detect_flip_zones()
so validators can read the zone level correctly.
"""

import re

# Read engines.py
with open('/opt/jayce/engines.py', 'r') as f:
    content = f.read()

# Fix 1: Change 'price' to 'level' in flip_zones dict (line ~237)
old_pattern = """            flip_zones.append({
                'fib_level': fib_name,
                'price': fib_price,
                'zone_top': fib_price + zone_size,
                'zone_bot': fib_price - zone_size,
                'touches': touches,
                'rejections': rejections,
            })"""

new_pattern = """            flip_zones.append({
                'fib_level': fib_name,
                'level': fib_price,  # FIXED: was 'price', validators expect 'level'
                'price': fib_price,  # Keep for backwards compat
                'zone_top': fib_price + zone_size,
                'zone_bottom': fib_price - zone_size,  # FIXED: was 'zone_bot'
                'zone_bot': fib_price - zone_size,  # Keep for backwards compat
                'touches': touches,
                'rejections': rejections,
                'fresh': True,  # Added: validators check this
            })"""

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print("✅ Fixed flip_zones dict keys in detect_flip_zones()")
else:
    print("⚠️ Could not find exact pattern - checking alternate...")
    # Try regex approach
    if "'price': fib_price," in content and "'zone_bot':" in content:
        content = content.replace("'price': fib_price,", "'level': fib_price,  # FIXED\n                'price': fib_price,  # backwards compat")
        content = content.replace("'zone_bot': fib_price - zone_size,", "'zone_bottom': fib_price - zone_size,\n                'zone_bot': fib_price - zone_size,  # backwards compat")
        print("✅ Fixed keys using fallback method")
    else:
        print("❌ Could not locate flip_zones pattern")

# Write back
with open('/opt/jayce/engines.py', 'w') as f:
    f.write(content)

print("\nDone! Now restart scanner: sudo systemctl restart jayce-scanner")
