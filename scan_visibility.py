"""
SCAN VISIBILITY v2.0 - BANGERS ONLY MODE
=========================================
Full transparency logging for each scan cycle.
"""

import logging
from datetime import datetime

# Dedicated visibility logger
vis_logger = logging.getLogger('visibility')
vis_logger.setLevel(logging.INFO)
vis_logger.handlers = []  # Clear existing

fh = logging.FileHandler('/opt/jayce/logs/visibility.log')
fh.setFormatter(logging.Formatter('%(message)s'))
vis_logger.addHandler(fh)

CYCLE_COUNT = 0

def log_cycle_start():
    global CYCLE_COUNT
    CYCLE_COUNT += 1
    vis_logger.info("")
    vis_logger.info("=" * 70)
    vis_logger.info(f"  SCAN CYCLE #{CYCLE_COUNT} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    vis_logger.info("=" * 70)

def log_sources(trending=0, movers_5m=0, movers_1h=0):
    total = trending + movers_5m + movers_1h
    vis_logger.info("")
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  📥 SOURCES RECEIVED                                            │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    vis_logger.info(f"│    TRENDING (extension):    {trending:>4}                              │")
    vis_logger.info(f"│    5M Volume Movers:        {movers_5m:>4}                              │")
    vis_logger.info(f"│    1H Volume Movers:        {movers_1h:>4}                              │")
    vis_logger.info(f"│    ─────────────────────────────                               │")
    vis_logger.info(f"│    TOTAL RAW:               {total:>4}                              │")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_filters(cpmm_clmm=0, duplicates=0, low_liquidity=0, low_mcap=0, no_profile=0, too_new=0):
    total_removed = cpmm_clmm + duplicates + low_liquidity + low_mcap + no_profile + too_new
    vis_logger.info("")
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  🔻 FILTERS APPLIED                                             │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    vis_logger.info(f"│    CPMM/CLMM removed:       {cpmm_clmm:>4}                              │")
    vis_logger.info(f"│    Duplicates removed:      {duplicates:>4}                              │")
    vis_logger.info(f"│    Below liquidity ($10k):  {low_liquidity:>4}                              │")
    vis_logger.info(f"│    Below market cap ($100k):{low_mcap:>4}                              │")
    vis_logger.info(f"│    No profile:              {no_profile:>4}                              │")
    vis_logger.info(f"│    Too new (<1hr):          {too_new:>4}                              │")
    vis_logger.info(f"│    ─────────────────────────────                               │")
    vis_logger.info(f"│    TOTAL REMOVED:           {total_removed:>4}                              │")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_psef_results(passed=0, failed_impulse=0, failed_structure=0, failed_pullback=0, failed_rsi=0):
    total_failed = failed_impulse + failed_structure + failed_pullback + failed_rsi
    vis_logger.info("")
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  🚦 PRE-SETUP ENVIRONMENT FILTER (PSEF)                         │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    vis_logger.info(f"│    ❌ Failed Impulse Gate:    {failed_impulse:>4}                            │")
    vis_logger.info(f"│    ❌ Failed Structure Gate:  {failed_structure:>4}                            │")
    vis_logger.info(f"│    ❌ Failed Pullback Gate:   {failed_pullback:>4}                            │")
    vis_logger.info(f"│    ❌ Failed RSI Memory Gate: {failed_rsi:>4}                            │")
    vis_logger.info(f"│    ─────────────────────────────                               │")
    vis_logger.info(f"│    ✅ PASSED PSEF:            {passed:>4}  (ready for deep scan)      │")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_candidates(candidates):
    vis_logger.info("")
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  🎯 TOP CANDIDATES FOR DEEP SCAN                                │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    for i, c in enumerate(candidates[:20], 1):
        symbol = c.get('symbol', '???')[:12]
        source = c.get('source', '?')[:8]
        score = c.get('light_score', 0)
        reason = c.get('psef_reason', 'qualified')[:20]
        vis_logger.info(f"│  {i:>2}. {symbol:<12} | {source:<8} | Score: {score:>3} | {reason:<20}│")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_deep_scan_results(results):
    vis_logger.info("")
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  🔬 DEEP SCAN RESULTS                                           │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    setups_found = [r for r in results if r.get('setup_detected')]
    no_setup = len(results) - len(setups_found)
    vis_logger.info(f"│    Tokens analyzed:         {len(results):>4}                              │")
    vis_logger.info(f"│    No setup found:          {no_setup:>4}                              │")
    vis_logger.info(f"│    Setups detected:         {len(setups_found):>4}                              │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    if setups_found:
        for r in setups_found:
            symbol = r.get('symbol', '???')[:12]
            setup = r.get('setup', '???')[:18]
            grade = r.get('grade', '?')
            score = r.get('score', 0)
            alert = "🚨 ALERTED" if r.get('alert_sent') else "⏸️ Below threshold"
            vis_logger.info(f"│  {symbol:<12} | {setup:<18} | {grade:<3} | {score:>3} | {alert:<17}│")
    else:
        vis_logger.info("│    No setups detected this cycle                               │")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_alerts_sent(alerts):
    vis_logger.info("")
    if not alerts:
        vis_logger.info("📭 No alerts sent this cycle (BANGERS ONLY: Grade A/A+ & Score >= 85)")
        return
    vis_logger.info("┌─────────────────────────────────────────────────────────────────┐")
    vis_logger.info("│  🚨 ALERTS SENT (BANGERS ONLY)                                  │")
    vis_logger.info("├─────────────────────────────────────────────────────────────────┤")
    for a in alerts:
        symbol = a.get('symbol', '???')[:12]
        setup = a.get('setup', '???')[:20]
        grade = a.get('grade', '?')
        score = a.get('score', 0)
        vis_logger.info(f"│  🎯 {symbol:<12} | {setup:<20} | {grade:<3} | {score:>3}        │")
    vis_logger.info("└─────────────────────────────────────────────────────────────────┘")

def log_cycle_end(duration_seconds):
    vis_logger.info("")
    vis_logger.info(f"⏱️ Cycle completed in {duration_seconds:.1f} seconds")
    vis_logger.info("─" * 70)

def log_final(count, tokens):
    vis_logger.info("")
    vis_logger.info(f"✅ FINAL TOKENS SCANNED: {count}")
    vis_logger.info("")
    vis_logger.info("📋 SAMPLE TOKENS (first 15):")
    for i, t in enumerate(tokens[:15], 1):
        symbol = t.get('symbol', '???')[:12]
        source = t.get('source', '?')[:8]
        mc = t.get('market_cap', 0) or 0
        liq = t.get('liquidity', 0) or 0
        vis_logger.info(f"   {i:>2}. {symbol:<12} | {source:<8} | MC: ${mc:>12,.0f} | Liq: ${liq:>10,.0f}")

def log_engine_results(detections):
    vis_logger.info("")
    vis_logger.info(f"🎯 ENGINE DETECTIONS: {len(detections)}")
    for d in detections:
        vis_logger.info(f"   → {d.get('symbol', '?')} — {d.get('setup', '?')} — Grade: {d.get('grade', '?')}")
