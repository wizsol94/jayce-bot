#!/usr/bin/env python3
"""
PATCH: Use engines.py flip zone detection in hybrid_intake
"""

with open('/opt/jayce/hybrid_intake.py', 'r') as f:
    content = f.read()

old_code = '''    # --- FLIP ZONE DETECTION ---
    # The level that was broken becomes the flip zone
    breakout_level = prior_resistance  # The resistance that was broken
    
    flip_zone = _detect_flip_zone(candles, breakout_level)
    has_valid_flip_zone = flip_zone is not None and flip_zone.valid
    
    if has_valid_flip_zone:
        structure_score += 15
        if flip_zone.touches >= 2:
            reasons.append(f'FZ_{flip_zone.touches}touch')
        elif flip_zone.has_consolidation:
            reasons.append('FZ_consol')'''

new_code = '''    # --- FLIP ZONE DETECTION ---
    # Use engines.py flip zone detection (fib-based, proper touch counting)
    breakout_level = prior_resistance  # The resistance that was broken
    
    from engines import analyze_structure as _eng_analyze
    _eng_structure = _eng_analyze(candles)
    _eng_flip_zones = _eng_structure.get('flip_zones', []) if _eng_structure else []
    
    # Valid flip zone = any fib level with 2+ touches
    has_valid_flip_zone = any(fz.get('touches', 0) >= 2 for fz in _eng_flip_zones)
    
    # Create FlipZone object for compatibility
    flip_zone = None
    if has_valid_flip_zone:
        best_fz = max(_eng_flip_zones, key=lambda x: x.get('touches', 0))
        flip_zone = FlipZone(
            level=best_fz.get('level', best_fz.get('price', 0)),
            touches=best_fz.get('touches', 0),
            has_consolidation=True,
            zone_top=best_fz.get('zone_top', 0),
            zone_bottom=best_fz.get('zone_bottom', best_fz.get('zone_bot', 0)),
            valid=True
        )
        structure_score += 15
        reasons.append(f'FZ_{best_fz.get("touches", 0)}touch')'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('/opt/jayce/hybrid_intake.py', 'w') as f:
        f.write(content)
    print("✅ Patched hybrid_intake.py - Now uses engines.py flip zone detection")
else:
    print("❌ Could not find exact match")
