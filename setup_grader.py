"""
SETUP GRADER v2.0 - BANGERS ONLY
================================
Grades WizTheory setups using all analysis modules.
Only A and A+ grades trigger alerts.

Weights (100 points total):
- PSEF Pass: 20 pts
- Structure Grade: 30 pts (primary signal)
- RSI Memory: 15 pts
- RSI Expansion: 10 pts (bonus)
- Candle Quality: 15 pts
- Flashcard Match: 10 pts (confirmation only)

Alert Policy:
- ONLY Grade A or A+ sends alert
- Score must be >= 85
- If token re-triggers, only alert if grade improved
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# GRADING WEIGHTS (Updated per user spec)
# ══════════════════════════════════════════════════════════════════════════════

WEIGHTS = {
    'psef': 20,           # PSEF pass = 20 points
    'structure': 30,      # Structure grade - PRIMARY (A=30, B=18, C=6)
    'rsi_memory': 8,     # RSI memory intact = 15 points
    'rsi_expansion': 5,  # RSI breakout/runner = bonus 10 points
    'candle_quality': 15, # Candle tags quality
    'flashcard': 10,      # Flashcard pattern match - CONFIRMATION only
}

# Alert thresholds
ALERT_MIN_GRADE = 'A'
ALERT_MIN_SCORE = 85

# ══════════════════════════════════════════════════════════════════════════════
# GRADE CONVERSION
# ══════════════════════════════════════════════════════════════════════════════

def letter_to_points(grade: str, max_points: int) -> int:
    """Convert letter grade to points."""
    grade_map = {
        'A+': 1.0,
        'A': 0.9,
        'B+': 0.75,
        'B': 0.6,
        'C+': 0.4,
        'C': 0.2,
        'D': 0.1,
        'F': 0
    }
    multiplier = grade_map.get(grade.upper(), 0.2)
    return int(max_points * multiplier)

def score_to_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 95:
        return 'A+'
    elif score >= 85:
        return 'A'
    elif score >= 75:
        return 'B+'
    elif score >= 65:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'

# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT SCORERS
# ══════════════════════════════════════════════════════════════════════════════

def score_psef(psef_result: Dict) -> Dict:
    """Score PSEF result."""
    if not psef_result:
        return {'points': 0, 'max': WEIGHTS['psef'], 'reason': 'No PSEF data'}
    
    if psef_result.get('passed', False):
        return {
            'points': WEIGHTS['psef'],
            'max': WEIGHTS['psef'],
            'reason': 'All 4 gates passed'
        }
    else:
        failed = psef_result.get('failed_gate', 'unknown')
        return {
            'points': 0,
            'max': WEIGHTS['psef'],
            'reason': f'Failed {failed} gate'
        }

def score_structure(structure_result: Dict) -> Dict:
    """Score structure analysis - PRIMARY SIGNAL."""
    if not structure_result:
        return {'points': 0, 'max': WEIGHTS['structure'], 'reason': 'No structure data'}
    
    grade = structure_result.get('grade', 'C')
    trend = structure_result.get('trend', 'UNKNOWN')
    
    points = letter_to_points(grade, WEIGHTS['structure'])
    
    return {
        'points': points,
        'max': WEIGHTS['structure'],
        'reason': f'{trend} trend, grade {grade}'
    }

def score_rsi(rsi_result: Dict) -> Dict:
    """Score RSI analysis (both memory and expansion)."""
    if not rsi_result:
        return {'points': 0, 'max': WEIGHTS['rsi_memory'] + WEIGHTS['rsi_expansion'], 'reason': 'No RSI data'}
    
    points = 0
    reasons = []
    
    # Memory points
    if rsi_result.get('RSI_MEMORY_INTACT', False):
        memory_grade = rsi_result.get('memory_grade', 'C')
        points += letter_to_points(memory_grade, WEIGHTS['rsi_memory'])
        reasons.append(f'Memory intact ({memory_grade})')
    else:
        reasons.append('Memory lost')
    
    # Expansion bonus
    if rsi_result.get('RSI_RUNNER_MODE', False):
        points += WEIGHTS['rsi_expansion']
        reasons.append('RUNNER MODE')
    elif rsi_result.get('RSI_BREAKOUT_PRESSURE', False):
        points += int(WEIGHTS['rsi_expansion'] * 0.7)
        reasons.append('Breakout pressure')
    
    return {
        'points': points,
        'max': WEIGHTS['rsi_memory'] + WEIGHTS['rsi_expansion'],
        'reason': ' | '.join(reasons)
    }

def score_candles(candle_summary: Dict) -> Dict:
    """Score candle intelligence."""
    if not candle_summary:
        return {'points': 0, 'max': WEIGHTS['candle_quality'], 'reason': 'No candle data'}
    
    character = candle_summary.get('recent_character', 'MIXED')
    expansion = candle_summary.get('expansion_count', 0)
    rejection = candle_summary.get('rejection_count', 0)
    sweep = candle_summary.get('sweep_count', 0)
    
    points = 0
    reasons = []
    
    # Trending character is best
    if character == 'TRENDING':
        points += 10
        reasons.append('Trending')
    elif character == 'COILING':
        points += 7
        reasons.append('Coiling')
    else:
        points += 3
        reasons.append(character)
    
    # Bonus for key candle types
    if expansion >= 2:
        points += 3
        reasons.append(f'{expansion} expansions')
    if sweep >= 1:
        points += 2
        reasons.append(f'{sweep} sweeps')
    
    points = min(points, WEIGHTS['candle_quality'])
    
    return {
        'points': points,
        'max': WEIGHTS['candle_quality'],
        'reason': ' | '.join(reasons)
    }

def score_flashcard(flashcard_result: Dict) -> Dict:
    """Score flashcard pattern match - CONFIRMATION only."""
    if not flashcard_result:
        return {'points': 0, 'max': WEIGHTS['flashcard'], 'reason': 'No flashcard match'}
    
    similarity = flashcard_result.get('similarity', 0)
    setup_type = flashcard_result.get('setup_type', 'Unknown')
    
    # Scale similarity to points (0-100% -> 0-10 pts)
    points = int((similarity / 100) * WEIGHTS['flashcard'])
    
    if similarity >= 80:
        reason = f'{setup_type} match {similarity}% (strong)'
    elif similarity >= 60:
        reason = f'{setup_type} match {similarity}% (moderate)'
    elif similarity >= 40:
        reason = f'{setup_type} match {similarity}% (weak)'
    else:
        reason = f'Low pattern match {similarity}%'
    
    return {
        'points': points,
        'max': WEIGHTS['flashcard'],
        'reason': reason
    }

# ══════════════════════════════════════════════════════════════════════════════
# MAIN GRADER
# ══════════════════════════════════════════════════════════════════════════════

def grade_setup(
    psef_result: Dict = None,
    structure_result: Dict = None,
    rsi_result: Dict = None,
    candle_summary: Dict = None,
    flashcard_result: Dict = None
) -> Dict:
    """
    Grade a complete setup using all analysis components.
    
    Returns:
    - grade: A+, A, B+, B, C, D
    - score: 0-100
    - should_alert: true/false
    - breakdown: component scores
    - reason: summary
    """
    result = {
        'grade': 'D',
        'score': 0,
        'should_alert': False,
        'breakdown': {},
        'reason': ''
    }
    
    # Score each component
    psef_score = score_psef(psef_result)
    structure_score = score_structure(structure_result)
    rsi_score = score_rsi(rsi_result)
    candle_score = score_candles(candle_summary)
    flashcard_score = score_flashcard(flashcard_result)
    
    # Calculate total
    total_points = (
        psef_score['points'] +
        structure_score['points'] +
        rsi_score['points'] +
        candle_score['points'] +
        flashcard_score['points']
    )
    
    max_points = (
        psef_score['max'] +
        structure_score['max'] +
        rsi_score['max'] +
        candle_score['max'] +
        flashcard_score['max']
    )
    
    # Normalize to 100
    score = int((total_points / max_points) * 100) if max_points > 0 else 0
    
    # Determine grade
    grade = score_to_grade(score)
    
    # Alert decision - MUST have PSEF pass + high score
    psef_passed = psef_result.get('passed', False) if psef_result else False
    should_alert = (
        grade in ['A+', 'A'] and
        score >= ALERT_MIN_SCORE and
        psef_passed
    )
    
    # Get setup type from flashcard if available
    setup_type = flashcard_result.get('setup_type', 'Setup') if flashcard_result else 'Setup'
    
    # Build result
    result['score'] = score
    result['grade'] = grade
    result['should_alert'] = should_alert
    result['breakdown'] = {
        'psef': psef_score,
        'structure': structure_score,
        'rsi': rsi_score,
        'candles': candle_score,
        'flashcard': flashcard_score
    }
    
    # Summary reason
    if should_alert:
        result['reason'] = f"🎯 BANGER: {setup_type} | Grade {grade} | Score {score}"
    elif grade in ['B+', 'B']:
        result['reason'] = f"📊 Watchlist: {setup_type} | Grade {grade} | Score {score}"
    else:
        result['reason'] = f"⚠️ Weak: Grade {grade} | Score {score}"
    
    return result

def should_realert(previous_grade: str, new_grade: str) -> bool:
    """
    Check if we should re-alert for this token.
    Only re-alert if grade improved.
    """
    grade_rank = {'A+': 5, 'A': 4, 'B+': 3, 'B': 2, 'C': 1, 'D': 0}
    
    prev_rank = grade_rank.get(previous_grade, 0)
    new_rank = grade_rank.get(new_grade, 0)
    
    return new_rank > prev_rank

# ══════════════════════════════════════════════════════════════════════════════
# QUICK GRADE (for visibility logging)
# ══════════════════════════════════════════════════════════════════════════════

def quick_grade_summary(grade_result: Dict) -> str:
    """One-line summary for logs."""
    grade = grade_result.get('grade', '?')
    score = grade_result.get('score', 0)
    alert = '🚨' if grade_result.get('should_alert', False) else '  '
    
    breakdown = grade_result.get('breakdown', {})
    psef = breakdown.get('psef', {}).get('points', 0)
    struct = breakdown.get('structure', {}).get('points', 0)
    rsi = breakdown.get('rsi', {}).get('points', 0)
    candle = breakdown.get('candles', {}).get('points', 0)
    flash = breakdown.get('flashcard', {}).get('points', 0)
    
    return f"{alert} Grade:{grade} Score:{score} [PSEF:{psef} STR:{struct} RSI:{rsi} CDL:{candle} FC:{flash}]"

if __name__ == '__main__':
    print("=" * 70)
    print("SETUP GRADER v2.0 - Weight Test")
    print("=" * 70)
    
    # Test perfect setup
    result = grade_setup(
        psef_result={'passed': True},
        structure_result={'grade': 'A', 'trend': 'BULLISH'},
        rsi_result={'RSI_MEMORY_INTACT': True, 'memory_grade': 'A', 'RSI_RUNNER_MODE': True},
        candle_summary={'recent_character': 'TRENDING', 'expansion_count': 3, 'sweep_count': 1},
        flashcard_result={'similarity': 85, 'setup_type': '382 + Flip Zone'}
    )
    print(f"Perfect setup: {result['reason']}")
    print(f"  {quick_grade_summary(result)}")
    print(f"  Should Alert: {result['should_alert']}")
