import sqlite3
from pathlib import Path

DB_PATH = '/opt/jayce/data/jayce.db'

def create_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. cycles
    c.execute('''
        CREATE TABLE IF NOT EXISTS cycles (
            cycle_id TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at TEXT,
            environment TEXT,
            cycle_duration_seconds REAL,
            raw_tokens_fetched_count INTEGER,
            unique_tokens_after_dedupe_count INTEGER,
            tokens_scanned_count INTEGER,
            errors_count INTEGER,
            notes TEXT
        )
    ''')
    
    # 2. cycle_tokens
    c.execute('''
        CREATE TABLE IF NOT EXISTS cycle_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT,
            timestamp TEXT,
            source_type TEXT,
            source_rank INTEGER,
            dex TEXT,
            symbol TEXT,
            name TEXT,
            chain TEXT,
            pair_address TEXT,
            contract_address TEXT,
            url TEXT,
            skipped INTEGER,
            skip_reason TEXT
        )
    ''')
    
    # 3. scoring_events
    c.execute('''
        CREATE TABLE IF NOT EXISTS scoring_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT,
            timestamp TEXT,
            symbol TEXT,
            contract_address TEXT,
            timeframe_used TEXT,
            engine_grade TEXT,
            retrace_pct REAL,
            impulse_pct REAL,
            rsi_value REAL,
            engine_score REAL,
            vision_score REAL,
            pattern_score REAL,
            combined_score REAL,
            vision_ran INTEGER,
            pattern_ran INTEGER,
            final_stage TEXT,
            debug_flags TEXT
        )
    ''')
    
    # 4. flashcard_matches
    c.execute('''
        CREATE TABLE IF NOT EXISTS flashcard_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT,
            timestamp TEXT,
            symbol TEXT,
            contract_address TEXT,
            flashcard_id TEXT,
            setup_type TEXT,
            similarity_score REAL,
            notes TEXT
        )
    ''')
    
    # 5. alerts_sent
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts_sent_ops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            contract_address TEXT,
            stage TEXT,
            combined_score REAL,
            channel TEXT,
            telegram_message_id TEXT,
            cooldown_applied INTEGER
        )
    ''')
    
    # 6. errors
    c.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            cycle_id TEXT,
            component TEXT,
            error_type TEXT,
            error_message TEXT,
            retry_count INTEGER,
            resolved INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ OPS Database tables created!")

if __name__ == '__main__':
    create_tables()
