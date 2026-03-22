"""
HYBRID INTAKE PIPELINE v3.0 - WizTheory Correct Logic

Stage 2: Metadata Filter (no API)
Stage 3: Candle Fetch + Structure Check (with proper flip zone detection)

CORE CONCEPT: Continuation structures only
- Previous ATH/major high must be BROKEN (not just touched)
- Breakout must produce clear expansion with volume
- Prior resistance becomes flip zone (2+ touches OR 1 touch + consolidation)
- First pullback returns to flip zone + fib level
- Alert triggers during FIRST pullback into zone
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MetadataScore:
    """Result of Stage 2 metadata scoring."""
    token: Dict
    score: int
    reasons: List[str]


@dataclass
class FlipZone:
    """Detected flip zone (prior resistance becoming support)."""
    level: float
    touches: int
    has_consolidation: bool
    zone_top: float
    zone_bottom: float
    valid: bool


@dataclass
class MiniStructureScore:
    """Result of Stage 3 mini structure check."""
    token: Dict
    metadata_score: int
    structure_score: int
    total_score: int
    reasons: List[str]
    
    # Key flags
    ath_breakout: bool = False
    major_high_break: bool = False
    impulse_detected: bool = False
    in_pullback: bool = False
    retracement_pct: float = 0
    impulse_pct: float = 0
    
    # Flip zone data
    flip_zone: Optional[FlipZone] = None
    has_valid_flip_zone: bool = False
    
    # Volume confirmation
    expansion_volume_strong: bool = False
    
    # Gate check for 50+FZ
    passes_50fz_gate: bool = False
    passes_382fz_gate: bool = False
    passes_618fz_gate: bool = False
    passes_786fz_gate: bool = False
    passes_underfib_gate: bool = False


def stage2_metadata_filter(tokens: List[Dict], top_n: int = 60) -> List[MetadataScore]:
    """
    STAGE 2: Metadata Filter (no API calls)
    
    Score tokens based on metadata only. Prioritize THE MOVE.
    Returns top N tokens for candle fetch.
    
    DEDUPLICATION: If a token appears multiple times (from different sources),
    we keep ALL versions for scoring, then deduplicate AFTER scoring to keep
    the highest-scoring version of each token.
    """
    scored = []
    
    for token in tokens:
        score = 50  # Base score
        reasons = []
        
        # --- THE MOVE (highest priority) ---
        price_change_1h = abs(token.get('price_change_1h', 0) or 
                             token.get('priceChange1h', 0) or 0)
        price_change_24h = abs(token.get('price_change_24h', 0) or 
                              token.get('priceChange24h', 0) or 0)
        
        # Big 1h move = potential setup forming NOW
        if price_change_1h > 40:
            score += 20
            reasons.append('BIG_MOVE_1H')
        elif price_change_1h > 25:
            score += 12
            reasons.append('strong_move')
        elif price_change_1h > 15:
            score += 6
        
        # 24h expansion = impulse happened
        if price_change_24h > 80:
            score += 15
            reasons.append('major_expansion')
        elif price_change_24h > 50:
            score += 10
            reasons.append('expansion')
        elif price_change_24h > 30:
            score += 5
        
        # --- VOLUME (confirms move is real) ---
        vol_5m = token.get('volume_5m', 0) or token.get('volume5m', 0) or 0
        vol_1h = token.get('volume_1h', 0) or token.get('volume1h', 0) or 0
        
        if vol_1h > 0 and vol_5m > 0:
            vol_ratio = (vol_5m * 12) / vol_1h
            if vol_ratio > 2.0:
                score += 10
                reasons.append('vol_spike')
            elif vol_ratio > 1.5:
                score += 5
        
        if vol_5m > 30000:
            score += 5
            reasons.append('high_vol')
        
        # --- LIQUIDITY (minimum threshold) ---
        liquidity = token.get('liquidity', 0) or token.get('liq', 0) or 0
        if liquidity < 10000:
            score -= 15
            reasons.append('LOW_LIQ')
        elif liquidity > 50000:
            score += 3
        
        # --- TRENDING (small bonus only) ---
        source = token.get('source', '')
        rank = token.get('rank', 999)
        
        if source == 'TRENDING' and rank <= 20:
            score += 5
            reasons.append('trending')
        
        # Cap score
        score = min(100, max(0, score))
        
        scored.append(MetadataScore(
            token=token,
            score=score,
            reasons=reasons
        ))
    
    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)
    
    # DEDUPLICATE: Keep only the highest-scoring version of each token
    seen_addresses = set()
    deduped = []
    deduped_count = 0
    for result in scored:
        pair_address = result.token.get('pair_address', '')
        if pair_address and pair_address not in seen_addresses:
            seen_addresses.add(pair_address)
            deduped.append(result)
        else:
            deduped_count += 1
    
    if deduped_count > 0:
        logger.debug(f"[HYBRID] Stage 2: Deduped {deduped_count} duplicate tokens")
    
    # Return top N
    return deduped[:top_n]


def _detect_flip_zone(candles: List[Dict], breakout_level: float) -> Optional[FlipZone]:
    """
    Detect flip zone at a given level.
    
    A flip zone requires EITHER:
    - 2+ touches/rejections at the resistance level
    - 1 touch + sideways consolidation before breakout
    
    Consolidation = multiple candles moving sideways with tight range, no chaotic wicks.
    """
    if not candles or len(candles) < 30 or breakout_level <= 0:
        return None
    
    # Define zone tolerance (3% of level)
    tolerance = breakout_level * 0.03
    zone_top = breakout_level + tolerance
    zone_bottom = breakout_level - tolerance
    
    # Find the breakout candle (first candle that closed above the zone)
    breakout_idx = None
    for i, c in enumerate(candles):
        close = float(c.get('c', 0) or 0)
        if close > zone_top:
            breakout_idx = i
            break
    
    if breakout_idx is None or breakout_idx < 10:
        return None  # No breakout found or not enough prior candles
    
    # Look at candles BEFORE the breakout
    prior_candles = candles[:breakout_idx]
    
    # Count touches/rejections at the zone
    touches = 0
    rejection_indices = []
    
    for i, c in enumerate(prior_candles):
        high = float(c.get('h', 0) or 0)
        close = float(c.get('c', 0) or 0)
        
        # Touch = high reached zone but close was below (rejection)
        if high >= zone_bottom and close < zone_top:
            touches += 1
            rejection_indices.append(i)
    
    # Check for consolidation (tight range sideways movement before breakout)
    has_consolidation = False
    
    if len(prior_candles) >= 5:
        # Look at last 10-20 candles before breakout
        consol_candles = prior_candles[-20:] if len(prior_candles) >= 20 else prior_candles[-10:]
        
        if len(consol_candles) >= 5:
            consol_highs = [float(c.get('h', 0) or 0) for c in consol_candles]
            consol_lows = [float(c.get('l', 0) or 0) for c in consol_candles]
            
            consol_highs = [h for h in consol_highs if h > 0]
            consol_lows = [l for l in consol_lows if l > 0]
            
            if consol_highs and consol_lows:
                range_high = max(consol_highs)
                range_low = min(consol_lows)
                range_size = range_high - range_low
                
                # Consolidation = tight range (less than 15% of level)
                if range_size < breakout_level * 0.15:
                    # Check for no chaotic wicks
                    wick_chaos = 0
                    for c in consol_candles:
                        o = float(c.get('o', 0) or 0)
                        h = float(c.get('h', 0) or 0)
                        l = float(c.get('l', 0) or 0)
                        close = float(c.get('c', 0) or 0)
                        
                        if h > l and o > 0:
                            body = abs(close - o)
                            total_range = h - l
                            # Chaotic = body < 30% of range (long wicks)
                            if total_range > 0 and body < total_range * 0.3:
                                wick_chaos += 1
                    
                    # Less than 30% chaotic candles = clean consolidation
                    if wick_chaos < len(consol_candles) * 0.3:
                        has_consolidation = True
    
    # Flip zone is valid if:
    # - 2+ touches at resistance, OR
    # - 1+ touch with consolidation before breakout
    valid = (touches >= 2) or (touches >= 1 and has_consolidation)
    
    return FlipZone(
        level=breakout_level,
        touches=touches,
        has_consolidation=has_consolidation,
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        valid=valid
    )


def _check_expansion_volume(candles: List[Dict], expansion_start_idx: int, expansion_end_idx: int) -> bool:
    """
    Check if expansion phase showed increasing volume.
    """
    if expansion_start_idx >= expansion_end_idx or expansion_end_idx >= len(candles):
        return False
    
    try:
        # Get volumes
        prior_volumes = []
        expansion_volumes = []
        
        # Prior volumes (before expansion)
        for i in range(max(0, expansion_start_idx - 10), expansion_start_idx):
            vol = float(candles[i].get('v', 0) or candles[i].get('volume', 0) or 0)
            if vol > 0:
                prior_volumes.append(vol)
        
        # Expansion volumes
        for i in range(expansion_start_idx, min(expansion_end_idx + 1, len(candles))):
            vol = float(candles[i].get('v', 0) or candles[i].get('volume', 0) or 0)
            if vol > 0:
                expansion_volumes.append(vol)
        
        if not prior_volumes or not expansion_volumes:
            return True  # Can't determine, assume OK
        
        avg_prior = sum(prior_volumes) / len(prior_volumes)
        avg_expansion = sum(expansion_volumes) / len(expansion_volumes)
        
        # Expansion volume should be at least 50% higher than prior
        return avg_expansion > avg_prior * 1.5
    
    except Exception:
        return True  # Can't determine, assume OK


def stage3_mini_structure_check(
    token: Dict, 
    candles: List[Dict],
    metadata_score: int = 50
) -> Optional[MiniStructureScore]:
    """
    STAGE 3: Mini Structure Check - WizTheory Correct Logic
    
    Detects CONTINUATION structures:
    1. Previous ATH/major high is BROKEN (not just touched)
    2. Breakout produces expansion with volume
    3. Prior resistance becomes flip zone
    4. First pullback returns to flip zone + fib level
    """
    if not candles or len(candles) < 30:
        return None
    
    reasons = []
    structure_score = 0
    
    # Extract price data
    highs = [float(c.get('h', 0) or 0) for c in candles]
    lows = [float(c.get('l', 0) or 0) for c in candles]
    closes = [float(c.get('c', 0) or 0) for c in candles]
    
    # Filter zeros
    highs = [h for h in highs if h > 0]
    lows = [l for l in lows if l > 0]
    closes = [c for c in closes if c > 0]
    
    if len(highs) < 30 or len(lows) < 30:
        return None
    
    # Current price
    current_price = closes[-1]
    
    # ═══════════════════════════════════════════════════════════════
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
        reasons.append(f'{impulse_pct:.0f}%_exp')
    
    # --- FLIP ZONE DETECTION ---
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
        reasons.append(f'FZ_{best_fz.get("touches", 0)}touch')
    
    # --- EXPANSION CALCULATION ---
    # Measure from breakout level to recent high
    expansion_pct = 0
    if breakout_level > 0:
        expansion_pct = ((expansion_high - breakout_level) / breakout_level) * 100
    
    impulse_pct = ((expansion_high - swing_low) / swing_low * 100) if swing_low > 0 else 0
    
    impulse_detected = expansion_pct >= 25 or impulse_pct >= 30
    
    if expansion_pct >= 35:
        structure_score += 15
        reasons.append(f'expansion_{expansion_pct:.0f}%')
    elif expansion_pct >= 25:
        structure_score += 10
        reasons.append(f'expansion_{expansion_pct:.0f}%')
    elif impulse_pct >= 30:
        structure_score += 8
        reasons.append(f'impulse_{impulse_pct:.0f}%')
    
    # --- VOLUME CONFIRMATION ---
    expansion_volume_strong = _check_expansion_volume(candles, prior_resistance_idx, expansion_high_idx)
    
    if expansion_volume_strong:
        structure_score += 5
        reasons.append('vol_confirm')
    
    # --- RETRACEMENT CHECK ---
    # Measure from recent high back to breakout level (flip zone)
    range_size = expansion_high - swing_low
    retracement_pct = ((expansion_high - current_price) / range_size * 100) if range_size > 0 else 0
    
    in_pullback = 20 <= retracement_pct <= 80
    
    # In pullback zone
    if 30 <= retracement_pct <= 55:
        structure_score += 10
        reasons.append(f'retrace_{retracement_pct:.0f}%')
    elif 25 <= retracement_pct <= 65:
        structure_score += 5
        reasons.append(f'retrace_{retracement_pct:.0f}%')
    
    # --- PRICE RELATIVE TO FLIP ZONE ---
    # Check if price is at/near the flip zone level
    if has_valid_flip_zone:
        distance_to_fz = abs(current_price - flip_zone.level) / flip_zone.level * 100
        if distance_to_fz < 5:  # Within 5% of flip zone
            structure_score += 10
            reasons.append('at_flip_zone')
    
    # --- STRUCTURE INTACT ---
    if current_price > swing_low * 1.05:
        structure_score += 5
        reasons.append('structure_intact')
    
    # --- CANDLE QUALITY ---
    clean_candles = 0
    for i in range(max(0, len(candles) - 30), len(candles)):
        c = candles[i]
        o = float(c.get('o', 0) or 0)
        h = float(c.get('h', 0) or 0)
        l = float(c.get('l', 0) or 0)
        close = float(c.get('c', 0) or 0)
        
        if h > l and o > 0:
            body = abs(close - o)
            total_range = h - l
            if body >= total_range * 0.5:
                clean_candles += 1
    
    if clean_candles >= 15:
        structure_score += 5
        reasons.append('clean_candles')
    
    # --- GATE CHECKS ---
    
    # 382+FZ Gate: 30-42% retracement + breakout + flip zone
    is_382_territory = 28 <= retracement_pct <= 45
    passes_382fz_gate = False
    
    if is_382_territory:
        if (ath_breakout or major_high_break) and has_valid_flip_zone:
            passes_382fz_gate = True
            reasons.append('382FZ_GATE_PASS')
        elif ath_breakout or major_high_break:
            reasons.append('382_NO_FZ')
        else:
            reasons.append('382_NO_BREAK')
    
    # 50+FZ Gate: 45-55% retracement + breakout + flip zone
    is_50fz_territory = 40 <= retracement_pct <= 60
    passes_50fz_gate = False
    
    if is_50fz_territory:
        if (ath_breakout or major_high_break) and has_valid_flip_zone:
            passes_50fz_gate = True
            reasons.append('50FZ_GATE_PASS')
        elif ath_breakout or major_high_break:
            reasons.append('50_NO_FZ')
        else:
            reasons.append('50_NO_BREAK')
    
    # 618+FZ Gate: 58-68% retracement + breakout + flip zone + strong expansion
    is_618_territory = 55 <= retracement_pct <= 70
    passes_618fz_gate = False
    
    if is_618_territory:
        # 618 requires stronger expansion (>=60% breakout or impulse)
        # Use whichever is higher: breakout_pct or impulse_pct
        expansion_check = max(breakout_pct, impulse_pct) if breakout_pct > 0 else impulse_pct
        strong_expansion = expansion_check >= 60
        
        if (ath_breakout or major_high_break) and has_valid_flip_zone and strong_expansion:
            passes_618fz_gate = True
            reasons.append('618FZ_GATE_PASS')
        elif (ath_breakout or major_high_break) and has_valid_flip_zone:
            # Has breakout and flip zone but weak expansion
            reasons.append(f'618_WEAK_EXP_{expansion_check:.0f}%')
        elif ath_breakout or major_high_break:
            reasons.append('618_NO_FZ')
        else:
            reasons.append('618_NO_BREAK')
    
    # 786+FZ Gate: 70-80% retracement + breakout + flip zone + STRONG expansion (>=100%)
    is_786_territory = 68 <= retracement_pct <= 82
    passes_786fz_gate = False
    
    if is_786_territory:
        # 786 requires very strong expansion (>=100% breakout)
        expansion_check = max(breakout_pct, impulse_pct) if breakout_pct > 0 else impulse_pct
        very_strong_expansion = expansion_check >= 100
        
        if (ath_breakout or major_high_break) and has_valid_flip_zone and very_strong_expansion:
            passes_786fz_gate = True
            reasons.append('786FZ_GATE_PASS')
        elif (ath_breakout or major_high_break) and has_valid_flip_zone:
            reasons.append(f'786_WEAK_EXP_{expansion_check:.0f}%')
        elif ath_breakout or major_high_break:
            reasons.append('786_NO_FZ')
        else:
            reasons.append('786_NO_BREAK')
    
    # 786+FZ Gate: 70-80% retracement + breakout + flip zone + STRONG expansion (>=100%)
    is_786_territory = 68 <= retracement_pct <= 82
    passes_786fz_gate = False
    
    if is_786_territory:
        # 786 requires very strong expansion (>=100% breakout)
        expansion_check = max(breakout_pct, impulse_pct) if breakout_pct > 0 else impulse_pct
        very_strong_expansion = expansion_check >= 100
        
        if (ath_breakout or major_high_break) and has_valid_flip_zone and very_strong_expansion:
            passes_786fz_gate = True
            reasons.append('786FZ_GATE_PASS')
        elif (ath_breakout or major_high_break) and has_valid_flip_zone:
            reasons.append(f'786_WEAK_EXP_{expansion_check:.0f}%')
        elif ath_breakout or major_high_break:
            reasons.append('786_NO_FZ')
        else:
            reasons.append('786_NO_BREAK')
    
    # If not in territory, default pass for other engines
    if not is_382_territory:
        passes_382fz_gate = True
    if not is_50fz_territory:
        passes_50fz_gate = True
    if not is_618_territory:
        passes_618fz_gate = True
    if not is_786_territory:
        passes_786fz_gate = True
    
    # Under-Fib Gate: >= 40% retracement + breakout + flip zone + decent expansion (>=60%)
    # Under-Fib = flip zone exists BELOW a fib level, price breaks fib to reach zone
    is_underfib_territory = retracement_pct >= 40  # Must retrace at least 40%
    passes_underfib_gate = False
    
    if is_underfib_territory:
        # Under-Fib requires >= 60% expansion
        expansion_check = max(breakout_pct, impulse_pct) if breakout_pct > 0 else impulse_pct
        decent_expansion = expansion_check >= 60
        
        if (ath_breakout or major_high_break) and has_valid_flip_zone and decent_expansion:
            passes_underfib_gate = True
            reasons.append('UNDERFIB_GATE_PASS')
        elif (ath_breakout or major_high_break) and has_valid_flip_zone:
            reasons.append(f'UNDERFIB_WEAK_EXP_{expansion_check:.0f}%')
    
    if not is_underfib_territory:
        passes_underfib_gate = True
    
    # Total score
    total_score = metadata_score + structure_score
    
    return MiniStructureScore(
        token=token,
        metadata_score=metadata_score,
        structure_score=structure_score,
        total_score=total_score,
        reasons=reasons,
        ath_breakout=ath_breakout,
        major_high_break=major_high_break,
        impulse_detected=impulse_detected,
        in_pullback=in_pullback,
        retracement_pct=retracement_pct,
        impulse_pct=impulse_pct,
        flip_zone=flip_zone,
        has_valid_flip_zone=has_valid_flip_zone,
        expansion_volume_strong=expansion_volume_strong,
        passes_50fz_gate=passes_50fz_gate,
        passes_382fz_gate=passes_382fz_gate,
        passes_618fz_gate=passes_618fz_gate,
        passes_786fz_gate=passes_786fz_gate,
        passes_underfib_gate=passes_underfib_gate
    )


async def run_hybrid_intake(
    tokens: List[Dict],
    fetch_candles_func,
    metadata_top_n: int = 60,
    structure_top_n: int = 40
) -> List[MiniStructureScore]:
    """
    Run the full hybrid intake pipeline (Stages 2-3).
    """
    logger.info(f"[HYBRID] Stage 2: Metadata filter on {len(tokens)} tokens...")
    
    # Stage 2: Metadata filter
    metadata_results = stage2_metadata_filter(tokens, top_n=metadata_top_n)
    
    logger.info(f"[HYBRID] Stage 2 complete: {len(metadata_results)} tokens passed")
    
    # Log top 10 metadata scores
    for i, result in enumerate(metadata_results[:10]):
        sym = result.token.get('symbol', '???')
        reasons_str = ', '.join(result.reasons[:3]) if result.reasons else 'base'
        logger.info(f"[HYBRID]   #{i+1}: {sym} (meta: {result.score}) [{reasons_str}]")
    
    # Stage 3: Candle fetch + structure check
    logger.info(f"[HYBRID] Stage 3: Fetching candles for {len(metadata_results)} tokens...")
    
    structure_results = []
    
    for i, meta_result in enumerate(metadata_results):
        token = meta_result.token
        symbol = token.get('symbol', '???')
        pair_address = token.get('pair_address', '')
        
        if not pair_address:
            continue
        
        try:
            # Fetch candles
            candles = await fetch_candles_func(pair_address, symbol, token.get('address', ''))
            
            if candles and len(candles) >= 30:
                # Run structure check
                struct_result = stage3_mini_structure_check(
                    token=token,
                    candles=candles,
                    metadata_score=meta_result.score
                )
                
                if struct_result:
                    structure_results.append(struct_result)
                    
                    # Log significant findings
                    if struct_result.has_valid_flip_zone and (struct_result.ath_breakout or struct_result.major_high_break):
                        logger.info(f"[HYBRID]   ⭐ {symbol}: {', '.join(struct_result.reasons[:5])}")
        
        except Exception as e:
            logger.debug(f"[HYBRID] Error processing {symbol}: {e}")
            continue
    
    logger.info(f"[HYBRID] Stage 3 complete: {len(structure_results)} tokens analyzed")
    
    # DEDUPLICATE structure results: Keep highest-scoring version of each token
    seen_addresses = set()
    deduped_results = []
    skipped_dupes = []
    
    # Debug: Log all pair_addresses before dedup
    all_pairs = [(r.token.get('symbol', '???'), r.token.get('pair_address', 'NONE')[:20], r.total_score) for r in structure_results]
    logger.info(f"[HYBRID] Pre-dedupe: {len(structure_results)} results")
    
    for result in sorted(structure_results, key=lambda x: x.total_score, reverse=True):
        pair_address = result.token.get('pair_address', '')
        symbol = result.token.get('symbol', '???')
        
        if not pair_address:
            logger.warning(f"[HYBRID] ⚠️ No pair_address for {symbol} (total={result.total_score}) - keeping anyway")
            deduped_results.append(result)
        elif pair_address not in seen_addresses:
            seen_addresses.add(pair_address)
            deduped_results.append(result)
        else:
            skipped_dupes.append(f"{symbol}:{result.total_score}")
            logger.info(f"[HYBRID] ↳ Skipped duplicate: {symbol} (score={result.total_score}, addr={pair_address[:20]}...)")
    
    if skipped_dupes:
        logger.info(f"[HYBRID] Stage 3: Deduped {len(skipped_dupes)} duplicates: {', '.join(skipped_dupes[:5])}")
    else:
        logger.info(f"[HYBRID] Stage 3: No duplicates found (all {len(deduped_results)} unique)")
    
    structure_results = deduped_results
    
    # Log top structure scores
    logger.info(f"[HYBRID] Top structure scores:")
    for i, result in enumerate(structure_results[:10]):
        sym = result.token.get('symbol', '???')
        fz = "FZ✓" if result.has_valid_flip_zone else "FZ✗"
        brk = "BRK✓" if (result.ath_breakout or result.major_high_break) else "BRK✗"
        reasons_str = ', '.join(result.reasons[:4])
        logger.info(f"[HYBRID]   #{i+1}: {sym} (total: {result.total_score}, struct: {result.structure_score}) [{fz}|{brk}] {reasons_str}")
    
    # Scoring integrity check: Verify all results have complete scores
    incomplete = [r for r in structure_results if r.total_score == 0 or r.metadata_score == 0]
    if incomplete:
        logger.warning(f"[HYBRID] ⚠️ {len(incomplete)} tokens with incomplete scores!")
        for r in incomplete[:3]:
            logger.warning(f"[HYBRID]   - {r.token.get('symbol', '???')}: meta={r.metadata_score} struct={r.structure_score} total={r.total_score}")
    
    # Return top N for WizTheory engine
    final_candidates = structure_results[:structure_top_n]
    
    logger.info(f"[HYBRID] Final: {len(final_candidates)} tokens → WizTheory engine")
    
    return final_candidates
