import os
from pathlib import Path
import asyncio
import logging
import base64
import anthropic
import json
import sqlite3
from ops_helpers import ops_start_cycle, ops_end_cycle, ops_log_token, ops_log_scoring, ops_log_flashcard, ops_log_alert, ops_log_error
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import math
import random

# v4.1: Import WizTheory detection engines
from engines import run_detection, format_engine_result_text, cleanup_engine_cooldowns
from candle_provider import fetch_candles
from hybrid_intake import run_hybrid_intake, stage2_metadata_filter
from alert_tracker import log_alert
# PSEF and Candle Intelligence modules
try:
    from psef import run_psef
    from candle_intelligence import analyze_candles, get_candle_summary, detect_flip_zones
    from structure_engine import analyze_structure
    from rsi_memory import analyze_rsi_full, analyze_rsi
    from setup_grader import grade_setup, quick_grade_summary, should_realert
    from bangers_pipeline import run_bangers_analysis, format_alert_message
    from impulse_detector import detect_wiztheory_setup
    from chart_intelligence import analyze_chart_intelligence, analyze_chart_intelligence_with_prime, check_prime_setup_condition, analyze_pullback_quality, detect_setup_maturity, analyze_momentum_behavior, analyze_full_intelligence
    from runner_intelligence import analyze_runner_intelligence, format_runner_log
    from scan_monitor import send_scan_monitor_simple
    from token_validator import validate_tokens_batch
    from structural_prescan import structural_prescan, run_prescan_batch, ScanBucket, quick_filter
    from flashcard_vision import analyze_with_flashcards, get_usage_stats
    from setup_watch import check_setup_watch, format_setup_watch_message, clear_old_alerts
    PSEF_ENABLED = False  # Disabled - validators handle quality
except ImportError as e:
    print(f"Warning: PSEF/Candle modules not loaded: {e}")
    PSEF_ENABLED = False

def format_wiztheory_alert(token: Dict, bangers_result: Dict, impulse_result: Dict, 
                           vision_result: Dict = None) -> str:
    """Format full WizTheory breakdown alert message."""
    
    symbol = token.get('symbol', '???')
    setup_type = bangers_result.get('wiz_setup_type', 'Unknown')
    grade = bangers_result.get('grade', '?')
    score = bangers_result.get('score', 0)
    
    # Get breakdown components
    breakdown = bangers_result.get('breakdown', {})
    
    # Impulse data
    impulse_data = impulse_result.get('impulse', {})
    expansion_pct = impulse_data.get('expansion_pct', 0)
    impulse_bonus = bangers_result.get('impulse_bonus', 0)
    
    # Structure
    structure = bangers_result.get('structure', {})
    struct_trend = structure.get('trend', 'UNKNOWN')
    struct_grade = structure.get('grade', 'C')
    struct_points = breakdown.get('structure', {}).get('points', 0)
    
    # RSI
    rsi_data = bangers_result.get('rsi', {})
    rsi_label = rsi_data.get('memory_state', 'UNKNOWN')
    rsi_points = breakdown.get('rsi_memory', {}).get('points', 0)
    
    # Candles
    candle_data = bangers_result.get('candles', {})
    candle_char = candle_data.get('character', 'UNKNOWN')
    candle_points = breakdown.get('candle_quality', {}).get('points', 0)
    
    # Vision
    vision_similarity = 0
    vision_bonus = 0
    if vision_result and vision_result.get('ran_vision'):
        vision_similarity = vision_result.get('similarity', 0)
        vision_bonus = vision_result.get('bonus_points', 0)
    
    # Levels
    flip_zone = impulse_result.get('flip_zone', {})
    entry_zone = flip_zone.get('origin', 0)
    current_price = token.get('price', 0)
    
    # Format price helper
    def fmt_price(p):
        if not p or p == 0:
            return "N/A"
        if p >= 1:
            return f"${p:,.4f}"
        elif p >= 0.001:
            return f"${p:.6f}"
        else:
            return f"${p:.10f}"
    
    # Build impulse line
    impulse_line = f"⚡ Impulse: {expansion_pct:.0f}% expansion"
    if impulse_bonus > 0:
        impulse_line += f" (+{impulse_bonus} bonus)"
    
    # Build vision line
    vision_line = f"👁 Vision: {vision_similarity:.0f}% similarity"
    if vision_bonus > 0:
        vision_line += f" (+{vision_bonus} bonus)"
    
    # Get token address for links
    token_address = token.get('address') or token.get('token_address', '')
    pair_address = token.get('pair_address', '')
    
    message = f"""🚨 <b>WIZTHEORY ALERT</b>: ${symbol}

🧠 Setup: {setup_type} + Flip Zone
🏆 Grade: {grade}
📊 Score: {score}

━━━━━━━━━━━━━━━━━━━━

📈 <b>Breakdown</b>

{impulse_line}
🧱 Structure: {struct_trend} ({struct_points}/30)
🧠 RSI: {rsi_label} ({rsi_points}/8)
🕯 Candles: {candle_char} ({candle_points}/15)
{vision_line}

━━━━━━━━━━━━━━━━━━━━

📍 <b>Levels</b>

🎯 Entry Zone: {fmt_price(entry_zone)}
💰 Current Price: {fmt_price(current_price)}

━━━━━━━━━━━━━━━━━━━━

🔎 <b>Chart Links</b>

📊 <a href="https://dexscreener.com/solana/{pair_address or token_address}">DexScreener</a>
🛰 <a href="https://birdeye.so/token/{token_address}?chain=solana">Birdeye</a>"""
    
    return message


# Whale tokens from whale_watchlist
def fetch_whale_tokens():
    """Fetch active whale tokens that haven't been processed recently."""
    import sqlite3
    try:
        conn = sqlite3.connect('/opt/jayce/data/queue.db')
        c = conn.cursor()
        # Get whale tokens that aren't expired and haven't been scanned in last 5 minutes
        c.execute("""
            SELECT token_address, pair_address, symbol, whale_wallet, buy_amount_sol, scan_count
            FROM whale_watchlist 
            WHERE expired = 0 
            AND (last_scan IS NULL OR datetime(last_scan) < datetime('now', '-5 minutes'))
            ORDER BY timestamp DESC
            LIMIT 20
        """)
        rows = c.fetchall()
        conn.close()
        
        tokens = []
        for row in rows:
            tokens.append({
                'address': row[0],
                'token_address': row[0],
                'pair_address': row[1],
                'symbol': row[2],
                'whale_wallet': row[3],
                'buy_amount_sol': row[4],
                'scan_count': row[5],
                'source': 'WHALE'
            })
        return tokens
    except Exception as e:
        print(f"Whale fetch error: {e}")
        return []

def mark_whale_scanned(token_address):
    """Update last_scan time and increment scan_count for whale token."""
    import sqlite3
    try:
        conn = sqlite3.connect('/opt/jayce/data/queue.db')
        c = conn.cursor()
        c.execute("""
            UPDATE whale_watchlist 
            SET last_scan = datetime('now'), scan_count = scan_count + 1
            WHERE token_address = ?
        """, (token_address,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Mark whale scanned error: {e}")

def expire_whale_token(token_address):
    """Mark whale token as expired (stop scanning)."""
    import sqlite3
    try:
        conn = sqlite3.connect('/opt/jayce/data/queue.db')
        c = conn.cursor()
        c.execute("UPDATE whale_watchlist SET expired = 1 WHERE token_address = ?", (token_address,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Expire whale error: {e}")

# Volume tokens now come from volume_scraper via queue database
def fetch_volume_from_queue():
    import sqlite3
    QUEUE_DB = '/opt/jayce/data/queue.db'
    tokens = []
    counts = {'VOL_5M': 0, 'VOL_1H': 0}
    try:
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        c.execute("SELECT symbol, pair_address, source, rank, url FROM token_queue WHERE source IN ('VOL_5M', 'VOL_1H') AND processed=0 ORDER BY source, rank LIMIT 100")
        rows = c.fetchall()
        for r in rows:
            tokens.append({'symbol': r[0], 'pair_address': r[1], 'address': '', 'source': r[2], 'rank': r[3], 'url': r[4], 'dex': ''})
            if r[2] == 'VOL_5M':
                counts['VOL_5M'] += 1
            else:
                counts['VOL_1H'] += 1
        conn.close()
    except Exception as e:
        print(f"Queue read error: {e}")
    return tokens, counts
from scan_visibility import log_cycle_start, log_sources, log_filters, log_final, log_engine_results, log_cycle_end

# ══════════════════════════════════════════════════════════════════════════════
# JAYCE SCANNER v4.2 — STABILITY + PERFORMANCE BASELINE
# ══════════════════════════════════════════════════════════════════════════════
# Changes from v4.1:
#   1. Performance logging (per-cycle + 24h summary)
#   2. Heartbeat system (Telegram health checks)
#   3. Scraping stability (rate limits, retries, pacing)
#   4. Structured error logging
#   5. Environment comparison flag (RAILWAY vs VPS)
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLES
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# v4.2: Environment flag for Railway vs VPS comparison
ENVIRONMENT = os.getenv('ENVIRONMENT', 'railway').upper()

# v4.2: Heartbeat settings
HEARTBEAT_CHAT_ID = os.getenv('HEARTBEAT_CHAT_ID', TELEGRAM_CHAT_ID)  # Can be separate private channel
HEARTBEAT_INTERVAL_MINUTES = int(os.getenv('HEARTBEAT_INTERVAL_MINUTES', 10))

# v4.1: Jayce Bot token for accessing flashcard images
JAYCE_BOT_TOKEN = os.getenv('JAYCE_BOT_TOKEN', '8235602450:AAG9g__NmneEhBTTwcJgiQpqOwZere6FQc0')

CHARTS_PER_SCAN = int(os.getenv('CHARTS_PER_SCAN', 70))
MIN_MARKET_CAP = int(os.getenv('MIN_MARKET_CAP', 100000))
MIN_LIQUIDITY = int(os.getenv('MIN_LIQUIDITY', 10000))
MIN_COIN_AGE_HOURS = float(os.getenv('MIN_COIN_AGE_HOURS', 3))  # Minimum 3 hours old
MIN_CANDLES = int(os.getenv('MIN_CANDLES', 36))  # 36 candles = 3 hours on 5M chart
IMPULSE_H24_THRESHOLD = float(os.getenv('IMPULSE_H24_THRESHOLD', 40))
IMPULSE_H6_THRESHOLD = float(os.getenv('IMPULSE_H6_THRESHOLD', 25))
IMPULSE_H1_THRESHOLD = float(os.getenv('IMPULSE_H1_THRESHOLD', 15))
FRESH_RUNNER_H1_THRESHOLD = float(os.getenv('FRESH_RUNNER_H1_THRESHOLD', 25))
WATCHLIST_DURATION_HOURS = int(os.getenv('WATCHLIST_DURATION_HOURS', 72))
POST_IMPULSE_H1_MIN = float(os.getenv('POST_IMPULSE_H1_MIN', -20))
POST_IMPULSE_H1_MAX = float(os.getenv('POST_IMPULSE_H1_MAX', 10))
DAILY_VISION_CAP = int(os.getenv('DAILY_VISION_CAP', 250))
TOP_MOVERS_INTERVAL = int(os.getenv('TOP_MOVERS_INTERVAL', 5))

ALERTS_ENABLED = os.getenv('ALERTS_ENABLED', 'true').lower() == 'true'
SCANNER_PAUSED = False
LAST_TELEGRAM_UPDATE_ID = 0

SCORE_FORMING = int(os.getenv('SCORE_FORMING', 40))
SCORE_VALID = int(os.getenv('SCORE_VALID', 55))
SCORE_CONFIRMED = int(os.getenv('SCORE_CONFIRMED', 70))
# PHASE 2: Two-Tier Alert System
FORMING_THRESHOLD = int(os.getenv('FORMING_THRESHOLD', 40))
CONFIRMED_THRESHOLD = int(os.getenv('CONFIRMED_THRESHOLD', 50))
VISION_MIN_GRADE = os.getenv('VISION_MIN_GRADE', 'B')
ALERT_COOLDOWN_MINUTES = int(os.getenv('ALERT_COOLDOWN_MINUTES', 120))
TOP_RANKED_LIMIT = int(os.getenv('TOP_RANKED_LIMIT', 150))
VOLUME_5M_LIMIT = int(os.getenv('VOLUME_5M_LIMIT', 30))
VOLUME_1H_LIMIT = int(os.getenv('VOLUME_1H_LIMIT', 30))
FORMING_CHAT_ID = os.getenv('HEARTBEAT_CHAT_ID', '')  # Use your private chat for FORMING alerts

def should_run_vision(engine_grade: str) -> bool:
    """Only run Vision if engine grade meets minimum threshold"""
    grade_order = ['C', 'B', 'B+', 'A', 'A+']
    if not engine_grade:
        return False
    min_grade = VISION_MIN_GRADE
    try:
        return grade_order.index(engine_grade) >= grade_order.index(min_grade)
    except ValueError:
        return False



# File-based pause control (bot.py creates/removes this file)
SCANNER_PAUSE_FILE = Path("/opt/jayce/data/scanner_paused.flag")
def is_scanner_paused():
    return SCANNER_PAUSE_FILE.exists()

ENGINE_WEIGHT = float(os.getenv('ENGINE_WEIGHT', 0.4))
VISION_WEIGHT = float(os.getenv('VISION_WEIGHT', 0.4))
PATTERN_WEIGHT = float(os.getenv('PATTERN_WEIGHT', 0.2))

DEDUP_FORMING_HOURS = int(os.getenv('DEDUP_FORMING_HOURS', 3))
DEDUP_VALID_HOURS = int(os.getenv('DEDUP_VALID_HOURS', 9))
DEDUP_CONFIRMED_HOURS = int(os.getenv('DEDUP_CONFIRMED_HOURS', 24))

CHART_TIMEFRAME = os.getenv('CHART_TIMEFRAME', '5M')
VISION_COOLDOWN_MINUTES = int(os.getenv('VISION_COOLDOWN_MINUTES', 45))
COOLDOWN_H1_OVERRIDE_DELTA = float(os.getenv('COOLDOWN_H1_OVERRIDE_DELTA', 10))
COOLDOWN_VOLUME_SPIKE_MULT = float(os.getenv('COOLDOWN_VOLUME_SPIKE_MULT', 2.0))

GITHUB_REPO = os.getenv('GITHUB_REPO', 'wizsol94/jayce-bot')
GITHUB_BACKUP_PATH = os.getenv('GITHUB_BACKUP_PATH', 'backups/jayce_training_dataset.json')
TRAINING_REFRESH_HOURS = int(os.getenv('TRAINING_REFRESH_HOURS', 6))

# v4.1: Flashcard training settings
FLASHCARD_EXAMPLES_PER_SETUP = int(os.getenv('FLASHCARD_EXAMPLES_PER_SETUP', 100))
FLASHCARD_CACHE_HOURS = int(os.getenv('FLASHCARD_CACHE_HOURS', 24))

TRAINED_SETUPS = {
    '382 + Flip Zone': {'count': 40, 'avg_outcome': 85},
    '50 + Flip Zone': {'count': 45, 'avg_outcome': 92},
    '618 + Flip Zone': {'count': 61, 'avg_outcome': 95},
    '786 + Flip Zone': {'count': 33, 'avg_outcome': 78},
    'Under-Fib Flip Zone': {'count': 40, 'avg_outcome': 152},
}

DB_PATH = os.getenv('DB_PATH', '/app/jayce_memory.db')
ALLOWED_DEXES = {'pumpfun', 'pumpswap', 'raydium'}

# ══════════════════════════════════════════════════════════════════════════════
# v4.2: PERFORMANCE METRICS — Baseline tracking for Railway vs VPS comparison
# ══════════════════════════════════════════════════════════════════════════════

DAILY_METRICS = {
    'date': None, 
    'coins_scanned': 0, 
    'coins_passed_prefilter': 0,
    'vision_calls': 0, 
    'engine_triggers': 0,
    'forming_alerts': 0, 
    'valid_alerts': 0, 
    'confirmed_alerts': 0,
    'blocked_no_impulse': 0, 
    'blocked_choppy': 0, 
    'blocked_low_score': 0,
    'blocked_cooldown': 0, 
    'cooldown_overrides': 0,
    'blocked_wash_trading': 0, 
    'blocked_staircase': 0, 
    'blocked_spike_chop': 0,
    'blocked_too_new': 0, 
    'blocked_low_candles': 0,
    'flashcard_fetches': 0,
    # v4.2: Engine-specific detection counts
    'engine_382': 0,
    'engine_50': 0,
    'engine_618': 0,
    'engine_786': 0,
    'engine_underfib': 0,
    # v4.2: Source category counts
    'source_top100': 0,
    'source_5m_vol': 0,
    'source_1h_vol': 0,
    # v4.2: Error tracking
    'errors_playwright': 0,
    'errors_timeout': 0,
    'errors_parsing': 0,
    'errors_other': 0,
    # v4.2: Performance timing
    'cycle_times': [],  # List of cycle durations in seconds
    'cycle_count': 0,
}

# ══════════════════════════════════════════════════════════════════════════════
# STICKY WATCHLIST — Near-miss setups for re-evaluation
# ══════════════════════════════════════════════════════════════════════════════

WATCHLIST: Dict[str, dict] = {}  # {pair_address: watchlist_entry}
WATCHLIST_TTL_MINUTES = 120  # Keep tokens for 2 hours

def add_to_sticky_watchlist(token: dict, setup_type: str, score: int, grade: str):
    """Add a near-miss token to the sticky watchlist for re-evaluation"""
    pair_address = token.get('pair_address', '')
    if not pair_address:
        return
    
    WATCHLIST[pair_address] = {
        'symbol': token.get('symbol', '???'),
        'pair_address': pair_address,
        'address': token.get('address', ''),
        'potential_setup': setup_type,
        'last_score': score,
        'last_grade': grade,
        'added_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(minutes=WATCHLIST_TTL_MINUTES),
        'evaluations': 1,
        'token_data': token  # Store full token data for re-evaluation
    }
    logger.info(f"[{ENVIRONMENT}] 👁️ WATCHLIST ADD: {token.get('symbol')} — {setup_type} (Score: {score}, Grade: {grade})")


def get_watchlist_tokens() -> List[dict]:
    """Get active watchlist tokens (not expired)"""
    now = datetime.now()
    active = []
    expired = []
    
    for pair_address, entry in WATCHLIST.items():
        if now < entry['expires_at']:
            active.append(entry)
        else:
            expired.append(pair_address)
    
    # Clean up expired entries
    for pair_address in expired:
        symbol = WATCHLIST[pair_address].get('symbol', '???')
        logger.debug(f"[{ENVIRONMENT}] 👁️ WATCHLIST EXPIRED: {symbol}")
        del WATCHLIST[pair_address]
    
    return active


def update_watchlist_entry(pair_address: str, score: int, grade: str):
    """Update an existing watchlist entry after re-evaluation"""
    if pair_address in WATCHLIST:
        WATCHLIST[pair_address]['last_score'] = score
        WATCHLIST[pair_address]['last_grade'] = grade
        WATCHLIST[pair_address]['evaluations'] += 1
        # Extend expiry slightly on re-evaluation
        WATCHLIST[pair_address]['expires_at'] = datetime.now() + timedelta(minutes=WATCHLIST_TTL_MINUTES)


def remove_from_watchlist(pair_address: str):
    """Remove a token from watchlist (e.g., after it triggers an alert)"""
    if pair_address in WATCHLIST:
        symbol = WATCHLIST[pair_address].get('symbol', '???')
        logger.info(f"[{ENVIRONMENT}] 👁️ WATCHLIST REMOVE: {symbol} (triggered)")
        del WATCHLIST[pair_address]


def is_near_miss(grade: str, score: int) -> bool:
    """Determine if a token is a near-miss (close to triggering)"""
    # B+ grades or high B grades are near-misses
    if grade == 'B+':
        return True
    if grade == 'B' and score >= 60:
        return True
    return False


def log_watchlist_status():
    """Log current watchlist status"""
    active = get_watchlist_tokens()
    if active:
        logger.info(f"[{ENVIRONMENT}] 👁️ WATCHLIST STATUS: {len(active)} tokens being tracked")
        for entry in active[:5]:  # Show top 5
            mins_left = (entry['expires_at'] - datetime.now()).total_seconds() / 60
            logger.info(f"[{ENVIRONMENT}]    • {entry['symbol']}: {entry['potential_setup']} (Score: {entry['last_score']}, {mins_left:.0f}m left)")



# v4.2: Heartbeat tracking
LAST_HEARTBEAT = None
SCANNER_START_TIME = None

VISION_COOLDOWN_CACHE = {}
TRAINING_DATA = []
TRAINING_LAST_LOADED = None

# v4.1: Cache for downloaded flashcard images (to avoid re-downloading)
FLASHCARD_IMAGE_CACHE = {}
FLASHCARD_CACHE_TIMESTAMP = None

CHOPPY_KEYWORDS = ['choppy', 'no structure', 'no setup', 'messy', 'sideways', 
                   'range-bound', 'no clear', 'unclear', 'weak structure', 'no impulse visible']

# ══════════════════════════════════════════════════════════════════════════════
# METRICS & COOLDOWNS
# ══════════════════════════════════════════════════════════════════════════════

def reset_metrics_if_new_day():
    """Reset daily metrics at midnight, send 24h summary first"""
    today = datetime.now().strftime('%Y-%m-%d')
    if DAILY_METRICS['date'] != today:
        # Send 24h summary before resetting (if we have data)
        if DAILY_METRICS['date'] is not None and DAILY_METRICS['cycle_count'] > 0:
            asyncio.create_task(send_daily_summary())
        
        DAILY_METRICS['date'] = today
        for key in DAILY_METRICS:
            if key == 'date':
                continue
            elif key == 'cycle_times':
                DAILY_METRICS[key] = []
            else:
                DAILY_METRICS[key] = 0


async def send_daily_summary():
    """Send 24-hour performance summary to Telegram"""
    try:
        m = DAILY_METRICS
        total_alerts = m['forming_alerts'] + m['valid_alerts'] + m['confirmed_alerts']
        
        # Calculate average cycle time
        avg_cycle = 0
        if m['cycle_times']:
            avg_cycle = sum(m['cycle_times']) / len(m['cycle_times'])
        
        summary = f"""📊 <b>[{ENVIRONMENT}] 24H PERFORMANCE SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Date: {m['date']}

<b>SCANNING</b>
• Tokens scanned: {m['coins_scanned']}
• Cycles completed: {m['cycle_count']}
• Avg cycle time: {avg_cycle:.1f}s

<b>SOURCE BREAKDOWN</b>
• Top 100 H6: {m['source_top100']}
• 5M Volume: {m['source_5m_vol']}
• 1H Volume: {m['source_1h_vol']}

<b>ENGINE DETECTIONS</b>
• .382: {m['engine_382']}
• .50: {m['engine_50']}
• .618: {m['engine_618']}
• .786: {m['engine_786']}
• Under-Fib: {m['engine_underfib']}

<b>ALERTS SENT</b>
• Forming: {m['forming_alerts']}
• Valid: {m['valid_alerts']}
• Confirmed: {m['confirmed_alerts']}
• Total: {total_alerts}

<b>ERRORS</b>
• Playwright: {m['errors_playwright']}
• Timeout: {m['errors_timeout']}
• Parsing: {m['errors_parsing']}
• Other: {m['errors_other']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=HEARTBEAT_CHAT_ID, text=summary, parse_mode=ParseMode.HTML)
        logger.info(f"[{ENVIRONMENT}] 📊 24h summary sent")
    except Exception as e:
        logger.error(f"[{ENVIRONMENT}] ❌ Failed to send daily summary: {e}")

def log_current_metrics():
    """Log current cycle metrics with environment tag"""
    m = DAILY_METRICS
    total = m['forming_alerts'] + m['valid_alerts'] + m['confirmed_alerts']
    logger.info(f"[{ENVIRONMENT}] 📊 Scanned: {m['coins_scanned']} | Engines: {m['engine_triggers']} | Vision: {m['vision_calls']} | Flashcards: {m['flashcard_fetches']} | Alerts: {total}")


def log_cycle_complete(cycle_time: float, tokens_scanned: int, alerts_sent: int, source_counts: dict):
    """Log structured cycle completion data"""
    DAILY_METRICS['cycle_times'].append(cycle_time)
    DAILY_METRICS['cycle_count'] += 1
    
    logger.info(f"""[{ENVIRONMENT}] ═══════════════════════════════════════════════
[{ENVIRONMENT}] ✅ CYCLE #{DAILY_METRICS['cycle_count']} COMPLETE
[{ENVIRONMENT}]    Time: {cycle_time:.1f}s
[{ENVIRONMENT}]    Tokens: {tokens_scanned}
[{ENVIRONMENT}]    Sources: TOP={source_counts.get('TOP_100', 0)} | 5M={source_counts.get('5M_VOL', 0)} | 1H={source_counts.get('1H_VOL', 0)} | Raw={source_counts.get('raw_total', 0)} | Unique={source_counts.get('unique_total', 0)}
[{ENVIRONMENT}]    Alerts: {alerts_sent}
[{ENVIRONMENT}] ═══════════════════════════════════════════════""")

def record_vision_rejection(token: dict):
    address = token.get('address', '')
    if address:
        VISION_COOLDOWN_CACHE[address] = {
            'rejected_at': datetime.now(),
            'h1_at_rejection': token.get('price_change_1h', 0),
            'volume_at_rejection': token.get('volume_24h', 0),
            'symbol': token.get('symbol', '???'),
        }

def is_on_vision_cooldown(token: dict) -> tuple:
    address = token.get('address', '')
    if not address or address not in VISION_COOLDOWN_CACHE:
        return (False, "")
    cache = VISION_COOLDOWN_CACHE[address]
    elapsed = (datetime.now() - cache['rejected_at']).total_seconds() / 60
    if elapsed >= VISION_COOLDOWN_MINUTES:
        del VISION_COOLDOWN_CACHE[address]
        return (False, "")
    h1_delta = token.get('price_change_1h', 0) - cache.get('h1_at_rejection', 0)
    if h1_delta >= COOLDOWN_H1_OVERRIDE_DELTA:
        del VISION_COOLDOWN_CACHE[address]
        DAILY_METRICS['cooldown_overrides'] += 1
        return (False, "")
    return (True, f"{VISION_COOLDOWN_MINUTES - elapsed:.0f}min left")

def cleanup_expired_cooldowns():
    now = datetime.now()
    expired = [a for a, c in VISION_COOLDOWN_CACHE.items() 
               if (now - c['rejected_at']).total_seconds() / 60 >= VISION_COOLDOWN_MINUTES]
    for addr in expired: del VISION_COOLDOWN_CACHE[addr]


# ══════════════════════════════════════════════════════════════════════════════
# v4.2: HEARTBEAT SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

async def send_heartbeat(cycle_time: float = 0):
    """Send heartbeat to Telegram every HEARTBEAT_INTERVAL_MINUTES"""
    global LAST_HEARTBEAT
    
    now = datetime.now()
    
    # Check if heartbeat is due
    if LAST_HEARTBEAT is not None:
        minutes_since = (now - LAST_HEARTBEAT).total_seconds() / 60
        if minutes_since < HEARTBEAT_INTERVAL_MINUTES:
            return  # Not time yet
    
    try:
        m = DAILY_METRICS
        total_alerts = m['forming_alerts'] + m['valid_alerts'] + m['confirmed_alerts']
        uptime = ""
        if SCANNER_START_TIME:
            uptime_delta = now - SCANNER_START_TIME
            hours = int(uptime_delta.total_seconds() // 3600)
            minutes = int((uptime_delta.total_seconds() % 3600) // 60)
            uptime = f"\n⏱️ Uptime: {hours}h {minutes}m"
        
        heartbeat_msg = f"""🫀 <b>[{ENVIRONMENT}] Scanner Alive</b>
━━━━━━━━━━━━━━━━━━
Cycle time: {cycle_time:.1f}s
Tokens today: {m['coins_scanned']}
Alerts today: {total_alerts}{uptime}"""
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=HEARTBEAT_CHAT_ID, text=heartbeat_msg, parse_mode=ParseMode.HTML)
        LAST_HEARTBEAT = now
        logger.info(f"[{ENVIRONMENT}] 🫀 Heartbeat sent")
    except Exception as e:
        logger.error(f"[{ENVIRONMENT}] ❌ Heartbeat failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# v4.2: STRUCTURED ERROR LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def log_error(error_type: str, message: str, details: dict = None):
    """Log structured error with environment tag and increment counter"""
    error_key = f"errors_{error_type}"
    if error_key in DAILY_METRICS:
        DAILY_METRICS[error_key] += 1
    else:
        DAILY_METRICS['errors_other'] += 1
    
    detail_str = f" | Details: {details}" if details else ""
    logger.error(f"[{ENVIRONMENT}] ❌ [{error_type.upper()}] {message}{detail_str}")


def log_scrape_error(error_type: str, url: str, error: Exception):
    """Log scraping-specific errors"""
    error_name = type(error).__name__
    log_error(error_type, f"{error_name} on {url[:50]}...", {'error': str(error)[:100]})

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def init_database():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS watchlist (
        token_address TEXT PRIMARY KEY, pair_address TEXT, symbol TEXT, name TEXT,
        first_seen TIMESTAMP, last_seen TIMESTAMP, impulse_h24 REAL, impulse_h6 REAL,
        impulse_h1 REAL, market_cap REAL, liquidity REAL, source TEXT, status TEXT DEFAULT 'WATCHING')''')
    c.execute('''CREATE TABLE IF NOT EXISTS vision_usage (date TEXT PRIMARY KEY, calls_used INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts_sent (token_address TEXT, setup_type TEXT, sent_at TIMESTAMP,
        PRIMARY KEY (token_address, setup_type))''')
    conn.commit(); conn.close()

def add_to_watchlist(token: dict, source: str = 'MOVERS'):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor(); now = datetime.now().isoformat()
    c.execute('''INSERT INTO watchlist (token_address, pair_address, symbol, name, first_seen, last_seen,
        impulse_h24, impulse_h6, impulse_h1, market_cap, liquidity, source, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'WATCHING')
        ON CONFLICT(token_address) DO UPDATE SET last_seen=?, market_cap=?, liquidity=?''',
        (token.get('address',''), token.get('pair_address',''), token.get('symbol','???'), token.get('name',''),
         now, now, token.get('price_change_24h',0), token.get('price_change_6h',0), token.get('price_change_1h',0),
         token.get('market_cap',0), token.get('liquidity',0), source, now, token.get('market_cap',0), token.get('liquidity',0)))
    conn.commit(); conn.close()

def get_watchlist() -> list:
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=WATCHLIST_DURATION_HOURS)).isoformat()
    c.execute('SELECT token_address, pair_address, symbol FROM watchlist WHERE first_seen > ? AND status = ?', (cutoff, 'WATCHING'))
    rows = c.fetchall(); conn.close()
    return [{'address': r[0], 'pair_address': r[1], 'symbol': r[2]} for r in rows]

def cleanup_old_watchlist():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=WATCHLIST_DURATION_HOURS)).isoformat()
    c.execute('DELETE FROM watchlist WHERE first_seen < ?', (cutoff,))
    conn.commit(); conn.close()

def was_alert_sent(token_address: str, setup_type: str, dedup_hours: int) -> bool:
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=dedup_hours)).isoformat()
    c.execute('SELECT 1 FROM alerts_sent WHERE token_address=? AND setup_type=? AND sent_at>?', (token_address, setup_type, cutoff))
    result = c.fetchone(); conn.close(); return result is not None

def record_alert_sent(token_address: str, setup_type: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO alerts_sent VALUES (?,?,?)', (token_address, setup_type, datetime.now().isoformat()))
    conn.commit(); conn.close()

def get_vision_usage_today() -> int:
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('SELECT calls_used FROM vision_usage WHERE date = ?', (datetime.now().strftime('%Y-%m-%d'),))
    row = c.fetchone(); conn.close(); return row[0] if row else 0

def increment_vision_usage():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO vision_usage VALUES (?, 1) ON CONFLICT(date) DO UPDATE SET calls_used = calls_used + 1', (today,))
    conn.commit(); conn.close()

def can_use_vision() -> bool:
    return get_vision_usage_today() < DAILY_VISION_CAP

# ══════════════════════════════════════════════════════════════════════════════
# TRAINING DATA
# ══════════════════════════════════════════════════════════════════════════════

async def load_training_from_github():
    global TRAINING_DATA, TRAINING_LAST_LOADED
    if not GITHUB_TOKEN: return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_BACKUP_PATH}",
                headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"})
            if resp.status_code == 200:
                content = base64.b64decode(resp.json().get('content', '')).decode()
                TRAINING_DATA = json.loads(content)
                TRAINING_LAST_LOADED = datetime.now()
                logger.info(f"✅ Loaded {len(TRAINING_DATA)} training charts from GitHub")
                
                # v4.1: Log setup counts
                setup_counts = {}
                for t in TRAINING_DATA:
                    setup = t.get('setup_name', 'Unknown')
                    setup_counts[setup] = setup_counts.get(setup, 0) + 1
                for setup, count in setup_counts.items():
                    logger.info(f"   📚 {setup}: {count} examples")
    except Exception as e:
        logger.error(f"❌ Training load error: {e}")
    return TRAINING_DATA

async def ensure_training_data():
    if not TRAINING_DATA or not TRAINING_LAST_LOADED:
        await load_training_from_github()
    elif (datetime.now() - TRAINING_LAST_LOADED).total_seconds() / 3600 >= TRAINING_REFRESH_HOURS:
        await load_training_from_github()

def get_pattern_matches(setup_name: str) -> dict:
    if not TRAINING_DATA:
        return {'match_percentage': 0, 'avg_outcome': 0}
    
    # Normalize the setup name to match training data format
    normalized_name = normalize_setup_name(setup_name)
    
    charts = [t for t in TRAINING_DATA if t.get('setup_name') == normalized_name]
    if not charts: return {'match_percentage': 0, 'avg_outcome': 0}
    outcomes = [c.get('outcome_percentage', 0) for c in charts if c.get('outcome_percentage', 0) > 0]
    return {'match_percentage': len(charts) * 2, 'avg_outcome': int(sum(outcomes)/len(outcomes)) if outcomes else 0}

# ══════════════════════════════════════════════════════════════════════════════
# v4.1: FLASHCARD IMAGE FETCHING FROM TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

async def download_telegram_image(file_id: str) -> bytes:
    """Download an image from Telegram using file_id, resized for API limits"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get file path from Telegram
            resp = await client.get(f"https://api.telegram.org/bot{JAYCE_BOT_TOKEN}/getFile?file_id={file_id}")
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            if not data.get('ok'):
                return None
            
            file_path = data.get('result', {}).get('file_path', '')
            if not file_path:
                return None
            
            # Step 2: Download the actual file
            file_url = f"https://api.telegram.org/file/bot{JAYCE_BOT_TOKEN}/{file_path}"
            file_resp = await client.get(file_url)
            if file_resp.status_code == 200:
                # Resize for API limits (max 1800px for many-image requests)
                try:
                    from PIL import Image
                    from io import BytesIO
                    
                    img = Image.open(BytesIO(file_resp.content))
                    max_dim = 1800
                    
                    if img.width > max_dim or img.height > max_dim:
                        ratio = min(max_dim / img.width, max_dim / img.height)
                        new_size = (int(img.width * ratio), int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                    
                    buf = BytesIO()
                    img.save(buf, format='PNG', optimize=True)
                    return buf.getvalue()
                except:
                    return file_resp.content
    except Exception as e:
        logger.error(f"❌ Telegram image download error: {e}")
    return None

async def get_flashcard_examples(setup_name: str, count: int = 100) -> list:
    """Get flashcard example images for a specific setup type"""
    global FLASHCARD_IMAGE_CACHE, FLASHCARD_CACHE_TIMESTAMP
    
    # Check if cache needs refresh
    if FLASHCARD_CACHE_TIMESTAMP:
        cache_age = (datetime.now() - FLASHCARD_CACHE_TIMESTAMP).total_seconds() / 3600
        if cache_age >= FLASHCARD_CACHE_HOURS:
            FLASHCARD_IMAGE_CACHE = {}
            FLASHCARD_CACHE_TIMESTAMP = None
    
    if not TRAINING_DATA:
        await ensure_training_data()
    
    # Normalize the setup name to match training data format
    normalized_name = normalize_setup_name(setup_name)
    
    # Filter training data for this setup type
    matching_charts = [t for t in TRAINING_DATA if t.get('setup_name') == normalized_name]
    if not matching_charts:
        logger.warning(f"⚠️ No training data for setup: {setup_name}")
        return []
    
    # Sort by outcome percentage (best performers first) and take top examples
    matching_charts.sort(key=lambda x: x.get('outcome_percentage', 0), reverse=True)
    
    # Use ALL matching flashcards for this setup (sorted by best outcome first)
    selected = matching_charts[:min(count, len(matching_charts))]
    
    examples = []
    for chart in selected:
        file_id = chart.get('screenshot_fingerprint_id', '')
        if not file_id:
            continue
        
        # Check cache first
        if file_id in FLASHCARD_IMAGE_CACHE:
            examples.append({
                'image_bytes': FLASHCARD_IMAGE_CACHE[file_id],
                'token': chart.get('token', '???'),
                'outcome': chart.get('outcome_percentage', 0),
                'notes': chart.get('notes', ''),
                'setup_name': setup_name,
            })
            continue
        
        # Download from Telegram
        image_bytes = await download_telegram_image(file_id)
        if image_bytes:
            FLASHCARD_IMAGE_CACHE[file_id] = image_bytes
            if not FLASHCARD_CACHE_TIMESTAMP:
                FLASHCARD_CACHE_TIMESTAMP = datetime.now()
            
            examples.append({
                'image_bytes': image_bytes,
                'token': chart.get('token', '???'),
                'outcome': chart.get('outcome_percentage', 0),
                'notes': chart.get('notes', ''),
                'setup_name': setup_name,
            })
            DAILY_METRICS['flashcard_fetches'] += 1
            logger.info(f"📸 Fetched flashcard: {chart.get('token')} ({setup_name}) — {chart.get('outcome_percentage')}% outcome")
        
        await asyncio.sleep(0.3)  # Rate limit
    
    return examples

def normalize_setup_name(setup_name: str) -> str:
    """Normalize setup name to match training data format
    Engine outputs: '.382 + Flip Zone' 
    Training data:  '382 + Flip Zone'
    """
    if not setup_name:
        return setup_name
    
    # Remove leading dot if present
    normalized = setup_name.lstrip('.')
    return normalized

def get_training_context(setup_name: str) -> str:
    """Get text context about training data for a setup"""
    if not TRAINING_DATA:
        return ""
    
    # Normalize the setup name to match training data format
    normalized_name = normalize_setup_name(setup_name)
    
    charts = [t for t in TRAINING_DATA if t.get('setup_name') == normalized_name]
    if not charts:
        return ""
    
    outcomes = [c.get('outcome_percentage', 0) for c in charts if c.get('outcome_percentage', 0) > 0]
    avg_outcome = int(sum(outcomes) / len(outcomes)) if outcomes else 0
    
    # Collect common notes/patterns
    all_notes = ' '.join([c.get('notes', '').upper() for c in charts])
    patterns = []
    if 'CLEAN STRUCTURE' in all_notes: patterns.append('clean structure')
    if 'WHALE CONVICTION' in all_notes: patterns.append('whale conviction')
    if 'RSI DIVERGENCE' in all_notes: patterns.append('RSI divergence')
    if 'HIGH VOLUME' in all_notes: patterns.append('high volume')
    if 'WICK ENTRY' in all_notes: patterns.append('wick entry')
    
    return f"Trained on {len(charts)} examples with avg {avg_outcome}% outcome. Common patterns: {', '.join(patterns) if patterns else 'various'}"

# ══════════════════════════════════════════════════════════════════════════════
# SCORING & FILTERS
# ══════════════════════════════════════════════════════════════════════════════

def calculate_setup_score(engine_score: float, vision_confidence: float, pattern_score: float) -> float:
    return (ENGINE_WEIGHT * engine_score) + (VISION_WEIGHT * vision_confidence) + (PATTERN_WEIGHT * pattern_score)

def get_alert_tier(score: float) -> tuple:
    if score >= SCORE_CONFIRMED: return ('CONFIRMED', '🟢', DEDUP_CONFIRMED_HOURS)
    elif score >= SCORE_VALID: return ('VALID', '🟡', DEDUP_VALID_HOURS)
    elif score >= SCORE_FORMING: return ('FORMING', '🔵', DEDUP_FORMING_HOURS)
    return (None, None, None)

def detect_impulse(token: dict) -> bool:
    return (token.get('price_change_24h', 0) >= IMPULSE_H24_THRESHOLD or
            token.get('price_change_6h', 0) >= IMPULSE_H6_THRESHOLD or
            token.get('price_change_1h', 0) >= IMPULSE_H1_THRESHOLD)

def detect_fresh_runner(token: dict) -> bool:
    return token.get('price_change_1h', 0) >= FRESH_RUNNER_H1_THRESHOLD

def should_use_vision(token: dict) -> tuple:
    h1, h24 = token.get('price_change_1h', 0), token.get('price_change_24h', 0)
    had_impulse = detect_impulse(token)
    is_cooling = POST_IMPULSE_H1_MIN <= h1 <= POST_IMPULSE_H1_MAX
    if had_impulse and is_cooling: return (True, 'PRIMARY', 'testing')
    if h1 >= FRESH_RUNNER_H1_THRESHOLD: return (True, 'SECONDARY', 'forming')
    return (False, None, None)

def pre_filter_token(token: dict) -> tuple:
    mc, liq = token.get('market_cap', 0), token.get('liquidity', 0)
    if mc < MIN_MARKET_CAP: return (False, "MC too low")
    if liq < MIN_LIQUIDITY: return (False, "Liq too low")
    dex = token.get('dex', '').lower()
    if dex and dex not in ALLOWED_DEXES: return (False, f"DEX: {dex}")
    if token.get('has_profile') is False: return (False, "No profile")
    return (True, "OK")

def hard_block_check(token: dict, vision_result: dict) -> tuple:
    if not detect_impulse(token) and not detect_fresh_runner(token):
        return (True, "No impulse")
    if vision_result:
        reasoning = vision_result.get('reasoning', '').lower()
        for kw in CHOPPY_KEYWORDS:
            if kw in reasoning: return (True, f"Choppy: {kw}")
        if not vision_result.get('is_setup') and vision_result.get('confidence', 0) < 30:
            return (True, "Vision rejected")
    return (False, "OK")

# ══════════════════════════════════════════════════════════════════════════════
# DEXSCREENER API — v4.2: With rate limiting, retries, and error tracking
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_with_retry(client, url: str, headers: dict, max_retries: int = 2) -> dict:
    """Fetch URL with retry logic and error tracking"""
    for attempt in range(max_retries + 1):
        try:
            # v4.2: Randomized delay between requests (0.5-1.2 seconds)
            delay = random.uniform(0.5, 1.2)
            await asyncio.sleep(delay)
            
            resp = await client.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:  # Rate limited
                log_error('timeout', f"Rate limited on {url[:50]}", {'status': 429})
                await asyncio.sleep(5)  # Wait longer on rate limit
            else:
                log_error('other', f"HTTP {resp.status_code} on {url[:50]}")
        except httpx.TimeoutException as e:
            log_scrape_error('timeout', url, e)
            if attempt < max_retries:
                await asyncio.sleep(2)
        except Exception as e:
            log_scrape_error('other', url, e)
            if attempt < max_retries:
                await asyncio.sleep(1)
    
    return {}


async def fetch_top_movers() -> list:
    """
    Scrape DexScreener EXACTLY how Wiz trades:
    1. Fetch page HTML via httpx (works on Railway!)
    2. Parse token data from the page
    3. Get Top 100 (Trending H6)
    
    v4.2: Added rate limiting, retries, and source tracking
    
    NOTE: httpx works on Railway while Playwright browser is blocked.
    We fetch the page and parse the embedded JSON data.
    """
    tokens, seen = [], set()
    source_counts = {'TOP_100': 0, '5M_VOL': 0, '1H_VOL': 0, 'raw_total': 0, 'unique_total': 0}
    
    # RAW token lists for scan monitor (before dedup) - tracks exact scan order
    raw_top100_symbols = []
    raw_5m_vol_symbols = []
    raw_1h_vol_symbols = []
    
    DEXSCREENER_URL = "https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&launchpads=1"
    
    try:
        logger.info(f"[{ENVIRONMENT}] 🌐 Fetching DexScreener data...")
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Use headers that look like a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Try to get the page - DexScreener may have API endpoints we can use
            # First, let's try their internal API that powers the frontend
            
            # Method 1: Try the pairs endpoint with ranking
            logger.info(f"[{ENVIRONMENT}] 📈 Fetching TOP 100 (Trending H6)...")
            
            # DexScreener doesn't have a public sorted API, so we use multiple endpoints
            # and combine + sort ourselves to approximate the Top 100
            
            all_pairs = []
            
            # Get boosted/promoted tokens (these are often in Top 100)
            try:
                data = await fetch_with_retry(client, 'https://api.dexscreener.com/token-boosts/top/v1', headers)
                items = data if isinstance(data, list) else []
                for item in items[:30]:
                    if item.get('chainId') == 'solana':
                        all_pairs.append({
                            'address': item.get('tokenAddress', ''),
                            'symbol': item.get('symbol', '???'),
                            'pair_address': '',
                            'source': 'TOP_100',
                            'boost': True
                        })
            except Exception as e:
                log_scrape_error('parsing', 'token-boosts endpoint', e)
            
            # v4.2: Delay between category fetches
            await asyncio.sleep(random.uniform(0.8, 1.5))
            
            # Get trending Solana pairs from search
            for query in ['', 'pump', 'sol']:
                try:
                    url = f'https://api.dexscreener.com/latest/dex/search?q={query}' if query else 'https://api.dexscreener.com/latest/dex/pairs/solana'
                    data = await fetch_with_retry(client, url, headers)
                    pairs = data.get('pairs', []) if data else []
                    for pair in pairs[:50]:
                        if pair.get('chainId') != 'solana':
                            continue
                        if pair.get('dexId', '').lower() not in ALLOWED_DEXES:
                            continue
                        
                        addr = pair.get('baseToken', {}).get('address', '')
                        mc = float(pair.get('marketCap', 0) or 0)
                        liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                        
                        if mc < MIN_MARKET_CAP or liq < MIN_LIQUIDITY:
                            continue
                        
                        # Calculate a trending score based on price changes
                        h1 = abs(float(pair.get('priceChange', {}).get('h1', 0) or 0))
                        h6 = abs(float(pair.get('priceChange', {}).get('h6', 0) or 0))
                        h24 = abs(float(pair.get('priceChange', {}).get('h24', 0) or 0))
                        vol = float(pair.get('volume', {}).get('h24', 0) or 0)
                        
                        # Trending score: weight recent activity higher
                        trending_score = (h1 * 3) + (h6 * 2) + h24 + (vol / 10000)
                        
                        all_pairs.append({
                            'address': addr,
                            'pair_address': pair.get('pairAddress', ''),
                            'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                            'source': 'TOP_100',
                            'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                            'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                            'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                            'market_cap': mc,
                            'liquidity': liq,
                            'volume_24h': vol,
                            'trending_score': trending_score,
                            'boost': False
                            })
                except Exception as e:
                    log_scrape_error('parsing', f'search endpoint ({query})', e)
            
            # Sort by trending score (approximates DexScreener's Trending H6)
            all_pairs.sort(key=lambda x: (x.get('boost', False), x.get('trending_score', 0)), reverse=True)
            
            # Dedupe and take top 100
            for pair in all_pairs:
                addr = pair.get('address', '')
                if addr and addr not in seen:
                    seen.add(addr)
                    tokens.append(pair)
                    source_counts['TOP_100'] += 1
                    raw_top100_symbols.append(pair.get('symbol', '???'))
                    logger.info(f"[{ENVIRONMENT}]    👀 {pair.get('symbol', '???')} (TOP_100)")
                    
                    if len(tokens) >= TOP_RANKED_LIMIT:
                        break
            
            logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['TOP_100']} tokens from TOP 100")
            
            # v4.2: Delay between category rotations
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Now get 5M movers - tokens with biggest 5min price changes
            # We'll use the h1 data and approximate
            logger.info(f"[{ENVIRONMENT}] ⏱️ Fetching 5M volume movers...")
            
            try:
                data = await fetch_with_retry(client, 'https://api.dexscreener.com/latest/dex/search?q=pumpfun', headers)
                pairs = data.get('pairs', []) if data else []
                # Sort by h1 change as proxy for recent activity
                pairs.sort(key=lambda x: abs(float(x.get('priceChange', {}).get('h1', 0) or 0)), reverse=True)
                
                for pair in pairs[:30]:
                    if pair.get('chainId') != 'solana':
                        continue
                    if pair.get('dexId', '').lower() not in ALLOWED_DEXES:
                        continue
                    
                    addr = pair.get('baseToken', {}).get('address', '')
                    if addr in seen:
                        continue
                        
                    mc = float(pair.get('marketCap', 0) or 0)
                    liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                    
                    if mc < MIN_MARKET_CAP or liq < MIN_LIQUIDITY:
                        continue
                    
                    seen.add(addr)
                    tokens.append({
                        'address': addr,
                        'pair_address': pair.get('pairAddress', ''),
                        'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                        'source': '5M_VOL',
                        'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                        'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                        'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                        'market_cap': mc,
                        'liquidity': liq,
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                    })
                    source_counts['5M_VOL'] += 1
                    raw_5m_vol_symbols.append(pair.get('baseToken', {}).get('symbol', '???'))
                    logger.info(f"[{ENVIRONMENT}]    👀 {pair.get('baseToken', {}).get('symbol', '???')} (5M_VOL)")
            except Exception as e:
                log_scrape_error('parsing', '5M volume endpoint', e)
            
            logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['5M_VOL']} tokens from 5M volume")
            
            # v4.2: Delay between category rotations
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Get 1H volume movers
            logger.info(f"[{ENVIRONMENT}] ⏰ Fetching 1H volume movers...")
            
            try:
                data = await fetch_with_retry(client, 'https://api.dexscreener.com/latest/dex/search?q=pumpswap', headers)
                pairs = data.get('pairs', []) if data else []
                # Sort by volume as proxy for 1H activity
                pairs.sort(key=lambda x: float(x.get('volume', {}).get('h24', 0) or 0), reverse=True)
                
                for pair in pairs[:30]:
                    if pair.get('chainId') != 'solana':
                        continue
                    if pair.get('dexId', '').lower() not in ALLOWED_DEXES:
                        continue
                    
                    addr = pair.get('baseToken', {}).get('address', '')
                    if addr in seen:
                        continue
                        
                    mc = float(pair.get('marketCap', 0) or 0)
                    liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                    
                    if mc < MIN_MARKET_CAP or liq < MIN_LIQUIDITY:
                        continue
                    
                    seen.add(addr)
                    tokens.append({
                        'address': addr,
                        'pair_address': pair.get('pairAddress', ''),
                        'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                        'source': '1H_VOL',
                        'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                        'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                        'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                        'market_cap': mc,
                        'liquidity': liq,
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                    })
                    source_counts['1H_VOL'] += 1
                    raw_1h_vol_symbols.append(pair.get('baseToken', {}).get('symbol', '???'))
                    logger.info(f"[{ENVIRONMENT}]    👀 {pair.get('baseToken', {}).get('symbol', '???')} (1H_VOL)")
            except Exception as e:
                log_scrape_error('parsing', '1H volume endpoint', e)
            
            logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['1H_VOL']} tokens from 1H volume")
            
    except Exception as e:
        log_error('other', f"DexScreener fetch error: {e}")
        return await fetch_top_movers_api_fallback()
    
    # v4.2: Update daily source metrics
    DAILY_METRICS['source_top100'] += source_counts['TOP_100']
    DAILY_METRICS['source_5m_vol'] += source_counts['5M_VOL']
    DAILY_METRICS['source_1h_vol'] += source_counts['1H_VOL']
    
    logger.info(f"[{ENVIRONMENT}] ═══════════════════════════════════════════════")
    raw_count = source_counts['TOP_100'] + source_counts['5M_VOL'] + source_counts['1H_VOL']
    source_counts['raw_total'] = raw_count
    source_counts['unique_total'] = len(tokens)
    logger.info(f"[{ENVIRONMENT}] 📊 Raw: {raw_count} → Unique: {len(tokens)} (deduped {raw_count - len(tokens)})")
    logger.info(f"[{ENVIRONMENT}]    TOP_100: {source_counts['TOP_100']}")
    logger.info(f"[{ENVIRONMENT}]    5M_VOL: {source_counts['5M_VOL']}")
    logger.info(f"[{ENVIRONMENT}]    1H_VOL: {source_counts['1H_VOL']}")
    logger.info(f"[{ENVIRONMENT}] ═══════════════════════════════════════════════")
    
    # Return tokens + raw symbol lists for scan monitor
    return tokens, {
        'raw_top100': raw_top100_symbols,
        'raw_5m_vol': raw_5m_vol_symbols,
        'raw_1h_vol': raw_1h_vol_symbols
    }


async def scrape_token_list(page, seen: set, source: str) -> list:
    """Scrape token list from current DexScreener page state"""
    tokens = []
    
    try:
        # Get all token rows - DexScreener uses links with /solana/ in the href
        rows = await page.query_selector_all('a[href*="/solana/"]')
        
        count = 0
        for row in rows:
            if count >= 100:  # Top 100 only
                break
                
            try:
                href = await row.get_attribute('href')
                if not href or '/solana/' not in href:
                    continue
                
                # Extract pair address from href (format: /solana/PAIR_ADDRESS)
                pair_address = href.split('/solana/')[-1].split('?')[0].split('/')[0]
                if not pair_address or len(pair_address) < 30:
                    continue
                
                if pair_address in seen:
                    continue
                
                # Try to get token symbol from the row text
                text_content = await row.text_content()
                symbol = '???'
                if text_content:
                    # Parse out the symbol - skip numbers/percentages/dollar amounts
                    parts = text_content.strip().split()
                    for part in parts:
                        clean = part.strip()
                        if clean and not clean.startswith('$') and not clean.endswith('%'):
                            if not clean.replace('.', '').replace(',', '').replace('-', '').isdigit():
                                symbol = clean[:15]
                                break
                
                seen.add(pair_address)
                tokens.append({
                    'address': '',  # Will be fetched later via pair lookup
                    'pair_address': pair_address,
                    'symbol': symbol,
                    'source': source
                })
                count += 1
                logger.info(f"   👀 {symbol} ({source})")
                
            except:
                continue
                
    except Exception as e:
        logger.error(f"❌ Scrape error: {e}")
    
    return tokens


async def fetch_top_movers_api_fallback() -> list:
    """Fallback to API if scraping fails"""
    tokens, seen = [], set()
    
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Use the search endpoints as backup
            logger.info("📈 API Fallback: Fetching from DexScreener API...")
            
            for query in ['pumpfun', 'pumpswap']:
                try:
                    resp = await client.get(f'https://api.dexscreener.com/latest/dex/search?q={query}')
                    if resp.status_code == 200:
                        for pair in resp.json().get('pairs', [])[:50]:
                            if pair.get('chainId') != 'solana': continue
                            if pair.get('dexId', '').lower() not in ALLOWED_DEXES: continue
                            addr = pair.get('baseToken', {}).get('address', '')
                            if not addr or addr in seen: continue
                            mc = float(pair.get('marketCap', 0) or 0)
                            if mc < MIN_MARKET_CAP: continue
                            liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                            if liq < MIN_LIQUIDITY: continue
                            seen.add(addr)
                            symbol = pair.get('baseToken', {}).get('symbol', '???')
                            tokens.append({
                                'address': addr, 
                                'pair_address': pair.get('pairAddress', ''),
                                'symbol': symbol, 
                                'source': 'API_FALLBACK',
                                'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                                'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0) or 0),
                                'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                                'market_cap': mc,
                                'liquidity': liq,
                                'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                            })
                            logger.info(f"   👀 {symbol} (API)")
                except Exception as e:
                    logger.error(f"❌ API fallback error: {e}")
                    
    except Exception as e:
        logger.error(f"❌ API error: {e}")
    
    logger.info(f"📊 API Fallback fetched {len(tokens)} tokens")
    return tokens

async def fetch_token_data(token_address: str) -> dict:
    try:
        await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f'https://api.dexscreener.com/latest/dex/tokens/{token_address}')
            if resp.status_code == 200:
                pairs = resp.json().get('pairs', [])
                pair = None
                for p in pairs:
                    if p.get('dexId', '').lower() in ALLOWED_DEXES:
                        if not pair or float(p.get('liquidity', {}).get('usd', 0) or 0) > float(pair.get('liquidity', {}).get('usd', 0) or 0):
                            pair = p
                if not pair: return {}
                pc = pair.get('priceChange', {})
                info = pair.get('info', {})
                
                # Calculate coin age in hours
                pair_created = pair.get('pairCreatedAt', 0)
                if pair_created:
                    age_hours = (datetime.now().timestamp() * 1000 - pair_created) / (1000 * 60 * 60)
                else:
                    age_hours = 999  # Unknown age, allow it
                
                return {
                    'address': token_address, 'pair_address': pair.get('pairAddress', ''),
                    'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                    'price_change_1h': float(pc.get('h1', 0) or 0),
                    'price_change_6h': float(pc.get('h6', 0) or 0),
                    'price_change_24h': float(pc.get('h24', 0) or 0),
                    'market_cap': float(pair.get('marketCap', 0) or 0),
                    'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                    'dex': pair.get('dexId', ''),
                    'has_profile': bool(info.get('imageUrl')) and len(info.get('socials', []) + info.get('websites', [])) >= 1,
                    'age_hours': age_hours,
                    'pair_created_at': pair_created,
                }
    except: pass
    return {}


async def fetch_token_data_by_pair(pair_address: str) -> dict:
    """Fetch token data using pair address instead of token address"""
    try:
        await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f'https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}')
            if resp.status_code == 200:
                data = resp.json()
                pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else {})
                if not pair:
                    return {}
                
                pc = pair.get('priceChange', {})
                info = pair.get('info', {})
                
                pair_created = pair.get('pairCreatedAt', 0)
                if pair_created:
                    age_hours = (datetime.now().timestamp() * 1000 - pair_created) / (1000 * 60 * 60)
                else:
                    age_hours = 999
                
                return {
                    'address': pair.get('baseToken', {}).get('address', ''),
                    'pair_address': pair_address,
                    'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                    'price_change_1h': float(pc.get('h1', 0) or 0),
                    'price_change_6h': float(pc.get('h6', 0) or 0),
                    'price_change_24h': float(pc.get('h24', 0) or 0),
                    'market_cap': float(pair.get('marketCap', 0) or 0),
                    'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                    'dex': pair.get('dexId', ''),
                    'has_profile': bool(info.get('imageUrl')) and len(info.get('socials', []) + info.get('websites', [])) >= 1,
                    'age_hours': age_hours,
                    'pair_created_at': pair_created,
                }
    except Exception as e:
        pass
    return {}

# ══════════════════════════════════════════════════════════════════════════════
# CHART SCREENSHOT — Returns (bytes, candles) for engine detection
# ══════════════════════════════════════════════════════════════════════════════



async def fetch_from_extension_queue():
    """Fetch tokens from Chrome extension queue (iMac collector)"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                'http://127.0.0.1:5000/queue',
                headers={'X-API-Key': 'jayce_collector_2026_secret_key'}
            )
            
            if resp.status_code == 200:
                data = resp.json()
                tokens = data.get('tokens', [])
                
                source_counts = {'TRENDING': 0, 'VOL_5M': 0, 'VOL_1H': 0}
                enriched_tokens = []
                
                for t in tokens:
                    src = t.get('source', 'TRENDING')
                    if src in source_counts:
                        source_counts[src] += 1
                    
                    enriched_tokens.append({
                        'symbol': t.get('symbol', '???'),
                        'pair_address': t.get('pair_address', ''),
                        'address': t.get('contract_address', ''),
                        'source': src,
                        'rank': t.get('rank', 0),
                        'url': t.get('url', ''),
                        'dex': ''
                    })
                
                logger.info(f"[{ENVIRONMENT}] 📥 Extension queue: {len(enriched_tokens)} tokens")
                logger.info(f"[{ENVIRONMENT}]    TRENDING: {source_counts['TRENDING']} | 5M: {source_counts['VOL_5M']} | 1H: {source_counts['VOL_1H']}")
                
                return enriched_tokens, source_counts
            else:
                logger.warning(f"[{ENVIRONMENT}] Extension queue error: {resp.status_code}")
                return [], {}
                
    except Exception as e:
        logger.error(f"[{ENVIRONMENT}] Extension queue fetch failed: {e}")
        return [], {}


async def fetch_combined_tokens():
    """Combined API - DEX Screener + GeckoTerminal"""
    all_tokens = {}
    source_counts = {'DEX_BOOST': 0, 'DEX_PROFILE': 0, 'DEX_SEARCH': 0, 'GECKO_TREND': 0, 'GECKO_5M': 0, 'GECKO_1H': 0}
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            logger.info(f"[{ENVIRONMENT}]    Fetching DEX boosts...")
            resp = await client.get('https://api.dexscreener.com/token-boosts/top/v1', headers=headers)
            if resp.status_code == 200:
                for item in (resp.json() if isinstance(resp.json(), list) else []):
                    if item.get('chainId') == 'solana':
                        addr = item.get('tokenAddress', '')
                        if addr and addr not in all_tokens:
                            all_tokens[addr] = {'address': addr, 'symbol': item.get('symbol', '???'), 'source': 'DEX_BOOST', 'pair_address': '', 'dex': ''}
                            source_counts['DEX_BOOST'] += 1
            logger.info(f"[{ENVIRONMENT}]    DEX Boosts: {source_counts['DEX_BOOST']}")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    DEX Boosts error: {e}")
        await asyncio.sleep(0.3)
        try:
            logger.info(f"[{ENVIRONMENT}]    Fetching DEX profiles...")
            resp = await client.get('https://api.dexscreener.com/token-profiles/latest/v1', headers=headers)
            if resp.status_code == 200:
                for item in (resp.json() if isinstance(resp.json(), list) else []):
                    if item.get('chainId') == 'solana':
                        addr = item.get('tokenAddress', '')
                        if addr and addr not in all_tokens:
                            all_tokens[addr] = {'address': addr, 'symbol': '???', 'source': 'DEX_PROFILE', 'pair_address': '', 'dex': ''}
                            source_counts['DEX_PROFILE'] += 1
            logger.info(f"[{ENVIRONMENT}]    DEX Profiles: {source_counts['DEX_PROFILE']}")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    DEX Profiles error: {e}")
        await asyncio.sleep(0.3)
        queries = ['pump', 'sol', 'meme', 'ai', 'pepe', 'dog', 'trump', 'wojak', 'chad', 'doge']
        logger.info(f"[{ENVIRONMENT}]    Fetching DEX search...")
        for q in queries:
            try:
                resp = await client.get(f'https://api.dexscreener.com/latest/dex/search?q={q}', headers=headers)
                if resp.status_code == 200:
                    for p in resp.json().get('pairs', []):
                        if p.get('chainId') != 'solana': continue
                        dex = p.get('dexId', '').lower()
                        if dex not in ALLOWED_DEXES: continue
                        addr = p.get('baseToken', {}).get('address', '')
                        if addr and addr not in all_tokens:
                            all_tokens[addr] = {'address': addr, 'pair_address': p.get('pairAddress', ''), 'symbol': p.get('baseToken', {}).get('symbol', '???'), 'source': 'DEX_SEARCH', 'dex': dex, 'price_change_1h': float(p.get('priceChange', {}).get('h1', 0) or 0), 'market_cap': float(p.get('marketCap', 0) or 0), 'liquidity': float(p.get('liquidity', {}).get('usd', 0) or 0)}
                            source_counts['DEX_SEARCH'] += 1
                await asyncio.sleep(0.2)
            except: pass
        logger.info(f"[{ENVIRONMENT}]    DEX Search: {source_counts['DEX_SEARCH']}")
        await asyncio.sleep(0.3)
        try:
            logger.info(f"[{ENVIRONMENT}]    Fetching Gecko trending...")
            resp = await client.get('https://api.geckoterminal.com/api/v2/networks/solana/trending_pools', headers=headers)
            if resp.status_code == 200:
                for pool in resp.json().get('data', []):
                    attrs = pool.get('attributes', {})
                    addr = attrs.get('address', '')
                    name = attrs.get('name', '')
                    symbol = name.split('/')[0].strip()[:20] if '/' in name else name[:20]
                    if addr and addr not in all_tokens:
                        all_tokens[addr] = {'address': '', 'pair_address': addr, 'symbol': symbol, 'source': 'GECKO_TREND', 'dex': ''}
                        source_counts['GECKO_TREND'] += 1
            logger.info(f"[{ENVIRONMENT}]    Gecko Trending: {source_counts['GECKO_TREND']}")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    Gecko Trending error: {e}")
        await asyncio.sleep(0.3)
        try:
            logger.info(f"[{ENVIRONMENT}]    Fetching Gecko 5M...")
            resp = await client.get('https://api.geckoterminal.com/api/v2/networks/solana/pools?page=1&sort=h24_volume_usd_desc', headers=headers)
            if resp.status_code == 200:
                for pool in resp.json().get('data', [])[:30]:
                    attrs = pool.get('attributes', {})
                    addr = attrs.get('address', '')
                    name = attrs.get('name', '')
                    symbol = name.split('/')[0].strip()[:20] if '/' in name else name[:20]
                    if addr and addr not in all_tokens:
                        all_tokens[addr] = {'address': '', 'pair_address': addr, 'symbol': symbol, 'source': 'GECKO_5M', 'dex': ''}
                        source_counts['GECKO_5M'] += 1
            logger.info(f"[{ENVIRONMENT}]    Gecko 5M: {source_counts['GECKO_5M']}")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    Gecko 5M error: {e}")
        await asyncio.sleep(0.3)
        try:
            logger.info(f"[{ENVIRONMENT}]    Fetching Gecko 1H...")
            resp = await client.get('https://api.geckoterminal.com/api/v2/networks/solana/pools?page=1&sort=h1_tx_count_desc', headers=headers)
            if resp.status_code == 200:
                for pool in resp.json().get('data', [])[:30]:
                    attrs = pool.get('attributes', {})
                    addr = attrs.get('address', '')
                    name = attrs.get('name', '')
                    symbol = name.split('/')[0].strip()[:20] if '/' in name else name[:20]
                    if addr and addr not in all_tokens:
                        all_tokens[addr] = {'address': '', 'pair_address': addr, 'symbol': symbol, 'source': 'GECKO_1H', 'dex': ''}
                        source_counts['GECKO_1H'] += 1
            logger.info(f"[{ENVIRONMENT}]    Gecko 1H: {source_counts['GECKO_1H']}")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    Gecko 1H error: {e}")
    tokens = list(all_tokens.values())
    raw = sum(source_counts.values())
    logger.info(f"[{ENVIRONMENT}] 📊 Raw: {raw} -> Unique: {len(tokens)}")
    return tokens, source_counts


async def scrape_dexscreener_tokens(browser_ctx, limit: int = 150) -> list:
    """
    Scrape DEX Screener like Wiz does manually:
    1. Load the page with filters
    2. Scroll to load more tokens  
    3. Extract token data from the table
    """
    tokens = []
    seen_addresses = set()
    source_counts = {'TRENDING': 0, '5M_VOL': 0, '1H_VOL': 0}
    
    try:
        page = await browser_ctx.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Set user agent to look like a real browser
        await page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        
        # Your exact URL with filters
        base_url = "https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1"
        
        logger.info(f"[{ENVIRONMENT}] 🌐 Scraping DEX Screener (Trending 6H)...")
        await page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(3)
        
        # Wait for the table to load
        try:
            await page.wait_for_selector('a[href*="/solana/"]', timeout=15000)
        except:
            logger.warning(f"[{ENVIRONMENT}]    ⚠️ No tokens found on page, trying alternative selector")
        
        await asyncio.sleep(2)
        
        # Scroll down to load more tokens
        for i in range(8):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)
        
        await asyncio.sleep(2)
        
        # Try multiple selectors to find tokens
        rows = await page.query_selector_all('a[href*="/solana/"]')
        if len(rows) == 0:
            rows = await page.query_selector_all('a[href*="dexscreener.com/solana"]')
        if len(rows) == 0:
            # Try getting all links and filtering
            all_links = await page.query_selector_all('a[href]')
            rows = []
            for link in all_links:
                href = await link.get_attribute('href')
                if href and '/solana/' in href and len(href.split('/solana/')[-1]) > 30:
                    rows.append(link)
        
        logger.info(f"[{ENVIRONMENT}]    Found {len(rows)} links")
        
        for row in rows[:limit]:
            try:
                href = await row.get_attribute('href')
                if not href or '/solana/' not in href:
                    continue
                
                pair_address = href.split('/solana/')[-1].split('?')[0]
                if not pair_address or len(pair_address) < 30 or pair_address in seen_addresses:
                    continue
                
                seen_addresses.add(pair_address)
                text = await row.inner_text()
                lines = text.strip().split('\n')
                symbol = lines[0][:20] if lines else '???'
                
                tokens.append({
                    'pair_address': pair_address,
                    'symbol': symbol,
                    'source': 'TRENDING',
                    'address': '',
                    'dex': 'unknown'
                })
                source_counts['TRENDING'] += 1
                logger.info(f"[{ENVIRONMENT}]    👀 {symbol} (TRENDING)")
            except:
                continue
        
        logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['TRENDING']} tokens from Trending")
        
        # Click 5M tab
        try:
            btn_5m = await page.query_selector('button:has-text("5M"), [data-value="5M"]')
            if btn_5m:
                await btn_5m.click()
                await asyncio.sleep(2)
                rows_5m = await page.query_selector_all('a[href*="/solana/"]')
                for row in rows_5m[:30]:
                    try:
                        href = await row.get_attribute('href')
                        pair_address = href.split('/solana/')[-1].split('?')[0] if href else ''
                        if not pair_address or len(pair_address) < 30 or pair_address in seen_addresses:
                            continue
                        seen_addresses.add(pair_address)
                        text = await row.inner_text()
                        symbol = text.strip().split('\n')[0][:20]
                        tokens.append({'pair_address': pair_address, 'symbol': symbol, 'source': '5M_VOL', 'address': '', 'dex': 'unknown'})
                        source_counts['5M_VOL'] += 1
                        logger.info(f"[{ENVIRONMENT}]    👀 {symbol} (5M_VOL)")
                    except:
                        continue
                logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['5M_VOL']} tokens from 5M Volume")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    ⚠️ 5M tab error: {e}")
        
        # Click 1H tab
        try:
            btn_1h = await page.query_selector('button:has-text("1H"), [data-value="1H"]')
            if btn_1h:
                await btn_1h.click()
                await asyncio.sleep(2)
                rows_1h = await page.query_selector_all('a[href*="/solana/"]')
                for row in rows_1h[:30]:
                    try:
                        href = await row.get_attribute('href')
                        pair_address = href.split('/solana/')[-1].split('?')[0] if href else ''
                        if not pair_address or len(pair_address) < 30 or pair_address in seen_addresses:
                            continue
                        seen_addresses.add(pair_address)
                        text = await row.inner_text()
                        symbol = text.strip().split('\n')[0][:20]
                        tokens.append({'pair_address': pair_address, 'symbol': symbol, 'source': '1H_VOL', 'address': '', 'dex': 'unknown'})
                        source_counts['1H_VOL'] += 1
                        logger.info(f"[{ENVIRONMENT}]    👀 {symbol} (1H_VOL)")
                    except:
                        continue
                logger.info(f"[{ENVIRONMENT}]    ✅ Found {source_counts['1H_VOL']} tokens from 1H Volume")
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    ⚠️ 1H tab error: {e}")
        
        await page.close()
        
        raw_total = source_counts['TRENDING'] + source_counts['5M_VOL'] + source_counts['1H_VOL']
        logger.info(f"[{ENVIRONMENT}] 📊 Raw: {raw_total} → Unique: {len(tokens)} (deduped {raw_total - len(tokens)})")
        
        return tokens, source_counts
        
    except Exception as e:
        logger.error(f"[{ENVIRONMENT}] ❌ DEX Screener scrape error: {e}")
        return tokens, source_counts



async def get_extension_screenshot(pair_address: str) -> bytes:
    """Get screenshot captured by Chrome extension, resized for API limits"""
    import os
    filepath = f'/opt/jayce/data/screenshots/{pair_address}.png'
    if os.path.exists(filepath):
        try:
            # Resize to max 1800px (under 2000px API limit for many-image requests)
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(filepath)
            max_dim = 1800
            
            if img.width > max_dim or img.height > max_dim:
                ratio = min(max_dim / img.width, max_dim / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            
            buf = BytesIO()
            img.save(buf, format='PNG', optimize=True)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Screenshot resize error: {e}")
            # Fallback to original
            with open(filepath, 'rb') as f:
                return f.read()
    return None


async def screenshot_chart(pair_address: str, symbol: str, browser_ctx, token_address: str = None) -> tuple:
    if not pair_address: return None, None
    
    # Try extension screenshot first (real DEX Screener capture)
    ext_screenshot = await get_extension_screenshot(pair_address)
    if ext_screenshot:
        logger.info(f"📸 {symbol}: Using extension screenshot")
        # Fetch candles using candle provider (Birdeye → GeckoTerminal fallback)
        candles = await fetch_candles(pair_address, symbol, token_address)
        return ext_screenshot, candles
    
    # Fallback to GeckoTerminal chart generation
    await asyncio.sleep(3)  # Rate limit protection for GeckoTerminal
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pair_address}/ohlcv/minute?aggregate=5&limit=100")
        if resp.status_code != 200: return None, None
        ohlcv = resp.json().get('data', {}).get('attributes', {}).get('ohlcv_list', [])
        if len(ohlcv) < 10: return None, None
        
        candles = sorted([{'ts': int(c[0]), 'o': float(c[1]), 'h': float(c[2]), 'l': float(c[3]), 'c': float(c[4]), 'v': float(c[5])} for c in ohlcv], key=lambda x: x['ts'])
        
        # Scam filters
        vols = [c['v'] for c in candles if c['v'] > 0]
        if len(vols) >= 10:
            vol_mean = sum(vols) / len(vols)
            if vol_mean > 0:
                vol_cv = ((sum((v - vol_mean)**2 for v in vols) / len(vols))**0.5) / vol_mean
                if vol_cv < 0.5:
                    DAILY_METRICS['blocked_wash_trading'] += 1
                    return None, None
        
        # Render chart
        W, H = 1400, 700
        img = Image.new('RGB', (W, H), (13, 17, 23))
        draw = ImageDraw.Draw(img)
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except: font = ImageFont.load_default()
        
        draw.text((60, 10), f"{symbol} · 5M", fill=(255,255,255), font=font)
        
        highs, lows = [c['h'] for c in candles], [c['l'] for c in candles]
        price_max, price_min = max(highs), min(lows)
        price_range = price_max - price_min or price_max * 0.01
        
        n = len(candles)
        for i, c in enumerate(candles):
            x = 60 + int((i + 0.5) * 1280 / n)
            color = (0, 200, 83) if c['c'] >= c['o'] else (255, 23, 68)
            y_h = int(50 + (1 - (c['h'] - price_min) / price_range) * 590)
            y_l = int(50 + (1 - (c['l'] - price_min) / price_range) * 590)
            y_o = int(50 + (1 - (c['o'] - price_min) / price_range) * 590)
            y_c = int(50 + (1 - (c['c'] - price_min) / price_range) * 590)
            draw.line([(x, y_h), (x, y_l)], fill=color, width=1)
            draw.rectangle([(x-3, min(y_o,y_c)), (x+3, max(y_o,y_c)+1)], fill=color)
        
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue(), candles
    except Exception as e:
        logger.error(f"❌ Chart error: {e}")
        return None, None

# ══════════════════════════════════════════════════════════════════════════════
# v4.1: VISION AI WITH FLASHCARD TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def build_flashcard_vision_prompt(setup_name: str, training_context: str, num_examples: int) -> str:
    """Build the vision prompt that includes flashcard training context"""
    return f"""You are analyzing a chart to determine if it matches Wiz's trading style.

SETUP TYPE TO EVALUATE: "{setup_name}"

TRAINING CONTEXT: {training_context}

I'm showing you {num_examples} EXAMPLE FLASHCARD(S) of successful "{setup_name}" setups that Wiz has traded profitably. Study these examples carefully - they represent EXACTLY what a good setup looks like.

After the examples, you'll see the NEW CHART to analyze.

COMPARE the new chart to the flashcard examples and determine:
1. Does it have similar structure to the examples?
2. Does it show the same Fib retracement pattern?
3. Is there a clear flip zone like in the examples?
4. Would Wiz take this trade based on his trained examples?

RESPOND IN JSON:
{{
    "is_setup": true/false,
    "setup_type": "{setup_name}",
    "confidence": 0-100,
    "match_to_training": 0-100,
    "stage": "testing/forming/confirmed",
    "reasoning": "Brief explanation comparing to the training examples"
}}

The "match_to_training" score should reflect how closely this chart resembles the flashcard examples (0 = nothing alike, 100 = perfect match to Wiz's style).
"""

async def analyze_chart_with_flashcards(image_bytes: bytes, symbol: str, setup_name: str) -> dict:
    """Analyze chart using flashcard examples as visual references"""
    if not can_use_vision(): 
        return {'is_setup': False, 'confidence': 0}
    
    try:
        # Get flashcard examples for this setup type
        flashcard_examples = await get_flashcard_examples(setup_name, FLASHCARD_EXAMPLES_PER_SETUP)
        training_context = get_training_context(setup_name)
        
        # Build message content with flashcard images + new chart
        content = []
        
        # Add flashcard examples first
        for i, example in enumerate(flashcard_examples):
            content.append({
                "type": "text", 
                "text": f"📚 TRAINING EXAMPLE {i+1}: {example['token']} — {example['outcome']}% profit — {example['notes']}"
            })
            
            # Detect image format from bytes
            img_bytes = example['image_bytes']
            if img_bytes[:3] == b'\xff\xd8\xff':
                media_type = "image/jpeg"
            elif img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                media_type = "image/png"
            else:
                media_type = "image/jpeg"  # Default to JPEG
            
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(img_bytes).decode()
                }
            })
        
        # Add separator
        content.append({
            "type": "text",
            "text": f"\n{'═' * 50}\n🔍 NEW CHART TO ANALYZE: {symbol}\n{'═' * 50}"
        })
        
        # Add the new chart to analyze
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image_bytes).decode()
            }
        })
        
        # Add the prompt
        prompt = build_flashcard_vision_prompt(setup_name, training_context, len(flashcard_examples))
        content.append({"type": "text", "text": prompt})
        
        # Call Claude Vision
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": content}]
        )
        
        increment_vision_usage()
        DAILY_METRICS['vision_calls'] += 1
        
        text = response.content[0].text
        logger.info(f"🧠 Vision+Flashcards ({len(flashcard_examples)} examples): {symbol}")
        
        try:
            return json.loads(text)
        except:
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            return json.loads(m.group()) if m else {'is_setup': False}
            
    except Exception as e:
        logger.error(f"❌ Vision+Flashcards error: {e}")
        return {'is_setup': False, 'confidence': 0}

async def analyze_chart_vision(image_bytes: bytes, symbol: str, setup_name: str = None) -> dict:
    """
    v4.1: Enhanced vision analysis
    - If engine detected a setup, use flashcard-trained analysis
    - Otherwise, use basic analysis
    """
    if setup_name and TRAINING_DATA:
        # Use flashcard-trained analysis
        return await analyze_chart_with_flashcards(image_bytes, symbol, setup_name)
    
    # Fallback to basic analysis (no flashcards)
    if not can_use_vision(): 
        return {'is_setup': False, 'confidence': 0}
    
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        basic_prompt = """Analyze this 5M chart. Is it a Wiz Fib + Flip Zone setup?
SETUP TYPES: "382 + Flip Zone", "50 + Flip Zone", "618 + Flip Zone", "786 + Flip Zone", "Under-Fib Flip Zone"
RESPOND IN JSON: {"is_setup": true/false, "setup_type": "...", "confidence": 0-100, "stage": "testing/forming/confirmed", "reasoning": "..."}"""
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=500,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode()}},
                {"type": "text", "text": f"Token: {symbol}\n{basic_prompt}"}
            ]}])
        
        increment_vision_usage()
        DAILY_METRICS['vision_calls'] += 1
        text = response.content[0].text
        
        try: 
            return json.loads(text)
        except:
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            return json.loads(m.group()) if m else {'is_setup': False}
    except Exception as e:
        logger.error(f"❌ Vision error: {e}")
        return {'is_setup': False}

# ══════════════════════════════════════════════════════════════════════════════
# ALERT SYSTEM — v4.1: Includes flashcard match info
# ══════════════════════════════════════════════════════════════════════════════


async def send_forming_alert(token: dict, engine_result: dict, chart_bytes: bytes, combined_score: float):
    """Send FORMING alert to private channel"""
    try:
        symbol = token.get('symbol', '???')
        address = token.get('address', '')
        setup_name = engine_result.get('engine_name', 'Unknown')
        grade = engine_result.get('grade', '?')
        dex = token.get('dex', 'unknown').upper()
        
        if was_alert_sent(address, f"FORMING_{setup_name}", ALERT_COOLDOWN_MINUTES / 60):
            return False
        
        caption = f"""⏳ <b>FORMING SETUP</b>

<b>{symbol}</b> ({dex})
━━━━━━━━━━━━━━━━━━━━
<b>Setup:</b> {setup_name}
<b>Engine Grade:</b> {grade}
<b>Score:</b> {combined_score:.0f}/100
<b>Stage:</b> FORMING

<i>Watching for confirmation...</i>

<a href="https://dexscreener.com/solana/{address}">View Chart</a>
"""
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_photo(
            chat_id=FORMING_CHAT_ID or HEARTBEAT_CHAT_ID,
            photo=chart_bytes,
            caption=caption,
            parse_mode=ParseMode.HTML
        ) if chart_bytes else None
        
        record_alert_sent(address, f"FORMING_{setup_name}")
        log_alert(symbol, setup_name, int(combined_score), grade, address)
        logger.info(f"⏳ FORMING Alert: {symbol} — {setup_name} — Score: {combined_score:.0f}")
        return True
    except Exception as e:
        logger.error(f"❌ FORMING alert error: {e}")
        return False



async def send_wiztheory_alert(token: dict, bangers_result: dict, impulse_result: dict, 
                                vision_result: dict, chart_bytes: bytes):
    """Send full WizTheory breakdown alert"""
    try:
        symbol = token.get('symbol', '???')
        address = token.get('address') or token.get('token_address', '')
        setup_type = bangers_result.get('wiz_setup_type', 'Unknown')
        
        if was_alert_sent(address, f"WIZTHEORY_{setup_type}", ALERT_COOLDOWN_MINUTES / 60):
            return False
        
        # Build the full breakdown message
        caption = format_wiztheory_alert(token, bangers_result, impulse_result, vision_result)
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        if chart_bytes:
            await bot.send_photo(
                chat_id=FORMING_CHAT_ID or HEARTBEAT_CHAT_ID,
                photo=chart_bytes,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(
                chat_id=FORMING_CHAT_ID or HEARTBEAT_CHAT_ID,
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        
        record_alert_sent(address, f"WIZTHEORY_{setup_type}")
        log_alert(symbol, setup_type, int(bangers_result.get('score', 0)), bangers_result.get('grade', '?'), address)
        logger.info(f"🎯 WIZTHEORY Alert: {symbol} — {setup_type} — Grade: {bangers_result.get('grade')} — Score: {bangers_result.get('score')}")
        return True
    except Exception as e:
        logger.error(f"❌ WIZTHEORY alert error: {e}")
        return False

async def send_alert(token: dict, vision_result: dict, chart_bytes: bytes, tier_name: str, tier_emoji: str, combined_score: float, engine_result: dict = None):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        symbol = token.get('symbol', '???')
        address = token.get('address', '')
        
        # Use engine data if available
        if engine_result:
            setup_type = engine_result.get('engine_name', 'Unknown')
            grade = engine_result.get('grade', '?')
            engine_score = engine_result.get('score', 0)
            whale = '🐋' if engine_result.get('has_whale') else ''
            engine_info = format_engine_result_text(engine_result)
        else:
            setup_type = vision_result.get('setup_type', 'Unknown')
            grade, engine_score, whale, engine_info = '?', 0, '', ''
        
        confidence = vision_result.get('confidence', 0)
        match_to_training = vision_result.get('match_to_training', 0)  # v4.1
        mc = token.get('market_cap', 0)
        liq = token.get('liquidity', 0)
        h1 = token.get('price_change_1h', 0)
        h24 = token.get('price_change_24h', 0)
        
        # v4.1: Add flashcard match indicator
        flashcard_indicator = ""
        if match_to_training >= 80:
            flashcard_indicator = "📚 STRONG MATCH"
        elif match_to_training >= 60:
            flashcard_indicator = "📖 Good Match"
        elif match_to_training >= 40:
            flashcard_indicator = "📄 Partial Match"
        
        msg = f"""🚨 <b>JAYCE ALERT — {symbol}</b> {tier_emoji} <b>{tier_name}</b> {whale}

<b>Setup:</b> {setup_type}
<b>Grade:</b> {grade} | <b>Score:</b> {combined_score:.0f}/100
<b>Engine:</b> {engine_score} | <b>Vision:</b> {confidence}
{f'<b>Training Match:</b> {match_to_training}% {flashcard_indicator}' if match_to_training else ''}

💰 MC: ${mc:,.0f} | 💧 Liq: ${liq:,.0f}
📈 1h: {h1:+.1f}% | 24h: {h24:+.1f}%

{engine_info}

<code>{address}</code>"""

        pair = token.get('pair_address', address)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📊 DexScreener", url=f"https://dexscreener.com/solana/{pair}")]])
        
        if chart_bytes:
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=chart_bytes, caption=msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
        record_alert_sent(address, setup_type)
        DAILY_METRICS[f'{tier_name.lower()}_alerts'] += 1
        logger.info(f"✅ Alert: {symbol} — {setup_type} — {tier_emoji} {tier_name} — Training Match: {match_to_training}%")
    except Exception as e:
        logger.error(f"❌ Alert error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN PROCESS TOKEN — v4.1: Engine + Flashcard Vision hybrid
# ══════════════════════════════════════════════════════════════════════════════

async def process_token(token: dict, browser_ctx, psef_result: dict = None, psef_candles: list = None) -> bool:
    symbol = token.get('symbol', '???')
    address = token.get('address', '')
    DAILY_METRICS['coins_scanned'] += 1
    
    # ══════════════════════════════════════════════════════════════
    # COIN AGE FILTER — Skip baby charts (less than 3 hours old)
    # ══════════════════════════════════════════════════════════════
    age_hours = token.get('age_hours', 999)
    if age_hours < MIN_COIN_AGE_HOURS:
        logger.info(f"⏳ {symbol}: Too new ({age_hours:.1f}h < {MIN_COIN_AGE_HOURS}h) — SKIPPED")
        return False
    
    # Pre-filter
    passed, reason = pre_filter_token(token)
    if not passed:
        logger.info(f"❌ {symbol}: Pre-filter failed: {reason}")
        return False
    DAILY_METRICS['coins_passed_prefilter'] += 1
    
    # Vision gate
    should_vision, trigger, stage = should_use_vision(token)
    if False:  # Disabled - let engine decide
        DAILY_METRICS['blocked_no_impulse'] += 1
        return False
    if not can_use_vision():
        logger.info(f"❌ {symbol}: Vision cap reached")
        return False
    
    on_cd, cd_reason = is_on_vision_cooldown(token)
    if on_cd:
        logger.info(f"❌ {symbol}: On cooldown - {cd_reason}")
        DAILY_METRICS['blocked_cooldown'] += 1
        return False
    
    # Screenshot + candles
    pair_address = token.get('pair_address', '')
    if not pair_address:
        logger.info(f"❌ {symbol}: No pair address")
        return False
    
    token_address = token.get('address', '')
    chart_bytes, candles = await screenshot_chart(pair_address, symbol, browser_ctx, token_address)
    if not chart_bytes: return False
    
    # ══════════════════════════════════════════════════════════════
    # CANDLE COUNT FILTER — Need enough chart development
    # ══════════════════════════════════════════════════════════════
    if candles and len(candles) < MIN_CANDLES:
        logger.info(f"📊 {symbol}: Not enough candles ({len(candles)} < {MIN_CANDLES}) — SKIPPED")
        return False
    
    # v4.1: Run WizTheory engine detection
    engine_result = None
    detected_setup = None
    if candles and len(candles) >= 10:
        # Add hybrid gate info to token for engine
        token['passes_50fz_gate'] = candidate.get('passes_50fz_gate', True) if 'candidate' in dir() else True
        token['ath_breakout'] = candidate.get('ath_breakout', False) if 'candidate' in dir() else False
        token['major_high_break'] = candidate.get('major_high_break', False) if 'candidate' in dir() else False
        
        engine_result = run_detection(token, candles)
        if engine_result:
            DAILY_METRICS['engine_triggers'] += 1
            detected_setup = engine_result.get('engine_name')
            
            # v4.2: Track engine-specific detections
            engine_id = engine_result.get('engine_id', '')
            if engine_id == '382':
                DAILY_METRICS['engine_382'] += 1
            elif engine_id == '50':
                DAILY_METRICS['engine_50'] += 1
            elif engine_id == '618':
                DAILY_METRICS['engine_618'] += 1
            elif engine_id == '786':
                DAILY_METRICS['engine_786'] += 1
            elif engine_id == 'underfib':
                DAILY_METRICS['engine_underfib'] += 1
            
            logger.info(f"[{ENVIRONMENT}] 🎯 ENGINE: {symbol} → {detected_setup} Grade: {engine_result['grade']}")
    
    # PHASE 2: Vision gating - only run Vision if engine grade meets threshold
    vision_result = {'is_setup': False, 'confidence': 0, 'match_to_training': 0}
    engine_grade = engine_result.get('grade', '') if engine_result else ''
    
    # ══════════════════════════════════════════════════════════════
    # WIZTHEORY PIPELINE (BANGERS ONLY)
    # ══════════════════════════════════════════════════════════════
    # Pipeline: PSEF → Impulse Detector → Structure → RSI → Candles → Grader
    # Target: 3-10 high-quality alerts per day
    # Only A/A+ grades trigger alerts
    
    # Use PSEF candles if available, otherwise use candles from screenshot
    analysis_candles = psef_candles if psef_candles else candles
    
    if not analysis_candles or len(analysis_candles) < 20:
        logger.info(f"⏭️ {symbol}: Not enough candles for analysis")
        return False
    
    # ══════════════════════════════════════════════════════════════
    # STEP 1: IMPULSE DETECTOR (WizTheory Setup Detection)
    # ══════════════════════════════════════════════════════════════
    impulse_result = detect_wiztheory_setup(analysis_candles)
    
    # Log impulse detection
    logger.info(f"[{ENVIRONMENT}]    📐 Impulse: {impulse_result.get('summary', 'No setup')}")
    
    # ══════════════════════════════════════════════════════════════
    # SETUP WATCH: Alert BEFORE bounce when price approaching zone
    # ══════════════════════════════════════════════════════════════
    if impulse_result.get('setup_detected', False):
        # Get current price from latest candle
        current_price = 0
        if analysis_candles:
            last_candle = analysis_candles[-1]
            current_price = float(last_candle.get('close') or last_candle.get('c') or 0)
        
        watch_alert = check_setup_watch(
            symbol=symbol,
            token_address=token.get('address') or token.get('token_address', ''),
            current_price=current_price,
            impulse_result=impulse_result,
            candles=analysis_candles,
            structure_result=bangers_result.get('structure', {})
        )
        
        if watch_alert:
            logger.info(f"[{ENVIRONMENT}]    👁️ SETUP WATCH: {symbol} - {watch_alert['setup_type']} @ {watch_alert['distance_pct']:.1f}% from zone")
            
            # Send Setup Watch alert
            try:
                watch_message = format_setup_watch_message(watch_alert)
                await send_telegram_message(watch_message)
                logger.info(f"[{ENVIRONMENT}]    📨 Setup Watch alert sent for {symbol}")
            except Exception as e:
                logger.error(f"[{ENVIRONMENT}]    ❌ Failed to send watch alert: {e}")
    
    # If no valid WizTheory setup detected, skip (unless engine already found something)
    if not impulse_result.get('setup_detected', False) and not engine_result:
        logger.info(f"[{ENVIRONMENT}]    ⏭️ {symbol}: No WizTheory setup detected")
        return False
    
    # Get setup type from impulse detector (382, 50, 618, 786, UNDER_FIB)
    wiz_setup_type = impulse_result.get('setup_type', None)
    impulse_data = impulse_result.get('impulse', {})
    retrace_data = impulse_result.get('retrace', {})
    
    # Check retrace quality - reject poor retraces
    retrace_quality = retrace_data.get('retrace_quality', 'UNKNOWN')
    if retrace_quality == 'POOR' and not impulse_result.get('setup_detected', False):
        logger.info(f"[{ENVIRONMENT}]    ⏭️ {symbol}: Retrace quality POOR - skipping")
        return False
    
    # Check for setup failure conditions
    if retrace_data.get('setup_failing', False):
        failure_reason = retrace_data.get('failure_reason', 'Unknown')
        logger.info(f"[{ENVIRONMENT}]    ❌ {symbol}: Setup failing - {failure_reason}")
        return False
    
    # ══════════════════════════════════════════════════════════════
    # STEP 2: RUN FULL ANALYSIS PIPELINE
    # ══════════════════════════════════════════════════════════════
    
    # Run the full BANGERS analysis pipeline
    bangers_result = run_bangers_analysis(
        candles=analysis_candles,
        psef_result=psef_result if psef_result else {'passed': True},
        engine_result=engine_result,
        flashcard_similarity=engine_result.get('confidence', 0) if engine_result else 0
    )
    
    # Enhance result with impulse data
    bangers_result['impulse'] = impulse_result
    bangers_result['wiz_setup_type'] = wiz_setup_type
    bangers_result['retrace_quality'] = retrace_quality
    
    # ══════════════════════════════════════════════════════════════
    # IMPULSE BONUS: Reward valid WizTheory impulse setups
    # ══════════════════════════════════════════════════════════════
    impulse_bonus = 0
    
    # Check EITHER impulse detector OR engine result for valid setup
    imp_score = impulse_data.get('score', 0)
    eng_score = engine_result.get('score', 0) if engine_result else 0
    eng_grade = engine_result.get('grade', '') if engine_result else ''
    
    # Use the higher score between impulse detector and engine
    best_score = max(imp_score, eng_score)
    
    # Apply bonus if either system detected a valid setup
    if impulse_result.get('setup_detected', False) or (engine_result and eng_grade in ['A+', 'A', 'B+']):
        if best_score >= 80:
            impulse_bonus = 15
        elif best_score >= 60:
            impulse_bonus = 10
        elif best_score >= 40:
            impulse_bonus = 5
        
        if impulse_bonus > 0:
            bangers_result['score'] = min(100, bangers_result['score'] + impulse_bonus)
            bangers_result['impulse_bonus'] = impulse_bonus
            logger.info(f"[{ENVIRONMENT}]    🚀 Impulse bonus: +{impulse_bonus} pts (best score: {best_score})")
        
    # ══════════════════════════════════════════════════════════════════════
    # NEW INTELLIGENCE LAYERS (capped scoring) - Always run for detected setups
    # ══════════════════════════════════════════════════════════════════════
    if engine_result and eng_grade in ['A+', 'A', 'B+', 'B']:
        try:
            # Layer 4: Pullback Quality
            pullback_result = analyze_pullback_quality(candles)
            pullback_bonus = pullback_result['score_impact']  # -6 to +6
            
            # Layer 5: Setup Maturity (info only, no score impact)
            flip_zone = engine_result.get('entry_zone', 0) if engine_result else 0
            maturity_result = detect_setup_maturity(candles, flip_zone)
            
            # Layer 6: Momentum/RSI
            momentum_result = analyze_momentum_behavior(candles)
            momentum_bonus = momentum_result['score_impact']  # -2 to +3
            
            # Apply capped intel bonus
            intel_bonus = pullback_bonus + momentum_bonus  # Max: -8 to +9
            if intel_bonus != 0:
                new_score = bangers_result['score'] + intel_bonus
                new_score = max(0, min(100, new_score))
                bangers_result['score'] = new_score
                bangers_result['intel_bonus'] = intel_bonus
                logger.info(f"[{ENVIRONMENT}]    🧠 Intel bonus: {intel_bonus:+d} pts ({pullback_result['quality']} | {momentum_result['classification']})")
            else:
                logger.info(f"[{ENVIRONMENT}]    🧠 Intel: {pullback_result['quality']} | {momentum_result['classification']} | {maturity_result['maturity']}")
            
            # Store for logging/alerts
            bangers_result['pullback'] = pullback_result
            bangers_result['maturity'] = maturity_result
            bangers_result['momentum'] = momentum_result
            
            # Log maturity for timing context
            if maturity_result['maturity'] in ['SETUP_READY', 'SETUP_TRIGGERED']:
                logger.info(f"[{ENVIRONMENT}]    ⏱️ Maturity: {maturity_result['maturity']} - {maturity_result['recommendation']}")
            elif maturity_result['maturity'] == 'SETUP_LATE':
                logger.info(f"[{ENVIRONMENT}]    ⚠️ Maturity: SETUP_LATE - {maturity_result['recommendation']}")
                
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    ⚠️ Intel layers error: {e}")
            
            # Recalculate grade after impulse bonus
            new_score = bangers_result['score']
            if new_score >= 95:
                bangers_result['grade'] = 'A+'
            elif new_score >= 80:
                bangers_result['grade'] = 'A'
            elif new_score >= 75:
                bangers_result['grade'] = 'B+'
            elif new_score >= 65:
                bangers_result['grade'] = 'B'
            
            # Update should_alert
            bangers_result['should_alert'] = bangers_result['grade'] in ['A', 'A+'] and new_score >= 80
    
    # Boost or downgrade based on impulse quality
    impulse_score = impulse_data.get('score', 0)
    impulse_grade = impulse_result.get('grade', 'C')
    
    # If impulse detected a valid setup with good grade, boost confidence
    if impulse_result.get('setup_detected', False) and impulse_grade in ['A', 'B']:
        # Add impulse bonus to overall score (up to 5 points)
        impulse_bonus = min(5, impulse_score // 20)
        bangers_result['score'] = min(100, bangers_result['score'] + impulse_bonus)
        bangers_result['impulse_bonus'] = impulse_bonus
        
        # Recalculate grade if score improved
        new_score = bangers_result['score']
        if new_score >= 95:
            bangers_result['grade'] = 'A+'
        elif new_score >= 80:
            bangers_result['grade'] = 'A'
        
        # Update should_alert based on new grade
        bangers_result['should_alert'] = bangers_result['grade'] in ['A', 'A+'] and new_score >= 80
    
    # Log the analysis
    logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
    logger.info(f"[{ENVIRONMENT}] WIZTHEORY ANALYSIS: {symbol}")
    logger.info(f"[{ENVIRONMENT}]    Setup: {wiz_setup_type or 'Unknown'} | Grade: {bangers_result['grade']} | Score: {bangers_result['score']}")
    
    # Log impulse data
    if impulse_data:
        exp_pct = impulse_data.get('expansion_pct', 0)
        imp_score = impulse_data.get('score', 0)
        logger.info(f"[{ENVIRONMENT}]    Impulse: {exp_pct:.0f}% expansion | Score: {imp_score} | Retrace: {retrace_quality}")
    
    # Get breakdown for logging
    grader = bangers_result.get('grader', {})
    breakdown = grader.get('breakdown', {})
    
    logger.info(f"[{ENVIRONMENT}]    Structure: {bangers_result.get('structure', {}).get('trend', '?')} ({breakdown.get('structure', {}).get('points', 0)}/30)")
    logger.info(f"[{ENVIRONMENT}]    RSI: {bangers_result.get('rsi', {}).get('mode', '?')} ({breakdown.get('rsi', {}).get('points', 0)}/25)")
    logger.info(f"[{ENVIRONMENT}]    Candles: {bangers_result.get('candles', {}).get('recent_character', '?')} ({breakdown.get('candles', {}).get('points', 0)}/15)")
    
    # ══════════════════════════════════════════════════════════════
    # STEP 3: FLASHCARD VISION AI (Only for scores 70+)
    # ══════════════════════════════════════════════════════════════
    vision_bonus = 0
    vision_result = None
    
    # Use wiz_setup_type if available, otherwise fall back to engine detection
    vision_setup_type = wiz_setup_type
    if not vision_setup_type and engine_result:
        # Map engine names to setup types
        engine_name = engine_result.get('engine_name', '')
        if '382' in engine_name:
            vision_setup_type = '382'
        elif '618' in engine_name:
            vision_setup_type = '618'
        elif '786' in engine_name:
            vision_setup_type = '786'
        elif '50' in engine_name or 'fifty' in engine_name.lower():
            vision_setup_type = '50'
        elif 'under' in engine_name.lower() or 'fib' in engine_name.lower():
            vision_setup_type = 'Under-Fib'
    
    if bangers_result['score'] >= 60 and vision_setup_type and chart_bytes:
        # Save chart temporarily for Vision comparison
        import tempfile
        import os as vision_os
        temp_chart = f"/tmp/vision_chart_{symbol}.png"
        try:
            with open(temp_chart, 'wb') as f:
                f.write(chart_bytes)
            
            # Run Vision AI comparison
            vision_result = analyze_with_flashcards(
                live_chart_path=temp_chart,
                setup_type=vision_setup_type,
                current_score=bangers_result['score']
            )
            
            if vision_result.get('ran_vision'):
                vision_bonus = vision_result.get('bonus_points', 0)
                similarity = vision_result.get('similarity', 0)
                
                # Log Vision results
                logger.info(f"[{ENVIRONMENT}]    👁️ Vision: {similarity}% similarity | +{vision_bonus} bonus")
                
                if vision_result.get('top_matches'):
                    logger.info(f"[{ENVIRONMENT}]    Flashcard Matches:")
                    for match in vision_result.get('top_matches', [])[:3]:
                        logger.info(f"[{ENVIRONMENT}]      - {match.get('chart_id', '?')} → {match.get('similarity', 0)}%")
                
                # Apply vision bonus to score
                bangers_result['score'] = min(100, bangers_result['score'] + vision_bonus)
                bangers_result['vision_bonus'] = vision_bonus
                bangers_result['vision_similarity'] = similarity
                
                # Recalculate grade
                new_score = bangers_result['score']
                if new_score >= 95:
                    bangers_result['grade'] = 'A+'
                elif new_score >= 80:
                    bangers_result['grade'] = 'A'
                elif new_score >= 75:
                    bangers_result['grade'] = 'B+'
                
                # Update should_alert
                bangers_result['should_alert'] = bangers_result['grade'] in ['A', 'A+'] and new_score >= 80
            else:
                logger.info(f"[{ENVIRONMENT}]    👁️ Vision skipped: {vision_result.get('reason', 'unknown')}")
                
        except Exception as e:
            logger.error(f"[{ENVIRONMENT}]    👁️ Vision error: {e}")
        finally:
            if vision_os.path.exists(temp_chart):
                vision_os.remove(temp_chart)
    
    # ══════════════════════════════════════════════════════════════════════
    # RUNNER INTELLIGENCE LAYER (post-detection analysis)
    # ══════════════════════════════════════════════════════════════════════
    runner_result = None
    if engine_result and eng_grade in ['A+', 'A', 'B+', 'B']:
        try:
            entry_zone = engine_result.get('entry_zone', 0)
            runner_result = analyze_runner_intelligence(candles, entry_zone)
            
            if runner_result['runner_probability'] in ['HIGH', 'MEDIUM']:
                runner_log = format_runner_log(runner_result)
                if runner_log:
                    logger.info(f"[{ENVIRONMENT}]    {runner_log}")
            
            # Store for alert
            bangers_result['runner'] = runner_result
            
        except Exception as e:
            logger.warning(f"[{ENVIRONMENT}]    ⚠️ Runner intelligence error: {e}")
    
    if bangers_result['should_alert']:
        # WIZTHEORY BANGER FOUND - Send alert with full breakdown
        setup_label = wiz_setup_type if wiz_setup_type else (engine_result.get('engine_name', 'Setup') if engine_result else 'Setup')
        
        # Format full WizTheory breakdown message
        alert_message = format_wiztheory_alert(
            token=token,
            bangers_result=bangers_result,
            impulse_result=impulse_result,
            vision_result=vision_result
        )
        logger.info(f"[{ENVIRONMENT}]    🎯 WIZTHEORY ALERT: {setup_label} | Grade {bangers_result['grade']} | Score {bangers_result['score']}")
        if impulse_data:
            logger.info(f"[{ENVIRONMENT}]    📐 Expansion: {impulse_data.get('expansion_pct', 0):.0f}% | Retrace: {retrace_quality}")
        logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
        
        # Add impulse data to token for alert formatting
        token['wiz_setup_type'] = wiz_setup_type
        token['impulse_data'] = impulse_data
        token['retrace_quality'] = retrace_quality
        
        # Remove from watchlist if it was there
        remove_from_watchlist(token.get('pair_address', ''))
        
        # Send alert with full WizTheory breakdown
        await send_wiztheory_alert(token, bangers_result, impulse_result, vision_result, chart_bytes)
        DAILY_METRICS['alerts_sent'] += 1
        return True
    else:
        # Not a banger - check for watchlist
        logger.info(f"[{ENVIRONMENT}]    Alert: NO (Grade {bangers_result['grade']}, Score {bangers_result['score']})")
        
        if bangers_result['grade'] in ['B+', 'B'] and engine_result:
            add_to_sticky_watchlist(
                token,
                engine_result.get('setup_name', 'Unknown'),
                bangers_result['score'],
                bangers_result['grade']
            )
            logger.info(f"[{ENVIRONMENT}]    👁️ Added to WATCHLIST")
        
        logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
        return False
    
    # Hard block (skip if engine already triggered with good grade)
    if engine_result and engine_result.get('grade') in ['A+', 'A', 'B+']:
        pass  # Trust engine detection - skip hard block
    else:
        blocked, block_reason = hard_block_check(token, vision_result)
        if blocked:
            DAILY_METRICS['blocked_choppy'] += 1
            record_vision_rejection(token)
            return False
    
    # v4.1: Scoring with training match bonus
    engine_score = engine_result.get('score', 0) if engine_result else 0
    vision_confidence = vision_result.get('confidence', 0)
    match_to_training = vision_result.get('match_to_training', 0)
    
    if not vision_result.get('is_setup'): 
        vision_confidence *= 0.3
    
    # v4.1: Boost pattern score based on training match
    setup_name = engine_result.get('engine_name') if engine_result else vision_result.get('setup_type', '')
    pattern_data = get_pattern_matches(setup_name)
    
    # Pattern score now incorporates training match
    if match_to_training >= 70:
        pattern_score = 80  # High match = high pattern score
    elif match_to_training >= 50:
        pattern_score = 60
    elif match_to_training >= 30:
        pattern_score = 45
    else:
        pattern_score = 30  # Low match = lower pattern score
    
    combined_score = calculate_setup_score(engine_score, vision_confidence, pattern_score)
    logger.info(f"📊 {symbol}: Engine={engine_score} Vision={vision_confidence:.0f} TrainMatch={match_to_training} Pattern={pattern_score} → Combined={combined_score:.0f}")
    
    # OPS: Log full scoring breakdown
    eng_grade = engine_result.get('grade', '') if engine_result else ''
    retrace = engine_result.get('retrace_pct', 0) if engine_result else 0
    impulse = engine_result.get('impulse_pct', 0) if engine_result else 0
    rsi = engine_result.get('rsi', 0) if engine_result else 0
    final_stage = 'CONFIRMED' if combined_score >= CONFIRMED_THRESHOLD else ('FORMING' if combined_score >= FORMING_THRESHOLD else 'NONE')
    vision_ran = engine_result and should_run_vision(eng_grade)
    ops_log_scoring(symbol, address, eng_grade, retrace, impulse, rsi, engine_score, vision_confidence, pattern_score, combined_score, vision_ran, final_stage)
    
    # PHASE 2: Two-Tier Alert System
    alert_sent = False
    
    # CONFIRMED alerts (score >= 50) - send to main channel
    if combined_score >= CONFIRMED_THRESHOLD:
        if not was_alert_sent(address, f"CONFIRMED_{setup_name}", ALERT_COOLDOWN_MINUTES / 60):
            tier_name, tier_emoji, _ = get_alert_tier(combined_score)
            if tier_name:
                await send_alert(token, vision_result, chart_bytes, tier_name, tier_emoji, combined_score, engine_result)
                alert_sent = True
    
    # FORMING alerts (score >= 40 but < 50) - send to private channel
    elif combined_score >= FORMING_THRESHOLD and engine_result:
        if not was_alert_sent(address, f"FORMING_{setup_name}", ALERT_COOLDOWN_MINUTES / 60):
            await send_forming_alert(token, engine_result, chart_bytes, combined_score)
            alert_sent = True
    
    if not alert_sent and combined_score < FORMING_THRESHOLD:
        DAILY_METRICS['blocked_low_score'] += 1
        record_vision_rejection(token)
        return False
    return True

# ══════════════════════════════════════════════════════════════════════════════
# SCAN LOOPS
# ══════════════════════════════════════════════════════════════════════════════

async def scan_top_movers(browser_ctx):
    """
    TWO-STAGE SCANNER — Mimics manual trading workflow
    
    STAGE 1: LIGHT SCAN (~100-200 tokens)
    - Use lightweight metrics (price change, volume, liquidity)
    - NO candle fetching
    - Rank and select top 15-20 candidates
    
    STAGE 2: ENGINE ANALYSIS (~15-20 tokens)
    - Fetch candles ONLY for selected candidates
    - Run full WizTheory engine detection
    - Grade: A+, A, B+, B, C
    
    STAGE 3: ALERT LOGIC
    - A+ → Alert immediately
    - A → Vision confirmation
    - B+ and below → Skip
    """
    cycle_start = datetime.now()
    reset_metrics_if_new_day()
    ops_start_cycle(ENVIRONMENT)
    
    logger.info(f"[{ENVIRONMENT}] " + "═" * 50)
    logger.info(f"[{ENVIRONMENT}] 🔍 TWO-STAGE SCANNER v6.0")
    
    # ══════════════════════════════════════════════════════════════
    # STAGE 1: LIGHT SCAN — Quick filter using token metrics
    # ══════════════════════════════════════════════════════════════
    logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
    logger.info(f"[{ENVIRONMENT}] STAGE 0: WHALE WATCHLIST")
    
    # Fetch whale tokens first (priority scanning)
    whale_tokens = fetch_whale_tokens()
    whale_alerts = 0
    
    if whale_tokens:
        logger.info(f"[{ENVIRONMENT}]    🐋 {len(whale_tokens)} whale tokens to scan")
        
        for wt in whale_tokens:
            symbol = wt.get('symbol', '???')
            token_address = wt.get('token_address', '')
            pair_address = wt.get('pair_address', '')
            whale_wallet = wt.get('whale_wallet', '')[:8] + '...'
            buy_sol = wt.get('buy_amount_sol', 0)
            
            logger.info(f"[{ENVIRONMENT}]    🐋 Scanning {symbol} (whale: {whale_wallet} bought {buy_sol} SOL)")
            
            # Mark as scanned
            mark_whale_scanned(token_address)
            
            # Fetch candles for this whale token
            try:
                candles = await fetch_candles(pair_address, symbol, token_address)
                
                if not candles or len(candles) < 20:
                    logger.info(f"[{ENVIRONMENT}]       ⏳ {symbol}: Not enough candles yet ({len(candles) if candles else 0})")
                    continue
                
                # Run PSEF (whale tokens still need environment check)
                psef_result = run_psef(candles)
                if not psef_result.get('passed', False):
                    logger.info(f"[{ENVIRONMENT}]       ❌ {symbol}: PSEF failed - {psef_result.get('failed_gate', 'unknown')}")
                    continue
                
                logger.info(f"[{ENVIRONMENT}]       ✅ {symbol}: PSEF passed")
                
                # Run Chart Intelligence layers with Prime Gate
                try:
                    chart_intel = analyze_chart_intelligence_with_prime(candles)
                    prime = chart_intel['prime']
                    breakout = chart_intel['breakout']
                    
                    if not prime['is_prime']:
                        logger.info(f"[{ENVIRONMENT}]       ⏭️ {symbol}: Not prime - {prime['reason']}")
                        continue
                    
                    struct = chart_intel['structure']
                    logger.info(f"[{ENVIRONMENT}]       🧠 {symbol}: PRIME ({prime['confidence']}) | {struct['quality']} | {breakout['breakout_type']}")
                except Exception as e:
                    logger.warning(f"[{ENVIRONMENT}]       ⚠️ {symbol}: Chart intel error: {e}")
                    chart_intel = None
                
                # Run engine detection
                engine_result = run_detection(wt, candles)
                if not engine_result:
                    logger.info(f"[{ENVIRONMENT}]       ⏳ {symbol}: No WizTheory setup detected yet")
                    continue
                
                logger.info(f"[{ENVIRONMENT}]       🎯 {symbol}: {engine_result.get('engine_name')} detected!")
                
                # Run BANGERS pipeline
                bangers_result = run_bangers_analysis(
                    candles=candles,
                    psef_result=psef_result,
                    engine_result=engine_result,
                    flashcard_similarity=engine_result.get('confidence', 0)
                )
                
                logger.info(f"[{ENVIRONMENT}]       📊 {symbol}: {bangers_result['summary']}")
                
                if bangers_result['should_alert']:
                    # WHALE + BANGER!
                    logger.info(f"[{ENVIRONMENT}]       🐋🎯 WHALE BANGER: {symbol} Grade {bangers_result['grade']} Score {bangers_result['score']}")
                    
                    # Add whale info to token for alert
                    wt['is_whale'] = True
                    wt['whale_wallet'] = whale_wallet
                    wt['buy_amount_sol'] = buy_sol
                    
                    # Get screenshot and send alert
                    chart_bytes, _ = await screenshot_chart(pair_address, symbol, browser_ctx, token_address)
                    if chart_bytes:
                        await send_forming_alert(wt, engine_result, chart_bytes, bangers_result['score'])
                        whale_alerts += 1
                        DAILY_METRICS['alerts_sent'] += 1
                    
                    # Expire after successful alert
                    expire_whale_token(token_address)
                
            except Exception as e:
                logger.error(f"[{ENVIRONMENT}]       ❌ {symbol}: Error - {e}")
                continue
        
        logger.info(f"[{ENVIRONMENT}]    🐋 Whale scan complete: {whale_alerts} alerts")
    else:
        logger.info(f"[{ENVIRONMENT}]    🐋 No whale tokens to scan")
    
    logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
    logger.info(f"[{ENVIRONMENT}] STAGE 1: LIGHT SCAN + WATCHLIST")
    
    # Fetch ALL tokens from extension queue (TRENDING + VOL_5M + VOL_1H)
    ext_tokens, ext_counts = await fetch_from_extension_queue()
    
    # Capture RAW symbol lists by source (for scan monitor)
    # Preserve exact order from extension queue (matches DexScreener UI)
    raw_top100_symbols = [t.get('symbol', '???') for t in ext_tokens if t.get('source') == 'TRENDING']
    raw_5m_vol_symbols = [t.get('symbol', '???') for t in ext_tokens if t.get('source') == 'VOL_5M']
    raw_1h_vol_symbols = [t.get('symbol', '???') for t in ext_tokens if t.get('source') == 'VOL_1H']
    
    logger.info(f"[{ENVIRONMENT}] 📊 Raw sources: TOP={len(raw_top100_symbols)} | 5M={len(raw_5m_vol_symbols)} | 1H={len(raw_1h_vol_symbols)}")
    
    # Dedupe by address (keep first occurrence)
    seen_addresses = set()
    tokens = []
    for t in ext_tokens:
        addr = t.get("address", "") or t.get("pair_address", "")
        if addr and addr not in seen_addresses:
            seen_addresses.add(addr)
            tokens.append(t)
    
    # ══════════════════════════════════════════════════════════════
    # STRICT TOKEN VALIDATION - Match DexScreener UI filters
    # Chain: Solana | DEX: PumpFun/PumpSwap | Liq: $10K | MC: $100K | Age: 1hr
    # ══════════════════════════════════════════════════════════════
    logger.info(f"[{ENVIRONMENT}] 🔍 Validating {len(tokens)} tokens against filters...")
    
    # Validate each source separately
    trending_tokens = [t for t in ext_tokens if t.get('source') == 'TRENDING']
    vol5m_tokens = [t for t in ext_tokens if t.get('source') == 'VOL_5M']
    vol1h_tokens = [t for t in ext_tokens if t.get('source') == 'VOL_1H']
    
    validated_trending = await validate_tokens_batch(trending_tokens, 'TRENDING')
    validated_5m = await validate_tokens_batch(vol5m_tokens, 'VOL_5M')
    validated_1h = await validate_tokens_batch(vol1h_tokens, 'VOL_1H')
    
    # Update raw symbol lists with validated tokens only
    raw_top100_symbols = [t.get('symbol', '???') for t in validated_trending]
    raw_5m_vol_symbols = [t.get('symbol', '???') for t in validated_5m]
    raw_1h_vol_symbols = [t.get('symbol', '???') for t in validated_1h]
    
    # Merge validated tokens
    all_validated = validated_trending + validated_5m + validated_1h
    seen_addresses = set()
    tokens = []
    for t in all_validated:
        addr = t.get("address", "") or t.get("pair_address", "")
        if addr and addr not in seen_addresses:
            seen_addresses.add(addr)
            tokens.append(t)
    
    logger.info(f"[{ENVIRONMENT}] ✅ Validation complete: {len(all_validated)} passed → {len(tokens)} unique")
    logger.info(f"[{ENVIRONMENT}]    TRENDING: {len(validated_trending)} | 5M: {len(validated_5m)} | 1H: {len(validated_1h)}")
    
    # Source counts from extension queue
    source_counts = {"TRENDING": ext_counts.get("TRENDING", 0), "VOL_5M": ext_counts.get("VOL_5M", 0), "VOL_1H": ext_counts.get("VOL_1H", 0)}
    logger.info(f"[{ENVIRONMENT}] Queue: {len(tokens)} unique tokens (TREND:{source_counts['TRENDING']} 5M:{source_counts['VOL_5M']} 1H:{source_counts['VOL_1H']})")
    
    # Visibility logging
    log_cycle_start()
    log_sources(
        trending=source_counts.get('TRENDING', 0),
        movers_5m=source_counts.get('VOL_5M', 0),
        movers_1h=source_counts.get('VOL_1H', 0)
    )
    
    # Get active watchlist tokens
    watchlist_entries = get_watchlist_tokens()
    watchlist_count = len(watchlist_entries)
    if watchlist_count > 0:
        logger.info(f"[{ENVIRONMENT}]    👁️ Active watchlist: {watchlist_count} tokens")
    
    # Enrich tokens with basic data (no candles)
    logger.info(f"[{ENVIRONMENT}]    Enriching {len(tokens)} tokens...")
    for token in tokens:
        if not token.get('market_cap') or not token.get('liquidity'):
            if token.get('pair_address'):
                data = await fetch_token_data_by_pair(token['pair_address'])
            elif token.get('address'):
                data = await fetch_token_data(token['address'])
            else:
                data = None
            if data:
                token.update(data)
            await asyncio.sleep(0.2)
    
    # ══════════════════════════════════════════════════════════════
    # STRUCTURAL PRESCAN - Analyze ALL tokens for setup shape
    # Replaces old volume/price-based light filter
    # ══════════════════════════════════════════════════════════════
    logger.info(f"[{ENVIRONMENT}] 🔬 STRUCTURAL PRESCAN: Analyzing {len(tokens)} tokens for setup shape...")
    
    # Define lightweight candle fetch for prescan (fewer candles, faster)
    async def fetch_prescan_candles(pair_address: str, limit: int = 50):
        """Fetch limited candles for prescan analysis."""
        try:
            from candle_provider import fetch_candles
            # Find the token in our list to get symbol
            token = next((t for t in tokens if t.get('pair_address') == pair_address), {})
            symbol = token.get('symbol', '???')
            token_address = token.get('address', token.get('contract_address', ''))
            candles = await fetch_candles(pair_address, symbol, token_address)
            if candles and len(candles) > limit:
                candles = candles[-limit:]  # Take most recent
            return candles
        except Exception as e:
            logger.debug(f"Prescan candle fetch failed for {pair_address}: {e}")
            return []
    
    # Run structural prescan on all validated tokens
    from structural_prescan import run_prescan_batch, ScanBucket
    
    prescan_results = await run_prescan_batch(tokens, fetch_prescan_candles)
    
    deep_scan_tokens = prescan_results.get('DEEP_SCAN_NOW', [])
    monitor_tokens = prescan_results.get('MONITOR', [])
    reject_tokens = prescan_results.get('REJECT', [])
    
    logger.info(f"[{ENVIRONMENT}]    📊 Prescan Results:")
    logger.info(f"[{ENVIRONMENT}]       🎯 DEEP_SCAN_NOW: {len(deep_scan_tokens)} tokens")
    logger.info(f"[{ENVIRONMENT}]       👁️  MONITOR: {len(monitor_tokens)} tokens")
    logger.info(f"[{ENVIRONMENT}]       ❌ REJECT: {len(reject_tokens)} tokens")
    
    # Log top DEEP_SCAN candidates
    for result in deep_scan_tokens[:5]:
        reasons_str = ', '.join(result.reasons[:3]) if result.reasons else 'N/A'
        logger.info(f"[{ENVIRONMENT}]       → {result.symbol}: Score {result.score:.0f} | {reasons_str}")
    
    # ══════════════════════════════════════════════════════════════
    # HYBRID INTAKE PIPELINE v2.1
    # Stage 2: Metadata Filter → Stage 3: Mini Structure Check
    # ══════════════════════════════════════════════════════════════
    
    async def hybrid_fetch_candles(pair_address: str, symbol: str, token_address: str):
        return await fetch_candles(pair_address, symbol, token_address)
    
    # Run hybrid intake (Stages 2-3)
    hybrid_results = await run_hybrid_intake(
        tokens=tokens,
        fetch_candles_func=hybrid_fetch_candles,
        metadata_top_n=60,   # Stage 2: top 60 get candles
        structure_top_n=40   # Stage 3: top 40 go to WizTheory
    )
    
    # Convert hybrid results to candidate format
    scored_tokens = []
    for result in hybrid_results:
        scored_tokens.append({
            'token': result.token,
            'light_score': result.total_score,
            'metadata_score': result.metadata_score,
            'structure_score': result.structure_score,
            'prescan_bucket': 'HYBRID',
            'prescan_reasons': result.reasons,
            'passes_50fz_gate': result.passes_50fz_gate,
            'passes_382fz_gate': result.passes_382fz_gate,
            'passes_618fz_gate': result.passes_618fz_gate,
            'passes_786fz_gate': result.passes_786fz_gate,
            'passes_underfib_gate': result.passes_underfib_gate,
            'ath_breakout': result.ath_breakout,
            'major_high_break': result.major_high_break,
            'retracement_pct': result.retracement_pct,
            'breakout_score': 0,
            'fib_proximity': 0
        })
    
    # Merge watchlist tokens
    watchlist_candidates = []
    watchlist_addresses = set()
    for entry in watchlist_entries:
        watchlist_addresses.add(entry['pair_address'])
        boosted_score = entry['last_score'] + 30
        watchlist_candidates.append({
            'token': entry['token_data'],
            'light_score': boosted_score,
            'from_watchlist': True,
            'watchlist_setup': entry['potential_setup'],
            'evaluations': entry['evaluations'],
            'prescan_bucket': 'WATCHLIST',
            'passes_50fz_gate': True,  # Watchlist tokens pass by default
            'ath_breakout': False,
            'major_high_break': False,
        })
    
    # Remove duplicates
    new_candidates = [s for s in scored_tokens if s['token'].get('pair_address') not in watchlist_addresses]
    
    # Combine and sort
    all_candidates = watchlist_candidates + new_candidates
    all_candidates.sort(key=lambda x: x['light_score'], reverse=True)
    
    # Take top 40 (already filtered by hybrid intake)
    max_deep_scan = 40
    candidates = all_candidates[:max_deep_scan]
    
    from_watchlist = sum(1 for c in candidates if c.get('from_watchlist', False))
    from_new = len(candidates) - from_watchlist
    
    logger.info(f"[{ENVIRONMENT}]    Hybrid intake complete:")
    logger.info(f"[{ENVIRONMENT}]    Selected for WizTheory: {len(candidates)} (New: {from_new}, Watchlist: {from_watchlist})")
    
    # Log top ranked
    logger.info(f"[{ENVIRONMENT}]    📊 TOP RANKED (Hybrid):")
    for rank, c in enumerate(candidates[:10], 1):
        sym = c['token'].get('symbol', '???')
        total = c['light_score']
        struct = c.get('structure_score', 0)
        gate = "✓" if c.get('passes_50fz_gate', True) else "✗"
        reasons = ', '.join(c.get('prescan_reasons', [])[:3])
        logger.info(f"[{ENVIRONMENT}]       #{rank}: {sym} (total:{total} struct:{struct}) [50FZ:{gate}] [{reasons}]")

        # PSEF: PRE-SETUP ENVIRONMENT FILTER
    # Only tokens passing all 4 gates proceed to deep scan
    # ══════════════════════════════════════════════════════════════
    psef_passed = []
    psef_stats = {'impulse': 0, 'structure': 0, 'pullback': 0, 'rsi': 0}
    
    if PSEF_ENABLED:
        logger.info(f"[{ENVIRONMENT}] PSEF: Filtering {len(candidates)} candidates...")
        for candidate in candidates:
            token = candidate['token']
            pair_address = token.get('pair_address', '')
            symbol = token.get('symbol', '???')
            
            # Fetch candles for PSEF analysis
            candles = None
            if pair_address:
                token_address = token.get('address', '') or token.get('token_address', '')
                candles = await fetch_candles(pair_address, symbol, token_address)
            
            if candles and len(candles) >= 20:
                psef_result = run_psef(candles)
                if psef_result.get('passed', False):
                    candidate['psef_reason'] = 'All gates passed'
                    candidate['psef_result'] = psef_result  # Store full result
                    candidate['psef_candles'] = candles      # Store candles for pipeline
                    
                    # Run Chart Intelligence layers with Prime Gate
                    try:
                        chart_intel = analyze_chart_intelligence_with_prime(candles)
                        candidate['chart_intel'] = chart_intel
                        prime = chart_intel['prime']
                        breakout_t = chart_intel['breakout']['breakout_type']
                        
                        if prime['is_prime']:
                            struct_q = chart_intel['structure']['quality']
                            logger.info(f"[{ENVIRONMENT}]    🧠 {symbol}: PRIME ({prime['confidence']}) | {struct_q} | {breakout_t}")
                        else:
                            logger.info(f"[{ENVIRONMENT}]    ⏭️ {symbol}: Not prime - {prime['reason']}")
                    except Exception as e:
                        logger.warning(f"[{ENVIRONMENT}]    ⚠️ {symbol}: Chart intel error: {e}")
                        candidate['chart_intel'] = None
                    
                    psef_passed.append(candidate)
                    logger.info(f"[{ENVIRONMENT}]    ✅ {symbol}: PSEF PASSED")
                else:
                    failed_gate = psef_result.get('failed_gate', 'unknown')
                    if 'impulse' in failed_gate.lower():
                        psef_stats['impulse'] += 1
                    elif 'structure' in failed_gate.lower():
                        psef_stats['structure'] += 1
                    elif 'pullback' in failed_gate.lower():
                        psef_stats['pullback'] += 1
                    elif 'rsi' in failed_gate.lower():
                        psef_stats['rsi'] += 1
                    logger.debug(f"[{ENVIRONMENT}]    ❌ {symbol}: Failed {failed_gate}")
            else:
                # No candle data - skip PSEF, allow through
                candidate['psef_reason'] = 'No candle data (skipped PSEF)'
                candidate['psef_result'] = {'passed': False, 'failed_gate': 'no_data'}
                candidate['psef_candles'] = None
                psef_passed.append(candidate)
        
        logger.info(f"[{ENVIRONMENT}]    PSEF Results: {len(psef_passed)}/{len(candidates)} passed")
        logger.info(f"[{ENVIRONMENT}]    Failed: Impulse={psef_stats['impulse']} Structure={psef_stats['structure']} Pullback={psef_stats['pullback']} RSI={psef_stats['rsi']}")
        
        # Use PSEF-filtered candidates for deep scan
        candidates = psef_passed
    
    # ══════════════════════════════════════════════════════════════
    # STAGE 2: ENGINE ANALYSIS — Fetch candles, run detection
    # ══════════════════════════════════════════════════════════════
    logger.info(f"[{ENVIRONMENT}] STAGE 2: ENGINE ANALYSIS ({len(candidates)} tokens)")
    
    alerts = 0
    engine_results = []
    
    for i, candidate in enumerate(candidates):
        if not ALERTS_ENABLED:
            break
        
        token = candidate['token']
        symbol = token.get('symbol', '???')
        pair_address = token.get('pair_address', '')
        
        logger.info(f"[{ENVIRONMENT}]    [{i+1}/{len(candidates)}] {symbol} (score: {candidate['light_score']})")
        
        add_to_watchlist(token, token.get('source', 'MOVERS'))
        
        try:
            # Pass PSEF data from candidate to process_token
            psef_result = candidate.get('psef_result', {'passed': False})
            psef_candles = candidate.get('psef_candles', None)
            if await process_token(token, browser_ctx, psef_result=psef_result, psef_candles=psef_candles):
                alerts += 1
        except Exception as e:
            log_error('other', f"Process token error: {e}")
        
        # Rate limit: 5 seconds between candle fetches
        await asyncio.sleep(5)
    
    # ══════════════════════════════════════════════════════════════
    # CYCLE COMPLETE
    # ══════════════════════════════════════════════════════════════
    cycle_time = (datetime.now() - cycle_start).total_seconds()
    
    logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
    logger.info(f"[{ENVIRONMENT}] CYCLE COMPLETE")
    logger.info(f"[{ENVIRONMENT}]    Time: {cycle_time:.0f}s")
    logger.info(f"[{ENVIRONMENT}]    Scanned: {len(tokens)} → {len(candidates)} candidates")
    logger.info(f"[{ENVIRONMENT}]    Alerts: {alerts}")
    logger.info(f"[{ENVIRONMENT}] ══════════════════════════════════════════════════")
    
    log_cycle_complete(cycle_time, len(tokens), alerts, source_counts)
    ops_end_cycle(cycle_time, sum(source_counts.values()), len(tokens), len(candidates), 0)
    log_current_metrics()
    
    # ══════════════════════════════════════════════════════════════
    # TELEGRAM SCAN MONITOR — Visibility layer (private work chat)
    # ══════════════════════════════════════════════════════════════
    try:
        # Use RAW symbol lists captured BEFORE merge (exact scan order)
        source_breakdown = {
            'TOP_100': raw_top100_symbols,
            '5M_VOL': raw_5m_vol_symbols,
            '1H_VOL': raw_1h_vol_symbols
        }
        
        # Get all scanned token symbols
        scanned_symbols = [t.get('symbol', '???') for t in tokens]
        
        # Get candidate info
        candidate_list = []
        for c in candidates:
            sym = c.get('token', {}).get('symbol', c.get('symbol', '???'))
            reason = c.get('watchlist_setup', 'potential')[:20] if c.get('from_watchlist') else 'structure'
            candidate_list.append({'symbol': sym, 'reason': reason})
        
        # Filter stats - use consistent count
        total_scanned = len(tokens)
        filter_stats = {
            'total': total_scanned,
            'passed_filters': len(scored_tokens) if 'scored_tokens' in dir() else len(candidates),
            'candidates': len(candidates),
            'alerts': alerts
        }
        
        # Alert list
        alert_list = []
        
        send_scan_monitor_simple(
            rotation="COMBINED",
            scanned_tokens=scanned_symbols,
            candidates=candidate_list,
            alerts=alert_list,
            filter_stats=filter_stats,
            source_breakdown=source_breakdown
        )
    except Exception as e:
        logger.warning(f"[{ENVIRONMENT}] Scan monitor error: {e}")
    
    await send_heartbeat(cycle_time)


async def scan_watchlist(browser_ctx):
    watchlist = get_watchlist()
    if not watchlist: return
    logger.info(f"[{ENVIRONMENT}] 👀 Checking {len(watchlist)} watchlist tokens")
    for token in watchlist:
        if not ALERTS_ENABLED: break
        data = await fetch_token_data(token['address'])
        if not data: continue
        token.update(data)
        should_v, _, _ = should_use_vision(token)
        if should_v and can_use_vision():
            try: await process_token(token, browser_ctx)
            except: pass
            await asyncio.sleep(2)

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

async def check_telegram_commands():
    global SCANNER_PAUSED, LAST_TELEGRAM_UPDATE_ID
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try: await bot.delete_webhook(drop_pending_updates=True)
    except: pass
    await asyncio.sleep(3)
    
    # Command polling disabled - bot.py handles /pause /resume now
    # Scanner just checks the pause file
    pass

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    global SCANNER_START_TIME
    SCANNER_START_TIME = datetime.now()
    
    logger.info(f"[{ENVIRONMENT}] " + "═" * 60)
    logger.info(f"[{ENVIRONMENT}] 🤖 JAYCE SCANNER v4.2 — STABILITY + BASELINE")
    logger.info(f"[{ENVIRONMENT}]    Environment: {ENVIRONMENT}")
    logger.info(f"[{ENVIRONMENT}]    Engines: .382 | .50 | .618 | .786 | Under-Fib")
    logger.info(f"[{ENVIRONMENT}]    Heartbeat: Every {HEARTBEAT_INTERVAL_MINUTES} min")
    logger.info(f"[{ENVIRONMENT}]    Weights: Engine={ENGINE_WEIGHT} Vision={VISION_WEIGHT} Pattern={PATTERN_WEIGHT}")
    logger.info(f"[{ENVIRONMENT}] " + "═" * 60)
    
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY]):
        logger.error(f"[{ENVIRONMENT}] ❌ Missing env vars!")
        return
    
    init_database()
    reset_metrics_if_new_day()
    
    # v4.1: Load training data at startup
    await load_training_from_github()
    logger.info(f"[{ENVIRONMENT}] 📚 Jayce is now studying {len(TRAINING_DATA)} flashcard examples!")
    
    # v4.2: Send startup heartbeat
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=HEARTBEAT_CHAT_ID, 
            text=f"🚀 <b>[{ENVIRONMENT}] Scanner Started</b>\nv4.2 Stability + Baseline Mode\nHeartbeat every {HEARTBEAT_INTERVAL_MINUTES} min", 
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"[{ENVIRONMENT}] ❌ Startup message failed: {e}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        
        asyncio.create_task(check_telegram_commands())
        
        scan_count = 0
        while True:
            try:
                if is_scanner_paused():
                    await asyncio.sleep(10)
                    continue
                
                scan_count += 1
                await scan_top_movers(context)
                
                if scan_count % 3 == 0:
                    await scan_watchlist(context)
                
                if scan_count % 12 == 0:
                    cleanup_old_watchlist()
                    cleanup_expired_cooldowns()
                    cleanup_engine_cooldowns()
                
                await asyncio.sleep(TOP_MOVERS_INTERVAL * 60)
            except Exception as e:
                logger.error(f"❌ Main error: {e}")
                await asyncio.sleep(30)

if __name__ == '__main__':
    asyncio.run(main())
