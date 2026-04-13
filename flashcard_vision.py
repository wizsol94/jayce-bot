"""
FLASHCARD VISION AI v1.0
========================
Compares live charts to trained flashcards using Vision AI.

Budget Controls:
- Daily cap: 50 requests
- Monthly cap: 1000 requests
- Min score gate: 70+ only
- Narrowed search: Only compare to matching setup type

Cost: ~$0.01-0.02 per comparison
"""

import os
import json
import base64
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

# Budget limits
DAILY_CAP = 50
MONTHLY_CAP = 1000
MIN_SCORE_GATE = 60  # Lowered to allow Vision to participate in scoring  # Only run Vision on scores 70+

# Anthropic API (for Vision)
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
    """Load usage tracking data."""
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
    """Save usage tracking data."""
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f, indent=2)


def check_budget() -> Tuple[bool, str]:
    """Check if we're within budget limits."""
    usage = load_usage()
    today = str(date.today())
    month = date.today().strftime('%Y-%m')
    
    # Reset daily counter if new day
    if usage['daily']['date'] != today:
        usage['daily'] = {'date': today, 'count': 0}
        save_usage(usage)
    
    # Reset monthly counter if new month
    if usage['monthly']['month'] != month:
        usage['monthly'] = {'month': month, 'count': 0}
        save_usage(usage)
    
    # Check limits
    if usage['daily']['count'] >= DAILY_CAP:
        return False, f"Daily cap reached ({DAILY_CAP})"
    
    if usage['monthly']['count'] >= MONTHLY_CAP:
        return False, f"Monthly cap reached ({MONTHLY_CAP})"
    
    return True, "OK"


def increment_usage():
    """Increment usage counters."""
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
    """Get current usage statistics."""
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


def get_flashcards_for_setup(setup_type: str, limit: int = 10) -> List[Dict]:
    """
    Get flashcard images for a specific setup type.
    Returns the best examples (highest outcome %) first.
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
    
    # Sort by outcome percentage (best performers first)
    setup_cards.sort(key=lambda x: x.get('outcome_percentage', 0), reverse=True)
    
    # Get top N with their file paths
    result = []
    for card in setup_cards[:limit]:
        chart_id = card.get('chart_id', '').replace('/', '_')
        file_path = f"{folder_path}/{chart_id}.jpg"
        
        if os.path.exists(file_path):
            result.append({
                'metadata': card,
                'file_path': file_path,
                'outcome': card.get('outcome_percentage', 0)
            })
    
    return result


def image_to_base64(file_path: str) -> Optional[str]:
    """Convert image file to base64 string."""
    try:
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to read image {file_path}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# VISION AI COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def compare_charts_vision(
    live_chart_path: str,
    flashcard_paths: List[str],
    setup_type: str
) -> Dict:
    """
    Use Vision AI to compare live chart against flashcard examples.
    
    Returns similarity score and best match info.
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
    
    # Load flashcard images (max 3 to save tokens)
    flashcard_images = []
    for path in flashcard_paths[:3]:
        b64 = image_to_base64(path)
        if b64:
            flashcard_images.append({'path': path, 'b64': b64})
    
    if not flashcard_images:
        return {
            'success': False,
            'error': 'No flashcard images loaded',
            'similarity': 0
        }
    
    # Build Vision API request
    try:
        messages = [
            {
                "role": "system",
                "content": """You are a crypto chart pattern analyzer. Compare the LIVE chart to the REFERENCE flashcard examples.

Rate similarity from 0-100 based on:
- Chart structure similarity
- Fib retracement pattern match
- Flip zone formation
- Overall setup quality match

Respond ONLY with JSON:
{"matches": [{"ref": 1, "similarity": 85}, {"ref": 2, "similarity": 78}, {"ref": 3, "similarity": 72}], "confidence": "high", "notes": "brief reason"}

Rate ALL reference images by similarity (0-100). Return matches sorted by similarity descending."""
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"LIVE CHART (analyzing for {setup_type} setup):"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{live_b64}"}}
                ]
            }
        ]
        
        # Add flashcard reference images
        for i, fc in enumerate(flashcard_images):
            messages.append({
                "role": "user", 
                "content": [
                    {"type": "text", "text": f"REFERENCE {i+1} ({setup_type} example):"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{fc['b64']}"}}
                ]
            })
        
        messages.append({
            "role": "user",
            "content": "Compare the LIVE chart to these reference examples. How similar is it? Respond with JSON only."
        })
        
        # Convert to Claude message format
        claude_messages = []
        claude_content = []
        
        # Add system prompt as first user message for Claude
        system_text = messages[0]["content"]
        claude_content.append({"type": "text", "text": system_text})
        
        # Add all images and text from user messages
        for msg in messages[1:]:
            if msg["role"] == "user":
                msg_content = msg["content"]
                if isinstance(msg_content, list):
                    for item in msg_content:
                        if item.get("type") == "text":
                            claude_content.append({"type": "text", "text": item["text"]})
                        elif item.get("type") == "image_url":
                            # Extract base64 from data URL
                            data_url = item["image_url"]["url"]
                            if data_url.startswith("data:image/jpeg;base64,"):
                                b64_data = data_url.replace("data:image/jpeg;base64,", "")
                                # Detect media type from base64 header
                                media_type = "image/jpeg"
                                if b64_data.startswith("/9j/"):
                                    media_type = "image/jpeg"
                                elif b64_data.startswith("iVBORw"):
                                    media_type = "image/png"
                                
                                claude_content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": b64_data
                                    }
                                })
                elif isinstance(msg_content, str):
                    claude_content.append({"type": "text", "text": msg_content})
        
        claude_messages = [{"role": "user", "content": claude_content}]
        
        # Call Claude Vision API (Anthropic)
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 150,
                "messages": claude_messages
            },
            timeout=30
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
        
        # Check for API errors in response
        if 'error' in result:
            logger.error(f"Vision API returned error: {result['error']}")
            return {
                'success': False,
                'error': str(result['error']),
                'similarity': 0
            }
        
        try:
            # Claude format: result['content'][0]['text']
            content = result['content'][0]['text']
        except (KeyError, IndexError) as e:
            logger.error(f"Vision API unexpected response format: {result}")
            return {
                'success': False,
                'error': f'Unexpected response format: {e}',
                'similarity': 0
            }
        
        # Debug log the raw response
        logger.info(f"Vision API raw response: {content[:300]}...")
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            
            # Handle top 10 matches
            matches = parsed.get('matches', [])
            if not matches and 'similarity' in parsed:
                # Fallback for old format
                matches = [{'ref': parsed.get('best_match', 1), 'similarity': parsed.get('similarity', 0)}]
            
            # Sort by similarity descending
            matches = sorted(matches, key=lambda x: x.get('similarity', 0), reverse=True)[:3]
            
            # Calculate average similarity of top 10
            similarities = [m.get('similarity', 0) for m in matches]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0
            
            # Build top 10 results with paths
            top_matches = []
            for m in matches:
                ref_idx = m.get('ref', 1) - 1
                if 0 <= ref_idx < len(flashcard_images):
                    top_matches.append({
                        'path': flashcard_images[ref_idx]['path'],
                        'similarity': m.get('similarity', 0),
                        'chart_id': os.path.basename(flashcard_images[ref_idx]['path']).replace('.jpg', '')
                    })
            
            return {
                'success': True,
                'similarity': round(avg_similarity, 1),
                'top_matches': top_matches,
                'confidence': parsed.get('confidence', 'unknown'),
                'notes': parsed.get('notes', ''),
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
    
    Only runs if:
    - current_score >= MIN_SCORE_GATE (70)
    - Within daily/monthly budget
    - Setup type has flashcard examples
    
    Returns:
    - similarity: 0-100 match score
    - bonus_points: Points to add to final score (0-10)
    - should_boost: Whether to boost the grade
    """
    result = {
        'ran_vision': False,
        'similarity': 0,
        'bonus_points': 0,
        'should_boost': False,
        'reason': '',
        'best_match': None
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
    
    # Gate 3: Get flashcards for this setup type
    flashcards = get_flashcards_for_setup(setup_type, limit=10)
    if not flashcards:
        result['reason'] = f'No flashcards for setup type: {setup_type}'
        return result
    
    # Gate 4: Check live chart exists
    if not os.path.exists(live_chart_path):
        result['reason'] = 'Live chart not found'
        return result
    
    # Run Vision comparison
    flashcard_paths = [fc['file_path'] for fc in flashcards]
    vision_result = compare_charts_vision(live_chart_path, flashcard_paths, setup_type)
    
    result['ran_vision'] = True
    result['vision_result'] = vision_result
    
    if vision_result.get('success'):
        similarity = vision_result.get('similarity', 0)  # Now average of top 10
        result['similarity'] = similarity
        result['top_matches'] = vision_result.get('top_matches', [])
        result['confidence'] = vision_result.get('confidence')
        result['notes'] = vision_result.get('notes')
        
        # Log top 3 highest matches (for inspection)
        if result['top_matches']:
            logger.info("Flashcard Matches:")
            for match in result['top_matches']:
                logger.info(f"  - {match['chart_id']} → {match['similarity']}%")
        
        # Calculate bonus points based on similarity
        if similarity >= 90:
            result['bonus_points'] = 10
            result['should_boost'] = True
        elif similarity >= 80:
            result['bonus_points'] = 7
            result['should_boost'] = True
        elif similarity >= 70:
            result['bonus_points'] = 5
            result['should_boost'] = False
        elif similarity >= 60:
            result['bonus_points'] = 3
            result['should_boost'] = False
        else:
            result['bonus_points'] = 0
            result['should_boost'] = False
        
        result['reason'] = f'Similarity: {similarity}%'
    else:
        result['reason'] = vision_result.get('error', 'Vision failed')
    
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("FLASHCARD VISION AI v1.0 - TEST")
    print("=" * 60)
    
    # Show flashcard counts
    print("\nFlashcard Library:")
    for setup in ['382', '50', '618', '786', 'Under-Fib']:
        cards = get_flashcards_for_setup(setup)
        print(f"  {setup}: {len(cards)} cards")
    
    # Show usage stats
    print("\nUsage Stats:")
    stats = get_usage_stats()
    print(f"  Daily: {stats['daily_used']}/{stats['daily_cap']}")
    print(f"  Monthly: {stats['monthly_used']}/{stats['monthly_cap']}")
    print(f"  Total: {stats['total']}")
    
    # Check if OpenAI key is set
    if OPENAI_API_KEY:
        print("\n✅ OpenAI API key configured")
    else:
        print("\n⚠️ OpenAI API key NOT configured")
        print("   Set OPENAI_API_KEY in /opt/jayce/.env")
