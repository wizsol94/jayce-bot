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
    
    # Return top N
    return scored[:top_n]


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
    
    # --- FIND KEY LEVELS ---
    
    # Recent high (in last 50% of candles - the expansion high)
    half_point = len(highs) // 2
    recent_high = max(highs[half_point:]) if half_point > 0 else max(highs[-50:])
    recent_high_idx = highs.index(recent_high) if recent_high in highs else len(highs) - 1
    
    # Prior high (in first 50% of candles - the resistance that was broken)
    prior_high = max(highs[:half_point]) if half_point > 10 else max(highs[:20])
    prior_high_idx = highs.index(prior_high) if prior_high in highs else 0
    
    # Overall ATH
    ath = max(highs)
    ath_idx = highs.index(ath) if ath in highs else len(highs) - 1
    
    # DEBUG: Log ATH position for troubleshooting
    symbol = token.get('symbol', '???')
    if symbol in ['PIGEON', 'HAT', 'WAR']:
        logger.info(f"[DEBUG] {symbol}: ATH_idx={ath_idx}, candle_count={len(highs)}, ath_pct={ath_idx/len(highs)*100:.1f}%, recent_high_idx={recent_high_idx}")
    
    # Swing low for impulse calculation
    swing_low = min(lows)
    
    # --- BREAKOUT DETECTION ---
    # With only ~24h of candle data, we can't reliably detect TRUE ATH.
    # Instead, detect BREAKOUT ABOVE PRIOR RESISTANCE within our data window.
    #
    # Valid breakout structure:
    # 1. Prior resistance exists in FIRST 60% of candles
    # 2. Recent high BROKE ABOVE that resistance (by at least 15%)
    # 3. The breakout happened in the LAST 50% of candles
    # 4. Price is now pulling back toward the broken resistance
    
    ath_breakout = False
    major_high_break = False
    candle_count = len(highs)
    
    # Calculate the breakout percentage (how much did recent high exceed prior resistance)
    breakout_pct = ((recent_high - prior_high) / prior_high * 100) if prior_high > 0 else 0
    
    # Valid breakout: recent high is significantly above prior resistance
    # AND the breakout happened recently (recent_high_idx in last 50%)
    # AND prior_high is actually in the first part of the data (it's prior resistance)
    
    breakout_is_recent = recent_high_idx > candle_count * 0.50
    prior_is_resistance = prior_high_idx < candle_count * 0.60
    significant_breakout = breakout_pct >= 15  # At least 15% above prior resistance
    
    if breakout_is_recent and prior_is_resistance and significant_breakout:
        # This is a valid breakout above prior resistance
        if breakout_pct >= 30:
            ath_breakout = True  # Strong breakout
            structure_score += 20
            reasons.append('ATH_BREAKOUT')
        else:
            major_high_break = True  # Moderate breakout
            structure_score += 15
            reasons.append('MAJOR_HIGH_BREAK')
    
    # If breakout is weak or didn't happen recently, NOT a continuation structure
    if not ath_breakout and not major_high_break:
        reasons.append('NO_BREAKOUT')
        reasons.append(f'{breakout_pct:.0f}%_exp')
    
    # --- FLIP ZONE DETECTION ---
    # The level that was broken becomes the flip zone
    breakout_level = prior_high  # The resistance that was broken
    
    flip_zone = _detect_flip_zone(candles, breakout_level)
    has_valid_flip_zone = flip_zone is not None and flip_zone.valid
    
    if has_valid_flip_zone:
        structure_score += 15
        if flip_zone.touches >= 2:
            reasons.append(f'FZ_{flip_zone.touches}touch')
        elif flip_zone.has_consolidation:
            reasons.append('FZ_consol')
    
    # --- EXPANSION CALCULATION ---
    # Measure from breakout level to recent high
    expansion_pct = 0
    if breakout_level > 0:
        expansion_pct = ((recent_high - breakout_level) / breakout_level) * 100
    
    impulse_pct = ((recent_high - swing_low) / swing_low * 100) if swing_low > 0 else 0
    
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
    expansion_volume_strong = _check_expansion_volume(candles, prior_high_idx, recent_high_idx)
    
    if expansion_volume_strong:
        structure_score += 5
        reasons.append('vol_confirm')
    
    # --- RETRACEMENT CHECK ---
    # Measure from recent high back to breakout level (flip zone)
    range_size = recent_high - swing_low
    retracement_pct = ((recent_high - current_price) / range_size * 100) if range_size > 0 else 0
    
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
    
    # Sort by total score
    structure_results.sort(key=lambda x: x.total_score, reverse=True)
    
    # Log top structure scores
    logger.info(f"[HYBRID] Top structure scores:")
    for i, result in enumerate(structure_results[:10]):
        sym = result.token.get('symbol', '???')
        fz = "FZ✓" if result.has_valid_flip_zone else "FZ✗"
        brk = "BRK✓" if (result.ath_breakout or result.major_high_break) else "BRK✗"
        reasons_str = ', '.join(result.reasons[:4])
        logger.info(f"[HYBRID]   #{i+1}: {sym} (total: {result.total_score}, struct: {result.structure_score}) [{fz}|{brk}] {reasons_str}")
    
    # Return top N for WizTheory engine
    final_candidates = structure_results[:structure_top_n]
    
    logger.info(f"[HYBRID] Final: {len(final_candidates)} tokens → WizTheory engine")
    
    return final_candidates
