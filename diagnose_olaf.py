#!/usr/bin/env python3
"""
OLAF DIAGNOSTIC SCRIPT
======================
Traces a specific token through the entire Jayce pipeline to identify
exactly where and why it was rejected or missed.
"""

import os
import sys
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, '/opt/jayce')

OLAF_SYMBOL = "OLAF"
OLAF_PAIR_ADDRESS = "13or77a7ngnh4edbeeczrg4inpuqgxdokcpsvbzakdxp"

print("=" * 70)
print("OLAF DIAGNOSTIC TRACE")
print("=" * 70)

# STEP 1: Check token queue
print("\n[STEP 1] Checking token queue database...")
QUEUE_DB = '/opt/jayce/data/queue.db'
try:
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    c.execute("""
        SELECT symbol, pair_address, source, rank, processed, created_at 
        FROM token_queue 
        WHERE LOWER(symbol) LIKE '%olaf%' OR LOWER(pair_address) LIKE '%13or77%'
        ORDER BY created_at DESC LIMIT 10
    """)
    rows = c.fetchall()
    if rows:
        print(f"   ✅ FOUND in token_queue: {len(rows)} entries")
        for r in rows:
            print(f"      {r[0]} | {r[2]} | Rank: {r[3]} | Processed: {r[4]} | {r[5]}")
    else:
        print("   ❌ NOT FOUND in token_queue")
        print("   → OLAF was never added to scan queue (coverage issue)")
    conn.close()
except Exception as e:
    print(f"   ⚠️ Queue DB error: {e}")

# STEP 2: Check logs
print("\n[STEP 2] Searching scanner logs...")
try:
    import subprocess
    result = subprocess.run(
        ['journalctl', '-u', 'jayce-scanner', '--since', '2 days ago', '--no-pager'],
        capture_output=True, text=True, timeout=30
    )
    journal_lines = [l for l in result.stdout.split('\n') if 'olaf' in l.lower()]
    if journal_lines:
        print(f"   ✅ Found {len(journal_lines)} OLAF mentions")
        for line in journal_lines[-20:]:
            print(f"   {line.strip()[:120]}")
    else:
        print("   ❌ No OLAF mentions in journalctl")
except Exception as e:
    print(f"   ⚠️ journalctl error: {e}")

# STEP 3: Live analysis
print("\n[STEP 3] Live analysis through pipeline...")

async def analyze_olaf():
    try:
        from candle_provider import fetch_candles
        from hybrid_intake import stage3_mini_structure_check
        from setup_validators.under_fib import validate_under_fib
        from engines import run_detection, analyze_structure
        import httpx
        
        print("\n   Fetching token data...")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f'https://api.dexscreener.com/latest/dex/pairs/solana/{OLAF_PAIR_ADDRESS}')
            if resp.status_code == 200:
                data = resp.json()
                pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else {})
                if pair:
                    mc = float(pair.get('marketCap', 0) or 0)
                    liq = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                    symbol = pair.get('baseToken', {}).get('symbol', '???')
                    dex = pair.get('dexId', '')
                    print(f"   Symbol: {symbol} | MC: ${mc:,.0f} | Liq: ${liq:,.0f} | DEX: {dex}")
                    
                    print(f"\n   === FILTER CHECKS ===")
                    print(f"   MC >= 100K: {'✅' if mc >= 100000 else '❌'}")
                    print(f"   Liq >= 10K: {'✅' if liq >= 10000 else '❌'}")
                    print(f"   DEX allowed: {'✅' if dex.lower() in {'pumpfun','pumpswap','raydium'} else '❌'}")
                else:
                    print("   ❌ No pair data"); return
            else:
                print(f"   ❌ API error: {resp.status_code}"); return
        
        print("\n   Fetching candles...")
        token_address = pair.get('baseToken', {}).get('address', '')
        candles = await fetch_candles(OLAF_PAIR_ADDRESS, symbol, token_address)
        if not candles:
            print("   ❌ No candles"); return
        print(f"   ✅ Got {len(candles)} candles")
        
        token = {'symbol': symbol, 'pair_address': OLAF_PAIR_ADDRESS, 'address': token_address, 'market_cap': mc, 'liquidity': liq, 'dex': dex}
        
        print("\n   === HYBRID INTAKE (Stage 3) ===")
        try:
            result = stage3_mini_structure_check(token, candles, metadata_score=70)
            if result:
                print(f"   Score: {result.total_score} | ATH Break: {result.ath_breakout} | Major Break: {result.major_high_break}")
                print(f"   Flip Zone: {result.has_valid_flip_zone} | Impulse: {result.impulse_pct:.1f}% | Retrace: {result.retracement_pct:.1f}%")
                print(f"   Reasons: {', '.join(result.reasons[:8])}")
                print(f"\n   GATE CHECKS:")
                print(f"   - UNDERFIB Gate: {'✅ PASS' if result.passes_underfib_gate else '❌ FAIL'}")
                print(f"   - 382 Gate: {'✅' if result.passes_382fz_gate else '❌'}")
                print(f"   - 50 Gate: {'✅' if result.passes_50fz_gate else '❌'}")
                print(f"   - 618 Gate: {'✅' if result.passes_618fz_gate else '❌'}")
                print(f"   - 786 Gate: {'✅' if result.passes_786fz_gate else '❌'}")
        except Exception as e:
            print(f"   ⚠️ Hybrid error: {e}")
        
        print("\n   === UNDER-FIB VALIDATOR ===")
        try:
            structure = analyze_structure(candles)
            print(f"   Swing High: {structure.get('swing_high', 0):.10f}")
            print(f"   Swing Low: {structure.get('swing_low', 0):.10f}")
            print(f"   Current: {structure.get('current_price', 0):.10f}")
            print(f"   Impulse: {structure.get('impulse_pct', 0):.1f}% | Retrace: {structure.get('retracement_pct', 0):.1f}%")
            print(f"   Flip Zones: {len(structure.get('flip_zones', []))}")
            for i, fz in enumerate(structure.get('flip_zones', [])[:3]):
                if isinstance(fz, dict):
                    print(f"      FZ{i+1}: {fz.get('level', 0):.10f} | touches={fz.get('touches', 0)} | fresh={fz.get('fresh', 'N/A')}")
            
            structure['passes_underfib_gate'] = True
            structure['ath_breakout'] = True
            structure['major_high_break'] = True
            
            validation = validate_under_fib(candles, symbol, structure)
            print(f"\n   RESULT: {'✅ PASSED' if validation.passed else '❌ FAILED'}")
            print(f"   Score: {validation.final_score} | Grade: {validation.final_grade}")
            print(f"   Gate Fib: {validation.gate_fib} | Destination: {validation.destination_zone:.10f}")
            if validation.reject_reason:
                print(f"   Reject Reason: {validation.reject_reason}")
            print(f"\n   LAYERS:")
            for layer in validation.layers:
                print(f"      {'✅' if layer.passed else '❌'} {layer.layer_name}: {layer.score}pts - {layer.reason}")
        except Exception as e:
            print(f"   ⚠️ Validator error: {e}")
            import traceback; traceback.print_exc()
        
        print("\n   === FULL ENGINE DETECTION ===")
        try:
            engine_result = run_detection(token, candles)
            if engine_result:
                print(f"   ✅ TRIGGERED: {engine_result.get('engine_name')} | Grade: {engine_result.get('grade')} | Score: {engine_result.get('score')}")
            else:
                print("   ❌ No engine triggered")
        except Exception as e:
            print(f"   ⚠️ Engine error: {e}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback; traceback.print_exc()

asyncio.run(analyze_olaf())

print("\n" + "=" * 70)
print("DIAGNOSIS COMPLETE - Check output above for failure bucket")
print("=" * 70)
