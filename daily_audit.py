"""
JAYCE DAILY AUDIT SYSTEM v1.0
=============================
Lightweight tracking for internal calibration.
Does NOT modify any detection, scoring, or alert logic.

Files:
- /opt/jayce/data/daily_audit.json - Daily stats
- /opt/jayce/data/alert_log.json - Individual alert records
- /opt/jayce/data/missed_setups.json - Manual missed setup log
"""

import json
import os
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DATA_DIR = '/opt/jayce/data'
DAILY_AUDIT_FILE = f'{DATA_DIR}/daily_audit.json'
ALERT_LOG_FILE = f'{DATA_DIR}/alert_log.json'
MISSED_SETUPS_FILE = f'{DATA_DIR}/missed_setups.json'

# In-memory counters for current session
_session_stats = {
    'tokens_scanned': 0,
    'candidates': 0,
    'alerts': 0,
    'vision_calls': 0,
    'similarity_scores': [],
    'grades': []
}


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(filepath: str) -> dict:
    """Load JSON file or return empty dict."""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load {filepath}: {e}")
    return {}


def _save_json(filepath: str, data: dict):
    """Save dict to JSON file."""
    _ensure_data_dir()
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not save {filepath}: {e}")


def _get_today() -> str:
    """Get today's date string."""
    return datetime.now().strftime('%Y-%m-%d')


# ═══════════════════════════════════════════════════════════════════
# TRACKING FUNCTIONS (call from scanner.py)
# ═══════════════════════════════════════════════════════════════════

def track_tokens_scanned(count: int):
    """Track number of tokens scanned in a cycle."""
    _session_stats['tokens_scanned'] += count


def track_candidates(count: int):
    """Track number of candidates that passed to engine analysis."""
    _session_stats['candidates'] += count


def track_vision_call(similarity: float = None):
    """Track a Vision API call and optionally the similarity score."""
    _session_stats['vision_calls'] += 1
    if similarity is not None and similarity > 0:
        _session_stats['similarity_scores'].append(similarity)


def track_alert(token: str, setup_type: str, grade: str, score: int, 
                similarity: float = None, vision_used: bool = False):
    """
    Track an alert being sent.
    Also logs to alert_log.json for detailed review.
    """
    _session_stats['alerts'] += 1
    _session_stats['grades'].append(grade)
    
    # Log individual alert
    alert_record = {
        'timestamp': datetime.now().isoformat(),
        'date': _get_today(),
        'token': token,
        'setup_type': setup_type,
        'grade': grade,
        'score': score,
        'similarity': similarity,
        'vision_used': vision_used
    }
    
    # Append to alert log
    alert_log = _load_json(ALERT_LOG_FILE)
    if 'alerts' not in alert_log:
        alert_log['alerts'] = []
    alert_log['alerts'].append(alert_record)
    
    # Keep only last 500 alerts
    if len(alert_log['alerts']) > 500:
        alert_log['alerts'] = alert_log['alerts'][-500:]
    
    _save_json(ALERT_LOG_FILE, alert_log)


def save_daily_stats():
    """
    Save current session stats to daily audit file.
    Call this at end of each cycle or periodically.
    """
    today = _get_today()
    audit = _load_json(DAILY_AUDIT_FILE)
    
    # Get or create today's entry
    if today not in audit:
        audit[today] = {
            'alerts': 0,
            'candidates': 0,
            'tokens_scanned': 0,
            'vision_calls': 0,
            'similarity_scores': [],
            'grades': []
        }
    
    # Accumulate stats
    audit[today]['alerts'] += _session_stats['alerts']
    audit[today]['candidates'] += _session_stats['candidates']
    audit[today]['tokens_scanned'] += _session_stats['tokens_scanned']
    audit[today]['vision_calls'] += _session_stats['vision_calls']
    audit[today]['similarity_scores'].extend(_session_stats['similarity_scores'])
    audit[today]['grades'].extend(_session_stats['grades'])
    
    # Calculate averages for storage
    if audit[today]['similarity_scores']:
        audit[today]['avg_similarity'] = round(
            sum(audit[today]['similarity_scores']) / len(audit[today]['similarity_scores']), 1
        )
    
    _save_json(DAILY_AUDIT_FILE, audit)
    
    # Reset session stats
    _session_stats['tokens_scanned'] = 0
    _session_stats['candidates'] = 0
    _session_stats['alerts'] = 0
    _session_stats['vision_calls'] = 0
    _session_stats['similarity_scores'] = []
    _session_stats['grades'] = []


# ═══════════════════════════════════════════════════════════════════
# MISSED SETUP LOGGING
# ═══════════════════════════════════════════════════════════════════

def log_missed_setup(token: str, setup_type: str, note: str = ""):
    """
    Log a missed setup for review.
    Can be called manually or via CLI.
    """
    missed = _load_json(MISSED_SETUPS_FILE)
    if 'missed' not in missed:
        missed['missed'] = []
    
    missed['missed'].append({
        'timestamp': datetime.now().isoformat(),
        'date': _get_today(),
        'token': token,
        'setup': setup_type,
        'note': note
    })
    
    # Keep only last 200 entries
    if len(missed['missed']) > 200:
        missed['missed'] = missed['missed'][-200:]
    
    _save_json(MISSED_SETUPS_FILE, missed)
    return True


# ═══════════════════════════════════════════════════════════════════
# DAILY SUMMARY GENERATION
# ═══════════════════════════════════════════════════════════════════

def generate_daily_summary(date: str = None) -> str:
    """
    Generate a clean daily summary.
    If date is None, uses today.
    """
    if date is None:
        date = _get_today()
    
    audit = _load_json(DAILY_AUDIT_FILE)
    missed = _load_json(MISSED_SETUPS_FILE)
    
    if date not in audit:
        return f"📊 No audit data for {date}"
    
    day = audit[date]
    
    # Count grades
    grade_counts = {}
    for g in day.get('grades', []):
        grade_counts[g] = grade_counts.get(g, 0) + 1
    
    # Count missed setups for this date
    missed_today = [m for m in missed.get('missed', []) if m.get('date') == date]
    
    # Build summary
    avg_sim = day.get('avg_similarity', 0)
    
    summary = f"""
📊 JAYCE DAILY AUDIT
════════════════════════════════════
Date: {date}

- Tokens scanned: {day.get('tokens_scanned', 0):,}
- Candidates: {day.get('candidates', 0):,}
- Alerts: {day.get('alerts', 0)}
- Vision calls: {day.get('vision_calls', 0)}
- Avg similarity: {avg_sim:.1f}%
"""
    
    if grade_counts:
        summary += "\nAlerts Breakdown:\n"
        for grade in ['A+', 'A', 'B+', 'B', 'C+', 'C', 'D']:
            if grade in grade_counts:
                summary += f"  - {grade}: {grade_counts[grade]}\n"
    
    summary += f"\nMissed Setups Logged: {len(missed_today)}"
    
    if missed_today:
        summary += "\n"
        for m in missed_today[-5:]:  # Show last 5
            summary += f"  - {m['token']} ({m['setup']}): {m.get('note', '')}\n"
    
    summary += "\n════════════════════════════════════"
    
    return summary


def get_week_summary() -> str:
    """Generate summary for the past 7 days."""
    audit = _load_json(DAILY_AUDIT_FILE)
    
    total_alerts = 0
    total_scanned = 0
    total_vision = 0
    all_grades = []
    
    from datetime import timedelta
    today = datetime.now()
    
    summary = "📊 JAYCE WEEKLY SUMMARY\n"
    summary += "════════════════════════════════════\n\n"
    
    for i in range(7):
        date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        if date in audit:
            day = audit[date]
            total_alerts += day.get('alerts', 0)
            total_scanned += day.get('tokens_scanned', 0)
            total_vision += day.get('vision_calls', 0)
            all_grades.extend(day.get('grades', []))
            
            summary += f"{date}: {day.get('alerts', 0)} alerts, {day.get('tokens_scanned', 0):,} scanned\n"
    
    summary += f"\n7-Day Totals:\n"
    summary += f"  - Alerts: {total_alerts}\n"
    summary += f"  - Tokens Scanned: {total_scanned:,}\n"
    summary += f"  - Vision Calls: {total_vision}\n"
    
    return summary


# ═══════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 daily_audit.py summary [date]  - Show daily summary")
        print("  python3 daily_audit.py week            - Show week summary")
        print("  python3 daily_audit.py missed TOKEN SETUP [NOTE]  - Log missed setup")
        sys.exit(0)
    
    cmd = sys.argv[1].lower()
    
    if cmd == 'summary':
        date = sys.argv[2] if len(sys.argv) > 2 else None
        print(generate_daily_summary(date))
    
    elif cmd == 'week':
        print(get_week_summary())
    
    elif cmd == 'missed':
        if len(sys.argv) < 4:
            print("Usage: python3 daily_audit.py missed TOKEN SETUP [NOTE]")
            sys.exit(1)
        token = sys.argv[2]
        setup = sys.argv[3]
        note = ' '.join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        log_missed_setup(token, setup, note)
        print(f"✅ Logged missed setup: {token} ({setup})")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
