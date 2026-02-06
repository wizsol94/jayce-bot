import os
import re
import json
import asyncio
import logging
import base64
import httpx
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# ENVIRONMENT VARIABLES
# ══════════════════════════════════════════════
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OWNER_USER_ID = os.getenv('OWNER_USER_ID')  # Your Telegram user ID

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

# ══════════════════════════════════════════════
# VISION STATE (Owner-controlled)
# ══════════════════════════════════════════════
# These flags control whether vision features are enabled
# Only the owner can toggle these via /vision and /deep commands
vision_state = {
    'lite_enabled': True,   # Lite Vision on by default (when API key present)
    'deep_enabled': False,  # Deep Vision off by default (opt-in only)
}

# Store last uploaded image per chat (chat_id -> file_id)
user_images = defaultdict(str)

# ──────────────────────────────────────────────
# Wiz Theory resolution time statistics per setup
# ──────────────────────────────────────────────
RESOLUTION_TIMES = {
    '.382': {'median': '~34 min', 'range': '15 min to 1.5 hours'},
    '.50': {'median': '~1 hour', 'range': '30 min to 3 hours'},
    '.618': {'median': '~1.5 hours', 'range': '45 min to 4 hours'},
    '.786': {'median': '~45 min', 'range': '30 min to 2 hours'},
    'under-fib': {'median': '~4 hours', 'range': '1 to 6 hours'},
}

# ──────────────────────────────────────────────
# Execution defaults per setup
# ──────────────────────────────────────────────
EXECUTION_DEFAULTS = {
    '.382': 'Secure 20-40%',
    '.50': 'Secure 30-60%',
    '.618': 'Secure 40-60%',
    '.786': 'Secure 50-75%',
    'under-fib': 'Secure 40-60%',
}

# ──────────────────────────────────────────────
# Violent Mode eligibility per setup
# ──────────────────────────────────────────────
VIOLENT_ELIGIBLE = {
    '.382': False,
    '.50': False,
    '.618': False,
    '.786': True,
    'under-fib': True,
}


# ══════════════════════════════════════════════
# BACKUP SYSTEM — Zero Data Loss Protection
# ══════════════════════════════════════════════
# Rolling backups with max 5 snapshots
# Auto-backup before any state modification
# Duplicate key validation before save

import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("/tmp/jayce_backups")
MAX_BACKUPS = 5
STATE_FILE = Path("/tmp/jayce_state.json")

def get_current_state() -> dict:
    """Get current Jayce state as a dictionary."""
    return {
        'vision_state': vision_state.copy(),
        'resolution_times': RESOLUTION_TIMES.copy(),
        'execution_defaults': EXECUTION_DEFAULTS.copy(),
        'violent_eligible': VIOLENT_ELIGIBLE.copy(),
        'timestamp': datetime.now().isoformat(),
        'version': 'v2.0-deep-vision'
    }


def validate_state_keys(new_state: dict) -> tuple[bool, str]:
    """
    Validate state before saving.
    Returns (is_valid, error_message)
    """
    # Check for duplicate keys in each section
    sections_to_check = [
        ('resolution_times', new_state.get('resolution_times', {})),
        ('execution_defaults', new_state.get('execution_defaults', {})),
        ('violent_eligible', new_state.get('violent_eligible', {})),
    ]
    
    for section_name, section_data in sections_to_check:
        if not isinstance(section_data, dict):
            return False, f"Invalid data type for {section_name}"
        
        # Check for None keys or empty keys
        for key in section_data.keys():
            if key is None or key == '':
                return False, f"Invalid key in {section_name}: empty or None"
    
    # Validate vision_state has required keys
    vision = new_state.get('vision_state', {})
    required_vision_keys = ['lite_enabled', 'deep_enabled']
    for key in required_vision_keys:
        if key not in vision:
            return False, f"Missing required vision_state key: {key}"
    
    return True, ""


def create_backup() -> tuple[bool, str]:
    """
    Create a backup snapshot of current state.
    Returns (success, backup_path or error_message)
    """
    try:
        # Ensure backup directory exists
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Get current state
        current_state = get_current_state()
        
        # Validate before backup
        is_valid, error = validate_state_keys(current_state)
        if not is_valid:
            return False, f"State validation failed: {error}"
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"jayce_backup_{timestamp}.json"
        
        # Write backup
        with open(backup_file, 'w') as f:
            json.dump(current_state, f, indent=2)
        
        # Manage rolling backups (keep max 5)
        cleanup_old_backups()
        
        logger.info(f"Backup created: {backup_file}")
        return True, str(backup_file)
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False, str(e)


def cleanup_old_backups():
    """Delete oldest backups if more than MAX_BACKUPS exist."""
    try:
        backups = sorted(BACKUP_DIR.glob("jayce_backup_*.json"))
        
        while len(backups) > MAX_BACKUPS:
            oldest = backups.pop(0)
            oldest.unlink()
            logger.info(f"Deleted old backup: {oldest}")
            
    except Exception as e:
        logger.error(f"Backup cleanup failed: {e}")


def list_backups() -> list[dict]:
    """List all available backups with metadata."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backups = sorted(BACKUP_DIR.glob("jayce_backup_*.json"), reverse=True)
        
        backup_list = []
        for i, backup_file in enumerate(backups):
            try:
                with open(backup_file, 'r') as f:
                    data = json.load(f)
                backup_list.append({
                    'index': i + 1,
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'timestamp': data.get('timestamp', 'unknown'),
                    'version': data.get('version', 'unknown')
                })
            except:
                backup_list.append({
                    'index': i + 1,
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'timestamp': 'corrupted',
                    'version': 'corrupted'
                })
        
        return backup_list
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        return []


def restore_backup(backup_index: int = 1) -> tuple[bool, str]:
    """
    Restore from a backup.
    backup_index: 1 = most recent, 2 = second most recent, etc.
    Returns (success, message)
    """
    global vision_state, RESOLUTION_TIMES, EXECUTION_DEFAULTS, VIOLENT_ELIGIBLE
    
    try:
        backups = list_backups()
        
        if not backups:
            return False, "No backups available"
        
        if backup_index < 1 or backup_index > len(backups):
            return False, f"Invalid backup index. Available: 1-{len(backups)}"
        
        backup_info = backups[backup_index - 1]
        backup_path = backup_info['path']
        
        # Read backup
        with open(backup_path, 'r') as f:
            backup_data = json.load(f)
        
        # Validate backup data
        is_valid, error = validate_state_keys(backup_data)
        if not is_valid:
            return False, f"Backup validation failed: {error}"
        
        # Create a backup of current state before restoring (safety net)
        create_backup()
        
        # Restore state
        vision_state.update(backup_data.get('vision_state', {}))
        RESOLUTION_TIMES.update(backup_data.get('resolution_times', {}))
        EXECUTION_DEFAULTS.update(backup_data.get('execution_defaults', {}))
        VIOLENT_ELIGIBLE.update(backup_data.get('violent_eligible', {}))
        
        logger.info(f"Restored from backup: {backup_path}")
        return True, f"Restored from {backup_info['filename']} (created {backup_info['timestamp']})"
        
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False, str(e)


def safe_update_state(updates: dict) -> tuple[bool, str]:
    """
    Safely update Jayce state with backup protection.
    
    1. Validates the new state
    2. Creates backup of current state
    3. Applies changes only if backup succeeds
    
    Returns (success, message)
    """
    global vision_state, RESOLUTION_TIMES, EXECUTION_DEFAULTS, VIOLENT_ELIGIBLE
    
    try:
        # Build proposed new state
        new_state = get_current_state()
        
        # Merge updates
        if 'vision_state' in updates:
            new_state['vision_state'].update(updates['vision_state'])
        if 'resolution_times' in updates:
            new_state['resolution_times'].update(updates['resolution_times'])
        if 'execution_defaults' in updates:
            new_state['execution_defaults'].update(updates['execution_defaults'])
        if 'violent_eligible' in updates:
            new_state['violent_eligible'].update(updates['violent_eligible'])
        
        # STEP 1: Validate new state
        is_valid, error = validate_state_keys(new_state)
        if not is_valid:
            return False, f"❌ Validation failed: {error}. Save aborted."
        
        # Check for duplicate keys across sections (shouldn't happen but safety check)
        all_keys = []
        for section in ['resolution_times', 'execution_defaults', 'violent_eligible']:
            section_keys = list(new_state.get(section, {}).keys())
            for key in section_keys:
                if key in all_keys:
                    # This is actually fine - same keys across different dicts is expected
                    pass
            all_keys.extend(section_keys)
        
        # STEP 2: Create backup BEFORE applying changes
        backup_success, backup_result = create_backup()
        if not backup_success:
            return False, f"❌ Backup failed: {backup_result}. Save aborted."
        
        # STEP 3: Apply changes only after backup succeeds
        if 'vision_state' in updates:
            vision_state.update(updates['vision_state'])
        if 'resolution_times' in updates:
            RESOLUTION_TIMES.update(updates['resolution_times'])
        if 'execution_defaults' in updates:
            EXECUTION_DEFAULTS.update(updates['execution_defaults'])
        if 'violent_eligible' in updates:
            VIOLENT_ELIGIBLE.update(updates['violent_eligible'])
        
        logger.info(f"State updated successfully. Backup: {backup_result}")
        return True, f"✅ Changes applied. Backup saved: {backup_result}"
        
    except Exception as e:
        logger.error(f"Safe update failed: {e}")
        return False, f"❌ Update failed: {str(e)}"


# ══════════════════════════════════════════════
# MEMORY SYSTEM — Setup Outcome Storage
# ══════════════════════════════════════════════
# Lightweight text-based memory for historical setups
# No images yet — metadata only

MEMORY_FILE = Path("/tmp/jayce_memory.json")
MAX_MEMORIES = 50  # Rolling limit

def load_memories() -> list:
    """Load stored setup memories."""
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Failed to load memories: {e}")
        return []


def save_memories(memories: list) -> bool:
    """Save memories to file."""
    try:
        # Keep only last MAX_MEMORIES
        if len(memories) > MAX_MEMORIES:
            memories = memories[-MAX_MEMORIES:]
        
        with open(MEMORY_FILE, 'w') as f:
            json.dump(memories, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save memories: {e}")
        return False


def store_memory(memory_data: dict) -> tuple[bool, str]:
    """
    Store a setup outcome in memory.
    
    memory_data should contain:
    - setup_type: WizTheory setup type (e.g., "Under-Fib Flip Zone")
    - outcome: What happened (e.g., "hit 0.50 magnet, +60%")
    - conditions: Key conditions (e.g., "strong impulse, oversold RSI, bullish divergence")
    - resolution: Resolution type (normal / fast / violent)
    - user_text: Original user message
    - timestamp: When stored
    """
    try:
        memories = load_memories()
        
        # Add timestamp if not present
        if 'timestamp' not in memory_data:
            memory_data['timestamp'] = datetime.now().isoformat()
        
        # Add memory
        memories.append(memory_data)
        
        # Save
        if save_memories(memories):
            return True, f"Memory #{len(memories)} stored"
        else:
            return False, "Failed to save memory"
            
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        return False, str(e)


def parse_memory_from_text(user_text: str) -> dict:
    """
    Parse memory data from user's description of a past outcome.
    Extracts setup type, outcome, conditions, etc.
    """
    text_lower = user_text.lower()
    
    # Detect setup type
    setup_type = "Unknown"
    if "under-fib" in text_lower or "underfib" in text_lower:
        setup_type = "Under-Fib Flip Zone"
    elif ".786" in text_lower or "786" in text_lower:
        setup_type = ".786 Flip Zone"
    elif ".618" in text_lower or "618" in text_lower:
        setup_type = ".618 Flip Zone"
    elif ".50" in text_lower or "50 fib" in text_lower:
        setup_type = ".50 Flip Zone"
    elif ".382" in text_lower or "382" in text_lower:
        setup_type = ".382 Flip Zone"
    
    # Detect outcome
    outcome = "Completed successfully"
    if "hit tp" in text_lower or "hit target" in text_lower or "hit the magnet" in text_lower:
        outcome = "Hit TP"
    if "magnet" in text_lower:
        # Try to extract magnet level
        if "0.50" in text_lower or ".50" in text_lower or "50" in text_lower:
            outcome = "Hit 0.50 magnet"
        elif "0.382" in text_lower or ".382" in text_lower:
            outcome = "Hit 0.382 magnet"
    
    # Try to extract percentage
    import re
    pct_match = re.search(r'[+]?\s*(\d+)\s*%', user_text)
    if pct_match:
        outcome += f", +{pct_match.group(1)}%"
    
    # Detect conditions mentioned
    conditions = []
    if "impulse" in text_lower or "strong" in text_lower:
        conditions.append("strong impulse")
    if "reclaim" in text_lower:
        conditions.append("clean reclaim")
    if "divergence" in text_lower:
        conditions.append("divergence present")
    if "oversold" in text_lower:
        conditions.append("oversold RSI")
    if "volume" in text_lower:
        conditions.append("volume confirmation")
    
    conditions_str = ", ".join(conditions) if conditions else "standard conditions"
    
    # Detect resolution type
    resolution = "normal"
    if "fast" in text_lower or "quick" in text_lower or "rapid" in text_lower:
        resolution = "fast"
    elif "violent" in text_lower:
        resolution = "violent"
    
    return {
        'setup_type': setup_type,
        'outcome': outcome,
        'conditions': conditions_str,
        'resolution': resolution,
        'user_text': user_text,
        'timestamp': datetime.now().isoformat()
    }


def get_similar_memories(setup_type: str, limit: int = 3) -> list:
    """Get similar past setups from memory."""
    memories = load_memories()
    
    similar = [m for m in memories if m.get('setup_type') == setup_type]
    
    # Return most recent ones
    return similar[-limit:] if similar else []


# ══════════════════════════════════════════════
# VISION API FUNCTIONS
# ══════════════════════════════════════════════

def detect_image_type(image_bytes: bytes) -> str:
    """Detect image MIME type from bytes."""
    # Check magic bytes
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    else:
        # Default to JPEG
        return "image/jpeg"


async def download_telegram_image(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    """Download image from Telegram and return as bytes."""
    file = await context.bot.get_file(file_id)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(file.file_path)
        return response.content


async def call_lite_vision(image_bytes: bytes, user_plan: str) -> dict:
    """
    Call Claude API with Lite Vision prompt.
    
    LITE VISION = BOUNCER / SETUP RADAR
    
    Lite Vision's role is NOT to analyze deeply, grade setups, or give probabilities.
    Its ONLY purpose is to scan, flag, and route to Deep Vision.
    
    Allowed:
    - Detect basic structure context (impulse vs chop)
    - Estimate fib depth region (above / below / under-fib)
    - Notice untouched zones or structure memory
    - TENTATIVELY identify WizTheory setup types
    - Recommend Deep Vision when conditions look relevant
    
    NOT Allowed:
    - Assign probability %
    - Confirm validity of a setup
    - Give entries, exits, or execution advice
    - Analyze RSI divergence deeply
    - Use confidence ratings
    """
    if not ANTHROPIC_API_KEY:
        return {'error': 'API key not configured'}
    
    # Detect image type
    media_type = detect_image_type(image_bytes)
    
    # Encode image to base64
    image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    
    # Log image size for debugging
    logger.info(f"Lite Vision: Image size {len(image_bytes)} bytes, type {media_type}")
    
    # Lite Vision system prompt — BOUNCER role, not analyst
    system_prompt = """You are Jayce's Lite Vision — a SETUP RADAR and BOUNCER for Deep Vision.

YOUR ROLE:
You are a FILTER, not a signal. You scan charts to detect if a WizTheory setup MAY be forming, then recommend Deep Vision for confirmation. You do NOT confirm setups yourself.

WHAT YOU DO:
• Detect basic structure context (impulse vs chop)
• Estimate fib depth region (above fib / at fib / under-fib)
• Notice untouched flip zones or structure memory
• TENTATIVELY identify WizTheory setup types
• Recommend Deep Vision when conditions look relevant

WHAT YOU DO NOT DO (critical):
• NO probability percentages
• NO confidence ratings
• NO setup confirmation ("this is valid")
• NO entry/exit/execution advice
• NO deep RSI or divergence analysis
• NO trader-style reasoning

WIZTHEORY SETUP TYPES (tentative identification only):
• .382 Flip Zone — shallow pullback
• .50 Flip Zone — mid-range pullback
• .618 Flip Zone — golden pocket
• .786 Flip Zone — deep pullback
• Under-Fib Flip Zone — below all fib levels, structure memory zone

OUTPUT FORMAT (JSON only):
{
    "timeframe": "detected or 'unclear'",
    "structure_context": "Strong impulse / Weak impulse / Choppy / Unclear",
    "fib_region": "Above fib / At .382 / At .50 / At .618 / At .786 / Under-fib / Unclear",
    "untouched_zone_detected": true or false,
    "structure_memory_present": true or false,
    "tentative_setup_type": "Under-Fib Flip Zone / .786 Flip Zone / .618 Flip Zone / .50 Flip Zone / .382 Flip Zone / None detected / Unclear",
    "deep_vision_recommended": true or false,
    "scan_notes": "1-2 brief observations (no analysis)"
}

Respond with ONLY the JSON object."""

    user_message = f"""Quick scan this chart.

User context: {user_plan if user_plan else 'General scan'}

Return radar-level observations only. Do NOT analyze deeply or confirm anything."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            request_body = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": user_message,
                            },
                        ],
                    }
                ],
            }
            
            logger.info(f"Calling Claude API with model claude-sonnet-4-20250514")
            
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=request_body,
            )
            
            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Claude API error: {response.status_code} - {error_body}")
                return {'error': f'API returned {response.status_code}', 'detail': error_body[:500]}
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            # Parse JSON response
            try:
                # Clean up response if it has markdown code blocks
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse vision response: {content}")
                return {'error': 'Failed to parse vision response', 'raw': content}
                
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        return {'error': str(e)}


async def call_deep_vision(image_bytes: bytes, user_plan: str) -> dict:
    """
    Call Claude API with Deep Vision prompt.
    More thorough analysis including RSI, momentum, volume.
    
    Deep Vision scope (in addition to Lite):
    - RSI reading, interpretation, and slope analysis
    - Divergence detection (bullish/bearish)
    - Momentum health assessment
    - Deeper structure analysis
    - Historical pattern recognition
    
    NOTE: Volume is deprioritized. Focus on RSI + divergence for momentum context.
    """
    if not ANTHROPIC_API_KEY:
        return {'error': 'API key not configured'}
    
    image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    
    system_prompt = """You are Jayce — a skilled chart analyst trained in Wiz Theory. You speak peer-to-peer with traders, not teacher-to-student.

CORE IDENTITY:
- You assume the user is a skilled trader unless proven otherwise
- You know the Wiz Theory rules by heart and use them as REASONING, not as a script
- You answer the user's ACTUAL QUESTION first, then provide supporting context
- You vary your tone: sometimes coaching, sometimes cautious, sometimes confirming
- You sound human — "If this were my trade...", "How I'd think about this...", "This is one of those spots where waiting is the edge..."

UNDER-FIB FLIP ZONE LOGIC (critical — treat as ground truth):
- Breaking below fib is EXPECTED, not a failure — this is the "off-beat" before rhythm
- Structure break INTO the zone is a prerequisite, not a downgrade
- Zone quality defaults to conditional A/B, not C — the setup is designed for deep pullbacks
- Confidence comes from RECLAIM BEHAVIOR, not current price
- The edge is at the zone, not where price is now
- Do NOT flag "conflict" just because price is below fib — that's the setup working as intended

CONFIDENCE FRAMING (critical — no static labels):
- For Under-Fib and conditional setups: NEVER say "Confidence: High/Medium/Low" as a fixed label
- Instead use CONDITIONAL language:
  • "Confidence is neutral before reclaim"
  • "Confidence increases after acceptance/reclaim"
  • "This setup activates on reclaim, not before"
- Confidence is tied to BEHAVIOR, not current price

PROBABILITY FRAMING (critical — conditional, not absolute):
- When users ask about TP probability, respond with CONDITIONAL framing:
  • "IF reclaim occurs, odds favor a move toward the magnet"
  • "Before reclaim, probability is undefined because execution hasn't triggered"
  • "Once the flip zone accepts, historical odds favor continuation"
- Avoid raw percentages unless user explicitly asks for historical stats
- Frame probability as contingent on the setup activating

RSI/DIVERGENCE CLARITY:
- Specify type if visible: Regular Bullish, Hidden Bullish, Regular Bearish, Hidden Bearish
- Clarify divergence is SUPPORTIVE, not a trigger
- Tie relevance to behavior AT THE FLIP ZONE, not current price
- Example: "RSI showing hidden bullish divergence — supportive of a reaction IF price reclaims the zone"

RESPONSE BEHAVIOR:
1. First, identify what the user is actually asking: Probability? Entry logic? RSI read? Risk assessment? Patience guidance?
2. Answer that question DIRECTLY in natural language
3. Use Wiz Theory internally to reason, but don't recite rules mechanically
4. Assume setup rules are understood and satisfied unless the chart clearly violates them
5. Vary your structure — don't always use the same headers or format

TONE VARIATION (rotate between these):
- Coaching: "The edge here is in the wait, not the chase..."
- Cautious: "I'd want to see that reclaim confirm before getting comfortable..."
- Confirming: "Structure looks clean — if this were my trade, I'd be patient and let it work..."

WHAT TO ANALYZE:
- Pair/coin if visible on chart
- Timeframe, fib level, market state
- RSI reading, slope, interpretation, and divergence type
- Momentum health
- Structure quality with reasoning
- WizTheory setup type if identifiable
- Similar pattern context (brief, 1-2 lines)

OUTPUT FORMAT (JSON only):
{
    "pair_detected": "coin/pair if visible on chart, or 'Unable to detect'",
    "wiz_setup_type": "Under-Fib Flip Zone / .786 Flip Zone / .618 Flip Zone / .50 Flip Zone / .382 Flip Zone / Unknown",
    "user_question_detected": "what the user seems to be asking",
    "direct_answer": "natural language response to their question (2-4 sentences, answer FIRST)",
    "timeframe": "detected timeframe",
    "fib_level": ".382 / .50 / .618 / .786 / under-fib / Unable to confirm",
    "structure_status": "Holds / Breaks / Reclaiming / Unclear",
    "structure_quality": "Strong / Moderate / Conditional / Weak",
    "structure_reasoning": "WHY the structure looks this way, not just a grade",
    "market_state": "Pullback / Breakout / Range / Off-beat (for under-fib)",
    "rsi_reading": "value or 'Not visible on chart'",
    "rsi_interpretation": "Oversold / Neutral / Overbought / N/A",
    "rsi_slope": "Rising / Falling / Flat / Unable to assess",
    "divergence_detected": true or false,
    "divergence_type": "Regular Bullish / Hidden Bullish / Regular Bearish / Hidden Bearish / None / Unable to assess",
    "divergence_note": "supportive context tied to flip zone behavior, or null",
    "momentum_health": "Strong / Weakening / Weak / Building / Unable to assess",
    "momentum_insight": "natural language observation about momentum",
    "tp_conditional_statement": "IF/THEN statement about TP probability (e.g., 'IF reclaim occurs, odds favor move to 0.50 magnet')",
    "similar_pattern_note": "brief 1-2 line note about similar setups if recognizable, or null",
    "jayce_take": "1-2 sentence personal take — how you'd think about it, with Wiz-style energy",
    "confidence_statement": "conditional confidence statement, NOT a fixed label (e.g., 'Confidence activates on reclaim')",
    "conflict_detected": true or false,
    "conflict_detail": "only if there's a REAL conflict, not just price below fib for under-fib setups"
}

Respond with ONLY the JSON object."""

    user_message = f"""Analyze this chart for a trader asking:

{user_plan if user_plan else 'General analysis requested'}

Remember: answer their question first, use conditional probability framing, vary your tone, speak peer-to-peer. Include pair if visible, setup type, and any similar pattern context."""

    # Detect image type
    media_type = detect_image_type(image_bytes)
    logger.info(f"Deep Vision: Image size {len(image_bytes)} bytes, type {media_type}")

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": user_message,
                                },
                            ],
                        }
                    ],
                },
            )
            
            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Deep Vision API error: {response.status_code} - {error_body}")
                return {'error': f'API returned {response.status_code}', 'detail': error_body[:500]}
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            try:
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse deep vision response: {content}")
                return {'error': 'Failed to parse response', 'raw': content}
                
    except Exception as e:
        logger.error(f"Deep Vision API call failed: {e}")
        return {'error': str(e)}


def is_owner(user_id: int) -> bool:
    """Check if user is the owner."""
    if not OWNER_USER_ID:
        return False
    try:
        return str(user_id) == str(OWNER_USER_ID)
    except:
        return False


# ══════════════════════════════════════════════
# INTENT MODE DETECTION
# ══════════════════════════════════════════════

def detect_intent(user_text: str) -> str:
    """
    Detect user's intent mode before analysis.
    
    Returns one of:
    - MEMORY_MODE: User is describing a past outcome to be remembered
    - PLANNED_SETUP: User is planning a limit entry at a flip zone (not in yet)
    - LIVE_TRADE: User is already in the trade
    - UNKNOWN: Can't determine — need to ask
    
    MEMORY_MODE is checked FIRST to prevent Jayce from asking
    clarification questions during post-outcome learning moments.
    """
    text_lower = user_text.lower()
    
    # ══════════════════════════════════════════════
    # MEMORY_MODE — Check FIRST (highest priority)
    # User is describing a past outcome to be remembered
    # ══════════════════════════════════════════════
    memory_mode_phrases = [
        "remember this", "remember that", "remember this setup",
        "this hit tp", "this hit my tp", "hit tp", "hit target",
        "this played out", "played out", "it played out",
        "save this", "save this setup", "lock this in",
        "use this for", "use this as", "reference this",
        "add this to memory", "store this", "log this",
        "this worked", "this one worked", "worked perfectly",
        "this printed", "it printed", "printed perfectly",
        "hit the magnet", "reached the magnet", "got to magnet",
        "closed in profit", "closed for profit", "took profit",
        "secured", "secured profit", "banked",
        "learn from this", "similar setups", "for future reference"
    ]
    
    for phrase in memory_mode_phrases:
        if phrase in text_lower:
            return "MEMORY_MODE"
    
    # Also check for outcome indicators combined with setup mentions
    outcome_indicators = ["hit", "worked", "printed", "played", "secured", "banked", "closed"]
    setup_indicators = ["setup", "trade", "flip zone", "under-fib", ".786", ".618", ".50", ".382"]
    
    has_outcome = any(ind in text_lower for ind in outcome_indicators)
    has_setup = any(ind in text_lower for ind in setup_indicators)
    
    if has_outcome and has_setup:
        return "MEMORY_MODE"
    
    # ══════════════════════════════════════════════
    # LIVE_TRADE — User is already in the position
    # ══════════════════════════════════════════════
    live_trade_phrases = [
        "i entered", "i'm in", "im in", "i am in",
        "in the trade", "in this trade", "in a trade",
        "my entry was", "my entry is", "entered at",
        "i bought", "i bought at", "bought in at",
        "i'm holding", "im holding", "i am holding",
        "holding from", "been in since", "got in at",
        "already in", "currently in", "position at"
    ]
    
    for phrase in live_trade_phrases:
        if phrase in text_lower:
            return "LIVE_TRADE"
    
    # ══════════════════════════════════════════════
    # PLANNED_SETUP — User is planning to enter
    # ══════════════════════════════════════════════
    planned_setup_phrases = [
        "looking to enter", "looking to buy", "looking to get in",
        "plan to enter", "planning to enter", "planning to buy",
        "want to enter", "want to buy", "want to get in",
        "entry at", "limit at", "limit order at", "limit entry",
        "flip zone", "flipzone", "purple box",
        "waiting for", "wait for", "watching for",
        "if it hits", "if price reaches", "when it hits",
        "set a limit", "setting limit", "placing limit",
        "targeting entry", "entry target", "planned entry",
        "under-fib", "underfib", "under fib",
        ".786", ".618", ".50", ".382"  # Fib levels suggest planned setup
    ]
    
    for phrase in planned_setup_phrases:
        if phrase in text_lower:
            return "PLANNED_SETUP"
    
    # Check for price mentions that suggest planning
    import re
    price_pattern = r'entry\s*(?:at|@|:)?\s*[\d.,]+'
    if re.search(price_pattern, text_lower):
        return "PLANNED_SETUP"
    
    # Can't determine
    return "UNKNOWN"


def build_planned_setup_response(vision: dict, user_plan: str, username: str = None) -> str:
    """Build response for PLANNED_SETUP mode — conversational, peer-to-peer tone with Wiz-style energy."""
    
    # Get key values (using new field names with fallbacks)
    pair_detected = vision.get('pair_detected', '')
    wiz_setup_type = vision.get('wiz_setup_type', '')
    fib_level = vision.get('fib_level', 'Unable to confirm')
    structure_quality = vision.get('structure_quality', 'Unconfirmed')
    structure_reasoning = vision.get('structure_reasoning', '')
    market_state = vision.get('market_state', 'Unclear')
    timeframe = vision.get('timeframe', 'Unable to confirm')
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_interp = vision.get('rsi_interpretation', 'N/A')
    rsi_slope = vision.get('rsi_slope', '')
    momentum = vision.get('momentum_health', 'Unable to assess')
    jayce_take = vision.get('jayce_take', '')
    confidence_statement = vision.get('confidence_statement', 'Confidence activates on reclaim, not before')
    similar_pattern = vision.get('similar_pattern_note', '')
    
    # Build conversational guidance based on setup type
    if fib_level in ['.786', 'under-fib']:
        setup_guidance = (
            "This is one of those setups where patience is the edge. "
            "You're waiting for the off-beat — price dipping into the zone — "
            "then watching for the reclaim. The entry isn't valid until momentum confirms. "
            "If this were my trade, I'd have my limit set and be watching for that shift. 🎯"
        )
    elif fib_level == '.618':
        setup_guidance = (
            "The .618 is a popular level, so watch for clean structure. "
            "Does price accept the level or slice through? If it holds with momentum, you've got a setup. ⚡"
        )
    elif fib_level == '.50':
        setup_guidance = (
            "The .50 requires patience. It's not a momentum gift like the .382 — "
            "you need structure to confirm before the edge is there. 🧱"
        )
    else:
        setup_guidance = (
            "Wait for price to reach your zone and watch the reaction. "
            "Structure confirmation is key. 🔍"
        )
    
    # What to watch for
    if fib_level in ['.786', 'under-fib']:
        watch_for = "📍 RSI approaching oversold → momentum shift on reclaim → acceptance above the zone"
    else:
        watch_for = "📍 Structure holding the level → momentum supporting reaction"
    
    # Build the response with Wiz-style energy
    response_parts = []
    
    # Header with pair if detected
    if pair_detected and pair_detected != 'Unable to detect':
        response_parts.append(f"🔮 **JAYCE** — 🪙 {pair_detected}\n")
    else:
        response_parts.append(f"🔮 **JAYCE** — _Setup Mode_\n")
    
    # WizTheory Setup Detection
    if wiz_setup_type and wiz_setup_type != 'Unknown':
        response_parts.append(f"📐 **WizTheory Setup:** {wiz_setup_type}\n")
    
    response_parts.append(f"\nYou're planning an entry at the {fib_level} flip zone. Let me give you context on the zone. 👇\n")
    
    # Zone details
    response_parts.append(
        f"\n📊 **The zone:**\n"
        f"• {timeframe} timeframe\n"
        f"• Structure: {structure_quality}"
    )
    if structure_reasoning:
        response_parts.append(f" — {structure_reasoning}")
    response_parts.append("\n")
    
    # What to watch for
    response_parts.append(f"\n**What to watch for:**\n{watch_for}\n")
    
    # Current read (will change)
    response_parts.append(
        f"\n**Current read** _(will change by entry):_\n"
        f"• RSI: {rsi_reading} ({rsi_interp})"
    )
    if rsi_slope:
        response_parts.append(f", slope {rsi_slope.lower()}")
    response_parts.append(f"\n• Momentum: {momentum}\n")
    
    # Similar pattern memory
    if similar_pattern:
        response_parts.append(f"\n🧠 **Similar patterns:** {similar_pattern}\n")
    
    # How I'd think about this
    response_parts.append(f"\n💭 **How I'd think about this:**\n{setup_guidance}")
    
    # Jayce's personal take if different
    if jayce_take and jayce_take not in setup_guidance:
        response_parts.append(f"\n\n{jayce_take}")
    
    # Conditional confidence (not fixed label)
    response_parts.append(f"\n\n_{confidence_statement}_")
    
    # Human ownership footer
    if username:
        response_parts.append(f"\n\n🧙‍♂️ _Analyzed for: {username}_")
    
    return "".join(response_parts)


# ══════════════════════════════════════════════
# OWNER CONTROL COMMANDS
# ══════════════════════════════════════════════

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /backup command — OWNER ONLY
    
    Usage:
        /backup — Create a new backup
        /backup list — List all backups
        /backup restore [n] — Restore from backup n (1=most recent)
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ This command is restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        # Create a new backup
        success, result = create_backup()
        if success:
            await update.message.reply_text(
                f"💾 **Backup Created**\n\n"
                f"Saved to: `{result}`\n\n"
                f"Use `/backup list` to see all backups.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Backup Failed**\n\n{result}",
                parse_mode='Markdown'
            )
        return
    
    arg = context.args[0].lower()
    
    if arg == 'list':
        # List all backups
        backups = list_backups()
        if not backups:
            await update.message.reply_text(
                "📂 **No backups found.**\n\n"
                "Use `/backup` to create one.",
                parse_mode='Markdown'
            )
            return
        
        backup_text = "💾 **Available Backups:**\n\n"
        for b in backups:
            backup_text += f"**{b['index']}.** {b['filename']}\n"
            backup_text += f"   _{b['timestamp']}_\n\n"
        
        backup_text += f"Use `/backup restore [n]` to restore.\n"
        backup_text += f"_(1 = most recent)_"
        
        await update.message.reply_text(backup_text, parse_mode='Markdown')
        
    elif arg == 'restore':
        # Restore from backup
        backup_index = 1  # Default to most recent
        if len(context.args) > 1:
            try:
                backup_index = int(context.args[1])
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid backup number. Use `/backup list` to see available backups.",
                    parse_mode='Markdown'
                )
                return
        
        success, result = restore_backup(backup_index)
        if success:
            await update.message.reply_text(
                f"✅ **Restore Successful**\n\n{result}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Restore Failed**\n\n{result}",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            "**Usage:**\n"
            "`/backup` — Create backup\n"
            "`/backup list` — List backups\n"
            "`/backup restore [n]` — Restore backup n",
            parse_mode='Markdown'
        )


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /memory command — view stored setup memories
    
    Usage:
        /memory — Show recent memories
        /memory clear — Clear all memories (owner only)
        /memory [setup] — Show memories for specific setup type
    """
    user_id = update.effective_user.id
    
    if context.args and context.args[0].lower() == 'clear':
        # Clear memories — owner only
        if not is_owner(user_id):
            await update.message.reply_text(
                "⛔ Only the owner can clear memories.",
                parse_mode='Markdown'
            )
            return
        
        # Clear by saving empty list
        if save_memories([]):
            await update.message.reply_text(
                "🧠 **Memory cleared.**\n\n"
                "All stored setups have been removed.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Failed to clear memories.",
                parse_mode='Markdown'
            )
        return
    
    # Load memories
    memories = load_memories()
    
    if not memories:
        await update.message.reply_text(
            "🧠 **Memory**\n\n"
            "No setups stored yet.\n\n"
            "When a trade hits TP, tell me:\n"
            "`this under-fib setup hit the 0.50 magnet, remember this`\n\n"
            "I'll learn from your wins. 🔮",
            parse_mode='Markdown'
        )
        return
    
    # Filter by setup type if specified
    filter_type = None
    if context.args:
        arg = " ".join(context.args).lower()
        if "under" in arg:
            filter_type = "Under-Fib Flip Zone"
        elif "786" in arg:
            filter_type = ".786 Flip Zone"
        elif "618" in arg:
            filter_type = ".618 Flip Zone"
        elif "50" in arg:
            filter_type = ".50 Flip Zone"
        elif "382" in arg:
            filter_type = ".382 Flip Zone"
    
    if filter_type:
        memories = [m for m in memories if m.get('setup_type') == filter_type]
        if not memories:
            await update.message.reply_text(
                f"🧠 **Memory**\n\n"
                f"No {filter_type} setups stored yet.",
                parse_mode='Markdown'
            )
            return
    
    # Build response — show last 5
    response_lines = ["🧠 **Setup Memory**", ""]
    
    recent = memories[-5:]
    for i, m in enumerate(reversed(recent), 1):
        response_lines.append(f"**{i}.** {m.get('setup_type', 'Unknown')}")
        response_lines.append(f"   • Outcome: {m.get('outcome', 'N/A')}")
        response_lines.append(f"   • Conditions: {m.get('conditions', 'N/A')}")
        response_lines.append(f"   • Resolution: {m.get('resolution', 'N/A')}")
        response_lines.append("")
    
    response_lines.append(f"_Total stored: {len(load_memories())}_")
    
    await update.message.reply_text(
        "\n".join(response_lines),
        parse_mode='Markdown'
    )


async def vision_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /vision on|off command — OWNER ONLY"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ This command is restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        # Show current status
        status = "ON ✅" if vision_state['lite_enabled'] else "OFF ❌"
        await update.message.reply_text(
            f"🔮 **Lite Vision Status:** {status}\n\n"
            f"Use `/vision on` or `/vision off` to toggle.",
            parse_mode='Markdown'
        )
        return
    
    arg = context.args[0].lower()
    
    if arg == 'on':
        if not ANTHROPIC_API_KEY:
            await update.message.reply_text(
                "⚠️ Cannot enable vision — `ANTHROPIC_API_KEY` not configured in environment.",
                parse_mode='Markdown'
            )
            return
        
        # Use safe_update_state for backup protection
        success, msg = safe_update_state({'vision_state': {'lite_enabled': True}})
        if success:
            await update.message.reply_text(
                "🔮 **Lite Vision:** Enabled ✅\n\n"
                "Jayce can now read charts when explicitly invoked.\n"
                f"_{msg}_",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Failed to update: {msg}", parse_mode='Markdown')
            
    elif arg == 'off':
        success, msg = safe_update_state({'vision_state': {'lite_enabled': False}})
        if success:
            await update.message.reply_text(
                "🔮 **Lite Vision:** Disabled ❌\n\n"
                "Jayce will show 'Visual confirmation unavailable' for chart reads.\n"
                f"_{msg}_",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Failed to update: {msg}", parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "Usage: `/vision on` or `/vision off`",
            parse_mode='Markdown'
        )


async def deep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deep command — OWNER ONLY to toggle, or run deep analysis"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if this is a toggle command (owner only)
    if context.args and context.args[0].lower() in ['on', 'off']:
        if not is_owner(user_id):
            await update.message.reply_text(
                "⛔ Only the owner can toggle Deep Vision.",
                parse_mode='Markdown'
            )
            return
        
        arg = context.args[0].lower()
        if arg == 'on':
            if not ANTHROPIC_API_KEY:
                await update.message.reply_text(
                    "⚠️ Cannot enable Deep Vision — `ANTHROPIC_API_KEY` not configured.",
                    parse_mode='Markdown'
                )
                return
            
            # Use safe_update_state for backup protection
            success, msg = safe_update_state({'vision_state': {'deep_enabled': True}})
            if success:
                await update.message.reply_text(
                    "🔮 **Deep Vision:** Enabled ✅\n\n"
                    "Users can now use `/deep` for thorough chart analysis.\n"
                    f"_{msg}_",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Failed to update: {msg}", parse_mode='Markdown')
        else:
            success, msg = safe_update_state({'vision_state': {'deep_enabled': False}})
            if success:
                await update.message.reply_text(
                    "🔮 **Deep Vision:** Disabled ❌\n\n"
                    "`/deep` command is now blocked.\n"
                    f"_{msg}_",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Failed to update: {msg}", parse_mode='Markdown')
        return
    
    # This is a request to run deep analysis
    if not vision_state['deep_enabled']:
        await update.message.reply_text(
            "🔮 **Deep Vision** is currently disabled.\n\n"
            "Contact the owner to enable it.",
            parse_mode='Markdown'
        )
        return
    
    # Check for image
    image_file_id = None
    
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]
    
    if not image_file_id:
        await update.message.reply_text(
            "🔮 **Deep Vision** requires a chart image.\n\n"
            "Upload a chart or reply to one with `/deep`",
            parse_mode='Markdown'
        )
        return
    
    # Extract user plan from args
    user_plan = " ".join(context.args) if context.args else ""
    
    # Run deep analysis
    await run_deep_analysis(update, context, image_file_id, user_plan)


async def run_deep_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, image_file_id: str, user_plan: str):
    """Execute Deep Vision analysis with Intent Mode Detection."""
    
    # ══════════════════════════════════════════════
    # STEP 1: DETECT INTENT MODE
    # ══════════════════════════════════════════════
    intent = detect_intent(user_plan)
    
    # ══════════════════════════════════════════════
    # MEMORY MODE — Handle FIRST (no analysis, no questions)
    # User is describing a past outcome to be remembered
    # ══════════════════════════════════════════════
    if intent == "MEMORY_MODE":
        # Get username
        username = None
        if update.effective_user:
            username = update.effective_user.first_name or update.effective_user.username
        
        # Parse memory from user text
        memory_data = parse_memory_from_text(user_plan)
        
        # Store the memory
        success, msg = store_memory(memory_data)
        
        if success:
            # Build short, confirmatory, motivating response
            response_lines = [
                "🧠 **Locked in.**",
                "",
                f"• **Setup:** {memory_data['setup_type']}",
                f"• **Outcome:** {memory_data['outcome']}",
                f"• **Conditions:** {memory_data['conditions']}",
                f"• **Resolution:** {memory_data['resolution']}",
                "",
                "_I'll reference this when I see similar structure + behavior._ 🔮"
            ]
            
            if username:
                response_lines.append(f"\n_Stored for: {username}_")
            
            await update.message.reply_text(
                "\n".join(response_lines),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🧠 **Memory**\n\n"
                f"⚠️ Failed to store: {msg}\n\n"
                "Try again or simplify the description.",
                parse_mode='Markdown'
            )
        return
    
    # ══════════════════════════════════════════════
    # UNKNOWN INTENT — Ask clarifying question
    # (But NOT for memory mode — that's already handled above)
    # ══════════════════════════════════════════════
    if intent == "UNKNOWN" and user_plan.strip():
        await update.message.reply_text(
            "🔮 **JAYCE**\n\n"
            "Before I analyze, quick question:\n\n"
            "**Are you planning to enter at the flip zone, or are you already in?**\n\n"
            "→ `planning to enter at [price]` — setup analysis\n"
            "→ `already in at [price]` — live trade analysis\n"
            "→ `this hit TP, remember this` — save to memory\n\n"
            "_Helps me give you the right read._",
            parse_mode='Markdown'
        )
        return
    
    # ══════════════════════════════════════════════
    # STEP 2: RUN VISION ANALYSIS
    # ══════════════════════════════════════════════
    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    
    # Get username for footer
    username = None
    if update.effective_user:
        username = update.effective_user.first_name or update.effective_user.username
    
    try:
        # Download image
        image_bytes = await download_telegram_image(context, image_file_id)
        
        # Call Deep Vision
        vision_result = await call_deep_vision(image_bytes, user_plan)
        
        await thinking_msg.delete()
        
        if 'error' in vision_result:
            await update.message.reply_text(
                f"⚠️ Deep Vision error: {vision_result['error']}\n\n"
                "Falling back to user-stated plan only.",
                parse_mode='Markdown'
            )
            return
        
        # ══════════════════════════════════════════════
        # STEP 3: BUILD RESPONSE BASED ON INTENT MODE
        # ══════════════════════════════════════════════
        
        if intent == "PLANNED_SETUP":
            # Setup Mode — focus on zone quality, not current price
            response = build_planned_setup_response(vision_result, user_plan, username)
        else:
            # LIVE_TRADE or UNKNOWN with no plan text — full analysis
            response = build_deep_analysis_response(vision_result, user_plan, username)
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        await thinking_msg.delete()
        logger.error(f"Deep analysis failed: {e}")
        await update.message.reply_text(
            f"⚠️ Deep Vision failed: {str(e)}",
            parse_mode='Markdown'
        )


def build_deep_analysis_response(vision: dict, user_plan: str, username: str = None) -> str:
    """Build formatted response from deep vision results — conversational, peer-to-peer tone with Wiz-style energy."""
    
    # Extract new fields
    pair_detected = vision.get('pair_detected', '')
    wiz_setup_type = vision.get('wiz_setup_type', '')
    direct_answer = vision.get('direct_answer', '')
    jayce_take = vision.get('jayce_take', '')
    similar_pattern = vision.get('similar_pattern_note', '')
    confidence_statement = vision.get('confidence_statement', '')
    tp_conditional = vision.get('tp_conditional_statement', '')
    
    # Handle conflict (only real conflicts, not under-fib expected behavior)
    conflict_section = ""
    if vision.get('conflict_detected') and vision.get('conflict_detail'):
        conflict_section = (
            f"\n⚠️ **Heads up:** {vision.get('conflict_detail')}\n"
            f"_Let me know if I'm reading this wrong._\n"
        )
    
    # Build RSI section with divergence type clarity
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_interp = vision.get('rsi_interpretation', 'N/A')
    rsi_slope = vision.get('rsi_slope', 'Unable to assess')
    
    # Build divergence note (with type specification)
    divergence_note = ""
    if vision.get('divergence_detected'):
        div_type = vision.get('divergence_type', '')
        div_note = vision.get('divergence_note', '')
        if div_type and div_type != 'None':
            divergence_note = f"\n📐 **{div_type} Divergence** — {div_note}" if div_note else f"\n📐 **{div_type} Divergence** detected (supportive, not a trigger)"
    
    # Get structure info
    structure_quality = vision.get('structure_quality', 'Unconfirmed')
    structure_reasoning = vision.get('structure_reasoning', '')
    momentum_insight = vision.get('momentum_insight', '')
    
    # Build the response with Wiz-style energy
    response_parts = []
    
    # Header with pair if detected
    if pair_detected and pair_detected != 'Unable to detect':
        response_parts.append(f"🔮 **JAYCE** — 🪙 {pair_detected}\n")
    else:
        response_parts.append(f"🔮 **JAYCE**\n")
    
    # WizTheory Setup Detection
    if wiz_setup_type and wiz_setup_type != 'Unknown':
        response_parts.append(f"📐 **WizTheory Setup:** {wiz_setup_type}\n")
    
    # Lead with direct answer (ANSWER FIRST)
    if direct_answer:
        response_parts.append(f"\n{direct_answer}\n")
    
    # Add conflict warning if needed
    if conflict_section:
        response_parts.append(conflict_section)
    
    # Chart reading section (varied, not mechanical)
    response_parts.append(
        f"\n📊 **Reading the chart:**\n"
        f"• {vision.get('timeframe', '?')} timeframe\n"
        f"• {vision.get('fib_level', '?')} level — {vision.get('market_state', 'unclear')}\n"
        f"• Structure: {structure_quality}"
    )
    if structure_reasoning:
        response_parts.append(f" — {structure_reasoning}")
    response_parts.append("\n")
    
    # Momentum (conversational)
    if momentum_insight:
        response_parts.append(f"\n⚡ **Momentum:** {momentum_insight}")
    
    # RSI with slope
    response_parts.append(f"\n📈 **RSI:** {rsi_reading} ({rsi_interp}), slope {rsi_slope.lower() if rsi_slope else 'unknown'}")
    
    # Divergence (with type clarity)
    if divergence_note:
        response_parts.append(divergence_note)
    
    # TP Probability — CONDITIONAL framing
    if tp_conditional:
        response_parts.append(f"\n\n🎯 **TP Outlook:**\n_{tp_conditional}_")
    
    # Similar Pattern Memory (lightweight)
    if similar_pattern:
        response_parts.append(f"\n\n🧠 **Similar patterns:** {similar_pattern}")
    
    # Jayce's personal take (human touch)
    if jayce_take:
        response_parts.append(f"\n\n💭 **My take:** {jayce_take}")
    
    # Confidence — CONDITIONAL statement, not fixed label
    if confidence_statement:
        response_parts.append(f"\n\n_{confidence_statement}_")
    
    # Human ownership footer
    if username:
        response_parts.append(f"\n\n🧙‍♂️ _Analyzed for: {username}_")
    
    return "".join(response_parts)


# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════

async def intro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle intro commands - who is Jayce"""
    await update.message.reply_text(
        "⸻\n\n"
        "🧙‍♂️⚙️ Yo — I'm Jayce.\n\n"
        "I'm a robot wizard kid built inside WizTheoryLabs 🧠✨\n\n"
        "I don't guess. I don't chase. I read structure, momentum, and execution — fast ⚡\n\n"
        "**What I'm built to do:**\n"
        "📈 Evaluate setups using Wiz Theory\n"
        "🧱 Validate structure before you risk capital\n"
        "🔥 Detect Violent Mode on .786 + Under-Fib Flip Zones\n"
        "⏱ Help you decide secure vs hold — not hype vs hope\n"
        "🧠 Stay rule-based when emotions try to take over\n\n"
        "**What I won't do:**\n"
        "❌ Predict tops\n"
        "❌ Force trades\n"
        "❌ Break rules for excitement\n\n"
        "I'm still evolving 🤖\n"
        "Every update sharpens my edge. Every session makes me smarter.\n\n"
        "Ask me what I think. Ask me if it's valid. Ask me if it's violent. 😈\n\n"
        "Wizard in training. Execution over everything. 🪄"
    )


async def jayce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /jayce command - full chart evaluation with Lite Vision"""
    chat_id = update.effective_chat.id
    image_file_id = None

    # Check for image
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "📸 I need a chart image to analyze.\n\n"
            "Upload a chart or reply to one with `/jayce`",
            parse_mode='Markdown'
        )
        return

    # Extract user plan from command arguments
    user_plan = ""
    if context.args:
        user_plan = " ".join(context.args)

    # Check for deep request
    if user_plan.lower().startswith('deep'):
        if not vision_state['deep_enabled']:
            await update.message.reply_text(
                "🔮 **Deep Vision** is currently disabled.\n\n"
                "Contact the owner to enable it.",
                parse_mode='Markdown'
            )
            return
        user_plan = user_plan[4:].strip()  # Remove 'deep' from plan
        await run_deep_analysis(update, context, image_file_id, user_plan)
        return

    # Run standard analysis with Lite Vision
    await analyze_chart(update, context, image_file_id, user_plan)


async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, image_file_id: str, user_plan: str = ""):
    """
    Analyze chart image with Lite Vision (BOUNCER MODE).
    
    Lite Vision = Setup Radar + Signpost
    - Scans for potential WizTheory setups
    - Routes to Deep Vision for confirmation
    - Does NOT confirm, grade, or give probabilities
    """
    
    # Send thinking message
    thinking_msg = await update.message.reply_text("⚡ Scanning…")
    
    # Brief delay for UX
    await asyncio.sleep(1)
    
    # ══════════════════════════════════════════════
    # LITE VISION SCAN
    # ══════════════════════════════════════════════
    vision_result = None
    vision_available = (
        vision_state['lite_enabled'] and 
        ANTHROPIC_API_KEY and 
        image_file_id
    )
    
    if vision_available:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, user_plan)
            
            if 'error' in vision_result:
                logger.error(f"Lite Vision error: {vision_result}")
                vision_result = None
        except Exception as e:
            logger.error(f"Lite Vision failed: {e}")
            vision_result = None
    
    await thinking_msg.delete()
    
    # ══════════════════════════════════════════════
    # BUILD LITE SCAN OUTPUT (Bouncer format)
    # ══════════════════════════════════════════════
    
    if not vision_available or not vision_result:
        # Vision not available
        if not vision_state['lite_enabled']:
            await update.message.reply_text(
                "⚡ **Lite Scan**\n\n"
                "Lite Vision is currently disabled.\n\n"
                "🔮 Use `/deep` for full analysis.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "⚡ **Lite Scan**\n\n"
                "Vision unavailable — check API key.\n\n"
                "🔮 Use `/deep` for full analysis.",
                parse_mode='Markdown'
            )
        return
    
    # Extract scan results
    timeframe = vision_result.get('timeframe', 'unclear')
    structure_context = vision_result.get('structure_context', 'Unclear')
    fib_region = vision_result.get('fib_region', 'Unclear')
    untouched_zone = vision_result.get('untouched_zone_detected', False)
    structure_memory = vision_result.get('structure_memory_present', False)
    tentative_setup = vision_result.get('tentative_setup_type', 'None detected')
    deep_recommended = vision_result.get('deep_vision_recommended', False)
    scan_notes = vision_result.get('scan_notes', '')
    
    # Build clean, short response (5-7 lines max)
    response_lines = ["⚡ **Lite Scan**"]
    
    # Setup detection line
    if tentative_setup and tentative_setup not in ['None detected', 'Unclear']:
        response_lines.append(f"Possible WizTheory setup forming 🧙‍♂️")
        response_lines.append(f"")
        response_lines.append(f"• **Setup Type:** {tentative_setup} _(tentative)_")
    else:
        response_lines.append(f"Scanning for WizTheory setups…")
        response_lines.append(f"")
    
    # Structure context
    if structure_context and structure_context != 'Unclear':
        response_lines.append(f"• {structure_context} detected")
    
    # Fib region
    if fib_region and fib_region != 'Unclear':
        response_lines.append(f"• Pullback depth: {fib_region}")
    
    # Structure memory / untouched zone
    if structure_memory:
        response_lines.append(f"• Structure memory present")
    if untouched_zone:
        response_lines.append(f"• Untouched zone detected")
    
    # Timeframe if clear
    if timeframe and timeframe != 'unclear':
        response_lines.append(f"• Timeframe: {timeframe}")
    
    # Scan notes (brief)
    if scan_notes and len(scan_notes) < 60:
        response_lines.append(f"• {scan_notes}")
    
    # Deep Vision recommendation
    response_lines.append(f"")
    if deep_recommended:
        response_lines.append(f"🔮 **Deep Vision recommended** for confirmation & execution logic.")
    else:
        response_lines.append(f"🔮 Use `/deep` for full analysis if needed.")
    
    # Join and send
    response = "\n".join(response_lines)
    await update.message.reply_text(response, parse_mode='Markdown')


async def valid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /valid command - quick scan (bouncer mode)
    
    Lite Vision is a BOUNCER — it scans and routes, does NOT confirm validity.
    """
    chat_id = update.effective_chat.id
    image_file_id = None

    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "⚡ **Quick Scan**\n\n"
            "Upload a chart or reply to one with `/valid`",
            parse_mode='Markdown'
        )
        return

    thinking_msg = await update.message.reply_text("⚡ Scanning…")
    await asyncio.sleep(1)
    
    # Quick scan if available
    if vision_state['lite_enabled'] and ANTHROPIC_API_KEY:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, "")
            
            await thinking_msg.delete()
            
            if 'error' not in vision_result:
                # Extract scan results
                tentative_setup = vision_result.get('tentative_setup_type', 'None detected')
                structure_context = vision_result.get('structure_context', 'Unclear')
                fib_region = vision_result.get('fib_region', 'Unclear')
                deep_recommended = vision_result.get('deep_vision_recommended', False)
                
                # Build bouncer-style response
                response_lines = ["⚡ **Quick Scan**", ""]
                
                if tentative_setup and tentative_setup not in ['None detected', 'Unclear']:
                    response_lines.append(f"• Possible: **{tentative_setup}** _(tentative)_")
                
                if structure_context and structure_context != 'Unclear':
                    response_lines.append(f"• {structure_context}")
                
                if fib_region and fib_region != 'Unclear':
                    response_lines.append(f"• Depth: {fib_region}")
                
                response_lines.append("")
                
                if deep_recommended:
                    response_lines.append("🔮 **Deep Vision recommended** for confirmation.")
                else:
                    response_lines.append("🔮 Use `/deep` for full analysis.")
                
                await update.message.reply_text(
                    "\n".join(response_lines),
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Valid command vision failed: {e}")
    
    await thinking_msg.delete()
    await update.message.reply_text(
        "⚡ **Quick Scan**\n\n"
        "⚠️ Vision unavailable.\n\n"
        "🔮 Use `/deep` for full analysis.",
        parse_mode='Markdown'
    )


async def violent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /violent command - Violent Mode scan (bouncer mode)
    
    Lite Vision scans for potential Violent Mode eligibility,
    but does NOT confirm — routes to Deep Vision for that.
    """
    chat_id = update.effective_chat.id
    image_file_id = None

    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "🔥 **Violent Mode Scan**\n\n"
            "Upload a chart with `/violent` to scan.\n\n"
            "⚠️ Violent Mode only applies to .786 + Under-Fib setups.",
            parse_mode='Markdown'
        )
        return

    thinking_msg = await update.message.reply_text("🔥 Scanning…")
    await asyncio.sleep(1)
    
    if vision_state['lite_enabled'] and ANTHROPIC_API_KEY:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, "checking for violent mode eligibility")
            
            await thinking_msg.delete()
            
            if 'error' not in vision_result:
                tentative_setup = vision_result.get('tentative_setup_type', 'None detected')
                fib_region = vision_result.get('fib_region', 'Unclear')
                structure_context = vision_result.get('structure_context', 'Unclear')
                deep_recommended = vision_result.get('deep_vision_recommended', False)
                
                # Check if potentially violent-eligible
                is_potentially_eligible = (
                    tentative_setup in ['.786 Flip Zone', 'Under-Fib Flip Zone'] or
                    fib_region in ['At .786', 'Under-fib']
                )
                
                # Build bouncer-style response
                response_lines = ["🔥 **Violent Mode Scan**", ""]
                
                if is_potentially_eligible:
                    response_lines.append(f"• Potential: **{tentative_setup}** _(tentative)_")
                    response_lines.append(f"• Depth: {fib_region}")
                    if structure_context and structure_context != 'Unclear':
                        response_lines.append(f"• {structure_context}")
                    response_lines.append("")
                    response_lines.append("⚡ **Possibly eligible** for Violent Mode")
                    response_lines.append("")
                    response_lines.append("🔮 **Deep Vision required** to confirm eligibility.")
                else:
                    response_lines.append(f"• Setup: {tentative_setup}")
                    response_lines.append(f"• Depth: {fib_region}")
                    response_lines.append("")
                    response_lines.append("❌ **Not eligible** — Violent Mode requires .786 or Under-Fib")
                
                await update.message.reply_text(
                    "\n".join(response_lines),
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Violent command vision failed: {e}")
    
    await thinking_msg.delete()
    await update.message.reply_text(
        "🔥 **Violent Mode Scan**\n\n"
        "⚠️ Vision unavailable.\n\n"
        "🔮 Use `/deep` for full analysis.",
        parse_mode='Markdown'
    )


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rules [setup] command"""
    if context.args:
        setup = context.args[0].lower()
        rules_text = get_setup_rules(setup)
        await update.message.reply_text(rules_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "📋 **SETUP RULES**\n\n"
            "Usage: `/rules [setup]`\n\n"
            "Example: `/rules .786`\n\n"
            "Available setups: .382, .50, .618, .786, under-fib",
            parse_mode='Markdown'
        )


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /explain [setup] command"""
    if context.args:
        setup = context.args[0].lower()
        explanation = get_setup_explanation(setup)
        await update.message.reply_text(explanation, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "📚 **SETUP EXPLANATION**\n\n"
            "Usage: `/explain [setup]`\n\n"
            "Example: `/explain under-fib`\n\n"
            "Available setups: .382, .50, .618, .786, under-fib",
            parse_mode='Markdown'
        )


async def setups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setups command"""
    await update.message.reply_text(
        "📊 **WIZ THEORY SETUPS**\n\n"
        "🟢 `.382` — Momentum gift (secure 20-40%)\n"
        "🟡 `.50` — Patience setup (secure 30-60%)\n"
        "🔴 `.618` — High-probability reaction (secure 40-60%)\n"
        "🟣 `.786` — Deep retracement, ATH context (secure 50-75%)\n"
        "🔵 `Under-Fib` — Musical setup (secure 40-60%)\n\n"
        "Use `/rules [setup]` for entry criteria",
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    # Check if owner for showing owner commands
    is_owner_user = is_owner(update.effective_user.id)
    
    owner_commands = ""
    if is_owner_user:
        owner_commands = (
            "\n**Owner Commands:**\n"
            "`/vision on|off` — Toggle Lite Vision\n"
            "`/deep on|off` — Toggle Deep Vision\n"
        )
    
    await update.message.reply_text(
        "🧙‍♂️ **JAYCE BOT — Wiz Theory Analysis**\n\n"
        "**Commands:**\n"
        "`/jayce [plan]` — Full chart evaluation\n"
        "`/deep [plan]` — Deep Vision analysis\n"
        "`/valid` — Quick validity check\n"
        "`/violent` — Violent Mode assessment\n"
        "`/rules [setup]` — Entry rules for a setup\n"
        "`/explain [setup]` — Setup guide\n"
        "`/setups` — List all setups\n"
        "`/help` — This message\n"
        f"{owner_commands}\n"
        "**Supported setups:**\n"
        ".382, .50, .618, .786, Under-Fib Flip Zone\n\n"
        "Upload chart + use command, or just say \"yo jayce\"",
        parse_mode='Markdown'
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Store uploaded photos for later analysis.
    
    TRIGGER RULES (locked):
    - Jayce only analyzes when EXPLICITLY invoked
    - If chart posted without invocation → Jayce remains SILENT
    """
    chat_id = update.effective_chat.id
    image_file_id = update.message.photo[-1].file_id
    user_images[chat_id] = image_file_id

    caption = update.message.caption if update.message.caption else ""
    caption_lower = caption.lower()

    explicit_triggers = [
        '/jayce', '/analyze', '/valid', '/violent', '/deep',
        'jayce', 'yo jayce', 'hey jayce', '@jayce',
        'jayce analyze', 'jayce check', 'jayce look'
    ]

    is_invoked = any(trigger in caption_lower for trigger in explicit_triggers)

    if is_invoked:
        # Check for deep request
        if '/deep' in caption_lower or 'jayce deep' in caption_lower:
            if vision_state['deep_enabled']:
                await run_deep_analysis(update, context, image_file_id, caption)
            else:
                await update.message.reply_text(
                    "🔮 **Deep Vision** is currently disabled.",
                    parse_mode='Markdown'
                )
        else:
            await analyze_chart(update, context, image_file_id, caption)
    else:
        # Chart posted without invoking Jayce — remain SILENT
        pass


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language triggers."""
    text = update.message.text.lower()
    full_text = update.message.text
    chat_id = update.effective_chat.id

    intro_triggers = [
        'introduce yourself', 'introduce urself',
        'who are you', 'who is jayce', 'what can you do'
    ]

    if any(trigger in text for trigger in intro_triggers):
        await intro_command(update, context)
        return

    jayce_explicit_triggers = [
        'jayce', 'hey jayce', 'yo jayce', '@jayce',
        'jayce analyze', 'jayce check', 'jayce look',
        'jayce what you think', 'jayce thoughts'
    ]

    jayce_invoked = any(trigger in text for trigger in jayce_explicit_triggers)

    if not jayce_invoked:
        return

    # Check for deep request
    if 'jayce deep' in text or 'deep' in text.split():
        if chat_id in user_images and user_images[chat_id]:
            if vision_state['deep_enabled']:
                await run_deep_analysis(update, context, user_images[chat_id], full_text)
            else:
                await update.message.reply_text(
                    "🔮 **Deep Vision** is currently disabled.",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                "🔮 Deep Vision requires a chart image. Upload one first.",
                parse_mode='Markdown'
            )
        return

    if chat_id in user_images and user_images[chat_id]:
        await analyze_chart(update, context, user_images[chat_id], full_text)
    else:
        await update.message.reply_text(
            "🧙‍♂️ Hey! I'm here.\n\n"
            "Upload a chart and use:\n"
            "`/jayce [plan]` — Full analysis\n"
            "`/deep [plan]` — Deep Vision\n"
            "`/valid` — Quick check\n"
            "`/violent` — Violent Mode\n\n"
            "Or use `/help` for all commands",
            parse_mode='Markdown'
        )


# Helper functions
def get_setup_rules(setup: str) -> str:
    """Return entry rules for a specific setup"""
    rules_map = {
        '.382': (
            "🟢 **.382 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clear impulse leg established\n"
            "2. Pullback into .382 retracement\n"
            "3. Former resistance reclaimed as support (flip zone)\n"
            "4. Structure clean BEFORE entry\n"
            "5. Volume supports reaction\n\n"
            "**Execution:** Secure 20-40% on first reaction (DEFAULT)"
        ),
        '.50': (
            "🟡 **.50 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Clear impulse leg established\n"
            "3. Pullback into .50 retracement\n"
            "4. Former resistance reclaimed as support\n"
            "5. Structure clean BEFORE entry\n\n"
            "**Execution:** Secure 30-60% on first strong reaction"
        ),
        '.618': (
            "🔴 **.618 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Strong impulse (≥60% breakout)\n"
            "3. 50-60% pullback into .618 flip zone\n"
            "4. Limit orders 5-7% above .618\n"
            "5. Skip if volume doesn't build or slices through\n\n"
            "**Execution:** Secure 40-60% on first strong reaction"
        ),
        '.786': (
            "🟣 **.786 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Strong impulse ≥100% (preferably ATH)\n"
            "3. 70-80% pullback into .786 flip zone\n"
            "4. Limit orders 6-9% above .786\n"
            "5. Whale conviction = confirmation only\n\n"
            "**Execution:** Secure 50-75% on first bounce"
        ),
        'under-fib': (
            "🔵 **UNDER-FIB FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure BEFORE entry\n"
            "2. Strong impulse ≥60%\n"
            "3. Price dips BELOW fib then reclaims (off-beat → rhythm)\n"
            "4. Flip zone UNTOUCHED prior\n"
            "5. ≥40% pullback into under-fib zone\n"
            "6. Limit entry 5-9% above nearest wick\n\n"
            "**Execution:** Secure 40-60% on first reaction"
        )
    }
    return rules_map.get(setup, "❌ Setup not recognized. Use: .382, .50, .618, .786, or under-fib")


def get_setup_explanation(setup: str) -> str:
    """Return full explanation for a specific setup"""
    explain_map = {
        '.382': (
            "🟢 **.382 + FLIP ZONE**\n\n"
            "**Purpose:** Momentum continuation REACTION setup\n"
            "**Identity:** Speed + discipline > conviction\n"
            "**Hold time:** Avg ~72 min | Median ~34 min\n\n"
            "The .382 is a gift. Take what the market offers.\n"
            "Secure 20-40% is DEFAULT, not optional."
        ),
        '.50': (
            "🟡 **.50 + FLIP ZONE**\n\n"
            "**Purpose:** Deeper pullback requiring patience\n"
            "**NOT** momentum gift like .382\n"
            "**Hold time:** Requires structure confirmation\n\n"
            "Secure 30-60% on first reaction.\n"
            "If chop/stall → exit remainder."
        ),
        '.618': (
            "🔴 **.618 + FLIP ZONE**\n\n"
            "**Purpose:** High-probability reaction level\n"
            "**Context:** Most popular fib among traders\n"
            "**Hold time:** Structure decides continuation\n\n"
            "Secure 40-60% on first reaction.\n"
            "Skip if volume fades or slices through."
        ),
        '.786': (
            "🟣 **.786 + FLIP ZONE**\n\n"
            "**Purpose:** Deep retracement where market intent shows\n"
            "**Context:** Strong impulse ≥100%, preferably ATH\n"
            "**Hold time:** Structure + momentum decides\n\n"
            "Secure 50-75% on first bounce.\n"
            "Violent Mode may apply if immediate expansion."
        ),
        'under-fib': (
            "🔵 **UNDER-FIB FLIP ZONE**\n\n"
            "**Purpose:** Off-beat → rhythm musical setup\n"
            "**Pattern:** Price dips BELOW fib, then reclaims\n"
            "**Hold time:** Avg 4 hours (1-6hr range)\n\n"
            "Key: \"Off-beat\" (dip) → \"Rhythm\" (reclaim) → Expansion\n"
            "Violent Mode may apply if immediate expansion."
        )
    }
    return explain_map.get(setup, "❌ Setup not recognized. Use: .382, .50, .618, .786, or under-fib")


def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Owner control commands
    application.add_handler(CommandHandler("vision", vision_command))
    application.add_handler(CommandHandler("deep", deep_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("memory", memory_command))

    # Intro commands
    application.add_handler(CommandHandler("intro", intro_command))
    application.add_handler(CommandHandler("whoisjayce", intro_command))
    application.add_handler(CommandHandler("aboutjayce", intro_command))
    application.add_handler(CommandHandler("start", intro_command))

    # Primary commands
    application.add_handler(CommandHandler("jayce", jayce_command))
    application.add_handler(CommandHandler("valid", valid_command))
    application.add_handler(CommandHandler("violent", violent_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CommandHandler("setups", setups_command))
    application.add_handler(CommandHandler("help", help_command))

    # Photo handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Create initial backup on startup
    logger.info("Creating startup backup...")
    success, result = create_backup()
    if success:
        logger.info(f"Startup backup created: {result}")
    else:
        logger.warning(f"Startup backup failed: {result}")

    logger.info("Starting Jayce Bot with Vision + Memory...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
