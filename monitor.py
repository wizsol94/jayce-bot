#!/usr/bin/env python3
"""
JAYCE LIVE MONITOR v1.0
========================
Shows all tokens being scanned in real-time with MC and address.
Run in a separate terminal.
"""

import sqlite3
import time
import os
from datetime import datetime

DB_PATH = "/opt/jayce/data/queue.db"

def format_mc(mc):
    if mc >= 1_000_000:
        return f"${mc/1_000_000:.2f}M"
    elif mc >= 1_000:
        return f"${mc/1_000:.1f}K"
    else:
        return f"${mc:.0f}"

def clear_screen():
    os.system('clear')

def get_recent_tokens():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get tokens from queue grouped by source
        c.execute("""
            SELECT symbol, token_address, source, timestamp 
            FROM token_queue 
            ORDER BY timestamp DESC 
            LIMIT 200
        """)
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def get_whale_tokens():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT symbol, token_address, whale_wallet, buy_amount_sol, timestamp
            FROM whale_watchlist
            WHERE expired = 0
            ORDER BY timestamp DESC
            LIMIT 20
        """)
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def monitor_loop():
    while True:
        clear_screen()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print("=" * 80)
        print(f"  🎯 JAYCE LIVE MONITOR | {now}")
        print("=" * 80)
        
        tokens = get_recent_tokens()
        
        # Group by source
        trending = [t for t in tokens if t[2] == 'TRENDING'][:30]
        vol_5m = [t for t in tokens if t[2] == 'VOL_5M'][:20]
        vol_1h = [t for t in tokens if t[2] == 'VOL_1H'][:20]
        
        # TRENDING
        print(f"\n  📈 TRENDING ({len(trending)} tokens)")
        print("  " + "-" * 76)
        print(f"  {'Symbol':<15} {'Address':<45} {'Source':<10}")
        print("  " + "-" * 76)
        for t in trending[:15]:
            symbol = t[0][:14] if t[0] else "???"
            addr = t[1][:44] if t[1] else "???"
            print(f"  {symbol:<15} {addr:<45} {t[2]:<10}")
        if len(trending) > 15:
            print(f"  ... and {len(trending) - 15} more")
        
        # 5M VOLUME
        print(f"\n  ⚡ 5M VOLUME ({len(vol_5m)} tokens)")
        print("  " + "-" * 76)
        for t in vol_5m[:10]:
            symbol = t[0][:14] if t[0] else "???"
            addr = t[1][:44] if t[1] else "???"
            print(f"  {symbol:<15} {addr:<45} {t[2]:<10}")
        if len(vol_5m) > 10:
            print(f"  ... and {len(vol_5m) - 10} more")
        
        # 1H VOLUME
        print(f"\n  🕐 1H VOLUME ({len(vol_1h)} tokens)")
        print("  " + "-" * 76)
        for t in vol_1h[:10]:
            symbol = t[0][:14] if t[0] else "???"
            addr = t[1][:44] if t[1] else "???"
            print(f"  {symbol:<15} {addr:<45} {t[2]:<10}")
        if len(vol_1h) > 10:
            print(f"  ... and {len(vol_1h) - 10} more")
        
        # WHALE WATCHLIST
        whales = get_whale_tokens()
        if whales:
            print(f"\n  🐋 WHALE WATCHLIST ({len(whales)} tokens)")
            print("  " + "-" * 76)
            print(f"  {'Symbol':<15} {'Wallet':<20} {'SOL':<10} {'Time':<20}")
            print("  " + "-" * 76)
            for w in whales[:5]:
                symbol = w[0][:14] if w[0] else "???"
                wallet = (w[2][:8] + "...") if w[2] else "???"
                sol = f"{w[3]:.1f}" if w[3] else "0"
                ts = w[4][-19:] if w[4] else "???"
                print(f"  {symbol:<15} {wallet:<20} {sol:<10} {ts:<20}")
        
        print("\n" + "=" * 80)
        print("  Refreshing every 30 seconds... Press Ctrl+C to exit")
        print("=" * 80)
        
        time.sleep(30)

if __name__ == '__main__':
    try:
        monitor_loop()
    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped.")
