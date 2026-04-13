"""
FLASHCARD VISION AI v2.0 - CONTROLLED DIVERSITY SAMPLING
=========================================================
Mimics how a real trader scans flashcards visually.

NOT based on "best trades" or strict metadata.
Instead: Controlled diversity sampling across outcome ranges.

System:
1. Load ALL flashcards for detected setup type
2. Sample 7 flashcards with controlled diversity:
   - 2 HIGH outcome (winners)
   - 3 MID outcome (average)
   - 2 LOW outcome (failures/weak)
3. Rotate selection to expose full library over time
4. Vision compares structure, pullback, momentum, reaction

Cost: ~$0.03-0.04 per comparison (7 images)
"""

import os
import json
import base64
import random
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

FLASHCARD_DIR = "/opt/jayce/flashcards"
METADATA_FILE = f"{FLASHCARD_DIR}/metadata.json"
USAGE_FILE = "/opt/jayce/data/vision_usage.json"
ROTATION_FILE = "/opt/jayce/data/flashcard_rotation.json"

# Budget limits
DAILY_CAP = 50
MONTHLY_CAP = 1000
MIN_SCORE_GATE = 60

# Controlled Diversity Sampling
SAMPLE_SIZE = 7
HIGH_COUNT = 2   # Top performers (outcome >= 70%)
MID_COUNT = 3    # Average performers (30% <= outcome < 70%)
LOW_COUNT = 2    # Weak/failed (outcome < 30%)

# Outcome thresholds
HIGH_THRESHOLD = 70
LOW_THRESHOLD = 30

# Anthropic API
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Setup type mapping
SETUP_FOLDERS = {
    '382': '382',
    '50': '50', 
    '618': '618',
    '786': '786',
    'UNDER_FIB': 'Under-Fib',
    'Under-Fib': 'Under-Fib'
}


# ══════════════════════════════════════════════════════════════════════════════
# USAGE TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def load_usage() -> Dict:
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        'daily': {'date': str(date.today()), 'count': 0},
        'monthly': {'month': date.today().strftime('%Y-%m'), 'count': 0},
        'total': 0
    }


def save_usage(usage: Dict):
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f, indent=2)


def check_budget() -> Tuple[bool, str]:
    usage = load_usage()
    today = str(date.today())
    month = date.today().strftime('%Y-%m')
    
    if usage['daily']['date'] != today:
        usage['daily'] = {'date': today, 'count': 0}
        save_usage(usage)
    
    if usage['monthly']['month'] != month:
        usage['monthly'] = {'month': month, 'count': 0}
        save_usage(usage)
    
    if usage['daily']['count'] >= DAILY_CAP:
        return False, f"Daily cap reached ({DAILY_CAP})"
    
    if usage['monthly']['count'] >= MONTHLY_CAP:
        return False, f"Monthly cap reached ({MONTHLY_CAP})"
    
    return True, "OK"


def increment_usage():
    usage = load_usage()
    today = str(date.today())
    month = date.today().strftime('%Y-%m')
    
    if usage['daily']['date'] != today:
        usage['daily'] = {'date': today, 'count': 0}
    if usage['monthly']['month'] != month:
        usage['monthly'] = {'month': month, 'count': 0}
    
    usage['daily']['count'] += 1
    usage['monthly']['count'] += 1
    usage['total'] += 1
    
    save_usage(usage)
    return usage


def get_usage_stats() -> Dict:
    usage = load_usage()
    return {
        'daily_used': usage['daily']['count'],
        'daily_cap': DAILY_CAP,
        'daily_remaining': max(0, DAILY_CAP - usage['daily']['count']),
        'monthly_used': usage['monthly']['count'],
        'monthly_cap': MONTHLY_CAP,
        'monthly_remaining': max(0, MONTHLY_CAP - usage['monthly']['count']),
        'total': usage['total']
    }


# ══════════════════════════════════════════════════════════════════════════════
# ROTATION TRACKING (Avoid sending same flashcards repeatedly)
# ══════════════════════════════════════════════════════════════════════════════

def load_rotation_history() -> Dict:
    try:
        if os.path.exists(ROTATION_FILE):
            with open(ROTATION_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}


def save_rotation_history(history: Dict):
    os.makedirs(os.path.dirname(ROTATION_FILE), exist_ok=True)
    with open(ROTATION_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_recently_used(setup_type: str, max_history: int = 21) -> List[str]:
    """Get recently used flashcard IDs for this setup type."""
    history = load_rotation_history()
    setup_history = history.get(setup_type, [])
    return setup_history[-max_history:] if setup_history else []


def record_used_flashcards(setup_type: str, chart_ids: List[str]):
    """Record which flashcards were used to avoid repeats."""
    history = load_rotation_history()
    if setup_type not in history:
        history[setup_type] = []
    history[setup_type].extend(chart_ids)
    # Keep last 50 to allow rotation
    history[setup_type] = history[setup_type][-50:]
    save_rotation_history(history)


# ══════════════════════════════════════════════════════════════════════════════
# FLASHCARD LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_metadata() -> List[Dict]:
    """Load flashcard metadata."""
    try:
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load flashcard metadata: {e}")
        return []


def get_all_flashcards_for_setup(setup_type: str) -> List[Dict]:
    """
    Load ALL flashcards for a setup type.
    No limit - we load everything, then sample intelligently.
    """
    metadata = load_metadata()
    folder = SETUP_FOLDERS.get(setup_type, setup_type)
    folder_path = f"{FLASHCARD_DIR}/{folder}"
    
    if not os.path.exists(folder_path):
        logger.warning(f"Flashcard folder not found: {folder_path}")
        return []
    
    # Filter metadata for this setup type
    setup_cards = [
        m for m in metadata 
        if m.get('fib_depth') == setup_type or SETUP_FOLDERS.get(m.get('fib_depth')) == folder
    ]
    
    # Build full list with file paths
    result = []
    for card in setup_cards:
        chart_id = card.get('chart_id', '').replace('/', '_')
        file_path = f"{folder_path}/{chart_id}.jpg"
        
        if os.path.exists(file_path):
            result.append({
                'chart_id': chart_id,
                'metadata': card,
                'file_path': file_path,
                'outcome': card.get('outcome_percentage', 50)  # Default to mid if unknown
            })
    
    logger.info(f"[FLASHCARD] Loaded {len(result)} flashcards for {setup_type}")
    return result


def controlled_diversity_sample(
    all_cards: List[Dict], 
    setup_type: str
) -> List[Dict]:
    """
    CONTROLLED DIVERSITY SAMPLING
    
    Select 7 flashcards with balanced outcome distribution:
    - 2 HIGH (outcome >= 70%) - winners
    - 3 MID (30% <= outcome < 70%) - average
    - 2 LOW (outcome < 30%) - failures/weak
    
    Also avoids recently used flashcards for rotation.
    """
    if not all_cards:
        return []
    
    # Get recently used to avoid repeats
    recently_used = set(get_recently_used(setup_type))
    
    # Separate into buckets by outcome
    high_cards = [c for c in all_cards if c['outcome'] >= HIGH_THRESHOLD and c['chart_id'] not in recently_used]
    mid_cards = [c for c in all_cards if LOW_THRESHOLD <= c['outcome'] < HIGH_THRESHOLD and c['chart_id'] not in recently_used]
    low_cards = [c for c in all_cards if c['outcome'] < LOW_THRESHOLD and c['chart_id'] not in recently_used]
    
    # If buckets are empty after filtering recently used, allow repeats
    if not high_cards:
        high_cards = [c for c in all_cards if c['outcome'] >= HIGH_THRESHOLD]
    if not mid_cards:
        mid_cards = [c for c in all_cards if LOW_THRESHOLD <= c['outcome'] < HIGH_THRESHOLD]
    if not low_cards:
        low_cards = [c for c in all_cards if c['outcome'] < LOW_THRESHOLD]
    
    # Shuffle each bucket
    random.shuffle(high_cards)
    random.shuffle(mid_cards)
    random.shuffle(low_cards)
    
    # Sample from each bucket
    sampled = []
    
    # HIGH: Take up to HIGH_COUNT
    sampled.extend(high_cards[:HIGH_COUNT])
    
    # MID: Take up to MID_COUNT
    sampled.extend(mid_cards[:MID_COUNT])
    
    # LOW: Take up to LOW_COUNT
    sampled.extend(low_cards[:LOW_COUNT])
    
    # If we don't have enough in some buckets, fill from others
    current_count = len(sampled)
    if current_count < SAMPLE_SIZE:
        # Try to fill from mid first (most common)
        remaining_mid = [c for c in mid_cards if c not in sampled]
        remaining_high = [c for c in high_cards if c not in sampled]
        remaining_low = [c for c in low_cards if c not in sampled]
        
        fill_pool = remaining_mid + remaining_high + remaining_low
        random.shuffle(fill_pool)
        
        needed = SAMPLE_SIZE - current_count
        sampled.extend(fill_pool[:needed])
    
    # Record what we used for rotation
    used_ids = [c['chart_id'] for c in sampled]
    record_used_flashcards(setup_type, used_ids)
    
    # Log the diversity
    high_count = len([c for c in sampled if c['outcome'] >= HIGH_THRESHOLD])
    mid_count = len([c for c in sampled if LOW_THRESHOLD <= c['outcome'] < HIGH_THRESHOLD])
    low_count = len([c for c in sampled if c['outcome'] < LOW_THRESHOLD])
    
    logger.info(f"[FLASHCARD] Sampled {len(sampled)} cards: {high_count} HIGH, {mid_count} MID, {low_count} LOW")
    
    return sampled


def image_to_base64(file_path: str) -> Optional[str]:
    """Convert image file to base64 string."""
    try:
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to read image {file_path}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# VISION AI COMPARISON - TRADER STYLE
# ══════════════════════════════════════════════════════════════════════════════

def compare_charts_vision(
    live_chart_path: str,
    sampled_cards: List[Dict],
    setup_type: str
) -> Dict:
    """
    Use Vision AI to compare live chart against diverse flashcard examples.
    
    Prompt focuses on:
    - Structure similarity
    - Pullback behavior
    - Momentum patterns
    - Reaction at levels
    
    NOT just visual similarity - behavior similarity.
    """
    if not ANTHROPIC_API_KEY:
        return {
            'success': False,
            'error': 'Anthropic API key not configured',
            'similarity': 0,
            'best_match': None
        }
    
    # Check budget
    within_budget, reason = check_budget()
    if not within_budget:
        return {
            'success': False,
            'error': f'Budget limit: {reason}',
            'similarity': 0,
            'best_match': None,
            'fallback': True
        }
    
    # Load live chart
    live_b64 = image_to_base64(live_chart_path)
    if not live_b64:
        return {
            'success': False,
            'error': 'Failed to load live chart',
            'similarity': 0
        }
    
    # Load flashcard images
    flashcard_images = []
    for card in sampled_cards:
        b64 = image_to_base64(card['file_path'])
        if b64:
            flashcard_images.append({
                'chart_id': card['chart_id'],
                'b64': b64,
                'outcome': card['outcome'],
                'path': card['file_path']
            })
    
    if not flashcard_images:
        return {
            'success': False,
            'error': 'No flashcard images loaded',
            'similarity': 0
        }
    
    # Build Vision API request with TRADER-STYLE prompt
    try:
        # Build reference info for prompt
        ref_info = []
        for i, fc in enumerate(flashcard_images):
            outcome_label = "WINNER" if fc['outcome'] >= 70 else ("AVERAGE" if fc['outcome'] >= 30 else "WEAK/FAILED")
            ref_info.append(f"REF {i+1}: {outcome_label} ({fc['outcome']}% outcome)")
        
        ref_text = "\n".join(ref_info)
        
        system_prompt = f"""You are an expert crypto trader analyzing chart patterns. 

Compare the LIVE chart to these REFERENCE flashcard examples from past trades.

Reference Cards:
{ref_text}

Focus on BEHAVIOR SIMILARITY, not just visual similarity:
- Structure: Does price structure match? (HH/HL patterns, trend integrity)
- Pullback: Is the pullback behavior similar? (depth, speed, control)
- Momentum: RSI behavior, volume patterns, exhaustion signs
- Reaction: How price reacts at key levels (fib zones, flip zones)

Respond ONLY with JSON:
{{
  "top_matches": [
    {{"ref": 1, "similarity": 85, "pattern_type": "winner/average/weak"}},
    {{"ref": 3, "similarity": 72, "pattern_type": "winner/average/weak"}},
    {{"ref": 5, "similarity": 68, "pattern_type": "winner/average/weak"}}
  ],
  "current_resembles": "winning/average/failing",
  "confidence": 0-100,
  "reasoning": "Brief explanation of what behavior patterns match"
}}

Return top 3 most similar references. Be honest - if it looks like a failing pattern, say so."""

        # Build Claude message content
        claude_content = []
        
        # Add system prompt
        claude_content.append({"type": "text", "text": system_prompt})
        
        # Add live chart
        claude_content.append({"type": "text", "text": f"\n\nLIVE CHART (analyzing for {setup_type} setup):"})
        claude_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": live_b64
            }
        })
        
        # Add reference flashcards
        for i, fc in enumerate(flashcard_images):
            outcome_label = "WINNER" if fc['outcome'] >= 70 else ("AVERAGE" if fc['outcome'] >= 30 else "WEAK/FAILED")
            claude_content.append({"type": "text", "text": f"\n\nREFERENCE {i+1} - {outcome_label} ({fc['outcome']}% outcome):"})
            claude_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": fc['b64']
                }
            })
        
        # Final instruction
        claude_content.append({"type": "text", "text": "\n\nCompare the LIVE chart to these references. Which patterns does it behave most similarly to? Respond with JSON only."})
        
        claude_messages = [{"role": "user", "content": claude_content}]
        
        # Call Claude Vision API
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": claude_messages
            },
            timeout=45
        )
        
        # Increment usage counter
        increment_usage()
        
        if response.status_code != 200:
            logger.error(f"Vision API error {response.status_code}: {response.text[:300]}")
            return {
                'success': False,
                'error': f'API error: {response.status_code}',
                'similarity': 0
            }
        
        result = response.json()
        
        if 'error' in result:
            logger.error(f"Vision API returned error: {result['error']}")
            return {
                'success': False,
                'error': str(result['error']),
                'similarity': 0
            }
        
        try:
            content = result['content'][0]['text']
        except (KeyError, IndexError) as e:
            logger.error(f"Vision API unexpected response format: {result}")
            return {
                'success': False,
                'error': f'Unexpected response format: {e}',
                'similarity': 0
            }
        
        logger.info(f"Vision API raw response: {content[:500]}...")
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            
            top_matches = parsed.get('top_matches', [])
            
            # Sort by similarity descending
            top_matches = sorted(top_matches, key=lambda x: x.get('similarity', 0), reverse=True)[:3]
            
            # Calculate average similarity
            similarities = [m.get('similarity', 0) for m in top_matches]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0
            
            # Build detailed results
            detailed_matches = []
            for m in top_matches:
                ref_idx = m.get('ref', 1) - 1
                if 0 <= ref_idx < len(flashcard_images):
                    fc = flashcard_images[ref_idx]
                    detailed_matches.append({
                        'chart_id': fc['chart_id'],
                        'path': fc['path'],
                        'similarity': m.get('similarity', 0),
                        'pattern_type': m.get('pattern_type', 'unknown'),
                        'outcome': fc['outcome']
                    })
            
            return {
                'success': True,
                'similarity': round(avg_similarity, 1),
                'top_matches': detailed_matches,
                'current_resembles': parsed.get('current_resembles', 'unknown'),
                'confidence': parsed.get('confidence', 0),
                'reasoning': parsed.get('reasoning', ''),
                'usage': get_usage_stats()
            }
        else:
            return {
                'success': False,
                'error': 'Failed to parse response',
                'similarity': 0,
                'raw': content
            }
            
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        return {
            'success': False,
            'error': str(e),
            'similarity': 0
        }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def analyze_with_flashcards(
    live_chart_path: str,
    setup_type: str,
    current_score: int
) -> Dict:
    """
    Main entry point for flashcard Vision analysis.
    
    Uses Controlled Diversity Sampling to mimic real trader behavior.
    
    Returns:
    - similarity: 0-100 match score
    - current_resembles: winning/average/failing
    - bonus_points: Points to add to final score
    - should_boost: Whether to boost the grade
    """
    result = {
        'ran_vision': False,
        'similarity': 0,
        'bonus_points': 0,
        'should_boost': False,
        'reason': '',
        'best_match': None,
        'current_resembles': 'unknown'
    }
    
    # Gate 1: Score check
    if current_score < MIN_SCORE_GATE:
        result['reason'] = f'Score {current_score} below gate ({MIN_SCORE_GATE})'
        return result
    
    # Gate 2: Budget check
    within_budget, budget_reason = check_budget()
    if not within_budget:
        result['reason'] = budget_reason
        return result
    
    # Gate 3: Check live chart exists
    if not os.path.exists(live_chart_path):
        result['reason'] = 'Live chart not found'
        return result
    
    # Load ALL flashcards for this setup type
    all_cards = get_all_flashcards_for_setup(setup_type)
    if not all_cards:
        result['reason'] = f'No flashcards for setup type: {setup_type}'
        return result
    
    # Apply Controlled Diversity Sampling
    sampled_cards = controlled_diversity_sample(all_cards, setup_type)
    if not sampled_cards:
        result['reason'] = 'Failed to sample flashcards'
        return result
    
    # Run Vision comparison with diverse sample
    vision_result = compare_charts_vision(live_chart_path, sampled_cards, setup_type)
    
    result['ran_vision'] = True
    result['vision_result'] = vision_result
    
    if vision_result.get('success'):
        similarity = vision_result.get('similarity', 0)
        result['similarity'] = similarity
        result['top_matches'] = vision_result.get('top_matches', [])
        result['confidence'] = vision_result.get('confidence', 0)
        result['reasoning'] = vision_result.get('reasoning', '')
        result['current_resembles'] = vision_result.get('current_resembles', 'unknown')
        
        # Log matches
        if result['top_matches']:
            logger.info(f"[FLASHCARD] Pattern Analysis:")
            logger.info(f"  Current chart resembles: {result['current_resembles'].upper()} pattern")
            for match in result['top_matches']:
                logger.info(f"  - {match['chart_id']} ({match['pattern_type']}) → {match['similarity']}%")
        
        # Calculate bonus points based on similarity AND pattern type
        resembles = result['current_resembles'].lower()
        
        if resembles == 'winning':
            # Looks like a winner
            if similarity >= 85:
                result['bonus_points'] = 12
                result['should_boost'] = True
            elif similarity >= 75:
                result['bonus_points'] = 8
                result['should_boost'] = True
            elif similarity >= 65:
                result['bonus_points'] = 5
                result['should_boost'] = False
            else:
                result['bonus_points'] = 3
                result['should_boost'] = False
        
        elif resembles == 'average':
            # Looks average
            if similarity >= 80:
                result['bonus_points'] = 5
                result['should_boost'] = False
            elif similarity >= 65:
                result['bonus_points'] = 3
                result['should_boost'] = False
            else:
                result['bonus_points'] = 1
                result['should_boost'] = False
        
        elif resembles == 'failing':
            # Looks like a failure - penalize
            result['bonus_points'] = -5
            result['should_boost'] = False
            logger.warning(f"[FLASHCARD] ⚠️ Chart resembles FAILING pattern!")
        
        else:
            # Unknown - modest bonus based on similarity
            if similarity >= 75:
                result['bonus_points'] = 5
            elif similarity >= 60:
                result['bonus_points'] = 2
            else:
                result['bonus_points'] = 0
        
        result['reason'] = f'{resembles.upper()} pattern, {similarity}% match'
    else:
        result['reason'] = vision_result.get('error', 'Vision failed')
    
    return result


# Legacy function for compatibility
def get_flashcards_for_setup(setup_type: str, limit: int = 10) -> List[Dict]:
    """Legacy function - now uses controlled diversity sampling internally."""
    all_cards = get_all_flashcards_for_setup(setup_type)
    return all_cards[:limit]


# ══════════════════════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("FLASHCARD VISION AI v2.0 - CONTROLLED DIVERSITY")
    print("=" * 60)
    
    # Show flashcard counts by outcome
    print("\nFlashcard Library (by outcome):")
    for setup in ['382', '50', '618', '786', 'Under-Fib']:
        cards = get_all_flashcards_for_setup(setup)
        high = len([c for c in cards if c['outcome'] >= 70])
        mid = len([c for c in cards if 30 <= c['outcome'] < 70])
        low = len([c for c in cards if c['outcome'] < 30])
        print(f"  {setup}: {len(cards)} total ({high} HIGH, {mid} MID, {low} LOW)")
    
    # Show usage stats
    print("\nUsage Stats:")
    stats = get_usage_stats()
    print(f"  Daily: {stats['daily_used']}/{stats['daily_cap']}")
    print(f"  Monthly: {stats['monthly_used']}/{stats['monthly_cap']}")
    print(f"  Total: {stats['total']}")
    
    # Show sampling config
    print("\nSampling Config:")
    print(f"  Sample size: {SAMPLE_SIZE}")
    print(f"  HIGH (>={HIGH_THRESHOLD}%): {HIGH_COUNT} cards")
    print(f"  MID ({LOW_THRESHOLD}-{HIGH_THRESHOLD}%): {MID_COUNT} cards")
    print(f"  LOW (<{LOW_THRESHOLD}%): {LOW_COUNT} cards")
