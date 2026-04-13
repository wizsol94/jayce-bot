"""
FLASHCARD ANALYSIS - Stage 5

Compares detected WizTheory setups to your flashcard library.
Boosts confidence for high-similarity matches.

RULES:
- Setup-specific: 50+FZ only compares to 50+FZ flashcards
- Max 10 flashcards per comparison
- Never blocks detection, only boosts confidence
- Runs AFTER WizTheory validates
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FLASHCARD_DIR = "/opt/jayce/flashcards"
MAX_FLASHCARDS_PER_TYPE = 10  # Limit for fast computation


@dataclass
class FlashcardMatch:
    """Result of comparing a setup to flashcards."""
    best_match_name: str
    similarity_score: float  # 0-100
    matching_factors: List[str]
    grade_boost: int  # 0, 1, or 2 levels
    confidence_note: str


def load_flashcards(engine_type: str) -> List[Dict]:
    """
    Load flashcards for a SPECIFIC engine type only.
    
    50+FZ setup → ONLY 50+FZ flashcards
    382 setup → ONLY 382 flashcards
    etc.
    
    Returns max 10 flashcards (sorted by best outcomes first).
    """
    flashcards = []
    
    # Map engine ID to flashcard folder names (strict matching)
    engine_folders = {
        '50': ['50_flip_zone', '50+fz', '50'],
        '382': ['382_flip_zone', '382+fz', '382'],
        '618': ['618_flip_zone', '618+fz', '618'],
        '786': ['786_flip_zone', '786+fz', '786'],
        'underfib': ['under_fib', 'underfib', 'under-fib']
    }
    
    folders_to_check = engine_folders.get(engine_type, [engine_type])
    
    for folder_name in folders_to_check:
        folder_path = os.path.join(FLASHCARD_DIR, folder_name)
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith('.json'):
                    try:
                        with open(os.path.join(folder_path, filename), 'r') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                flashcards.extend(data)
                            else:
                                flashcards.append(data)
                    except Exception as e:
                        logger.debug(f"Error loading flashcard {filename}: {e}")
    
    # Also check main flashcards.json filtered by engine type
    main_file = os.path.join(FLASHCARD_DIR, "flashcards.json")
    if os.path.exists(main_file):
        try:
            with open(main_file, 'r') as f:
                all_cards = json.load(f)
                for card in all_cards:
                    card_engine = str(card.get('engine', '')).lower().replace('+', '').replace('_', '').replace('-', '')
                    target_engine = engine_type.lower().replace('+', '').replace('_', '').replace('-', '')
                    
                    # Strict match - only same engine type
                    if card_engine == target_engine or target_engine in card_engine:
                        flashcards.append(card)
        except Exception as e:
            logger.debug(f"Error loading main flashcards.json: {e}")
    
    # Sort by outcome percentage (best performers first) and limit to 10
    flashcards.sort(key=lambda x: x.get('outcome_percentage', x.get('outcome', 0)), reverse=True)
    flashcards = flashcards[:MAX_FLASHCARDS_PER_TYPE]
    
    logger.debug(f"Loaded {len(flashcards)} flashcards for engine {engine_type}")
    return flashcards


def calculate_similarity(
    current_setup: Dict,
    flashcard: Dict,
    candles: List[Dict] = None
) -> Tuple[float, List[str]]:
    """
    Calculate similarity between current setup and a flashcard.
    
    Comparison factors:
    - Impulse expansion similarity (25 points)
    - Retracement depth similarity (30 points)  
    - Structure quality similarity (20 points)
    - Pullback behavior similarity (15 points)
    - Candle body vs wick behavior (10 points)
    
    Returns (similarity_score, matching_factors)
    """
    score = 0
    max_score = 100
    factors = []
    
    # --- IMPULSE SIZE SIMILARITY (25 points) ---
    current_impulse = current_setup.get('impulse_pct', 0)
    flash_impulse = flashcard.get('impulse_pct', flashcard.get('impulse', 50))
    
    if current_impulse > 0 and flash_impulse > 0:
        import math
        current_log = math.log10(max(current_impulse, 1))
        flash_log = math.log10(max(flash_impulse, 1))
        
        diff = abs(current_log - flash_log)
        if diff < 0.2:  # Very close
            score += 25
            factors.append('impulse_match')
        elif diff < 0.5:  # Close
            score += 18
            factors.append('impulse_similar')
        elif diff < 1.0:  # Somewhat close
            score += 10
    
    # --- RETRACEMENT DEPTH SIMILARITY (30 points) ---
    current_retrace = current_setup.get('retracement_pct', 50)
    flash_retrace = flashcard.get('retracement_pct', flashcard.get('retrace', 50))
    
    retrace_diff = abs(current_retrace - flash_retrace)
    if retrace_diff < 5:  # Within 5%
        score += 30
        factors.append('retrace_exact')
    elif retrace_diff < 10:  # Within 10%
        score += 22
        factors.append('retrace_close')
    elif retrace_diff < 15:  # Within 15%
        score += 12
        factors.append('retrace_similar')
    
    # --- STRUCTURE QUALITY (20 points) ---
    current_structure = current_setup.get('structure_quality', 'unknown')
    flash_structure = flashcard.get('structure_quality', flashcard.get('structure', 'clean'))
    
    current_clean = any(x in str(current_structure).lower() for x in ['clean', 'intact', 'hh', 'hl'])
    flash_clean = any(x in str(flash_structure).lower() for x in ['clean', 'intact', 'hh', 'hl'])
    
    if current_clean and flash_clean:
        score += 20
        factors.append('structure_match')
    elif current_clean or flash_clean:
        score += 10
    
    # --- PULLBACK BEHAVIOR (15 points) ---
    current_pullback = current_setup.get('pullback_type', 'unknown')
    flash_pullback = flashcard.get('pullback_type', flashcard.get('pullback', 'controlled'))
    
    current_controlled = any(x in str(current_pullback).lower() for x in ['controlled', 'gradual', 'clean'])
    flash_controlled = any(x in str(flash_pullback).lower() for x in ['controlled', 'gradual', 'clean'])
    
    if current_controlled and flash_controlled:
        score += 15
        factors.append('pullback_match')
    elif current_controlled or flash_controlled:
        score += 8
    
    # --- CANDLE BODY VS WICK BEHAVIOR (10 points) ---
    current_candle_quality = current_setup.get('candle_quality', 0)
    flash_candle_quality = flashcard.get('candle_quality', flashcard.get('clean_candles', 50))
    
    # If we have candles, calculate body vs wick ratio
    if candles and len(candles) >= 10:
        clean_count = 0
        for c in candles[-20:]:  # Last 20 candles
            o = float(c.get('o', 0) or 0)
            h = float(c.get('h', 0) or 0)
            l = float(c.get('l', 0) or 0)
            close = float(c.get('c', 0) or 0)
            
            if h > l and o > 0:
                body = abs(close - o)
                total_range = h - l
                if body >= total_range * 0.5:  # Body > 50% of range
                    clean_count += 1
        
        current_candle_quality = (clean_count / min(20, len(candles[-20:]))) * 100
    
    # Compare candle quality
    if current_candle_quality >= 50 and flash_candle_quality >= 50:
        score += 10
        factors.append('candle_quality_match')
    elif current_candle_quality >= 40:
        score += 5
    
    return score, factors


def analyze_flashcard_similarity(
    engine_type: str,
    current_setup: Dict,
    candles: List[Dict] = None
) -> Optional[FlashcardMatch]:
    """
    Main entry point: Compare current setup to flashcard library.
    
    ONLY loads flashcards matching the detected engine type.
    NEVER blocks detection - only boosts confidence.
    
    Args:
        engine_type: '50', '382', '618', '786', 'underfib'
        current_setup: Dict with impulse_pct, retracement_pct, etc.
        candles: Optional candle data for body/wick analysis
    
    Returns:
        FlashcardMatch with best match info, or None if no flashcards
    """
    # Load ONLY flashcards for this specific engine type
    flashcards = load_flashcards(engine_type)
    
    if not flashcards:
        logger.debug(f"No flashcards found for engine {engine_type}")
        return None
    
    best_match = None
    best_score = 0
    best_factors = []
    best_name = "Unknown"
    
    # Compare against max 10 flashcards
    for card in flashcards[:MAX_FLASHCARDS_PER_TYPE]:
        similarity, factors = calculate_similarity(current_setup, card, candles)
        
        if similarity > best_score:
            best_score = similarity
            best_factors = factors
            best_name = card.get('name', card.get('symbol', card.get('title', 'Example')))
            best_match = card
    
    if best_score < 30:  # No meaningful match
        return None
    
    # Determine grade boost based on similarity
    if best_score >= 80:
        grade_boost = 2  # Strong boost (e.g., A → A+)
        confidence_note = f"Strong match ({best_score:.0f}%)"
    elif best_score >= 60:
        grade_boost = 1  # Moderate boost
        confidence_note = f"Good match ({best_score:.0f}%)"
    else:
        grade_boost = 0  # No boost, just note
        confidence_note = f"Partial match ({best_score:.0f}%)"
    
    return FlashcardMatch(
        best_match_name=best_name,
        similarity_score=best_score,
        matching_factors=best_factors,
        grade_boost=grade_boost,
        confidence_note=confidence_note
    )


def apply_grade_boost(current_grade: str, boost: int) -> str:
    """Apply grade boost based on flashcard similarity."""
    grade_order = ['C', 'B', 'B+', 'A', 'A+']
    
    try:
        current_idx = grade_order.index(current_grade)
        new_idx = min(current_idx + boost, len(grade_order) - 1)
        return grade_order[new_idx]
    except ValueError:
        return current_grade


def format_flashcard_note(match: FlashcardMatch) -> str:
    """Format flashcard match for Telegram alert."""
    if not match:
        return ""
    
    factors_str = ', '.join(match.matching_factors[:3])
    return f"📚 Flashcard: {match.similarity_score:.0f}% similar to {match.best_match_name} [{factors_str}]"
