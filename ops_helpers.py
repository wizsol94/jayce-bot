"""OPS Truth Layer - Helper functions for instrumentation"""
import sqlite3
import uuid
from datetime import datetime

OPS_DB_PATH = '/opt/jayce/data/jayce.db'
CURRENT_CYCLE_ID = None

def ops_safe(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[OPS] DB error (non-fatal): {e}")
            return None
    return wrapper

@ops_safe
def ops_start_cycle(environment):
    global CURRENT_CYCLE_ID
    CURRENT_CYCLE_ID = str(uuid.uuid4())
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO cycles (cycle_id, started_at, environment) VALUES (?, ?, ?)',
              (CURRENT_CYCLE_ID, datetime.now().isoformat(), environment))
    conn.commit()
    conn.close()
    return CURRENT_CYCLE_ID

@ops_safe  
def ops_end_cycle(duration, raw_count, unique_count, scanned_count, error_count):
    global CURRENT_CYCLE_ID
    if not CURRENT_CYCLE_ID: return
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE cycles SET ended_at=?, cycle_duration_seconds=?, raw_tokens_fetched_count=?, unique_tokens_after_dedupe_count=?, tokens_scanned_count=?, errors_count=? WHERE cycle_id=?',
              (datetime.now().isoformat(), duration, raw_count, unique_count, scanned_count, error_count, CURRENT_CYCLE_ID))
    conn.commit()
    conn.close()

@ops_safe
def ops_log_token(source_type, source_rank, dex, symbol, pair_addr, contract_addr, skipped=0, skip_reason=''):
    global CURRENT_CYCLE_ID
    if not CURRENT_CYCLE_ID: return
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO cycle_tokens (cycle_id, timestamp, source_type, source_rank, dex, symbol, pair_address, contract_address, skipped, skip_reason, chain) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
              (CURRENT_CYCLE_ID, datetime.now().isoformat(), source_type, source_rank, dex, symbol, pair_addr, contract_addr, skipped, skip_reason, 'solana'))
    conn.commit()
    conn.close()

@ops_safe
def ops_log_scoring(symbol, contract_addr, engine_grade, retrace, impulse, rsi, eng_score, vis_score, pat_score, combined, vision_ran, stage, debug=''):
    global CURRENT_CYCLE_ID
    if not CURRENT_CYCLE_ID: return
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO scoring_events (cycle_id, timestamp, symbol, contract_address, engine_grade, retrace_pct, impulse_pct, rsi_value, engine_score, vision_score, pattern_score, combined_score, vision_ran, pattern_ran, final_stage, debug_flags, timeframe_used) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (CURRENT_CYCLE_ID, datetime.now().isoformat(), symbol, contract_addr, engine_grade, retrace, impulse, rsi, eng_score, vis_score, pat_score, combined, 1 if vision_ran else 0, 1, stage, debug, '5m'))
    conn.commit()
    conn.close()

@ops_safe
def ops_log_flashcard(symbol, contract_addr, fc_id, setup_type, sim_score, notes=''):
    global CURRENT_CYCLE_ID
    if not CURRENT_CYCLE_ID: return
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO flashcard_matches (cycle_id, timestamp, symbol, contract_address, flashcard_id, setup_type, similarity_score, notes) VALUES (?,?,?,?,?,?,?,?)',
              (CURRENT_CYCLE_ID, datetime.now().isoformat(), symbol, contract_addr, fc_id, setup_type, sim_score, notes))
    conn.commit()
    conn.close()

@ops_safe
def ops_log_alert(symbol, contract_addr, stage, combined, channel):
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO alerts_sent_ops (timestamp, symbol, contract_address, stage, combined_score, channel, cooldown_applied) VALUES (?,?,?,?,?,?,?)',
              (datetime.now().isoformat(), symbol, contract_addr, stage, combined, channel, 0))
    conn.commit()
    conn.close()

@ops_safe
def ops_log_error(component, error_type, error_msg):
    global CURRENT_CYCLE_ID
    conn = sqlite3.connect(OPS_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO errors (timestamp, cycle_id, component, error_type, error_message, retry_count, resolved) VALUES (?,?,?,?,?,?,?)',
              (datetime.now().isoformat(), CURRENT_CYCLE_ID, component, error_type, str(error_msg)[:500], 0, 0))
    conn.commit()
    conn.close()
