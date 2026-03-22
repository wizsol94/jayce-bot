"""
BANGERS ONLY PIPELINE v1.0
==========================
Unified deep analysis pipeline that wires together:
1. Structure Engine
2. RSI Momentum Memory
3. Candle Intelligence
4. Flashcard Pattern Matching
5. Setup Grader

This module is called from scanner.py after PSEF passes.
"""

from typing import Dict, List, Optional, Tuple
import logging

# Import all analysis modules
from structure_engine import analyze_structure
from rsi_memory import analyze_rsi_full
from candle_intelligence import analyze_candles, get_candle_summary
from setup_grader import grade_setup, quick_grade_summary

logger = logging.getLogger(__name__)

def run_bangers_analysis(
    candles: List[dict],
    psef_result: Dict,
    engine_result: Dict = None,
    flashcard_similarity: float = 0
) -> Dict:
    """
    Run the full BANGERS ONLY analysis pipeline.
    
    Pipeline:
    1. Structure Engine → trend, swings, BOS, grade
    2. RSI Memory → floor/ceiling, expansion mode
    3. Candle Intelligence → tags, character
    4. Flashcard Match → similarity score
    5. Setup Grader → final grade + alert decision
    
    Returns complete analysis with alert decision.
    """
    result = {
        'should_alert': False,
        'grade': 'D',
        'score': 0,
        'structure': None,
        'rsi': None,
        'candles': None,
        'flashcard': None,
        'grader': None,
        'summary': ''
    }
    
    if not candles or len(candles) < 20:
        result['summary'] = 'Not enough candles for analysis'
        return result
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: STRUCTURE ENGINE
    # ══════════════════════════════════════════════════════════════════════
    try:
        structure_result = analyze_structure(candles)
        result['structure'] = structure_result
        trend = structure_result.get('trend', 'UNKNOWN')
        structure_grade = structure_result.get('grade', 'C')
        logger.debug(f"    Structure: {trend} | Grade: {structure_grade}")
    except Exception as e:
        logger.error(f"    Structure Engine error: {e}")
        structure_result = {'grade': 'C', 'trend': 'UNKNOWN'}
        result['structure'] = structure_result
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: RSI MOMENTUM MEMORY
    # ══════════════════════════════════════════════════════════════════════
    try:
        rsi_result = analyze_rsi_full(candles, trend=trend, structure_grade=structure_grade)
        result['rsi'] = rsi_result
        logger.debug(f"    RSI: {rsi_result.get('summary', 'N/A')}")
    except Exception as e:
        logger.error(f"    RSI Memory error: {e}")
        rsi_result = {'RSI_MEMORY_INTACT': False, 'memory_grade': 'C'}
        result['rsi'] = rsi_result
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 3: CANDLE INTELLIGENCE
    # ══════════════════════════════════════════════════════════════════════
    try:
        tagged_candles = analyze_candles(candles)
        candle_summary = get_candle_summary(tagged_candles)
        result['candles'] = candle_summary
        logger.debug(f"    Candles: {candle_summary.get('recent_character', 'MIXED')}")
    except Exception as e:
        logger.error(f"    Candle Intelligence error: {e}")
        candle_summary = {'recent_character': 'MIXED'}
        result['candles'] = candle_summary
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 4: FLASHCARD PATTERN MATCH
    # ══════════════════════════════════════════════════════════════════════
    # Flashcard similarity comes from engine_result or Vision
    setup_type = 'Unknown'
    if engine_result:
        setup_type = engine_result.get('engine_name', 'Unknown')
        # Use engine confidence as flashcard similarity if available
        if flashcard_similarity == 0:
            flashcard_similarity = engine_result.get('confidence', 0)
    
    flashcard_result = {
        'similarity': flashcard_similarity,
        'setup_type': setup_type
    }
    result['flashcard'] = flashcard_result
    
    # ══════════════════════════════════════════════════════════════════════
    # STEP 5: SETUP GRADER - FINAL DECISION
    # ══════════════════════════════════════════════════════════════════════
    try:
        grader_result = grade_setup(
            psef_result=psef_result,
            structure_result=structure_result,
            rsi_result=rsi_result,
            candle_summary=candle_summary,
            flashcard_result=flashcard_result
        )
        result['grader'] = grader_result
        result['should_alert'] = grader_result.get('should_alert', False)
        result['grade'] = grader_result.get('grade', 'D')
        result['score'] = grader_result.get('score', 0)
        result['summary'] = quick_grade_summary(grader_result)
    except Exception as e:
        logger.error(f"    Setup Grader error: {e}")
        result['summary'] = f'Grader error: {e}'
    
    return result


def format_alert_message(token: dict, analysis: Dict, chart_bytes: bytes = None) -> str:
    """
    Format the Telegram alert message with full analysis breakdown.
    """
    symbol = token.get('symbol', '???')
    grade = analysis.get('grade', '?')
    score = analysis.get('score', 0)
    
    grader = analysis.get('grader', {})
    breakdown = grader.get('breakdown', {})
    
    # Get setup type
    flashcard = analysis.get('flashcard', {})
    setup_type = flashcard.get('setup_type', 'Setup')
    
    # Get structure info
    structure = analysis.get('structure', {})
    trend = structure.get('trend', 'UNKNOWN')
    
    # Get RSI info
    rsi = analysis.get('rsi', {})
    rsi_mode = rsi.get('mode', 'UNKNOWN')
    rsi_current = rsi.get('current_rsi', 0)
    
    # Build message
    lines = [
        f"🎯 BANGER ALERT: {symbol}",
        f"",
        f"Grade: {grade} | Score: {score}/100",
        f"Setup: {setup_type}",
        f"",
        f"📊 Analysis Breakdown:",
        f"  • Structure: {trend} ({structure.get('grade', '?')})",
        f"  • RSI: {rsi_mode} ({rsi_current:.0f})",
        f"  • Memory: {'✓' if rsi.get('RSI_MEMORY_INTACT') else '✗'}",
        f"  • Breakout: {'✓' if rsi.get('RSI_BREAKOUT_PRESSURE') else '—'}",
        f"  • Runner: {'✓' if rsi.get('RSI_RUNNER_MODE') else '—'}",
        f"",
        f"📈 Score Breakdown:",
        f"  PSEF: {breakdown.get('psef', {}).get('points', 0)}/20",
        f"  Structure: {breakdown.get('structure', {}).get('points', 0)}/30",
        f"  RSI: {breakdown.get('rsi', {}).get('points', 0)}/25",
        f"  Candles: {breakdown.get('candles', {}).get('points', 0)}/15",
        f"  Pattern: {breakdown.get('flashcard', {}).get('points', 0)}/10",
    ]
    
    # Add link
    pair_address = token.get('pair_address', '')
    if pair_address:
        lines.append(f"")
        lines.append(f"🔗 https://dexscreener.com/solana/{pair_address}")
    
    return "\n".join(lines)


if __name__ == '__main__':
    # Test the pipeline
    print("=" * 70)
    print("BANGERS PIPELINE TEST")
    print("=" * 70)
    
    # Create test candles (uptrend)
    candles = []
    base = 100
    for i in range(60):
        if i < 40:
            base += 1.5 if i % 5 < 4 else -0.3
        else:
            base -= 0.3 if i % 3 < 2 else 0.5
        candles.append({
            'o': base - 0.3,
            'h': base + 1.0,
            'l': base - 0.5,
            'c': base + 0.5,
            'v': 1000 + i * 10
        })
    
    # Run pipeline
    result = run_bangers_analysis(
        candles=candles,
        psef_result={'passed': True},
        engine_result={'engine_name': '382 + Flip Zone', 'confidence': 75},
        flashcard_similarity=75
    )
    
    print(f"Grade: {result['grade']}")
    print(f"Score: {result['score']}")
    print(f"Should Alert: {result['should_alert']}")
    print(f"Summary: {result['summary']}")
