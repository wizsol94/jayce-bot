# JAYCE SESSION NOTES - March 12, 2026

## COMPLETED THIS SESSION

### 1. TELEGRAM SCAN MONITOR v3.1
- File: `/opt/jayce/scan_monitor.py`
- Sends 3 separate messages per cycle (TOP, 5M, 1H)
- Shows FULL raw token lists before merge
- Smart message splitting for long lists
- Provenance labels for candidates (source-specific vs merged pool)
- Sends to private work chat (HEARTBEAT_CHAT_ID)

### 2. RAW TOKEN TRACKING
- Added to scanner.py in `scan_top_movers` function
- Captures: `raw_top100_symbols`, `raw_5m_vol_symbols`, `raw_1h_vol_symbols`
- Tracks tokens BEFORE merge/dedup

### 3. RUNNER INTELLIGENCE LAYER
- File: `/opt/jayce/runner_intelligence.py`
- Analyzes runner potential after WizTheory setup triggers
- 4 conditions: momentum_detected, momentum_memory, rsi_staircase, support_protected
- Divergence detection included

## ISSUE IDENTIFIED
Scanner API endpoints don't match DexScreener UI:
- `token-boosts/top/v1` - Wrong endpoint
- `search?q=pumpfun` - Just keyword search
- `search?q=pumpswap` - Just keyword search

DexScreener public API doesn't support UI filters:
- rankBy=trendingScoreH6
- dexIds=pumpswap,pumpfun
- minLiq=10000
- minMarketCap=100000
- minAge=1 (1 hour)

## NEXT STEPS
Enhance Chrome extension to capture all 3 rotations:
1. TOP 1-100 (trendingScoreH6)
2. 5M MOVERS 1-50
3. 1H MOVERS 1-50

Extension saves to queue with proper source tags.
Scanner reads from extension queue only.

## KEY FILES
- /opt/jayce/scanner.py - Main scanner
- /opt/jayce/scan_monitor.py - Telegram scan monitor v3.1
- /opt/jayce/runner_intelligence.py - Runner intelligence layer
- /opt/jayce/chart_intelligence.py - 6 intelligence layers
- /opt/jayce/data/queue.db - SQLite token queue

## SERVICES
- jayce-scanner (systemd) - Main scanner
- jayce-receiver (systemd) - Webhook receiver
- jayce-scraper (systemd) - Token scraper
