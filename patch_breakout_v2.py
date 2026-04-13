#!/usr/bin/env python3
"""
PATCH: Structural Breakout Detection v2.0

Respects setup-specific expansion requirements:
- 382: 30% min
- 50: 50% min  
- 618: 60% min
- 786: 100% min
- Under-Fib: 60% min

Breakout detection is STRUCTURAL, not candle-position based.
"""

with open('/opt/jayce/hybrid_intake.py', 'r') as f:
    content = f.read()

old_section_start = "    # --- FIND KEY LEVELS ---"
old_section_end = "reasons.append(f'{breakout_pct:.0f}%_exp')"

start_idx = content.find(old_section_start)
end_idx = content.find(old_section_end)

if start_idx == -1 or end_idx == -1:
    print("❌ Could not find target section")
    exit(1)

end_idx = end_idx + len(old_section_end)

new_logic = '''    # ═══════════════════════════════════════════════════════════════
    # STRUCTURAL BREAKOUT DETECTION v2.0
    # ═══════════════════════════════════════════════════════════════
    # Structure-based detection (not candle-position dependent)
    #
    # SETUP EXPANSION REQUIREMENTS (LOCKED - DO NOT CHANGE):
    # - 382: 30% min impulse
    # - 50:  50% min impulse
    # - 618: 60% min impulse
    # - 786: 100% min impulse
    # - Under-Fib: 60% min impulse
    # ═══════════════════════════════════════════════════════════════
    
    symbol = token.get('symbol', '???')
    candle_count = len(highs)
    current_price = closes[-1]
    
    # --- STEP 1: Find Expansion High (highest wick in chart) ---
    expansion_high = max(highs)
    expansion_high_idx = highs.index(expansion_high)
    
    # --- STEP 2: Find Prior Resistance (major high BEFORE expansion) ---
    prior_resistance = 0
    prior_resistance_idx = 0
    
    if expansion_high_idx >= 5:
        prior_highs = highs[:expansion_high_idx]
        if prior_highs:
            prior_resistance = max(prior_highs)
            prior_resistance_idx = prior_highs.index(prior_resistance)
    
    # Fallback: find second-highest peak at least 5 candles away
    if prior_resistance == 0:
        sorted_peaks = sorted(enumerate(highs), key=lambda x: x[1], reverse=True)
        for idx, val in sorted_peaks[1:]:
            if abs(idx - expansion_high_idx) >= 5:
                prior_resistance = val
                prior_resistance_idx = idx
                break
    
    # --- STEP 3: Find Swing Low (base of expansion) ---
    if expansion_high_idx > 0:
        swing_low = min(lows[:expansion_high_idx + 1])
        swing_low_idx = lows.index(swing_low)
    else:
        swing_low = min(lows)
        swing_low_idx = lows.index(swing_low)
    
    # Ensure swing low is BEFORE expansion high
    if swing_low_idx > expansion_high_idx and expansion_high_idx > 0:
        pre_high_lows = lows[:expansion_high_idx]
        if pre_high_lows:
            swing_low = min(pre_high_lows)
            swing_low_idx = pre_high_lows.index(swing_low)
    
    # --- STEP 4: Calculate Metrics ---
    impulse_range = expansion_high - swing_low
    impulse_pct = ((impulse_range) / swing_low * 100) if swing_low > 0 else 0
    
    breakout_pct = 0
    if prior_resistance > 0 and prior_resistance < expansion_high:
        breakout_pct = ((expansion_high - prior_resistance) / prior_resistance * 100)
    
    retracement_pct = 0
    if impulse_range > 0:
        retracement_pct = ((expansion_high - current_price) / impulse_range * 100)
        retracement_pct = max(0, retracement_pct)
    
    # --- STEP 5: Classify Breakout Type ---
    ath_breakout = False
    major_high_break = False
    
    # Minimum requirements for ANY valid breakout structure:
    # - At least 30% impulse (minimum for 382 setup)
    # - Price in pullback phase (at least 15% retracement)
    has_min_expansion = impulse_pct >= 30
    in_pullback = retracement_pct >= 15
    broke_resistance = breakout_pct >= 10
    
    if has_min_expansion and in_pullback:
        # ATH_BREAK: Strong expansion (enough for 786) + broke resistance
        if impulse_pct >= 100 and broke_resistance:
            ath_breakout = True
            structure_score += 20
            reasons.append('ATH_BREAKOUT')
        
        # MAJOR_HIGH_BREAK: Moderate expansion + broke resistance
        elif impulse_pct >= 50 and broke_resistance:
            major_high_break = True
            structure_score += 15
            reasons.append('MAJOR_HIGH_BREAK')
        
        # MAJOR_HIGH_BREAK: Good expansion even without clear prior resistance
        # (handles fresh coins where prior resistance not visible)
        elif impulse_pct >= 60:
            major_high_break = True
            structure_score += 12
            reasons.append('MAJOR_HIGH_BREAK')
        
        # Weaker but valid structure (enough for 382/50)
        elif impulse_pct >= 30:
            major_high_break = True
            structure_score += 8
            reasons.append('MAJOR_HIGH_BREAK')
    
    if not ath_breakout and not major_high_break:
        reasons.append('NO_BREAKOUT')
        reasons.append(f'{impulse_pct:.0f}%_exp')'''

new_content = content[:start_idx] + new_logic + content[end_idx:]

with open('/opt/jayce/hybrid_intake.py', 'w') as f:
    f.write(new_content)

print("✅ Patched breakout detection v2.0")
print("")
print("BREAKOUT CLASSIFICATION:")
print("  ATH_BREAK:        impulse >= 100% + broke prior resistance")
print("  MAJOR_HIGH_BREAK: impulse >= 50%  + broke prior resistance")
print("                 OR impulse >= 60%  (fresh coin)")
print("                 OR impulse >= 30%  (min for 382)")
print("")
print("All require: in pullback phase (ret >= 15%)")
