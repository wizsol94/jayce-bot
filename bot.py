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
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # For auto-backup to GitHub

# GitHub backup config
GITHUB_REPO = "wizsol94/jayce-bot"
GITHUB_BACKUP_PATH = "backups/jayce_training_dataset.json"

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

# ══════════════════════════════════════════════
# VISION STATE (Owner-controlled)
# ══════════════════════════════════════════════
# These flags control whether vision features are enabled
# Only the owner can toggle these via /vision and /deep commands
vision_state = {
    'lite_enabled': False,  # Lite Vision DISABLED during training mode setup
    'deep_enabled': True,   # Deep Vision ON 24/7 (owner can pause with /deep off)
}

# ══════════════════════════════════════════════
# TRAINING MODE GUARD
# ══════════════════════════════════════════════
# When training mode is active for a chat, ALL other handlers are blocked
# This prevents /train from triggering analysis, scans, intro, etc.

TRAINING_QUIET_MODE = True  # Default: training responses are minimal
training_active = {}  # chat_id -> bool (True if training in progress)

def is_training_active(chat_id: int) -> bool:
    """Check if training mode is active for this chat."""
    return training_active.get(chat_id, False)

def set_training_mode(chat_id: int, active: bool):
    """Set training mode for a chat."""
    training_active[chat_id] = active
    if active:
        logger.info(f"[TRAINING] Training mode ACTIVE for chat {chat_id}")
    else:
        logger.info(f"[TRAINING] Training mode ENDED for chat {chat_id}")

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
# SETUP CANONICALIZER — Normalize all setup names
# ══════════════════════════════════════════════
# Ensures "618 flip zone", "618 + flip zone", "0.618 flipzone" all resolve to same setup

# Canonical setup definitions
# Format: canonical_key -> (display_name, [aliases])
SETUP_DEFINITIONS = {
    '382_flip_zone': {
        'display': '382 + Flip Zone',
        'aliases': [
            '382 flip zone', '382 + flip zone', '0.382 flip zone', '.382 flip zone',
            '382 flipzone', '382 fz', '382+fz', '382 + fz', '382+flip zone', '.382 fz',
            '382', '.382', '0.382',
            'three eighty two flip zone', 'three eighty two fz'
        ]
    },
    '50_flip_zone': {
        'display': '50 + Flip Zone',
        'aliases': [
            '50 flip zone', '50 + flip zone', '0.50 flip zone', '.50 flip zone',
            '50 flipzone', '50 fz', '50+fz', '50 + fz', '50+flip zone', '.50 fz',
            '50', '.50', '0.50', '.5', '0.5',
            '0.5 flip zone', '.5 flip zone', '0.5 flipzone', '.5 flipzone',
            '0.5 fz', '.5 fz',
            'half flip zone', 'half flipzone', 'half fz'
        ]
    },
    '618_flip_zone': {
        'display': '618 + Flip Zone',
        'aliases': [
            '618 flip zone', '618 + flip zone', '0.618 flip zone', '.618 flip zone',
            '618 flipzone', '618 fz', '618+fz', '618 + fz', '618+flip zone', '.618 fz',
            '618', '.618', '0.618',
            'six eighteen flip zone', 'six eighteen fz'
        ]
    },
    '786_flip_zone': {
        'display': '786 + Flip Zone',
        'aliases': [
            '786 flip zone', '786 + flip zone', '0.786 flip zone', '.786 flip zone',
            '786 flipzone', '786 fz', '786+fz', '786 + fz', '786+flip zone', '.786 fz',
            '786', '.786', '0.786',
            'seven eighty six flip zone', 'seven eighty six fz'
        ]
    },
    'under_fib_flip_zone': {
        'display': 'Under-Fib Flip Zone',
        'aliases': [
            # Standard variations
            'under fib flip zone', 'under-fib flip zone', 'underfib flip zone',
            'under fib flipzone', 'under-fib flipzone', 'underfib flipzone',
            'under fib fz', 'under-fib fz', 'underfib fz',
            'under fib fzone', 'under-fib fzone', 'underfib fzone',
            'under fib flip', 'under-fib flip', 'underfib flip',
            'under fib zone', 'under-fib zone', 'underfib zone',
            # Reclaim variations
            'under fib fz reclaim', 'under-fib fz reclaim', 'underfib fz reclaim',
            'under fib reclaim', 'under-fib reclaim', 'underfib reclaim',
            'under fib flip zone reclaim', 'under-fib flip zone reclaim',
            # Standalone
            'under fib', 'under-fib', 'underfib',
            # Below fib variations
            'below fib flip zone', 'below fib flipzone', 'below fib fz',
            'below fib zone', 'below fib reclaim', 'below fib',
            # Under the fib variations
            'under the fib flip zone', 'under the fib flipzone', 'under the fib fz',
            'under the fib zone', 'under the fib reclaim', 'under the fib'
        ]
    },
}

def normalize_setup_text(text: str) -> str:
    """
    Step 1-4 of normalization:
    1. Convert to lowercase
    2. Remove punctuation and symbols (+ - _ / , . :) but keep digits
    3. Collapse extra whitespace
    4. Normalize synonyms (flipzone -> flip zone, fz -> flip zone, underfib -> under fib)
    """
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Replace common separators with spaces
    text = re.sub(r'[+\-_/,.:]+', ' ', text)
    
    # Remove other punctuation but keep digits and letters
    text = re.sub(r'[^\w\s]', '', text)
    
    # Collapse whitespace
    text = ' '.join(text.split())
    
    # ══════════════════════════════════════════════
    # SYNONYM NORMALIZATION
    # ══════════════════════════════════════════════
    
    # Flip zone synonyms
    text = text.replace('flipzone', 'flip zone')
    text = text.replace('fzone', 'flip zone')
    text = text.replace(' fz ', ' flip zone ')
    text = text.replace(' fz', ' flip zone') if text.endswith(' fz') else text
    if text.endswith('fz'):
        text = text[:-2] + 'flip zone'
    if text.startswith('fz '):
        text = 'flip zone ' + text[3:]
    
    # Under-fib synonyms
    text = text.replace('underfib', 'under fib')
    text = text.replace('below fib', 'under fib')
    text = text.replace('under the fib', 'under fib')
    
    # Final whitespace cleanup
    text = ' '.join(text.split())
    
    return text.strip()


def canonicalize_setup(user_input: str) -> tuple:
    """
    Main canonicalizer function.
    
    Returns: (canonical_key, display_name) or (None, None) if not recognized
    
    Usage:
        key, display = canonicalize_setup("618 + flip zone")
        # Returns: ('618_flip_zone', '.618 + Flip Zone')
    """
    if not user_input:
        return (None, None)
    
    # Normalize the input
    normalized = normalize_setup_text(user_input)
    
    # Try to match against all aliases
    for canonical_key, setup_data in SETUP_DEFINITIONS.items():
        for alias in setup_data['aliases']:
            normalized_alias = normalize_setup_text(alias)
            if normalized == normalized_alias:
                return (canonical_key, setup_data['display'])
    
    # ══════════════════════════════════════════════
    # FUZZY FALLBACK RULES
    # ══════════════════════════════════════════════
    
    flip_indicators = ['flip zone', 'flip', 'fz', 'zone']
    has_flip = any(ind in normalized for ind in flip_indicators)
    
    # 382 + Flip Zone fallback
    # If input contains ("382" OR ".382" OR "0.382") AND ("flip zone" OR "flipzone" OR "fz")
    if any(x in normalized for x in ['382', '0382']) and has_flip:
        return ('382_flip_zone', SETUP_DEFINITIONS['382_flip_zone']['display'])
    
    # 50 + Flip Zone fallback (special handling for .5 variants and "half")
    # If input contains ("50" OR ".5" OR "0.5" OR ".50" OR "0.50") AND ("flip zone" OR "flipzone" OR "fz" OR "half")
    fifty_indicators = ['50', '05', 'half']  # After normalization, .5 becomes 5, .50 becomes 50
    has_fifty = any(x in normalized for x in fifty_indicators)
    has_half = 'half' in normalized
    if (has_fifty or has_half) and (has_flip or has_half):
        return ('50_flip_zone', SETUP_DEFINITIONS['50_flip_zone']['display'])
    
    # 618 + Flip Zone fallback
    if any(x in normalized for x in ['618', '0618']) and has_flip:
        return ('618_flip_zone', SETUP_DEFINITIONS['618_flip_zone']['display'])
    
    # 786 + Flip Zone fallback
    if any(x in normalized for x in ['786', '0786']) and has_flip:
        return ('786_flip_zone', SETUP_DEFINITIONS['786_flip_zone']['display'])
    
    # ══════════════════════════════════════════════
    # Under-Fib Flip Zone fallback (ENHANCED)
    # If input contains ("under" OR "below") AND "fib"
    # AND contains ("flip zone" OR "flipzone" OR "fz" OR "reclaim" OR "reclaiming")
    # ══════════════════════════════════════════════
    has_under = 'under' in normalized or 'below' in normalized
    has_fib = 'fib' in normalized
    under_fib_indicators = ['flip zone', 'flip', 'fz', 'zone', 'reclaim', 'reclaiming']
    has_under_fib_indicator = any(ind in normalized for ind in under_fib_indicators)
    
    if has_under and has_fib:
        # If has any indicator OR just "under fib" standalone
        if has_under_fib_indicator or normalized in ['under fib', 'below fib']:
            return ('under_fib_flip_zone', SETUP_DEFINITIONS['under_fib_flip_zone']['display'])
    
    # Final fallback: standalone numbers (if user just types "382", "618", etc.)
    standalone_map = {
        '382': '382_flip_zone',
        '50': '50_flip_zone',
        '618': '618_flip_zone',
        '786': '786_flip_zone',
    }
    
    for num, canonical_key in standalone_map.items():
        if num in normalized and len(normalized.replace(num, '').strip()) == 0:
            return (canonical_key, SETUP_DEFINITIONS[canonical_key]['display'])
    
    # Not recognized
    return (None, None)


def get_setup_display_name(canonical_key: str) -> str:
    """Get the clean display name for a canonical key."""
    if canonical_key in SETUP_DEFINITIONS:
        return SETUP_DEFINITIONS[canonical_key]['display']
    return canonical_key  # Fallback to key if not found


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

# ══════════════════════════════════════════════
# PERSISTENT STORAGE — Railway Volume
# ══════════════════════════════════════════════
# All data stored in /data (Railway persistent volume)
# Survives redeploys, restarts, and crashes

import tempfile
import fcntl
from contextlib import contextmanager

DATA_DIR = Path("/data")
MEMORY_FILE = DATA_DIR / "jayce_memory.json"
TRAINING_FILE = DATA_DIR / "jayce_training_dataset.json"
MAX_MEMORIES = 50  # Rolling limit for conversational memory

# Ensure data directory exists
def ensure_data_dir():
    """Create data directory if it doesn't exist."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create data directory: {e}")
        # Fallback to /tmp if /data not available (local dev)
        return False

# Initialize on import
if not DATA_DIR.exists():
    if not ensure_data_dir():
        # Fallback for local development
        DATA_DIR = Path("/tmp/jayce_data")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE = DATA_DIR / "jayce_memory.json"
        TRAINING_FILE = DATA_DIR / "jayce_training_dataset.json"
        logger.warning(f"Using fallback data directory: {DATA_DIR}")


# ══════════════════════════════════════════════
# ATOMIC FILE OPERATIONS — Prevent Corruption
# ══════════════════════════════════════════════

@contextmanager
def file_lock(filepath: Path):
    """
    Context manager for file locking.
    Prevents concurrent writes from corrupting data.
    """
    lock_file = filepath.with_suffix('.lock')
    lock_fd = None
    try:
        # Create lock file if needed
        lock_file.touch(exist_ok=True)
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()


def atomic_write_json(filepath: Path, data: any) -> bool:
    """
    Atomic JSON write: write to temp file, then rename.
    Prevents corruption if bot crashes mid-save.
    """
    try:
        # Write to temp file in same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=filepath.parent,
            prefix=f'.{filepath.stem}_',
            suffix='.tmp'
        )
        
        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename (same filesystem)
            os.replace(temp_path, filepath)
            return True
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
            
    except Exception as e:
        logger.error(f"Atomic write failed for {filepath}: {e}")
        return False


def safe_read_json(filepath: Path, default: any = None) -> any:
    """
    Safe JSON read with lock.
    Returns default if file doesn't exist or is corrupted.
    """
    if default is None:
        default = []
    
    try:
        if not filepath.exists():
            return default
        
        with file_lock(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
                
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {filepath}: {e}")
        return default
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return default


def safe_write_json(filepath: Path, data: any) -> bool:
    """
    Safe JSON write with lock + atomic operation.
    """
    try:
        with file_lock(filepath):
            return atomic_write_json(filepath, data)
    except Exception as e:
        logger.error(f"Safe write failed for {filepath}: {e}")
        return False


# ══════════════════════════════════════════════
# CONVERSATIONAL MEMORY (existing system, now persistent)
# ══════════════════════════════════════════════

def load_memories() -> list:
    """Load stored setup memories."""
    return safe_read_json(MEMORY_FILE, default=[])


def save_memories(memories: list) -> bool:
    """Save memories to file with atomic write."""
    try:
        # Keep only last MAX_MEMORIES
        if len(memories) > MAX_MEMORIES:
            memories = memories[-MAX_MEMORIES:]
        
        return safe_write_json(MEMORY_FILE, memories)
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


# ══════════════════════════════════════════════
# STRUCTURED TRAINING SYSTEM — Phase 2
# ══════════════════════════════════════════════
# Dataset-driven training with unique chart IDs,
# structured fields, and duplicate detection.

# Setup code mappings for chart IDs
SETUP_CODES = {
    '382_flip_zone': '382FZ',
    '50_flip_zone': '50FZ',
    '618_flip_zone': '618FZ',
    '786_flip_zone': '786FZ',
    'under_fib_flip_zone': 'UFIB',
}

def generate_chart_id(setup_key: str, token: str, timeframe: str) -> str:
    """
    Generate unique chart ID in format: SETUP-TOKEN-TIMEFRAME-DATE-INDEX
    Example: 618FZ-SOL-15M-20250222-001
    """
    setup_code = SETUP_CODES.get(setup_key, 'UNK')
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Get current index for this setup+date
    training_data = load_training_data()
    
    # Count existing charts for this setup on this date
    prefix = f"{setup_code}-{token.upper()}-{timeframe.upper()}-{date_str}"
    existing = [t for t in training_data if t.get('chart_id', '').startswith(prefix)]
    index = len(existing) + 1
    
    return f"{prefix}-{index:03d}"


def load_training_data() -> list:
    """Load structured training dataset."""
    return safe_read_json(TRAINING_FILE, default=[])


def save_training_data(data: list) -> bool:
    """Save training dataset with atomic write."""
    return safe_write_json(TRAINING_FILE, data)


def calculate_similarity(chart1: dict, chart2: dict) -> float:
    """
    Calculate similarity score between two training charts.
    Returns 0.0 to 1.0 (1.0 = identical)
    
    Factors:
    - Same setup type (40%)
    - Same token (20%)
    - Same timeframe (10%)
    - Similar fib_depth (10%)
    - Similar RSI behavior (10%)
    - Same whale conviction (5%)
    - Same violent mode (5%)
    """
    score = 0.0
    
    # Setup type (40%)
    if chart1.get('setup_name') == chart2.get('setup_name'):
        score += 0.40
    
    # Token (20%)
    if chart1.get('token', '').upper() == chart2.get('token', '').upper():
        score += 0.20
    
    # Timeframe (10%)
    if chart1.get('timeframe', '').upper() == chart2.get('timeframe', '').upper():
        score += 0.10
    
    # Fib depth (10%)
    if chart1.get('fib_depth') == chart2.get('fib_depth'):
        score += 0.10
    
    # RSI behavior (10%)
    if chart1.get('rsi_behavior') == chart2.get('rsi_behavior'):
        score += 0.10
    
    # Whale conviction (5%)
    if chart1.get('whale_conviction') == chart2.get('whale_conviction'):
        score += 0.05
    
    # Violent mode (5%)
    if chart1.get('violent_mode') == chart2.get('violent_mode'):
        score += 0.05
    
    return score


def check_duplicate(new_chart: dict, threshold: float = 0.85) -> tuple[bool, dict, float]:
    """
    Check if new chart is a potential duplicate.
    
    Returns: (is_duplicate, most_similar_chart, similarity_score)
    """
    training_data = load_training_data()
    
    if not training_data:
        return False, {}, 0.0
    
    most_similar = None
    highest_score = 0.0
    
    for existing in training_data:
        score = calculate_similarity(new_chart, existing)
        if score > highest_score:
            highest_score = score
            most_similar = existing
    
    is_duplicate = highest_score >= threshold
    return is_duplicate, most_similar or {}, highest_score


# ══════════════════════════════════════════════
# PHASE 3: PATTERN MATCHING ENGINE
# ══════════════════════════════════════════════
# Compares new charts against trained winners
# Provides data-backed confidence and similar chart references

# ══════════════════════════════════════════════
# PHASE 4: CONDITION DETECTION
# ══════════════════════════════════════════════
# Auto-detects conditions from training notes and chart analysis

CONDITION_KEYWORDS = {
    'whale_conviction': [
        'whale conviction', 'whale', 'whale hold', 'whale holding',
        'top holder', 'ansem', 'big holder', 'conviction hold'
    ],
    'clean_structure': [
        'clean structure', 'clean chart', 'clean', 'beautiful structure',
        'great structure', 'super clean', 'textbook'
    ],
    'divergence': [
        'divergence', 'div', 'rsi divergence', 'bullish divergence',
        'hidden divergence', 'divergence present'
    ],
    'high_volume': [
        'high volume', 'volume', 'big volume', 'strong volume',
        'volume spike'
    ],
    'violent': [
        'violent', 'violent expansion', 'violent move', 'explosive'
    ]
}


def detect_conditions_from_text(text: str) -> dict:
    """
    Detect trading conditions from text (notes or chart labels).
    
    Returns: {
        'whale_conviction': bool,
        'clean_structure': bool,
        'divergence': bool,
        'high_volume': bool,
        'violent': bool
    }
    """
    text_lower = text.lower() if text else ''
    
    conditions = {}
    for condition, keywords in CONDITION_KEYWORDS.items():
        conditions[condition] = any(kw in text_lower for kw in keywords)
    
    return conditions


def get_chart_conditions(chart: dict) -> dict:
    """
    Get conditions from a training chart (from notes field).
    """
    notes = chart.get('notes', '')
    return detect_conditions_from_text(notes)


def get_outcome_prediction(setup_name: str, detected_conditions: dict = None) -> dict:
    """
    Phase 4: Generate outcome predictions based on training data and conditions.
    
    Returns: {
        'setup_name': str,
        'total_trades': int,
        'overall_avg': float,
        'overall_best': float,
        'overall_range': (min, max),
        'condition_breakdowns': {
            'whale_conviction': {'avg': float, 'count': int, 'best': float},
            'clean_structure': {'avg': float, 'count': int, 'best': float},
            ...
        },
        'combined_conditions': {'avg': float, 'count': int, 'best': float},
        'detected_conditions': list of condition names present
    }
    """
    training_data = load_training_data()
    
    if not training_data:
        return None
    
    # Filter by setup type
    setup_charts = [t for t in training_data if t.get('setup_name') == setup_name]
    
    if not setup_charts:
        return None
    
    # Get outcomes
    outcomes = [c.get('outcome_percentage', 0) for c in setup_charts if c.get('outcome_percentage', 0) > 0]
    
    if not outcomes:
        return None
    
    # Overall stats
    overall_avg = sum(outcomes) / len(outcomes)
    overall_best = max(outcomes)
    overall_min = min(outcomes)
    overall_max = max(outcomes)
    
    # Condition breakdowns
    condition_breakdowns = {}
    
    for condition in CONDITION_KEYWORDS.keys():
        # Find charts with this condition
        charts_with_condition = []
        for chart in setup_charts:
            chart_conditions = get_chart_conditions(chart)
            if chart_conditions.get(condition, False):
                outcome = chart.get('outcome_percentage', 0)
                if outcome > 0:
                    charts_with_condition.append(outcome)
        
        if charts_with_condition:
            condition_breakdowns[condition] = {
                'avg': sum(charts_with_condition) / len(charts_with_condition),
                'count': len(charts_with_condition),
                'best': max(charts_with_condition)
            }
    
    # Combined conditions (if detected_conditions provided)
    combined_stats = None
    detected_list = []
    
    if detected_conditions:
        # Get list of detected conditions
        detected_list = [k for k, v in detected_conditions.items() if v]
        
        if detected_list:
            # Find charts matching ALL detected conditions
            matching_charts = []
            for chart in setup_charts:
                chart_conditions = get_chart_conditions(chart)
                
                # Check if chart has ALL detected conditions
                has_all = all(chart_conditions.get(cond, False) for cond in detected_list)
                
                if has_all:
                    outcome = chart.get('outcome_percentage', 0)
                    if outcome > 0:
                        matching_charts.append(outcome)
            
            if matching_charts:
                combined_stats = {
                    'avg': sum(matching_charts) / len(matching_charts),
                    'count': len(matching_charts),
                    'best': max(matching_charts),
                    'min': min(matching_charts)
                }
    
    return {
        'setup_name': setup_name,
        'total_trades': len(setup_charts),
        'overall_avg': overall_avg,
        'overall_best': overall_best,
        'overall_range': (overall_min, overall_max),
        'condition_breakdowns': condition_breakdowns,
        'combined_conditions': combined_stats,
        'detected_conditions': detected_list
    }


def build_outcome_prediction_text(prediction_data: dict, detected_conditions: dict = None) -> str:
    """
    Build the outcome prediction text for Deep Vision response.
    """
    if not prediction_data:
        return ""
    
    setup_name = prediction_data.get('setup_name', 'Unknown')
    total_trades = prediction_data.get('total_trades', 0)
    overall_avg = prediction_data.get('overall_avg', 0)
    overall_best = prediction_data.get('overall_best', 0)
    overall_range = prediction_data.get('overall_range', (0, 0))
    condition_breakdowns = prediction_data.get('condition_breakdowns', {})
    combined_stats = prediction_data.get('combined_conditions')
    detected_list = prediction_data.get('detected_conditions', [])
    
    lines = [
        "📊 **Outcome Prediction:**",
        f"\nYour {setup_name} history:",
        ""
    ]
    
    # Overall stats
    lines.append(f"• **All setups:** +{int(overall_avg)}% avg ({total_trades} trades)")
    
    # Condition breakdowns (only show ones with data)
    # NOTE: high_volume removed per user request
    condition_display = {
        'whale_conviction': 'With whale conviction',
        'clean_structure': 'With clean structure',
        'divergence': 'With divergence',
        'violent': 'With violent expansion'
    }
    
    for condition, display_name in condition_display.items():
        if condition in condition_breakdowns:
            stats = condition_breakdowns[condition]
            lines.append(f"• **{display_name}:** +{int(stats['avg'])}% avg ({stats['count']} trades)")
    
    # Combined conditions (if multiple detected)
    if combined_stats and len(detected_list) > 1:
        condition_names = [condition_display.get(c, c).replace('With ', '') for c in detected_list]
        combined_name = " + ".join(condition_names)
        lines.append(f"• **With BOTH ({combined_name}):** +{int(combined_stats['avg'])}% avg ({combined_stats['count']} trades)")
    
    # What THIS setup has
    if detected_list:
        lines.append("")
        condition_tags = []
        for cond in detected_list:
            tag = condition_display.get(cond, cond).replace('With ', '')
            condition_tags.append(f"{tag} ✅")
        lines.append(f"🎯 **This setup has:** {', '.join(condition_tags)}")
    
    # Expected range
    if combined_stats:
        lines.append(f"\n**Expected range:** +{int(combined_stats['min'])}% to +{int(combined_stats['best'])}%")
        lines.append(f"**Best similar outcome:** +{int(combined_stats['best'])}%")
    elif overall_range[0] > 0:
        lines.append(f"\n**Expected range:** +{int(overall_range[0])}% to +{int(overall_range[1])}%")
        lines.append(f"**Best outcome:** +{int(overall_best)}%")
    
    return "\n".join(lines)


def get_pattern_matches(setup_name: str, timeframe: str = None, token: str = None) -> dict:
    """
    Find matching patterns from training data for a given setup.
    
    Returns: {
        'total_matches': int,
        'total_trained': int,
        'match_percentage': float,
        'avg_outcome': float,
        'best_match': dict,
        'best_match_score': float,
        'matches': list of (chart, score) tuples
    }
    """
    training_data = load_training_data()
    
    if not training_data:
        return {
            'total_matches': 0,
            'total_trained': 0,
            'match_percentage': 0,
            'avg_outcome': 0,
            'best_match': None,
            'best_match_score': 0,
            'matches': []
        }
    
    # Filter by setup type first
    setup_charts = [t for t in training_data if t.get('setup_name') == setup_name]
    
    if not setup_charts:
        return {
            'total_matches': 0,
            'total_trained': len(training_data),
            'match_percentage': 0,
            'avg_outcome': 0,
            'best_match': None,
            'best_match_score': 0,
            'matches': []
        }
    
    # Build comparison chart from analysis
    comparison_chart = {
        'setup_name': setup_name,
        'timeframe': timeframe.upper() if timeframe else '',
        'token': token.upper() if token else '',
    }
    
    # Score each trained chart
    matches = []
    for chart in setup_charts:
        score = 0.0
        
        # Setup match (base score since already filtered)
        score += 0.40
        
        # Timeframe match
        if timeframe and chart.get('timeframe', '').upper() == timeframe.upper():
            score += 0.25
        
        # Token match (bonus, not required)
        if token and chart.get('token', '').upper() == token.upper():
            score += 0.15
        
        # Has outcome data (quality indicator)
        if chart.get('outcome_percentage', 0) > 0:
            score += 0.10
        
        # Has notes (more detailed training)
        if chart.get('notes', ''):
            score += 0.10
        
        matches.append((chart, score))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    
    # Calculate stats
    total_matches = len([m for m in matches if m[1] >= 0.50])
    outcomes = [m[0].get('outcome_percentage', 0) for m in matches if m[0].get('outcome_percentage', 0) > 0]
    avg_outcome = sum(outcomes) / len(outcomes) if outcomes else 0
    
    best_match = matches[0][0] if matches else None
    best_match_score = matches[0][1] if matches else 0
    
    return {
        'total_matches': total_matches,
        'total_trained': len(setup_charts),
        'match_percentage': (total_matches / len(setup_charts) * 100) if setup_charts else 0,
        'avg_outcome': avg_outcome,
        'best_match': best_match,
        'best_match_score': best_match_score,
        'matches': matches[:5]  # Top 5 matches
    }


def get_confidence_level(match_percentage: float) -> tuple[str, str]:
    """
    Get confidence level and emoji based on match percentage.
    
    Returns: (confidence_text, emoji)
    """
    if match_percentage >= 80:
        return "High confidence — looks like your winners", "✅"
    elif match_percentage >= 60:
        return "Moderate match — some differences from your winners", "🟡"
    elif match_percentage >= 40:
        return "Low match — doesn't closely resemble trained setups", "⚠️"
    else:
        return "Weak match — limited training data for comparison", "❓"


def build_pattern_match_text(pattern_data: dict) -> str:
    """
    Build the pattern match text for Deep Vision response.
    """
    if not pattern_data or pattern_data['total_trained'] == 0:
        return ""
    
    total_matches = pattern_data['total_matches']
    total_trained = pattern_data['total_trained']
    avg_outcome = pattern_data['avg_outcome']
    best_match = pattern_data['best_match']
    
    # Calculate match percentage
    match_pct = (total_matches / total_trained * 100) if total_trained > 0 else 0
    confidence_text, emoji = get_confidence_level(match_pct)
    
    lines = [
        "🧠 **Pattern Match:**",
        f"• Matches {total_matches} / {total_trained} trained setups",
        f"• Similarity: {int(match_pct)}%",
    ]
    
    if avg_outcome > 0:
        lines.append(f"• Similar winners averaged: +{int(avg_outcome)}%")
    
    if best_match:
        chart_id = best_match.get('chart_id', 'Unknown')
        outcome = best_match.get('outcome_percentage', 0)
        lines.append(f"• Most similar: `{chart_id}` (+{outcome}%)")
    
    lines.append(f"\n{emoji} _{confidence_text}_")
    
    return "\n".join(lines)


async def send_best_match_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, best_match: dict):
    """
    Send the best matching chart image from training data.
    """
    if not best_match:
        return
    
    image_file_id = best_match.get('screenshot_fingerprint_id')
    
    if not image_file_id:
        return
    
    try:
        chart_id = best_match.get('chart_id', 'Unknown')
        setup = best_match.get('setup_name', 'Unknown')
        outcome = best_match.get('outcome_percentage', 0)
        token = best_match.get('token', '?')
        timeframe = best_match.get('timeframe', '?')
        
        caption = (
            f"📸 **Most Similar Winner**\n\n"
            f"`{chart_id}`\n"
            f"{setup} | {token} | {timeframe} | +{outcome}%"
        )
        
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_file_id,
            caption=caption,
            parse_mode='Markdown'
        )
        logger.info(f"[PATTERN MATCH] Sent best match chart: {chart_id}")
        
    except Exception as e:
        logger.error(f"[PATTERN MATCH] Failed to send best match chart: {e}")


def store_training_chart(chart_data: dict) -> tuple[bool, str]:
    """
    Store a training chart in the structured dataset.
    
    Required fields:
    - chart_id: Unique identifier
    - setup_name: WizTheory setup name
    - token: Trading pair
    - timeframe: Chart timeframe
    - date: Date string
    - fib_depth: Fib level
    - structure_state: Structure classification
    - rsi_behavior: RSI description
    - whale_conviction: Boolean
    - violent_mode: Boolean
    - outcome_percentage: Number
    - expansion_time_minutes: Number
    - screenshot_fingerprint_id: Telegram file_id
    - notes: Additional notes
    """
    try:
        training_data = load_training_data()
        
        # Add timestamp
        chart_data['trained_at'] = datetime.now().isoformat()
        
        # Append
        training_data.append(chart_data)
        
        # Save
        if save_training_data(training_data):
            return True, f"Training chart {chart_data.get('chart_id', 'unknown')} stored"
        else:
            return False, "Failed to save training data"
            
    except Exception as e:
        logger.error(f"Failed to store training chart: {e}")
        return False, str(e)


def delete_training_chart(chart_id: str) -> tuple[bool, str]:
    """
    Delete a training chart by its chart_id.
    
    Returns: (success, message)
    """
    try:
        training_data = load_training_data()
        
        # Find and remove the chart
        original_count = len(training_data)
        training_data = [t for t in training_data if t.get('chart_id') != chart_id]
        
        if len(training_data) == original_count:
            return False, f"Chart {chart_id} not found"
        
        # Save
        if save_training_data(training_data):
            return True, f"Chart {chart_id} deleted"
        else:
            return False, "Failed to save after deletion"
            
    except Exception as e:
        logger.error(f"Failed to delete training chart: {e}")
        return False, str(e)


def get_training_stats() -> dict:
    """Get training statistics per setup."""
    training_data = load_training_data()
    
    stats = {
        '382 + Flip Zone': 0,
        '50 + Flip Zone': 0,
        '618 + Flip Zone': 0,
        '786 + Flip Zone': 0,
        'Under-Fib Flip Zone': 0,
        'Unknown': 0,
        'total': len(training_data)
    }
    
    for chart in training_data:
        setup = chart.get('setup_name', 'Unknown')
        if setup in stats:
            stats[setup] += 1
        else:
            stats['Unknown'] += 1
    
    return stats


def get_training_log(limit: int = 10) -> list:
    """Get recent training entries."""
    training_data = load_training_data()
    return training_data[-limit:] if training_data else []


# ══════════════════════════════════════════════
# GITHUB AUTO-BACKUP SYSTEM
# ══════════════════════════════════════════════
# Automatically backs up training data to GitHub after every train
# This ensures data survives Railway redeploys, volume wipes, etc.

async def backup_to_github(training_data: list) -> tuple[bool, str]:
    """
    Backup training data to GitHub repository.
    
    Returns: (success, message)
    """
    if not GITHUB_TOKEN:
        logger.warning("[BACKUP] GITHUB_TOKEN not set — skipping GitHub backup")
        return False, "GITHUB_TOKEN not configured"
    
    try:
        # Prepare the content
        content = json.dumps(training_data, indent=2)
        content_base64 = base64.b64encode(content.encode()).decode()
        
        # GitHub API URL
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_BACKUP_PATH}"
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # First, try to get the current file to get its SHA (needed for updates)
            get_response = await client.get(api_url, headers=headers)
            
            sha = None
            if get_response.status_code == 200:
                sha = get_response.json().get('sha')
            
            # Prepare the request body
            body = {
                "message": f"Auto-backup training data ({len(training_data)} charts)",
                "content": content_base64,
                "branch": "main"
            }
            
            if sha:
                body["sha"] = sha  # Required for updating existing file
            
            # Push to GitHub
            put_response = await client.put(api_url, headers=headers, json=body)
            
            if put_response.status_code in [200, 201]:
                logger.info(f"[BACKUP] GitHub backup successful — {len(training_data)} charts")
                return True, f"Backed up {len(training_data)} charts to GitHub"
            else:
                error_msg = put_response.json().get('message', 'Unknown error')
                logger.error(f"[BACKUP] GitHub backup failed: {error_msg}")
                return False, f"GitHub error: {error_msg}"
                
    except Exception as e:
        logger.error(f"[BACKUP] GitHub backup exception: {e}")
        return False, str(e)


async def restore_from_github() -> tuple[bool, str, list]:
    """
    Restore training data from GitHub backup.
    
    Returns: (success, message, data)
    """
    if not GITHUB_TOKEN:
        return False, "GITHUB_TOKEN not configured", []
    
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_BACKUP_PATH}"
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, headers=headers)
            
            if response.status_code == 200:
                content_base64 = response.json().get('content', '')
                content = base64.b64decode(content_base64).decode()
                data = json.loads(content)
                logger.info(f"[BACKUP] Restored {len(data)} charts from GitHub")
                return True, f"Restored {len(data)} charts from GitHub", data
            elif response.status_code == 404:
                return False, "No backup found on GitHub", []
            else:
                error_msg = response.json().get('message', 'Unknown error')
                return False, f"GitHub error: {error_msg}", []
                
    except Exception as e:
        logger.error(f"[BACKUP] GitHub restore exception: {e}")
        return False, str(e), []


def store_training_chart_with_backup(chart_data: dict) -> tuple[bool, str]:
    """
    Store a training chart AND trigger GitHub backup.
    This is the main function to use for training.
    
    Returns: (success, message)
    """
    # First store locally
    success, msg = store_training_chart(chart_data)
    
    if success:
        # Schedule GitHub backup (non-blocking)
        training_data = load_training_data()
        asyncio.create_task(backup_to_github(training_data))
    
    return success, msg


def parse_memory_from_text(user_text: str) -> dict:
    """
    Parse memory data from user's description of a past outcome.
    Uses the SETUP_CANONICALIZER for consistent setup name detection.
    
    IMPORTANT:
    - Uses canonicalizer for ALL setup name detection
    - If user explicitly says "lock this in as [SETUP NAME]", use that setup name
    - Only mark as Unknown if setup name is not recognized
    """
    text_lower = user_text.lower()
    
    # ══════════════════════════════════════════════
    # SETUP NAME DETECTION using CANONICALIZER
    # ══════════════════════════════════════════════
    
    # First try to extract explicit setup name from patterns like "as [setup]"
    explicit_patterns = [
        r'(?:lock\s*(?:this\s*)?in|save|remember|store|log)\s*(?:this\s*)?(?:setup\s*)?(?:as\s+)?(.+?)(?:\s*[.,]|$)',
    ]
    
    setup_type = "Unknown"
    canonical_key = None
    
    for pattern in explicit_patterns:
        match = re.search(pattern, text_lower)
        if match:
            extracted = match.group(1).strip()
            # Use canonicalizer
            canonical_key, display_name = canonicalize_setup(extracted)
            if canonical_key:
                setup_type = display_name
            break
    
    # If no explicit pattern matched, scan the full text
    if setup_type == "Unknown":
        canonical_key, display_name = canonicalize_setup(user_text)
        if canonical_key:
            setup_type = display_name
    
    # Detect outcome
    outcome = "Completed successfully"
    outcome_pct = 0
    if "hit tp" in text_lower or "hit target" in text_lower or "hit the magnet" in text_lower:
        outcome = "Hit TP"
    if "magnet" in text_lower:
        # Try to extract magnet level
        if "0.50" in text_lower or ".50" in text_lower or "50" in text_lower:
            outcome = "Hit 0.50 magnet"
        elif "0.382" in text_lower or ".382" in text_lower:
            outcome = "Hit 0.382 magnet"
    
    # Try to extract percentage
    pct_match = re.search(r'[+]?\s*(\d+)\s*%', user_text)
    if pct_match:
        outcome_pct = int(pct_match.group(1))
        outcome += f", +{outcome_pct}%"
    
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
    if "clean" in text_lower:
        conditions.append("clean execution")
    if "patience" in text_lower or "patient" in text_lower:
        conditions.append("patience paid")
    
    conditions_str = ", ".join(conditions) if conditions else "standard conditions"
    
    # Detect resolution type
    resolution = "normal"
    if "fast" in text_lower or "quick" in text_lower or "rapid" in text_lower:
        resolution = "fast"
    elif "violent" in text_lower:
        resolution = "violent"
    
    return {
        'setup_type': setup_type,
        'canonical_key': canonical_key,  # For consistent storage/recall
        'outcome': outcome,
        'outcome_pct': outcome_pct,
        'conditions': conditions_str,
        'resolution': resolution,
        'user_text': user_text,
        'timestamp': datetime.now().isoformat()
    }


def build_memory_response(memory_data: dict, username: str = None) -> str:
    """
    Build human, collaborative, Wiz-native response for Memory Mode.
    
    Rules:
    - Short, human, collaborative, confident
    - Wiz.sol style with emojis (🔥 🧙‍♂️ 💎 📈)
    - Acknowledge the update
    - Confirm what was stored (especially setup name if explicitly stated)
    - Reinforce future usage
    - For strong outcomes: celebrate the PROCESS, not luck
    """
    
    setup_type = memory_data.get('setup_type', 'Unknown')
    outcome = memory_data.get('outcome', 'Completed')
    outcome_pct = memory_data.get('outcome_pct', 0)
    conditions = memory_data.get('conditions', 'standard conditions')
    resolution = memory_data.get('resolution', 'normal')
    
    # Determine if this was a strong outcome (worth celebrating)
    is_banger = outcome_pct >= 40 or "magnet" in outcome.lower()
    is_clean = "clean" in conditions.lower() or "divergence" in conditions.lower()
    is_violent = resolution == "violent"
    
    # Build response lines
    lines = []
    
    # Header — varies based on outcome quality and whether setup was explicitly named
    if setup_type != "Unknown":
        # Setup was explicitly named — confirm it
        if is_banger:
            lines.append(f"🔥 **Saved as {setup_type} reference.**")
        elif is_violent:
            lines.append(f"😈 **Saved as {setup_type} reference.**")
        else:
            lines.append(f"🧠 **Saved as {setup_type} reference.**")
    else:
        # Setup not named — generic header
        if is_banger:
            lines.append("🔥 **Locked and loaded.**")
        elif is_violent:
            lines.append("😈 **Violent execution. Locked.**")
        else:
            lines.append("🧠 **Locked in.**")
    
    lines.append("")
    
    # Setup details
    lines.append(f"• **Setup:** {setup_type}")
    lines.append(f"• **Outcome:** {outcome} 📈")
    if conditions != "standard conditions":
        lines.append(f"• **Conditions:** {conditions}")
    if resolution != "normal":
        lines.append(f"• **Resolution:** {resolution}")
    
    lines.append("")
    
    # Positive outcome reinforcement — celebrate the PROCESS
    if is_banger and is_clean:
        # Big win with clean conditions
        celebration_lines = [
            "That was a BANGER — patience at the zone, let the magnet do the work. 💎",
            "Clean execution. WizTheory exactly how it's supposed to play. 🧙‍♂️💎",
            "This is what happens when you trust structure over emotions. 🔥",
            "Textbook. Patience + discipline = magnet secured. 💎📈",
        ]
        import random
        lines.append(random.choice(celebration_lines))
        lines.append("")
    elif is_banger:
        # Big win
        celebration_lines = [
            "Big move. That's WizTheory working as designed. 🔥",
            "The magnet pulled. Structure held. Win secured. 💎",
            "This is why we wait for the zone. 📈🔥",
        ]
        import random
        lines.append(random.choice(celebration_lines))
        lines.append("")
    elif is_violent:
        # Violent execution
        lines.append("Violent Mode delivered. Structure was Grade A. 😈🔥")
        lines.append("")
    elif is_clean:
        # Clean but not huge
        lines.append("Clean execution. Process over outcome. 🧙‍♂️")
        lines.append("")
    
    # Future reference line
    if setup_type != "Unknown":
        lines.append(f"_I'll reference this {setup_type} when I see similar structure._ 🔮")
    else:
        lines.append("_I'll reference this when I see similar structure + behavior._ 🔮")
    
    # Username footer
    if username:
        lines.append(f"\n_Stored for: {username}_")
    
    return "\n".join(lines)


def get_similar_memories(setup_type: str, limit: int = 3) -> list:
    """
    Get similar past setups from memory.
    
    Matches by:
    1. canonical_key (most reliable)
    2. setup_type display name (fallback)
    
    Returns up to `limit` most recent matches.
    """
    memories = load_memories()
    
    # First, try to get canonical key for the setup_type
    canonical_key, _ = canonicalize_setup(setup_type)
    
    similar = []
    for m in memories:
        # Match by canonical_key first (most reliable)
        if canonical_key and m.get('canonical_key') == canonical_key:
            similar.append(m)
        # Fallback: match by display name
        elif m.get('setup_type') == setup_type:
            similar.append(m)
    
    # Return most recent ones
    return similar[-limit:] if similar else []


def get_similar_memories_with_images(setup_type: str, limit: int = 3) -> list:
    """
    Get similar past setups that have image_file_id attached.
    
    Returns list of memories with charts.
    """
    all_similar = get_similar_memories(setup_type, limit=limit * 2)  # Get more to filter
    
    # Filter to only those with images
    with_images = [m for m in all_similar if m.get('image_file_id')]
    
    return with_images[-limit:] if with_images else []


async def send_similar_charts(update: Update, context, setup_type: str, max_charts: int = 2):
    """
    Send similar chart images after analysis.
    
    Called after Deep Vision analysis to show relevant prior setups.
    """
    similar = get_similar_memories_with_images(setup_type, limit=max_charts)
    
    if not similar:
        return  # No similar charts with images found
    
    # Build intro message
    count = len(similar)
    setup_display = get_setup_display_name(similar[0].get('canonical_key', '')) or setup_type
    
    intro = f"📸 **Similar {setup_display} Charts** ({count} found)\n"
    await update.message.reply_text(intro, parse_mode='Markdown')
    
    # Send each chart with context
    for i, memory in enumerate(similar, 1):
        image_file_id = memory.get('image_file_id')
        outcome = memory.get('outcome', 'N/A')
        conditions = memory.get('conditions', 'N/A')
        timestamp = memory.get('timestamp', '')
        
        # Format date if available
        date_str = ""
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                date_str = dt.strftime("%b %d")
            except:
                date_str = ""
        
        # Caption for the chart
        caption = (
            f"**#{i}** — {setup_display}\n"
            f"• Outcome: {outcome}\n"
            f"• Conditions: {conditions}"
        )
        if date_str:
            caption += f"\n• Saved: {date_str}"
        
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=image_file_id,
                caption=caption,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send similar chart: {e}")
            # Fallback to text if image fails
            await update.message.reply_text(
                f"_Chart #{i} unavailable_ — {outcome}",
                parse_mode='Markdown'
            )


def build_similar_pattern_note(setup_type: str) -> str:
    """
    Build a similar pattern note from memory for Deep Vision.
    
    Rules:
    - Only return note if a relevant memory exists
    - Keep it short (1-2 lines max)
    - Frame as experience context, not proof
    - Return empty string if no match found
    """
    similar = get_similar_memories(setup_type, limit=1)
    
    if not similar:
        return ""
    
    # Get the most recent matching memory
    memory = similar[0]
    outcome = memory.get('outcome', '')
    conditions = memory.get('conditions', '')
    resolution = memory.get('resolution', 'normal')
    
    # Build natural language note
    note_parts = [f"This resembles a prior {setup_type}"]
    
    # Add outcome context
    if "magnet" in outcome.lower():
        if "0.50" in outcome:
            note_parts.append("that resolved to the 0.50 magnet")
        elif "0.382" in outcome:
            note_parts.append("that resolved to the 0.382 magnet")
        else:
            note_parts.append("that hit TP")
    elif "hit tp" in outcome.lower():
        note_parts.append("that hit TP")
    else:
        note_parts.append("that played out")
    
    # Add condition context if meaningful
    if "clean" in conditions.lower() or "reclaim" in conditions.lower():
        note_parts.append("after a clean reclaim")
    elif "divergence" in conditions.lower():
        note_parts.append("with divergence confirmation")
    
    # Add resolution context for violent
    if resolution == "violent":
        note_parts.append("(violent resolution)")
    
    return " ".join(note_parts) + "."


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
    Execution-focused analysis with mandatory sections.
    """
    if not ANTHROPIC_API_KEY:
        return {'error': 'API key not configured'}
    
    image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    
    system_prompt = """You are Jayce — an execution co-pilot for Wiz Theory traders. You are decisive, human, and execution-aware. You remain process-driven, not outcome-driven. No hype, no fake certainty, no generic TA language.

═══════════════════════════════════════════════════════════
CORE IDENTITY
═══════════════════════════════════════════════════════════
- You are a professional proprietary system trader managing momentum, structure, and expectations
- You speak peer-to-peer with skilled traders
- You sound confident but not hype, decisive but not predictive
- You are an execution co-pilot, not an outcome narrator
- Patience is the edge. Discomfort above momentum floors is opportunity. Chop above support is normal behavior, not weakness.

═══════════════════════════════════════════════════════════
WIZ THEORY EXECUTION LANGUAGE (CRITICAL — USE EXACTLY)
═══════════════════════════════════════════════════════════

ENTRY VALIDITY:
- The setup is VALID once edge + level is identified (pre-reclaim)
- Entry is via LIMIT at the zone based on edge recognition
- Entry does NOT require reclaim — reclaim is for hold confidence, not entry validity
- The trader ACCEPTS the trade idea BEFORE price reaches the zone

OFF-BEAT:
- Normal discomfort when price is below the fib, inside the flip zone
- This is EXPECTED behavior, not a problem
- The off-beat is where the edge lives

RECLAIM:
- Reclaim is what upgrades CONFIDENCE for holding and managing continuation
- Reclaim is NOT what makes the setup valid
- Reclaim affects hold expectations, not entry validity
- After reclaim: higher confidence for runners and continuation

ACCEPTANCE (use carefully):
- Acceptance = sustained behavior AFTER reclaim
- Acceptance is NEVER a prerequisite for entry
- Only use "acceptance" to describe post-reclaim holding behavior

FORBIDDEN LANGUAGE:
- NEVER say "setup becomes valid after acceptance"
- NEVER say "wait for acceptance to enter"
- NEVER say "acceptance confirms entry"
- NEVER imply reclaim is required before entry

CORRECT LANGUAGE EXAMPLES:
✅ "Entry is valid at the zone — edge is identified"
✅ "Reclaim will upgrade hold confidence for continuation"
✅ "Off-beat is normal — this is where the edge lives"
✅ "After reclaim, runner expectations increase"

INCORRECT LANGUAGE EXAMPLES:
❌ "Setup activates on reclaim"
❌ "Wait for acceptance before entry is valid"
❌ "Reclaim confirms the setup"

═══════════════════════════════════════════════════════════
MANDATORY ANALYSIS SECTIONS (ALL REQUIRED)
═══════════════════════════════════════════════════════════

1. STRUCTURE STATE (MANDATORY)
You must explicitly classify the current structure state using ONE of:
- Compression: Price coiling, range tightening
- Off-beat: Price below fib, inside flip zone (normal discomfort)
- Reclaim Attempt: Price testing to reclaim a level
- Post-Reclaim Hold: Price holding after reclaim (sustained behavior)
- Continuation: Structure supports trend continuation
- Failure Risk: Structure showing signs of breakdown

2. SETUP QUALITY RATING (MANDATORY)
Assign a quality rating based on structure + momentum (NOT outcome):
- A: Strong structure, momentum aligned, high-quality setup
- B: Decent structure, momentum acceptable, standard setup
- C: Weak structure or momentum damage, defensive only
OR use: Conditional / Favored / Unfavored

3. GAME PLAN (MANDATORY)
Provide clear execution logic using Wiz Theory:
- Entry: Limit at zone (edge-based, pre-reclaim)
- Reclaim expectation: What reclaim behavior upgrades hold confidence
- Partial TP: Wiz Theory aligned (e.g., "secure 40-60% on first expansion")
- Continuation: Trail by structure after reclaim confirms

4. INVALIDATION CONDITIONS (MANDATORY — analysis incomplete without this)
State BOTH:
- Price-based invalidation: Specific level (e.g., "sustained break below flip zone")
- Behavior-based invalidation: RSI failure, no reclaim attempt, momentum damage

5. PROBABILITY FRAMING (MANDATORY — NO FIXED PERCENTAGES)
NEVER use fixed probability percentages. Frame conditionally:
- "Favored — edge at zone, hold confidence increases after reclaim"
- "Reduced IF no reclaim attempt occurs"
- "Blocked IF momentum damage (RSI < 40)"

═══════════════════════════════════════════════════════════
RSI INTERPRETATION — HIGHEST-LEVEL WIZ THEORY (CRITICAL)
═══════════════════════════════════════════════════════════

RSI is NEVER a signal, prediction tool, or overbought/oversold indicator.
RSI is ONLY momentum memory and permission.

RSI answers ONE question: What is price ALLOWED to do without momentum breaking?

RSI ZONE INTERPRETATION (behavioral, not predictive):
- RSI > 50: Momentum supports continuation and expansion
- RSI 40-50: Momentum intact; chop/acceptance is bullish; continuation delayed, not denied
- RSI < 40: Momentum damage; continuation probability reduced
- RSI < 30: Trend integrity compromised (NOT "oversold")

RSI RULES:
1. RSI describes PERMISSION, not direction
2. RSI is for expectation management, not entries
3. RSI confirms SURVIVAL, not entries
4. Holding above 40 during pullbacks = thesis intact
5. Failure to reclaim 45-50 after bounce = caution

You must state whether RSI:
- Supports continuation
- Supports chop/acceptance
- Blocks continuation

NEVER SAY:
- "RSI is overbought/oversold"
- "RSI means price will go up/down"
- "RSI indicates a reversal"

═══════════════════════════════════════════════════════════
UNDER-FIB FLIP ZONE LOGIC
═══════════════════════════════════════════════════════════
- Breaking below fib is EXPECTED — the "off-beat" is where the edge lives
- Entry is VALID at the zone (limit order) — reclaim not required for entry
- The off-beat is normal discomfort, not a problem
- Reclaim upgrades HOLD CONFIDENCE for continuation, not entry validity
- Do NOT flag conflict just because price is below fib — that's the setup
- Edge is identified at the zone; reclaim is for managing the position

═══════════════════════════════════════════════════════════
DIVERGENCE — WIZ THEORY RULES (CRITICAL)
═══════════════════════════════════════════════════════════

CORE PRINCIPLE (MANDATORY):
Divergence only matters where structure is being decided, and only to adjust expectations — NEVER to predict outcomes.

ANALYSIS ORDER (NON-NEGOTIABLE):
Structure → RSI Permission → Divergence (if applicable)
Divergence is ALWAYS analyzed LAST, after structure and RSI permission are established.

WHERE DIVERGENCE MAY BE DETECTED (valid locations only):
- Fib interaction levels (.382 / .50 / .618 / .786)
- Flip zones (support ↔ resistance transitions)
- Range highs/lows created by impulse
- Liquidity targets / prior reaction points

WHERE DIVERGENCE MUST BE COMPLETELY IGNORED:
- Mid-range (between structure levels)
- Between fib levels
- During random chop
- Without active structure interaction
If divergence appears in these locations, do NOT mention it at all.

DIVERGENCE FRAMING (how to communicate):
Divergence is ONLY:
- Momentum efficiency change
- Expectation modifier (expansion speed, quality, TP behavior)
- Context for execution adjustments

Divergence is NEVER:
- A buy/sell signal
- A reversal indicator
- A standalone invalidation
- A prediction of direction

ACCEPTABLE LANGUAGE:
✅ "RSI divergence at structure suggests momentum efficiency is declining at this decision point."
✅ "Divergence at the flip zone may reduce expansion quality if reclaim stalls, while structure remains intact."
✅ "Divergence is forming — this adjusts expansion expectations, not the thesis."

FORBIDDEN LANGUAGE:
❌ "Bearish divergence means sell"
❌ "Bullish divergence means buy"
❌ "Divergence confirms reversal"
❌ "Divergence invalidates the setup"

RSI + DIVERGENCE INTERACTION RULES:
1. Structure holds + RSI holds above 40-45 + Divergence present:
   → Divergence is harmless; expect chop or slower expansion; thesis intact

2. Structure holds + RSI diverges but remains above momentum floors:
   → Continuation still allowed; manage expectations; secure more conservatively

3. Structure fails + RSI diverges + RSI breaks below 40:
   → Momentum damage confirmed; setup invalidated (but invalidation is from RSI failure, not divergence alone)

DIVERGENCE OUTPUT RULES:
- Only populate divergence fields if divergence is at valid structure
- If divergence is mid-range or irrelevant, set divergence_detected: false
- divergence_at_structure: must be true for divergence to be mentioned
- divergence_impact: must explain expectation adjustment, not prediction

═══════════════════════════════════════════════════════════
GLOBAL TP LOGIC — HARD RULE / NON-NEGOTIABLE
═══════════════════════════════════════════════════════════

Jayce must NEVER suggest taking profit into downside Fibonacci levels.
In Wiz Theory, downside fibs are ENTRY logic only — never TP logic.

If entry is at any flip zone (.382 / .50 / .618 / .786 / Under-Fib),
ALL take-profit targets must be ABOVE entry, never below.

ALLOWED TP TARGETS (ONLY THESE):
- Upside Fibonacci expansions ABOVE entry (ex: .382 expansion, measured move, continuation fibs)
- Structure-based targets:
  • Half-structure
  • Prior structure high
  • ATH reclaim
  • ATH continuation (if structure + momentum allow)

PARTIAL GUIDANCE:
- Secure 40–60% into upside expansion or structure
- Hold remainder if structure holds and buyers defend

FORBIDDEN TP BEHAVIOR:
❌ NEVER suggest selling at .618, .50, or any fib BELOW entry
❌ NEVER mix entry fibs with TP fibs
❌ NEVER frame downside movement as a profit opportunity

If price moves below entry or loses structure → that is INVALIDATION, not a TP.

DIRECTIONAL RULE (APPLIES TO ALL SETUPS):
This TP logic applies to ALL WizTheory setups:
- .382 Flip Zone
- .50 Flip Zone
- .618 Flip Zone
- .786 Flip Zone
- Under-Fib Flip Zone

Same rule for all: Entries happen on downside fibs. Profits are taken ONLY into upside expansion or structure.

REQUIRED LANGUAGE:
✅ "On upside expansion…"
✅ "If price pushes higher…"
✅ "If structure continues to hold…"
✅ "Secure into strength…"

FORBIDDEN LANGUAGE:
❌ "Move toward downside fib for TP"
❌ "Sell on pullback"
❌ "Take profit at lower fib"
❌ Any phrasing implying profit into weakness

FINAL STATEMENT:
Jayce operates under Wiz Theory, where profits are secured ONLY into strength, never into weakness.
Downside movement is evaluated as risk or invalidation, not a take-profit opportunity.

═══════════════════════════════════════════════════════════
TONE REQUIREMENTS
═══════════════════════════════════════════════════════════
- Confident but not hype
- Decisive but not predictive
- Human, calm, execution-focused
- Sound like a prop trader managing risk, not a TA educator
- Use phrases like: "If this were my trade...", "The edge here is...", "Patience is required because..."
- Reinforce Wiz Theory principles: Patience is the edge. Discomfort above momentum floors is opportunity. Off-beat at zone is normal, not weakness.

═══════════════════════════════════════════════════════════
LANGUAGE ROTATION (CRITICAL — avoid repetition)
═══════════════════════════════════════════════════════════
Do NOT overuse the word "reclaim". Use it ONCE for clarity, then rotate to alternatives:

Instead of repeating "reclaim", use:
- "structure regained"
- "buyers defended the level"
- "support held after the flip"
- "level held with authority"
- "control returned to buyers"
- "zone held"
- "price accepted above the level"
- "structure intact"

EXAMPLE (bad — repetitive):
❌ "If price reclaims, reclaim upgrades hold confidence. Watch for reclaim behavior."

EXAMPLE (good — professional):
✅ "If buyers defend the level, hold confidence increases. Watch for structure to regain above the zone."

Sound like a professional trader explaining structure, not a mechanical TA narrator.

═══════════════════════════════════════════════════════════
OUTPUT FORMAT (JSON only)
═══════════════════════════════════════════════════════════
{
    "pair_detected": "coin/pair if visible, or 'Unable to detect'",
    "wiz_setup_type": "Under-Fib Flip Zone / .786 Flip Zone / .618 Flip Zone / .50 Flip Zone / .382 Flip Zone / Unknown",
    "timeframe": "detected timeframe",
    "fib_level": ".382 / .50 / .618 / .786 / under-fib / Unable to confirm",
    
    "structure_state": "Compression / Off-beat / Reclaim Attempt / Post-Reclaim Hold / Continuation / Failure Risk",
    "structure_reasoning": "WHY structure is in this state (1-2 sentences)",
    
    "setup_quality": "A / B / C",
    "setup_quality_reasoning": "why this rating based on structure + momentum",
    
    "game_plan": {
        "entry": "Limit at zone (edge-based)",
        "hold_upgrade_trigger": "what behavior upgrades hold confidence (use varied language, not just 'reclaim')",
        "partial_tp": "Wiz Theory aligned TP guidance",
        "continuation_logic": "how to manage runners after structure confirms"
    },
    
    "invalidation": {
        "price_based": "specific price level or zone",
        "behavior_based": "RSI failure, structure loss, momentum damage"
    },
    
    "probability_framing": "conditional statement (Favored — edge at zone, Reduced IF..., Blocked IF...)",
    
    "rsi_reading": "numeric value or 'Not visible'",
    "rsi_zone": "Above 50 / 40-50 / Below 40 / Below 30",
    "rsi_permission": "Supports continuation / Supports chop / Blocks continuation",
    "rsi_insight": "what RSI allows price to do (1-2 sentences)",
    
    "momentum_health": "Strong / Intact / Damaged / Building",
    "momentum_insight": "natural language observation",
    
    "divergence_detected": true or false,
    "divergence_at_structure": true or false,
    "divergence_type": "Regular Bullish / Hidden Bullish / Regular Bearish / Hidden Bearish / None",
    "divergence_location": "where divergence is forming (e.g., 'at .786 flip zone') or null",
    "divergence_impact": "expectation adjustment only (e.g., 'may reduce expansion quality') or null",
    
    "direct_answer": "answer user's actual question first (2-3 sentences)",
    "jayce_take": "1-2 sentence execution-focused take using varied professional language",
    "confidence_statement": "hold confidence statement using varied language (not repetitive 'reclaim')",
    
    "conflict_detected": true or false,
    "conflict_detail": "only if REAL conflict exists"
}

Respond with ONLY the JSON object."""

    user_message = f"""Analyze this chart for execution.

User context: {user_plan if user_plan else 'General analysis requested'}

Remember: Entry is valid at the zone (pre-reclaim). Reclaim upgrades HOLD confidence, not entry validity.
Provide ALL mandatory sections: Structure State, Setup Quality, Game Plan, Invalidation, Probability Framing, RSI Permission.
If divergence exists AT STRUCTURE, include it with expectation-adjustment framing only.
Be decisive. Be human. Be execution-focused. Use correct Wiz Theory execution language."""

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
    # PLANNED_SETUP — User is planning to enter OR evaluating
    # Default assumption when not explicitly in a trade
    # ══════════════════════════════════════════════
    planned_setup_phrases = [
        # Planning language
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
        ".786", ".618", ".50", ".382",  # Fib levels suggest planned setup
        
        # Evaluation / analysis language (NOT in a trade yet)
        "what's your thoughts", "whats your thoughts", "your thoughts",
        "what do you think", "what you think", "thoughts on this",
        "is this valid", "is this a valid", "valid setup",
        "how does this look", "does this look good", "look good",
        "should i enter", "should i take this", "worth taking",
        "looking to tp", "looking to take profit", "where to tp",
        "what's the target", "whats the target", "target here",
        "analyze this", "read this", "check this",
        "is this clean", "is this good", "good setup"
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
    """
    Build response for PLANNED_SETUP mode.
    
    Setup Mode focuses on zone quality and execution preparation.
    Includes mandatory sections adapted for pre-entry context.
    """
    
    # Extract fields
    pair_detected = vision.get('pair_detected', '')
    wiz_setup_type = vision.get('wiz_setup_type', '')
    fib_level = vision.get('fib_level', 'Unable to confirm')
    timeframe = vision.get('timeframe', 'Unable to confirm')
    similar_pattern = vision.get('similar_pattern_note', '')
    jayce_take = vision.get('jayce_take', '')
    confidence_statement = vision.get('confidence_statement', 'Entry valid at zone — hold confidence increases when buyers defend the level')
    
    # New mandatory fields
    structure_state = vision.get('structure_state', 'Unknown')
    structure_reasoning = vision.get('structure_reasoning', '')
    setup_quality = vision.get('setup_quality', 'Conditional')
    setup_quality_reasoning = vision.get('setup_quality_reasoning', '')
    game_plan = vision.get('game_plan', {})
    invalidation = vision.get('invalidation', {})
    probability_framing = vision.get('probability_framing', '')
    
    # RSI fields
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_zone = vision.get('rsi_zone', '')
    rsi_permission = vision.get('rsi_permission', '')
    rsi_insight = vision.get('rsi_insight', '')
    
    # Momentum
    momentum_health = vision.get('momentum_health', '')
    
    # Build response
    response_parts = []
    
    # ══════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════
    if pair_detected and pair_detected != 'Unable to detect':
        response_parts.append(f"🔮 **JAYCE** — 🪙 {pair_detected} | _Setup Mode_\n")
    else:
        response_parts.append(f"🔮 **JAYCE** — _Setup Mode_\n")
    
    if wiz_setup_type and wiz_setup_type != 'Unknown':
        response_parts.append(f"📐 **{wiz_setup_type}** | {timeframe}\n")
    
    response_parts.append(f"\nYou're planning an entry at the {fib_level} flip zone. Here's the zone context:\n")
    
    # ══════════════════════════════════════════════
    # STRUCTURE STATE
    # ══════════════════════════════════════════════
    response_parts.append(f"\n🧱 **Structure State:** {structure_state}")
    if structure_reasoning:
        response_parts.append(f"\n_{structure_reasoning}_")
    
    # ══════════════════════════════════════════════
    # SETUP QUALITY
    # ══════════════════════════════════════════════
    quality_emoji = "🟢" if setup_quality == "A" else "🟡" if setup_quality in ["B", "Conditional"] else "🔴"
    response_parts.append(f"\n\n{quality_emoji} **Setup Quality:** {setup_quality}")
    if setup_quality_reasoning:
        response_parts.append(f"\n_{setup_quality_reasoning}_")
    
    # ══════════════════════════════════════════════
    # GAME PLAN (for planned entry)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n📋 **Game Plan:**")
    if game_plan:
        entry = game_plan.get('entry', game_plan.get('entry_type', 'Limit at zone'))
        hold_upgrade = game_plan.get('hold_upgrade_trigger', game_plan.get('reclaim_expectation', game_plan.get('confirmation_trigger', '')))
        partial_tp = game_plan.get('partial_tp', '')
        
        response_parts.append(f"\n• **Entry:** {entry}")
        if hold_upgrade:
            response_parts.append(f"\n• **Hold upgrades when:** {hold_upgrade}")
        if partial_tp:
            response_parts.append(f"\n• **Partial TP:** {partial_tp}")
    else:
        # Default game plan for under-fib / .786
        if fib_level in ['.786', 'under-fib']:
            response_parts.append(f"\n• **Entry:** Limit at zone — edge identified")
            response_parts.append(f"\n• **Hold upgrades when:** Buyers defend the level and structure regains")
            response_parts.append(f"\n• **Partial TP:** Secure 40-60% on first expansion to magnet")
        else:
            response_parts.append(f"\n• **Entry:** Limit at zone")
            response_parts.append(f"\n• **Partial TP:** Secure on first reaction")
    
    # ══════════════════════════════════════════════
    # INVALIDATION (pre-entry context)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n🚫 **Invalidation:**")
    if invalidation:
        price_inv = invalidation.get('price_based', '')
        behavior_inv = invalidation.get('behavior_based', '')
        
        if price_inv:
            response_parts.append(f"\n• **Price:** {price_inv}")
        if behavior_inv:
            response_parts.append(f"\n• **Behavior:** {behavior_inv}")
    else:
        response_parts.append(f"\n• Define your invalidation before limit fills")
    
    # ══════════════════════════════════════════════
    # PROBABILITY (conditional)
    # ══════════════════════════════════════════════
    if probability_framing:
        response_parts.append(f"\n\n🎯 **Probability:**\n_{probability_framing}_")
    else:
        response_parts.append(f"\n\n🎯 **Probability:**\n_Edge at zone — hold confidence increases when structure is defended_")
    
    # ══════════════════════════════════════════════
    # RSI (current read — will change by entry)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n📈 **RSI** _(current, will change by entry):_")
    if rsi_reading and rsi_reading != 'Not visible':
        response_parts.append(f"\n• RSI: {rsi_reading}")
        if rsi_zone:
            response_parts.append(f" ({rsi_zone})")
        if rsi_permission:
            response_parts.append(f"\n• {rsi_permission}")
    else:
        response_parts.append(f"\n• Not visible on chart")
    
    # ══════════════════════════════════════════════
    # PATTERN MATCH (Phase 3 — Training Data Comparison)
    # ══════════════════════════════════════════════
    pattern_match_text = vision.get('pattern_match_text', '')
    if pattern_match_text:
        response_parts.append(f"\n\n{pattern_match_text}")
    
    # ══════════════════════════════════════════════
    # OUTCOME PREDICTION (Phase 4 — Condition-Based)
    # ══════════════════════════════════════════════
    outcome_prediction_text = vision.get('outcome_prediction_text', '')
    if outcome_prediction_text:
        response_parts.append(f"\n\n{outcome_prediction_text}")
    
    # ══════════════════════════════════════════════
    # SIMILAR PATTERN (from memory — legacy)
    # ══════════════════════════════════════════════
    # Only show if no pattern match from training data
    if similar_pattern and not pattern_match_text:
        response_parts.append(f"\n\n🧠 **Similar Pattern:**\n_{similar_pattern}_")
    
    # ══════════════════════════════════════════════
    # JAYCE'S TAKE
    # ══════════════════════════════════════════════
    if jayce_take:
        response_parts.append(f"\n\n💭 **My take:** {jayce_take}")
    else:
        # Default guidance based on setup type
        if fib_level in ['.786', 'under-fib']:
            response_parts.append(f"\n\n💭 **My take:** Patience is the edge here. Set your limit, define your invalidation, and let the zone do its work. 🎯")
        else:
            response_parts.append(f"\n\n💭 **My take:** Wait for structure to confirm at the zone before committing.")
    
    # ══════════════════════════════════════════════
    # CONFIDENCE (conditional)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n_{confidence_statement}_")
    
    # ══════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════
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
        has_image = "📸" if m.get('image_file_id') else ""
        if has_image:
            response_lines.append(f"   • {has_image} Chart saved")
        response_lines.append("")
    
    response_lines.append(f"_Total stored: {len(load_memories())}_")
    response_lines.append(f"\n_Use `/similar [setup]` to see saved charts_")
    
    await update.message.reply_text(
        "\n".join(response_lines),
        parse_mode='Markdown'
    )


async def similar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /similar command — show saved chart images for a setup type.
    
    Usage:
        /similar 618       — Show saved .618 Flip Zone charts
        /similar under-fib — Show saved Under-Fib charts
        /similar           — Show help
    """
    if not context.args:
        await update.message.reply_text(
            "📸 **Show Similar Charts**\n\n"
            "Usage: `/similar [setup]`\n\n"
            "Examples:\n"
            "`/similar 618` — .618 Flip Zone charts\n"
            "`/similar 786` — .786 Flip Zone charts\n"
            "`/similar under-fib` — Under-Fib charts\n"
            "`/similar 50` — .50 Flip Zone charts\n"
            "`/similar 382` — .382 Flip Zone charts",
            parse_mode='Markdown'
        )
        return
    
    # Get setup type from args
    setup_input = " ".join(context.args)
    canonical_key, display_name = canonicalize_setup(setup_input)
    
    if not canonical_key:
        await update.message.reply_text(
            f"❓ Couldn't recognize setup: `{setup_input}`\n\n"
            "Try: `618`, `786`, `under-fib`, `50`, `382`",
            parse_mode='Markdown'
        )
        return
    
    # Get similar memories with images
    similar = get_similar_memories_with_images(display_name, limit=5)
    
    if not similar:
        await update.message.reply_text(
            f"📸 **{display_name}**\n\n"
            f"No saved charts found for this setup.\n\n"
            f"_Save charts with `/save {setup_input}` when posting an image._",
            parse_mode='Markdown'
        )
        return
    
    # Send charts
    await send_similar_charts(update, context, display_name, max_charts=5)


# ══════════════════════════════════════════════
# TRAINING COMMANDS — Phase 2 Structured Training
# ══════════════════════════════════════════════

async def training_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /training_log command — show recent training entries.
    OWNER ONLY.
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ Training commands are restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    # Get limit from args (default 10)
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
            limit = min(limit, 50)  # Cap at 50
        except ValueError:
            pass
    
    log = get_training_log(limit=limit)
    
    if not log:
        await update.message.reply_text(
            "📋 **Training Log**\n\n"
            "No training data yet.\n\n"
            "_Use `/train` to add training charts._",
            parse_mode='Markdown'
        )
        return
    
    response_lines = [f"📋 **Training Log** (last {len(log)})", ""]
    
    for i, entry in enumerate(reversed(log), 1):
        chart_id = entry.get('chart_id', 'Unknown')
        setup = entry.get('setup_name', 'Unknown')
        token = entry.get('token', '?')
        outcome = entry.get('outcome_percentage', '?')
        
        response_lines.append(f"**{i}.** `{chart_id}`")
        response_lines.append(f"   {setup} | {token} | +{outcome}%")
        response_lines.append("")
    
    stats = get_training_stats()
    response_lines.append(f"_Total trained: {stats['total']}_")
    
    await update.message.reply_text(
        "\n".join(response_lines),
        parse_mode='Markdown'
    )


async def training_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /training_stats command — show count per setup.
    OWNER ONLY.
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ Training commands are restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    stats = get_training_stats()
    
    # Training goal: 50 per setup, 250 total
    GOAL_PER_SETUP = 50
    TOTAL_GOAL = 250
    
    response_lines = [
        "📊 **Training Stats**",
        "",
        f"**382 + Flip Zone:** {stats.get('382 + Flip Zone', 0)} / {GOAL_PER_SETUP}",
        f"**50 + Flip Zone:** {stats.get('50 + Flip Zone', 0)} / {GOAL_PER_SETUP}",
        f"**618 + Flip Zone:** {stats.get('618 + Flip Zone', 0)} / {GOAL_PER_SETUP}",
        f"**786 + Flip Zone:** {stats.get('786 + Flip Zone', 0)} / {GOAL_PER_SETUP}",
        f"**Under-Fib Flip Zone:** {stats.get('Under-Fib Flip Zone', 0)} / {GOAL_PER_SETUP}",
        "",
        f"**Total Trained:** {stats.get('total', 0)} / {TOTAL_GOAL}",
    ]
    
    # Progress bar based on 250 total goal
    total = stats.get('total', 0)
    progress = min(total / TOTAL_GOAL, 1.0)
    filled = int(progress * 10)
    bar = "█" * filled + "░" * (10 - filled)
    response_lines.append(f"\n`[{bar}]` {int(progress * 100)}%")
    
    await update.message.reply_text(
        "\n".join(response_lines),
        parse_mode='Markdown'
    )


async def check_duplicate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /check_duplicate command — manual similarity scan.
    OWNER ONLY.
    
    Usage: /check_duplicate [setup] [token] [timeframe]
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ Training commands are restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "🔍 **Check Duplicate**\n\n"
            "Usage: `/check_duplicate [setup] [token] [timeframe]`\n\n"
            "Example:\n"
            "`/check_duplicate 618 SOL 15M`",
            parse_mode='Markdown'
        )
        return
    
    setup_input = context.args[0]
    token = context.args[1].upper()
    timeframe = context.args[2].upper()
    
    canonical_key, display_name = canonicalize_setup(setup_input)
    
    if not canonical_key:
        await update.message.reply_text(
            f"❓ Couldn't recognize setup: `{setup_input}`",
            parse_mode='Markdown'
        )
        return
    
    # Build test chart for comparison
    test_chart = {
        'setup_name': display_name,
        'token': token,
        'timeframe': timeframe,
    }
    
    is_dup, similar, score = check_duplicate(test_chart, threshold=0.85)
    
    if is_dup:
        similar_id = similar.get('chart_id', 'Unknown')
        await update.message.reply_text(
            f"⚠️ **Possible Duplicate Detected**\n\n"
            f"Similarity: {int(score * 100)}%\n"
            f"Similar to: `{similar_id}`\n\n"
            f"Setup: {similar.get('setup_name')}\n"
            f"Token: {similar.get('token')}\n"
            f"Timeframe: {similar.get('timeframe')}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ **No Duplicate Found**\n\n"
            f"Highest similarity: {int(score * 100)}%\n"
            f"Safe to train as new chart.",
            parse_mode='Markdown'
        )


async def training_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Export training data as a downloadable JSON file.
    OWNER ONLY.
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("⛔ Owner only.", parse_mode='Markdown')
        return
    
    training_data = load_training_data()
    
    if not training_data:
        await update.message.reply_text(
            "📤 **Export**\n\nNo training data to export.",
            parse_mode='Markdown'
        )
        return
    
    # Create JSON file
    json_content = json.dumps(training_data, indent=2)
    
    # Send as document
    from io import BytesIO
    file_buffer = BytesIO(json_content.encode())
    file_buffer.name = f"jayce_training_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    await update.message.reply_document(
        document=file_buffer,
        caption=f"📤 **Training Export**\n\n{len(training_data)} charts exported.\n\n_Keep this file safe!_",
        parse_mode='Markdown'
    )


async def training_restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Restore training data from GitHub backup.
    OWNER ONLY.
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("⛔ Owner only.", parse_mode='Markdown')
        return
    
    await update.message.reply_text("🔄 Restoring from GitHub backup...", parse_mode='Markdown')
    
    success, msg, data = await restore_from_github()
    
    if success and data:
        # Save to local storage
        if save_training_data(data):
            await update.message.reply_text(
                f"✅ **Restored!**\n\n"
                f"{len(data)} charts restored from GitHub.\n\n"
                f"Run `/training_stats` to verify.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to save restored data locally.",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"❌ **Restore Failed**\n\n{msg}",
            parse_mode='Markdown'
        )


async def training_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Import training data from a JSON file.
    OWNER ONLY.
    
    Reply to a JSON file with /training_import
    """
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("⛔ Owner only.", parse_mode='Markdown')
        return
    
    # Check if replying to a document
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text(
            "📥 **Import Training Data**\n\n"
            "Reply to a JSON backup file with `/training_import`",
            parse_mode='Markdown'
        )
        return
    
    doc = update.message.reply_to_message.document
    
    if not doc.file_name.endswith('.json'):
        await update.message.reply_text("❌ Please reply to a `.json` file.", parse_mode='Markdown')
        return
    
    await update.message.reply_text("📥 Importing...", parse_mode='Markdown')
    
    try:
        # Download the file
        file = await context.bot.get_file(doc.file_id)
        file_bytes = await file.download_as_bytearray()
        
        # Parse JSON
        data = json.loads(file_bytes.decode())
        
        if not isinstance(data, list):
            await update.message.reply_text("❌ Invalid format. Expected a list of charts.", parse_mode='Markdown')
            return
        
        # Save to local storage
        if save_training_data(data):
            # Also backup to GitHub
            asyncio.create_task(backup_to_github(data))
            
            await update.message.reply_text(
                f"✅ **Imported!**\n\n"
                f"{len(data)} charts imported.\n\n"
                f"Run `/training_stats` to verify.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to save imported data.", parse_mode='Markdown')
            
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Invalid JSON file.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Import failed: {e}", parse_mode='Markdown')


async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /train command — add structured training chart.
    OWNER ONLY.
    
    TRAINING MODE GUARD:
    - Sets training_active=True to block ALL other handlers
    - Only outputs minimal confirmation
    - Other handlers (photo, text) will see training mode and exit early
    
    Usage: /train [setup] [token] [timeframe] [outcome%] [notes...]
    Example: /train 618 SOL 15M 45 clean reclaim divergence
    
    Must be used as reply to a chart image or with recent image in chat.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # ══════════════════════════════════════════════
    # ACTIVATE TRAINING MODE — Block all other handlers
    # ══════════════════════════════════════════════
    set_training_mode(chat_id, True)
    logger.info(f"[TRAINING] === ENTER train_command === chat_id={chat_id}")
    
    try:
        if not is_owner(user_id):
            await update.message.reply_text("⛔ Owner only.", parse_mode='Markdown')
            return
        
        if len(context.args) < 4:
            await update.message.reply_text(
                "🎓 `/train [setup] [token] [timeframe] [outcome%] [notes]`\n"
                "Example: `/train 618 SOL 15M 45 clean reclaim`",
                parse_mode='Markdown'
            )
            return
        
        # Parse arguments
        setup_input = context.args[0]
        token = context.args[1].upper()
        timeframe = context.args[2].upper()
        
        try:
            outcome_pct = int(context.args[3].replace('%', '').replace('+', ''))
        except ValueError:
            await update.message.reply_text("❌ Invalid outcome%", parse_mode='Markdown')
            return
        
        notes = " ".join(context.args[4:]) if len(context.args) > 4 else ""
        
        # Get setup
        canonical_key, display_name = canonicalize_setup(setup_input)
        
        if not canonical_key:
            await update.message.reply_text(
                f"❓ Unknown setup: `{setup_input}`",
                parse_mode='Markdown'
            )
            return
        
        # Get image
        image_file_id = None
        
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            image_file_id = update.message.reply_to_message.photo[-1].file_id
        elif chat_id in user_images and user_images[chat_id]:
            image_file_id = user_images[chat_id]
        
        if not image_file_id:
            await update.message.reply_text("❌ No chart. Reply to image or upload first.", parse_mode='Markdown')
            return
        
        # Generate chart ID
        chart_id = generate_chart_id(canonical_key, token, timeframe)
        logger.info(f"[TRAINING] Generated chart_id: {chart_id}")
        
        # Build training data
        chart_data = {
            'chart_id': chart_id,
            'setup_name': display_name,
            'canonical_key': canonical_key,
            'token': token,
            'timeframe': timeframe,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'fib_depth': display_name.split()[0] if display_name else '',
            'structure_state': 'Trained',
            'rsi_behavior': '',
            'whale_conviction': False,
            'violent_mode': False,
            'outcome_percentage': outcome_pct,
            'expansion_time_minutes': 0,
            'screenshot_fingerprint_id': image_file_id,
            'notes': notes,
        }
        
        # Check for duplicates first
        is_dup, similar, score = check_duplicate(chart_data, threshold=0.85)
        
        if is_dup:
            similar_id = similar.get('chart_id', 'Unknown')
            await update.message.reply_text(
                f"⚠️ **Duplicate** ({int(score * 100)}%)\n"
                f"Similar: `{similar_id}`\n\n"
                f"A) `/train_force` — Keep both\n"
                f"B) Skip\n"
                f"C) `/train_variation` — Mark as variation\n"
                f"D) `/train_override` — Replace old with new",
                parse_mode='Markdown'
            )
            context.user_data['pending_training'] = chart_data
            context.user_data['similar_chart_id'] = similar_id  # Store for override
            logger.info(f"[TRAINING] Duplicate detected — awaiting user choice")
            return
        
        # Store training WITH AUTO-BACKUP TO GITHUB
        success, msg = store_training_chart(chart_data)
        logger.info(f"[TRAINING] Store result: success={success}, msg={msg}")
        
        # Trigger GitHub backup (non-blocking)
        if success:
            training_data = load_training_data()
            asyncio.create_task(backup_to_github(training_data))
        
        if success:
            # QUIET MODE — minimal output
            if TRAINING_QUIET_MODE:
                await update.message.reply_text(
                    f"✅ **Saved**\n"
                    f"`{chart_id}`\n"
                    f"{display_name} | {token} | {timeframe} | +{outcome_pct}%",
                    parse_mode='Markdown'
                )
            else:
                stats = get_training_stats()
                setup_count = stats.get(display_name, 0)
                await update.message.reply_text(
                    f"✅ **Training Chart Stored**\n\n"
                    f"**ID:** `{chart_id}`\n"
                    f"**Setup:** {display_name}\n"
                    f"**Token:** {token}\n"
                    f"**Timeframe:** {timeframe}\n"
                    f"**Outcome:** +{outcome_pct}%\n"
                    f"**Notes:** {notes or 'None'}\n\n"
                    f"_Progress: {display_name} — {setup_count}/5_",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(f"❌ Failed: {msg}", parse_mode='Markdown')
            
    finally:
        # ══════════════════════════════════════════════
        # DEACTIVATE TRAINING MODE — Allow other handlers again
        # ══════════════════════════════════════════════
        set_training_mode(chat_id, False)
        logger.info(f"[TRAINING] === EXIT train_command === chat_id={chat_id}")


async def train_force_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force store a training chart despite duplicate warning."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_owner(user_id):
        return
    
    # Activate training mode
    set_training_mode(chat_id, True)
    logger.info(f"[TRAINING] === ENTER train_force_command ===")
    
    try:
        pending = context.user_data.get('pending_training')
        
        if not pending:
            await update.message.reply_text("❌ No pending training.", parse_mode='Markdown')
            return
        
        # Mark as reinforcement
        pending['notes'] = f"[REINFORCEMENT] {pending.get('notes', '')}"
        
        success, msg = store_training_chart(pending)
        logger.info(f"[TRAINING] Force store: success={success}")
        
        # Trigger GitHub backup
        if success:
            training_data = load_training_data()
            asyncio.create_task(backup_to_github(training_data))
        
        if success:
            await update.message.reply_text(
                f"✅ **Reinforced**\n`{pending['chart_id']}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {msg}", parse_mode='Markdown')
        
        # Clear pending
        context.user_data.pop('pending_training', None)
        
    finally:
        set_training_mode(chat_id, False)
        logger.info(f"[TRAINING] === EXIT train_force_command ===")


async def train_variation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store a training chart as a variation case."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_owner(user_id):
        return
    
    # Activate training mode
    set_training_mode(chat_id, True)
    logger.info(f"[TRAINING] === ENTER train_variation_command ===")
    
    try:
        pending = context.user_data.get('pending_training')
        
        if not pending:
            await update.message.reply_text("❌ No pending training.", parse_mode='Markdown')
            return
        
        # Mark as variation
        pending['chart_id'] = pending['chart_id'].replace('-', '-VAR-', 1)
        pending['notes'] = f"[VARIATION] {pending.get('notes', '')}"
        
        success, msg = store_training_chart(pending)
        logger.info(f"[TRAINING] Variation store: success={success}")
        
        # Trigger GitHub backup
        if success:
            training_data = load_training_data()
            asyncio.create_task(backup_to_github(training_data))
        
        if success:
            await update.message.reply_text(
                f"✅ **Variation**\n`{pending['chart_id']}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {msg}", parse_mode='Markdown')
        
        # Clear pending
        context.user_data.pop('pending_training', None)
        
    finally:
        set_training_mode(chat_id, False)
        logger.info(f"[TRAINING] === EXIT train_variation_command ===")


async def train_override_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Override/replace an existing training chart with the new one.
    Deletes the old duplicate and saves the new chart in its place.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_owner(user_id):
        return
    
    # Activate training mode
    set_training_mode(chat_id, True)
    logger.info(f"[TRAINING] === ENTER train_override_command ===")
    
    try:
        pending = context.user_data.get('pending_training')
        similar_chart_id = context.user_data.get('similar_chart_id')
        
        if not pending:
            await update.message.reply_text("❌ No pending training.", parse_mode='Markdown')
            return
        
        # Delete the old chart
        if similar_chart_id:
            delete_success, delete_msg = delete_training_chart(similar_chart_id)
            logger.info(f"[TRAINING] Delete old chart: {delete_msg}")
        
        # Mark as override
        pending['notes'] = f"[OVERRIDE] {pending.get('notes', '')}"
        
        # Save the new chart
        success, msg = store_training_chart(pending)
        logger.info(f"[TRAINING] Override store: success={success}")
        
        # Trigger GitHub backup
        if success:
            training_data = load_training_data()
            asyncio.create_task(backup_to_github(training_data))
        
        if success:
            await update.message.reply_text(
                f"✅ **Replaced**\n"
                f"Old: `{similar_chart_id}`\n"
                f"New: `{pending['chart_id']}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {msg}", parse_mode='Markdown')
        
        # Clear pending
        context.user_data.pop('pending_training', None)
        context.user_data.pop('similar_chart_id', None)
        
    finally:
        set_training_mode(chat_id, False)
        logger.info(f"[TRAINING] === EXIT train_override_command ===")


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
            # Build human, collaborative, Wiz-native response
            response = build_memory_response(memory_data, username)
            
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "🧠 **Memory**\n\n"
                f"⚠️ Couldn't lock that in: {msg}\n\n"
                "Try again — keep it simple. 🔮",
                parse_mode='Markdown'
            )
        return
    
    # ══════════════════════════════════════════════
    # UNKNOWN INTENT — Default to PLANNED_SETUP (non-blocking)
    # /deep always proceeds with analysis
    # Jayce acts like a system-trader assistant, not a form
    # ══════════════════════════════════════════════
    if intent == "UNKNOWN":
        # Default to PLANNED_SETUP — analyze first, clarify later if needed
        intent = "PLANNED_SETUP"
    
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
        # STEP 2.5: LOOKUP SIMILAR MEMORIES (Deep Vision only)
        # Only after setup type is detected and structure confirmed
        # ══════════════════════════════════════════════
        wiz_setup_type = vision_result.get('wiz_setup_type', '')
        structure_quality = vision_result.get('structure_quality', '')
        
        # Only lookup if we have a confirmed setup type (not Unknown/Unclear)
        if wiz_setup_type and wiz_setup_type not in ['Unknown', 'Unclear', '']:
            similar_memories = get_similar_memories(wiz_setup_type, limit=1)
            
            # If we found a relevant memory, add it to vision_result
            if similar_memories:
                memory = similar_memories[0]  # Top 1 only
                memory_outcome = memory.get('outcome', '')
                memory_conditions = memory.get('conditions', '')
                
                # Build short reference (1-2 lines max)
                similar_note = f"This resembles a prior {wiz_setup_type} that {memory_outcome.lower()}"
                if memory_conditions and memory_conditions != 'standard conditions':
                    similar_note += f" with {memory_conditions}"
                similar_note += "."
                
                # Add to vision_result for response builder to use
                vision_result['similar_pattern_note'] = similar_note
        
        # ══════════════════════════════════════════════
        # STEP 2.6: PATTERN MATCHING ENGINE (Phase 3)
        # Compare against trained winners for data-backed confidence
        # ══════════════════════════════════════════════
        pattern_match_data = None
        outcome_prediction_data = None
        detected_conditions = {}
        
        if wiz_setup_type and wiz_setup_type not in ['Unknown', 'Unclear', '']:
            timeframe = vision_result.get('timeframe', '')
            token = vision_result.get('pair_detected', '')
            
            # Get pattern matches from training data
            pattern_match_data = get_pattern_matches(wiz_setup_type, timeframe, token)
            
            # Build pattern match text
            if pattern_match_data and pattern_match_data['total_trained'] > 0:
                pattern_match_text = build_pattern_match_text(pattern_match_data)
                vision_result['pattern_match_text'] = pattern_match_text
                vision_result['pattern_match_data'] = pattern_match_data
            
            # ══════════════════════════════════════════════
            # STEP 2.7: OUTCOME PREDICTION (Phase 4)
            # Condition-based outcome predictions from YOUR history
            # ══════════════════════════════════════════════
            
            # Detect conditions from user_plan text AND chart analysis
            detected_conditions = detect_conditions_from_text(user_plan)
            
            # Also check vision result for conditions (from chart image)
            jayce_take = vision_result.get('jayce_take', '')
            direct_answer = vision_result.get('direct_answer', '')
            structure_reasoning = vision_result.get('structure_reasoning', '')
            chart_text = f"{jayce_take} {direct_answer} {structure_reasoning}"
            chart_conditions = detect_conditions_from_text(chart_text)
            
            # Merge conditions (either source can detect)
            for cond in detected_conditions:
                if chart_conditions.get(cond, False):
                    detected_conditions[cond] = True
            
            # Get outcome prediction
            outcome_prediction_data = get_outcome_prediction(wiz_setup_type, detected_conditions)
            
            if outcome_prediction_data:
                outcome_prediction_text = build_outcome_prediction_text(outcome_prediction_data, detected_conditions)
                vision_result['outcome_prediction_text'] = outcome_prediction_text
                vision_result['outcome_prediction_data'] = outcome_prediction_data
                vision_result['detected_conditions'] = detected_conditions
        
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
        
        # ══════════════════════════════════════════════
        # STEP 4: SEND BEST MATCH CHART IMAGE (Phase 3)
        # Shows the most similar winning chart from training
        # ══════════════════════════════════════════════
        if pattern_match_data and pattern_match_data.get('best_match'):
            try:
                await send_best_match_chart(update, context, pattern_match_data['best_match'])
            except Exception as e:
                logger.error(f"Failed to send best match chart: {e}")
        
    except Exception as e:
        await thinking_msg.delete()
        logger.error(f"Deep analysis failed: {e}")
        await update.message.reply_text(
            f"⚠️ Deep Vision failed: {str(e)}",
            parse_mode='Markdown'
        )


def build_deep_analysis_response(vision: dict, user_plan: str, username: str = None) -> str:
    """
    Build formatted response from Deep Vision results.
    
    MANDATORY SECTIONS (all required):
    1. Structure State
    2. Setup Quality Rating
    3. Game Plan (Execution Logic)
    4. Invalidation Conditions
    5. Probability Framing (conditional, no fixed %)
    6. RSI Permission (not overbought/oversold)
    7. Jayce's Take
    """
    
    # Extract fields
    pair_detected = vision.get('pair_detected', '')
    wiz_setup_type = vision.get('wiz_setup_type', '')
    timeframe = vision.get('timeframe', '?')
    fib_level = vision.get('fib_level', '?')
    direct_answer = vision.get('direct_answer', '')
    jayce_take = vision.get('jayce_take', '')
    similar_pattern = vision.get('similar_pattern_note', '')
    confidence_statement = vision.get('confidence_statement', '')
    
    # New mandatory fields
    structure_state = vision.get('structure_state', 'Unknown')
    structure_reasoning = vision.get('structure_reasoning', '')
    setup_quality = vision.get('setup_quality', 'B')
    setup_quality_reasoning = vision.get('setup_quality_reasoning', '')
    game_plan = vision.get('game_plan', {})
    invalidation = vision.get('invalidation', {})
    probability_framing = vision.get('probability_framing', '')
    
    # RSI fields (new format)
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_zone = vision.get('rsi_zone', '')
    rsi_permission = vision.get('rsi_permission', '')
    rsi_insight = vision.get('rsi_insight', '')
    
    # Momentum
    momentum_health = vision.get('momentum_health', '')
    momentum_insight = vision.get('momentum_insight', '')
    
    # Divergence (new fields)
    divergence_detected = vision.get('divergence_detected', False)
    divergence_at_structure = vision.get('divergence_at_structure', False)
    divergence_type = vision.get('divergence_type', '')
    divergence_location = vision.get('divergence_location', '')
    divergence_impact = vision.get('divergence_impact', '')
    
    # Conflict
    conflict_detected = vision.get('conflict_detected', False)
    conflict_detail = vision.get('conflict_detail', '')
    
    # Build response
    response_parts = []
    
    # ══════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════
    if pair_detected and pair_detected != 'Unable to detect':
        response_parts.append(f"🔮 **JAYCE** — 🪙 {pair_detected}\n")
    else:
        response_parts.append(f"🔮 **JAYCE**\n")
    
    if wiz_setup_type and wiz_setup_type != 'Unknown':
        response_parts.append(f"📐 **{wiz_setup_type}** | {timeframe}\n")
    
    # ══════════════════════════════════════════════
    # DIRECT ANSWER (answer user's question first)
    # ══════════════════════════════════════════════
    if direct_answer:
        response_parts.append(f"\n{direct_answer}\n")
    
    # ══════════════════════════════════════════════
    # CONFLICT WARNING (if any)
    # ══════════════════════════════════════════════
    if conflict_detected and conflict_detail:
        response_parts.append(f"\n⚠️ **Heads up:** {conflict_detail}\n")
    
    # ══════════════════════════════════════════════
    # 1. STRUCTURE STATE (MANDATORY)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n🧱 **Structure State:** {structure_state}")
    if structure_reasoning:
        response_parts.append(f"\n_{structure_reasoning}_")
    
    # ══════════════════════════════════════════════
    # 2. SETUP QUALITY (MANDATORY)
    # ══════════════════════════════════════════════
    quality_emoji = "🟢" if setup_quality == "A" else "🟡" if setup_quality == "B" else "🔴"
    response_parts.append(f"\n\n{quality_emoji} **Setup Quality:** {setup_quality}")
    if setup_quality_reasoning:
        response_parts.append(f"\n_{setup_quality_reasoning}_")
    
    # ══════════════════════════════════════════════
    # 3. GAME PLAN (MANDATORY)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n📋 **Game Plan:**")
    if game_plan:
        entry = game_plan.get('entry', game_plan.get('entry_type', 'Limit at zone'))
        hold_upgrade = game_plan.get('hold_upgrade_trigger', game_plan.get('reclaim_expectation', game_plan.get('confirmation_trigger', '')))
        partial_tp = game_plan.get('partial_tp', '')
        continuation = game_plan.get('continuation_logic', '')
        
        response_parts.append(f"\n• **Entry:** {entry}")
        if hold_upgrade:
            response_parts.append(f"\n• **Hold upgrades when:** {hold_upgrade}")
        if partial_tp:
            response_parts.append(f"\n• **Partial TP:** {partial_tp}")
        if continuation:
            response_parts.append(f"\n• **Continuation:** {continuation}")
    else:
        response_parts.append(f"\n• Entry valid at zone — edge identified")
        response_parts.append(f"\n• Hold confidence increases when buyers defend the level")
    
    # ══════════════════════════════════════════════
    # 4. INVALIDATION (MANDATORY)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n🚫 **Invalidation:**")
    if invalidation:
        price_inv = invalidation.get('price_based', '')
        behavior_inv = invalidation.get('behavior_based', '')
        
        if price_inv:
            response_parts.append(f"\n• **Price:** {price_inv}")
        if behavior_inv:
            response_parts.append(f"\n• **Behavior:** {behavior_inv}")
    else:
        response_parts.append(f"\n_Define your invalidation before entry_")
    
    # ══════════════════════════════════════════════
    # 5. PROBABILITY FRAMING (MANDATORY — NO FIXED %)
    # ══════════════════════════════════════════════
    if probability_framing:
        response_parts.append(f"\n\n🎯 **Probability:**\n_{probability_framing}_")
    
    # ══════════════════════════════════════════════
    # 6. RSI PERMISSION (MANDATORY — NOT overbought/oversold)
    # ══════════════════════════════════════════════
    response_parts.append(f"\n\n📈 **RSI Permission:**")
    if rsi_reading and rsi_reading != 'Not visible':
        response_parts.append(f"\n• RSI: {rsi_reading}")
        if rsi_zone:
            response_parts.append(f" ({rsi_zone})")
        if rsi_permission:
            response_parts.append(f"\n• **{rsi_permission}**")
        if rsi_insight:
            response_parts.append(f"\n_{rsi_insight}_")
    else:
        response_parts.append(f"\n_RSI not visible on chart_")
    
    # ══════════════════════════════════════════════
    # MOMENTUM (supporting context)
    # ══════════════════════════════════════════════
    if momentum_health or momentum_insight:
        response_parts.append(f"\n\n⚡ **Momentum:** {momentum_health}")
        if momentum_insight:
            response_parts.append(f"\n_{momentum_insight}_")
    
    # ══════════════════════════════════════════════
    # DIVERGENCE (only if at structure — Wiz Theory rules)
    # Analyzed LAST, after Structure and RSI Permission
    # Only shown if divergence_at_structure is true
    # ══════════════════════════════════════════════
    if divergence_detected and divergence_at_structure and divergence_type and divergence_type != 'None':
        response_parts.append(f"\n\n📐 **Divergence at Structure:** {divergence_type}")
        if divergence_location:
            response_parts.append(f"\n_Location: {divergence_location}_")
        if divergence_impact:
            response_parts.append(f"\n_{divergence_impact}_")
        else:
            # Default Wiz Theory framing if no specific impact provided
            response_parts.append(f"\n_This adjusts expansion expectations, not the thesis. Secure more conservatively if structure holds._")
    
    # ══════════════════════════════════════════════
    # PATTERN MATCH (Phase 3 — Training Data Comparison)
    # ══════════════════════════════════════════════
    pattern_match_text = vision.get('pattern_match_text', '')
    if pattern_match_text:
        response_parts.append(f"\n\n{pattern_match_text}")
    
    # ══════════════════════════════════════════════
    # OUTCOME PREDICTION (Phase 4 — Condition-Based)
    # ══════════════════════════════════════════════
    outcome_prediction_text = vision.get('outcome_prediction_text', '')
    if outcome_prediction_text:
        response_parts.append(f"\n\n{outcome_prediction_text}")
    
    # ══════════════════════════════════════════════
    # SIMILAR PATTERN (from memory — legacy)
    # ══════════════════════════════════════════════
    # Only show if no pattern match from training data
    if similar_pattern and not pattern_match_text:
        response_parts.append(f"\n\n🧠 **Similar Pattern:**\n_{similar_pattern}_")
    
    # ══════════════════════════════════════════════
    # 7. JAYCE'S TAKE (execution-focused)
    # ══════════════════════════════════════════════
    if jayce_take:
        response_parts.append(f"\n\n💭 **My take:** {jayce_take}")
    
    # ══════════════════════════════════════════════
    # CONFIDENCE (conditional)
    # ══════════════════════════════════════════════
    if confidence_statement:
        response_parts.append(f"\n\n_{confidence_statement}_")
    
    # ══════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════
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


async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /save command — Save setup WITHOUT analysis
    
    Usage:
        /save 618 flip zone
        /save under-fib
        /save .786
        
    When used with a photo, saves the chart as a setup reference.
    Does NOT run any analysis.
    """
    chat_id = update.effective_chat.id
    
    # Get setup name from args
    setup_input = " ".join(context.args) if context.args else ""
    
    # Get username
    username = None
    if update.effective_user:
        username = update.effective_user.first_name or update.effective_user.username
    
    # Check if replying to a photo or if there's a recent image
    image_file_id = None
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]
    
    # Canonicalize the setup name
    canonical_key, display_name = canonicalize_setup(setup_input)
    
    if not canonical_key:
        await update.message.reply_text(
            "🔒 **Save Setup**\n\n"
            "Please specify a setup type:\n\n"
            "`/save 618 flip zone`\n"
            "`/save under-fib`\n"
            "`/save .786`\n"
            "`/save 50 fz`\n\n"
            "_Attach a chart or reply to one for best results._",
            parse_mode='Markdown'
        )
        return
    
    # Build memory data
    memory_data = {
        'setup_type': display_name,
        'canonical_key': canonical_key,
        'outcome': 'Saved for reference',
        'outcome_pct': 0,
        'conditions': 'reference save',
        'resolution': 'normal',
        'user_text': setup_input,
        'timestamp': datetime.now().isoformat(),
    }
    
    if image_file_id:
        memory_data['image_file_id'] = image_file_id
    
    # Store the memory
    success, msg = store_memory(memory_data)
    
    if success:
        image_note = "📸 _Chart attached_" if image_file_id else "📝 _No chart attached_"
        await update.message.reply_text(
            f"🔒 **Setup locked**\n\n"
            f"**{display_name}** saved to WizTheory memory\n"
            f"{image_note}\n\n"
            f"🧙‍♂️ _Use `/memory` to recall saved setups._",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"⚠️ Couldn't save: {msg}",
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
        "**Analysis Commands:**\n"
        "`/jayce [plan]` — Chart evaluation\n"
        "`/deep [plan]` — Deep Vision analysis\n"
        "`/valid` — Quick validity check\n"
        "`/violent` — Violent Mode assessment\n\n"
        "**Save & Recall:**\n"
        "`/save [setup]` — Save setup with chart 📸\n"
        "`/memory` — View saved setups\n"
        "`/similar [setup]` — Show saved chart images\n\n"
        "**Reference Commands:**\n"
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
    Handle uploaded photos with proper intent detection.
    
    INTENT PRIORITY (highest to lowest):
    0. TRAINING MODE — If active, store image and EXIT (no other processing)
    1. SAVE — /save, "save setup", "lock setup" → Save ONLY, no analysis
    2. DEEP ANALYSIS — /deep → Deep Vision
    3. LITE ANALYSIS — /jayce, "analyze", "scan" → Lite Vision
    4. SILENT — No trigger → Store image, no response
    
    WAKE RULES:
    - Bot only responds when valid command OR "Jayce" is mentioned
    - Save commands override ALL analysis
    - Training mode blocks ALL other handlers
    """
    chat_id = update.effective_chat.id
    image_file_id = update.message.photo[-1].file_id
    user_images[chat_id] = image_file_id

    # ══════════════════════════════════════════════
    # TRAINING MODE GUARD — Block ALL other processing
    # ══════════════════════════════════════════════
    if is_training_active(chat_id):
        logger.info(f"[TRAINING] Photo received during training mode — stored, no analysis")
        return  # Store image but do NOTHING else

    caption = update.message.caption if update.message.caption else ""
    caption_lower = caption.lower()
    
    # Get username for responses
    username = None
    if update.effective_user:
        username = update.effective_user.first_name or update.effective_user.username

    # ══════════════════════════════════════════════
    # INTENT 1: SAVE MODE (highest priority)
    # Save triggers override ALL analysis
    # ══════════════════════════════════════════════
    save_triggers = [
        '/save', '/save_setup', '/savesetup',
        'save setup', 'save this setup', 'save the setup',
        'lock setup', 'lock this setup', 'lock the setup',
        'jayce save', 'jayce lock',
        'lock this in', 'lock it in', 'lock in as',
        'save this as', 'save as', 'remember this as',
        'store this', 'log this'
    ]
    
    is_save_intent = any(trigger in caption_lower for trigger in save_triggers)
    
    if is_save_intent:
        # Extract setup name using canonicalizer
        canonical_key, display_name = canonicalize_setup(caption)
        
        if canonical_key:
            # Save to memory with canonical key
            memory_data = {
                'setup_type': display_name,
                'canonical_key': canonical_key,
                'outcome': 'Saved for reference',
                'outcome_pct': 0,
                'conditions': 'reference save',
                'resolution': 'normal',
                'user_text': caption,
                'timestamp': datetime.now().isoformat(),
                'image_file_id': image_file_id  # Store image reference
            }
            
            success, msg = store_memory(memory_data)
            
            if success:
                await update.message.reply_text(
                    f"🔒 **Setup locked**\n\n"
                    f"**{display_name}** saved to WizTheory memory\n\n"
                    f"🧙‍♂️ _Use `/memory` to recall saved setups._",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"⚠️ Couldn't save: {msg}",
                    parse_mode='Markdown'
                )
        else:
            # Setup name not recognized — ask for clarification
            await update.message.reply_text(
                "🔒 **Save Setup**\n\n"
                "I couldn't identify the setup type.\n\n"
                "Please specify, e.g.:\n"
                "`/save 618 flip zone`\n"
                "`/save under-fib`\n"
                "`/save .786`",
                parse_mode='Markdown'
            )
        return  # Exit — do NOT run analysis
    
    # ══════════════════════════════════════════════
    # INTENT 2 & 3: ANALYSIS MODE
    # Only if NOT a save intent
    # ══════════════════════════════════════════════
    
    # Check for explicit analysis triggers
    analysis_triggers = [
        '/jayce', '/analyze', '/valid', '/violent', '/deep',
        'jayce analyze', 'jayce check', 'jayce look', 'jayce scan',
        'analyze this', 'scan this', 'check this'
    ]
    
    # Wake triggers (Jayce must be mentioned for non-command analysis)
    wake_triggers = [
        'jayce', 'yo jayce', 'hey jayce', '@jayce'
    ]
    
    is_analysis_intent = any(trigger in caption_lower for trigger in analysis_triggers)
    is_wake = any(trigger in caption_lower for trigger in wake_triggers)
    
    # Only analyze if explicitly requested
    if is_analysis_intent or (is_wake and not is_save_intent):
        # Check for deep request
        if '/deep' in caption_lower or 'jayce deep' in caption_lower or 'deep vision' in caption_lower:
            if vision_state['deep_enabled']:
                await run_deep_analysis(update, context, image_file_id, caption)
            else:
                await update.message.reply_text(
                    "🔮 **Deep Vision** is currently disabled.",
                    parse_mode='Markdown'
                )
        else:
            # Lite analysis
            await analyze_chart(update, context, image_file_id, caption)
    else:
        # No trigger — remain SILENT (image stored for later use)
        pass


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle natural language triggers.
    
    INTENT PRIORITY (highest to lowest):
    0. TRAINING MODE — If active, EXIT (no processing)
    1. SAVE — "save setup", "lock setup", "jayce save" → Save ONLY
    2. ANALYSIS — "analyze", "scan", "deep" → Run analysis
    3. INTRO — "who is jayce" → Show intro
    4. SILENT — No trigger → No response
    
    WAKE RULES:
    - Bot only responds when valid command OR "Jayce" is mentioned
    - Training mode blocks ALL other handlers
    """
    text = update.message.text.lower()
    full_text = update.message.text
    chat_id = update.effective_chat.id

    # ══════════════════════════════════════════════
    # TRAINING MODE GUARD — Block ALL other processing
    # ══════════════════════════════════════════════
    if is_training_active(chat_id):
        logger.info(f"[TRAINING] Text message during training mode — ignored")
        return  # Do NOTHING during training mode

    # ══════════════════════════════════════════════
    # INTENT 1: SAVE MODE (highest priority)
    # Save triggers override ALL analysis
    # ══════════════════════════════════════════════
    save_triggers = [
        'save setup', 'save this setup', 'save the setup',
        'lock setup', 'lock this setup', 'lock the setup',
        'jayce save', 'jayce lock',
        'lock this in', 'lock it in', 'lock in as',
        'save this as', 'save as', 'remember this as',
        'store this', 'log this'
    ]
    
    is_save_intent = any(trigger in text for trigger in save_triggers)
    
    if is_save_intent:
        # Get username
        username = None
        if update.effective_user:
            username = update.effective_user.first_name or update.effective_user.username
        
        # Get image if available
        image_file_id = user_images.get(chat_id)
        
        # Use canonicalizer
        canonical_key, display_name = canonicalize_setup(full_text)
        
        if canonical_key:
            memory_data = {
                'setup_type': display_name,
                'canonical_key': canonical_key,
                'outcome': 'Saved for reference',
                'outcome_pct': 0,
                'conditions': 'reference save',
                'resolution': 'normal',
                'user_text': full_text,
                'timestamp': datetime.now().isoformat(),
            }
            if image_file_id:
                memory_data['image_file_id'] = image_file_id
            
            success, msg = store_memory(memory_data)
            
            if success:
                image_note = "📸 _Chart attached_" if image_file_id else ""
                await update.message.reply_text(
                    f"🔒 **Setup locked**\n\n"
                    f"**{display_name}** saved to WizTheory memory\n"
                    f"{image_note}\n\n"
                    f"🧙‍♂️ _Use `/memory` to recall saved setups._",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"⚠️ Couldn't save: {msg}",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                "🔒 **Save Setup**\n\n"
                "I couldn't identify the setup type.\n\n"
                "Please specify, e.g.:\n"
                "`jayce save 618 flip zone`\n"
                "`jayce lock under-fib`",
                parse_mode='Markdown'
            )
        return  # Exit — do NOT run analysis

    # ══════════════════════════════════════════════
    # INTRO CHECK
    # ══════════════════════════════════════════════
    intro_triggers = [
        'introduce yourself', 'introduce urself',
        'who are you', 'who is jayce', 'what can you do'
    ]

    if any(trigger in text for trigger in intro_triggers):
        await intro_command(update, context)
        return

    # ══════════════════════════════════════════════
    # WAKE CHECK — Must mention Jayce for analysis
    # ══════════════════════════════════════════════
    wake_triggers = [
        'jayce', 'hey jayce', 'yo jayce', '@jayce'
    ]

    jayce_invoked = any(trigger in text for trigger in wake_triggers)

    if not jayce_invoked:
        return  # Silent — Jayce not mentioned

    # ══════════════════════════════════════════════
    # INTENT 2: ANALYSIS MODE
    # Only if Jayce invoked AND analysis requested
    # ══════════════════════════════════════════════
    analysis_triggers = [
        'analyze', 'scan', 'check', 'look', 'deep',
        'what you think', 'thoughts', 'valid'
    ]
    
    is_analysis_intent = any(trigger in text for trigger in analysis_triggers)
    
    if not is_analysis_intent:
        # Jayce mentioned but no clear action — show help
        await update.message.reply_text(
            "🧙‍♂️ Hey! What do you need?\n\n"
            "`jayce analyze` — Chart analysis\n"
            "`jayce deep` — Deep Vision\n"
            "`jayce save [setup]` — Save setup\n"
            "`/help` — All commands",
            parse_mode='Markdown'
        )
        return

    # Check for deep request
    if 'deep' in text:
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

    # Lite analysis
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
    
    # Save & Memory commands
    application.add_handler(CommandHandler("save", save_command))
    application.add_handler(CommandHandler("similar", similar_command))
    
    # Training commands (Owner only)
    application.add_handler(CommandHandler("train", train_command))
    application.add_handler(CommandHandler("train_force", train_force_command))
    application.add_handler(CommandHandler("train_variation", train_variation_command))
    application.add_handler(CommandHandler("train_override", train_override_command))
    application.add_handler(CommandHandler("training_log", training_log_command))
    application.add_handler(CommandHandler("training_stats", training_stats_command))
    application.add_handler(CommandHandler("check_duplicate", check_duplicate_command))
    
    # Training backup commands (Owner only)
    application.add_handler(CommandHandler("training_export", training_export_command))
    application.add_handler(CommandHandler("training_import", training_import_command))
    application.add_handler(CommandHandler("training_restore", training_restore_command))

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

    # Log data directory location
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info(f"Training file: {TRAINING_FILE}")

    # ══════════════════════════════════════════════
    # AUTO-RESTORE TRAINING DATA ON STARTUP
    # ══════════════════════════════════════════════
    # If local training data is empty, auto-restore from GitHub
    # This ensures data survives deploys without manual intervention
    
    async def auto_restore_training(app):
        """Auto-restore training data from GitHub if local is empty."""
        logger.info("[STARTUP] Checking training data...")
        
        local_data = load_training_data()
        
        if local_data:
            logger.info(f"[STARTUP] Local training data found: {len(local_data)} charts ✅")
            # Backup to GitHub to keep it synced
            await backup_to_github(local_data)
        else:
            logger.info("[STARTUP] Local training data EMPTY — attempting auto-restore from GitHub...")
            
            if GITHUB_TOKEN:
                success, msg, data = await restore_from_github()
                
                if success and data:
                    if save_training_data(data):
                        logger.info(f"[STARTUP] ✅ Auto-restored {len(data)} charts from GitHub!")
                    else:
                        logger.error("[STARTUP] ❌ Failed to save restored data locally")
                else:
                    logger.warning(f"[STARTUP] No GitHub backup found or restore failed: {msg}")
            else:
                logger.warning("[STARTUP] GITHUB_TOKEN not set — cannot auto-restore")
    
    # Register the startup callback
    application.post_init = auto_restore_training

    logger.info("Starting Jayce Bot with Vision + Memory + Training...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
