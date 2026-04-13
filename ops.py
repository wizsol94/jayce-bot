#!/usr/bin/env python3
"""
OPS Truth Layer Dashboard - Read-only monitoring
Run in Terminal B: python3 /opt/jayce/ops.py
"""

import sqlite3
import time
import os
from datetime import datetime, timedelta

DB_PATH = '/opt/jayce/data/jayce.db'

def clear_screen():
    os.system('clear')

def get_db():
    return sqlite3.connect(DB_PATH)

def get_recent_cycles(limit=10):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT cycle_id, started_at, ended_at, cycle_duration_seconds, 
               tokens_scanned_count, unique_tokens_after_dedupe_count, errors_count
        FROM cycles ORDER BY started_at DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_cycle_tokens(cycle_id, limit=50):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT source_type, source_rank, dex, symbol, contract_address, skipped, skip_reason
        FROM cycle_tokens WHERE cycle_id = ? ORDER BY source_rank LIMIT ?
    ''', (cycle_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_recent_scoring(limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, symbol, engine_grade, engine_score, vision_score, 
               pattern_score, combined_score, final_stage, retrace_pct, impulse_pct, rsi_value, vision_ran
        FROM scoring_events ORDER BY timestamp DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_flashcard_matches(symbol=None, limit=20):
    conn = get_db()
    c = conn.cursor()
    if symbol:
        c.execute('''
            SELECT timestamp, symbol, flashcard_id, setup_type, similarity_score, notes
            FROM flashcard_matches WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?
        ''', (symbol, limit))
    else:
        c.execute('''
            SELECT timestamp, symbol, flashcard_id, setup_type, similarity_score, notes
            FROM flashcard_matches ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_recent_alerts(limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, symbol, stage, combined_score, channel
        FROM alerts_sent_ops ORDER BY timestamp DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_error_summary():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT component, COUNT(*) as cnt FROM errors 
        WHERE timestamp > datetime('now', '-24 hours')
        GROUP BY component
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def print_dashboard():
    clear_screen()
    print("=" * 70)
    print("🔍 JAYCE OPS TRUTH LAYER DASHBOARD")
    print(f"   Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # A) Recent Cycles
    print("\n📊 RECENT CYCLES:")
    print("-" * 70)
    cycles = get_recent_cycles(5)
    if cycles:
        for c in cycles:
            cid = c[0][:8] if c[0] else '???'
            duration = f"{c[3]:.1f}s" if c[3] else '?'
            scanned = c[4] or 0
            unique = c[5] or 0
            errors = c[6] or 0
            print(f"  🌀 {cid} | ⏱ {duration:>7} | 🔎 {scanned:>3} scanned | 🧩 {unique:>3} unique | ⚠️ {errors} errors")
    else:
        print("  No cycles recorded yet")
    
    # B) Recent Scoring Events
    print("\n🧠 RECENT SCORING (last 10):")
    print("-" * 70)
    scores = get_recent_scoring(10)
    if scores:
        for s in scores:
            ts = s[0][-8:] if s[0] else '???'
            sym = (s[1] or '???')[:10].ljust(10)
            grade = (s[2] or '?').ljust(3)
            eng = s[3] or 0
            vis = s[4] or 0
            pat = s[5] or 0
            comb = s[6] or 0
            stage = (s[7] or 'NONE')[:8].ljust(8)
            vis_ran = "👁️" if s[11] else "⏭️"
            ret = s[8] or 0
            imp = s[9] or 0
            rsi = s[10] or 0
            print(f"  {ts} | {sym} | {grade} | E:{eng:>3.0f} {vis_ran}V:{vis:>3.0f} P:{pat:>3.0f} → {comb:>3.0f} | {stage} | ret:{ret:.0f}% imp:{imp:.0f}% rsi:{rsi:.0f}")
    else:
        print("  No scoring events yet")
    
    # C) Flashcard Matches
    print("\n🃏 RECENT FLASHCARD MATCHES:")
    print("-" * 70)
    matches = get_flashcard_matches(limit=10)
    if matches:
        current_sym = None
        for m in matches:
            sym = m[1] or '???'
            fc_id = (m[2] or '???')[:20]
            setup = (m[3] or '???')[:15]
            sim = m[4] or 0
            if sym != current_sym:
                print(f"  📍 {sym}:")
                current_sym = sym
            print(f"      → {fc_id} ({setup}) sim:{sim:.0f}%")
    else:
        print("  No flashcard matches yet")
    
    # D) Recent Alerts
    print("\n🚨 RECENT ALERTS:")
    print("-" * 70)
    alerts = get_recent_alerts(10)
    if alerts:
        for a in alerts:
            ts = a[0][-8:] if a[0] else '???'
            sym = (a[1] or '???')[:12].ljust(12)
            stage = a[2] or '???'
            score = a[3] or 0
            emoji = "🚨" if stage == 'CONFIRMED' else "🌱"
            print(f"  {emoji} {ts} | {sym} | {stage:>10} | score:{score:.0f}")
    else:
        print("  No alerts sent yet")
    
    # E) Error Summary (24h)
    print("\n⚠️ ERROR SUMMARY (24h):")
    print("-" * 70)
    errors = get_error_summary()
    if errors:
        for e in errors:
            print(f"  {e[0]}: {e[1]} errors")
    else:
        print("  ✅ No errors in last 24h")
    
    print("\n" + "=" * 70)
    print("Press Ctrl+C to exit | Refreshes every 10s")
    print("=" * 70)

def main():
    print("Starting OPS Dashboard...")
    while True:
        try:
            print_dashboard()
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n👋 OPS Dashboard stopped")
            break
        except Exception as e:
            print(f"Dashboard error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
