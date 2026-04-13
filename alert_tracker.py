"""
ALERT TRACKER - Log and track which alerts you trade
"""
import sqlite3
from datetime import datetime

DB_PATH = '/opt/jayce/alert_tracker.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        symbol TEXT,
        setup TEXT,
        score INTEGER,
        grade TEXT,
        pair_address TEXT,
        traded INTEGER DEFAULT 0,
        result TEXT,
        notes TEXT
    )''')
    conn.commit()
    conn.close()

def log_alert(symbol, setup, score, grade, pair_address):
    """Log a new alert"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO alerts (timestamp, symbol, setup, score, grade, pair_address)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (datetime.now().isoformat(), symbol, setup, score, grade, pair_address))
    conn.commit()
    conn.close()

def mark_traded(alert_id, result='', notes=''):
    """Mark an alert as traded"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE alerts SET traded=1, result=?, notes=? WHERE id=?',
              (result, notes, alert_id))
    conn.commit()
    conn.close()

def get_stats():
    """Get trading stats"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM alerts')
    total = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM alerts WHERE traded=1')
    traded = c.fetchone()[0]
    
    c.execute('SELECT setup, COUNT(*) FROM alerts GROUP BY setup')
    by_setup = c.fetchall()
    
    c.execute('SELECT symbol, setup, score, timestamp FROM alerts ORDER BY id DESC LIMIT 10')
    recent = c.fetchall()
    
    conn.close()
    return {'total': total, 'traded': traded, 'by_setup': by_setup, 'recent': recent}

if __name__ == '__main__':
    stats = get_stats()
    print(f"\n📊 ALERT TRACKER STATS")
    print(f"Total alerts: {stats['total']}")
    print(f"Traded: {stats['traded']}")
    print(f"\nBy setup:")
    for setup, count in stats['by_setup']:
        print(f"  {setup}: {count}")
    print(f"\nRecent alerts:")
    for symbol, setup, score, ts in stats['recent']:
        print(f"  {symbol}: {setup} (Score: {score})")
