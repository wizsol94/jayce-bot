# JAYCE BOT — COMPLETE SYSTEM DOCUMENTATION
## Version 4.2 | March 2026

---

# 1. SYSTEM OVERVIEW

Jayce is an automated cryptocurrency token scanning and alert system designed to detect high-probability trading setups on Solana memecoins using the WizTheory methodology.

## Core Purpose
Continuously scan PumpFun and PumpSwap tokens on Solana, detect Fibonacci-based flip zone setups, grade them using multiple intelligence layers, and deliver real-time Telegram alerts for actionable trading opportunities.

## Architecture Summary
```
┌─────────────────────────────────────────────────────────────────┐
│                        iMAC (LOCAL)                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Chrome Extension — Jayce DexScreener Collector         │   │
│  │  • Auto-captures every 10 minutes                       │   │
│  │  • Scrapes TOP 1-100, 5M MOVERS, 1H MOVERS             │   │
│  │  • Sends tokens to VPS via HTTP POST                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP POST (tokens + source)
┌─────────────────────────────────────────────────────────────────┐
│                    VPS (DigitalOcean 104.236.105.118)          │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ jayce-receiver  │───▶│   queue.db      │                    │
│  │ (Flask API)     │    │ (SQLite)        │                    │
│  │ Port 5000       │    │ 300 tokens      │                    │
│  └─────────────────┘    └────────┬────────┘                    │
│                                  │                              │
│                                  ▼                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   jayce-scanner                          │   │
│  │  • Reads tokens from queue.db                           │   │
│  │  • Fetches candles from Birdeye API                     │   │
│  │  • Runs WizTheory detection engine                      │   │
│  │  • Applies 6 intelligence layers                        │   │
│  │  • Sends alerts via Telegram                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                  │                              │
└──────────────────────────────────┼──────────────────────────────┘
                                   │
                                   ▼ Telegram Bot API
┌─────────────────────────────────────────────────────────────────┐
│                         TELEGRAM                                │
│  • Alert Channel: Trading alerts (A/A+ setups)                 │
│  • Private Chat: Scan monitor, heartbeats                      │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components
| Component | Location | Purpose |
|-----------|----------|---------|
| Chrome Extension | iMac | Captures tokens from DexScreener UI |
| jayce-receiver | VPS :5000 | Receives tokens, stores in queue |
| jayce-scanner | VPS systemd | Main scanning engine |
| queue.db | VPS SQLite | Token queue database |
| Telegram Bot | Cloud | Delivers alerts |

---

# 2. DATA PIPELINE

## Step-by-Step Token Flow

### Step 1: DexScreener UI Capture
The Chrome extension opens DexScreener with your exact filters:
```
Chain: Solana
DEX: PumpFun + PumpSwap only
Min Liquidity: $10,000
Min Market Cap: $100,000
Min Age: 1 hour
Launchpads: Enabled
```

### Step 2: Extension Scrapes Tokens
For each rotation, the extension:
1. Navigates to the filtered DexScreener URL
2. Waits 6 seconds for page render
3. Scrapes all token rows (up to 100)
4. Extracts: symbol, pair_address, rank
5. Tags with source: TRENDING, VOL_5M, or VOL_1H

### Step 3: HTTP POST to VPS
```javascript
POST http://104.236.105.118:5000/tokens
Headers: X-API-Key: jayce_collector_2026_secret_key
Body: { tokens: [...], source: "TRENDING" }
```

### Step 4: Receiver Stores in Queue
The jayce-receiver Flask app:
1. Validates API key
2. Deletes old tokens of SAME source only
3. Inserts new tokens with timestamp
4. Preserves other sources (no cross-deletion)

### Step 5: Scanner Reads Queue
Every scan cycle, the scanner:
1. Calls `/queue` API endpoint
2. Receives all 300 tokens (100 per source)
3. Deduplicates by address (169 unique typical)
4. Captures raw lists per source for monitoring

### Step 6: Candle Fetching
For each candidate token:
1. Fetch 5-minute candles from Birdeye API
2. Get last 100 candles (8+ hours of data)
3. Calculate RSI, volume, structure

### Step 7: WizTheory Detection
Run full detection engine:
1. Structure analysis (impulse, pullback, consolidation)
2. Fibonacci level detection (382, 50, 618, 786)
3. Flip zone identification
4. Momentum confirmation
5. Volume analysis

### Step 8: Intelligence Layers
Apply 6 intelligence layers for scoring:
1. Breakout Expansion Recognition
2. Prime Setup Condition
3. Structure Quality
4. Pullback Quality
5. Setup Maturity
6. Momentum Continuation/RSI

### Step 9: Alert Decision
```
Score >= 80 AND Grade in [A+, A] → SEND ALERT
Score < 80 OR Grade in [B+, B, C] → LOG ONLY
```

### Step 10: Telegram Delivery
Alert sent to main channel with:
- Token symbol and address
- Setup type (382, 50, 618, 786, Under-Fib)
- Grade and score
- Chart link
- Entry zone information

---

## Rotation Sources

### TRENDING (TOP 1-100)
- **URL Parameter**: `rankBy=trendingScoreH6`
- **Purpose**: Tokens with highest 6-hour trending activity
- **Count**: 100 tokens per capture

### VOL_5M (5M MOVERS)
- **URL Parameter**: `rankBy=priceChangeM5`
- **Purpose**: Tokens with biggest 5-minute price movement
- **Count**: 100 tokens per capture

### VOL_1H (1H MOVERS)
- **URL Parameter**: `rankBy=priceChangeH1`
- **Purpose**: Tokens with biggest 1-hour price movement
- **Count**: 100 tokens per capture

---

# 3. EXTENSION QUEUE SYSTEM

## Database Schema
```sql
CREATE TABLE token_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    symbol TEXT,
    pair_address TEXT,
    contract_address TEXT,
    source TEXT,          -- TRENDING, VOL_5M, VOL_1H
    rank INTEGER,
    url TEXT,
    processed INTEGER DEFAULT 0,
    has_screenshot INTEGER DEFAULT 0
);
```

## Capture Frequency
- **Auto-capture**: Every 10 minutes
- **Manual capture**: On-demand via extension popup
- **Initial capture**: 30 seconds after Chrome opens

## Duplicate Handling
1. **Same-source replacement**: When TRENDING captures, old TRENDING tokens deleted
2. **Cross-source preservation**: VOL_5M capture doesn't affect TRENDING
3. **Address deduplication**: Scanner dedupes by pair_address before scanning

## Token Expiration
- Tokens remain until replaced by next same-source capture
- No time-based expiration currently
- Processed flag marks tokens after scanning (currently unused)

## Storage Capacity
- **Per source**: 100 tokens
- **Total**: 300 tokens (before dedup)
- **After dedup**: ~150-200 unique tokens typical

---

# 4. SCANNER ENGINE

## Scan Cycle Structure
```
CYCLE START
├── Read queue (300 tokens)
├── Deduplicate (→ ~170 unique)
├── Capture raw lists for monitor
├── Log sources breakdown
│
├── WHALE SCAN (priority)
│   └── Scan whale-flagged tokens first
│
├── LIGHT FILTER
│   ├── Market cap filter ($100K min)
│   ├── Liquidity filter ($10K min)
│   ├── Price change scoring
│   └── Select top 20 candidates
│
├── PSEF FILTER (Pre-Setup Environment)
│   ├── Impulse check
│   ├── Structure check
│   ├── Pullback check
│   └── RSI check
│
├── DEEP SCAN (top 20 candidates)
│   ├── Fetch candles (Birdeye API)
│   ├── Run WizTheory engine
│   ├── Apply intelligence layers
│   ├── Calculate final score
│   └── Grade assignment
│
├── ALERT DECISION
│   ├── A+ → Alert immediately
│   ├── A → Vision confirmation → Alert
│   └── B+ and below → Log only
│
├── SCAN MONITOR
│   └── Send 3 Telegram messages (TOP, 5M, 1H)
│
CYCLE COMPLETE (~4-5 minutes)
```

## Cycle Frequency
- **Target**: Every 4-5 minutes
- **Rate limiting**: 5 seconds between candle fetches
- **Daily cycles**: ~300 cycles/day

## Token Selection
1. All tokens from queue loaded
2. Deduplicated by address
3. Scored by light metrics (price change, volume, MC)
4. Top 20 selected for deep scan
5. Watchlist tokens get +20 score boost

## Ranking Logic
```python
light_score = (h1_change * 3) + (h6_change * 2) + h24_change + (volume / 10000)
```
Higher score = higher priority for deep scan.

---

# 5. WIZ THEORY DETECTION LOGIC

## Setup Types

### 382 Setup
- Price retraces to 38.2% Fibonacci level
- Flip zone forms at 382 level
- Requires: impulse move, clean pullback, volume confirmation

### 50 Setup
- Price retraces to 50% Fibonacci level
- Mid-level flip zone
- Most common setup type

### 618 Setup
- Price retraces to 61.8% Fibonacci level
- Deep pullback with strong structure
- Higher risk, higher reward

### 786 Setup
- Price retraces to 78.6% Fibonacci level
- Very deep pullback
- Requires strong structure confirmation

### Under-Fib Flip Zone
- Price dips below key fib level then reclaims
- "Spring" pattern
- Requires quick reclaim and momentum

## Structure Detection

### Impulse Recognition
```python
def detect_impulse():
    # Look for 3+ consecutive bullish candles
    # Minimum expansion: 25-40%
    # Volume increase required
    # Returns: impulse_start, impulse_end, expansion_pct
```

### Pullback Quality
```python
Classifications:
- PULLBACK_CLEAN: Smooth retrace, low wicks, decreasing volume
- PULLBACK_USABLE: Minor chop but readable structure
- PULLBACK_AGGRESSIVE: Fast retrace, high volatility
- PULLBACK_BAD: Chaotic, unclear structure
```

### Consolidation Detection
- 5+ candles in tight range (<10% range)
- Decreasing volume into consolidation
- Precedes breakout or continuation

## Momentum Checks

### RSI Analysis
```python
RSI Conditions:
- Momentum breakout: RSI >= 70 during impulse
- Momentum memory: RSI pullbacks hold above 40
- RSI staircase: Each RSI peak >= previous peak
- Divergence: Price HH + RSI LH = warning
```

### Volume Logic
```python
Volume Confirmations:
- Impulse volume > 2x average
- Pullback volume < impulse volume
- Breakout volume spike required
```

## Whale Integration
- Whale buys flagged via Wally webhook
- Whale tokens get priority scanning
- Whale wallet addresses tracked
- Buy amount (SOL) logged

---

# 6. FLASHCARD TRAINING SYSTEM

## Overview
The flashcard system uses Claude's vision API to compare new charts against trained examples of successful setups.

## Training Library
```
/opt/jayce/flashcards/
├── 382/     (42 images)
├── 50/      (47 images)
├── 618/     (66 images)
├── 786/     (36 images)
└── under_fib/ (41 images)

Total: 232 trained examples
```

## How Vision Works
1. Chart screenshot captured for candidate token
2. Screenshot sent to Claude API with prompt
3. Claude compares to training examples
4. Returns: pattern_match, confidence, notes

## Pattern Matching
```python
Vision Prompt Structure:
"Analyze this chart. Does it match the {setup_type} pattern?
Key characteristics of {setup_type}:
- [pattern description]
- [entry criteria]
- [confirmation signals]

Compare to training examples and rate confidence 0-100."
```

## Scoring Integration
- Vision confidence adds to base score
- High confidence (>80) → +10 points
- Medium confidence (60-80) → +5 points
- Low confidence (<60) → no bonus

## Usage Limits
- Tracked in `/opt/jayce/data/vision_usage.json`
- Monthly API call tracking
- Applied to A-grade setups only (not all tokens)

---

# 7. INTELLIGENCE LAYERS

## Layer 1: Breakout Expansion Recognition
**File**: `chart_intelligence.py`
**Function**: `analyze_breakout_expansion()`

Classifies the breakout type:
- `ATH_BREAK`: All-time high break (strongest)
- `MAJOR_HIGH_BREAK`: Major resistance break
- `LOCAL_BREAK`: Local high break (weakest)
- `NO_BREAKOUT`: No clear breakout

**Scoring**: ATH +15, Major +10, Local +5

---

## Layer 2: Prime Setup Condition
**Function**: `check_prime_setup_condition()`

Gate that blocks non-prime setups:
- Requires ATH_BREAK, MAJOR_HIGH_BREAK, or >=40% expansion
- LOCAL_BREAK and NO_BREAKOUT = blocked
- This is a PASS/FAIL gate, not a scoring layer

---

## Layer 3: Structure Quality
**Function**: `analyze_structure_quality()`

Evaluates overall chart structure:
- `STRUCTURE_STRONG`: Clean impulse, clear levels
- `STRUCTURE_USABLE`: Minor issues but tradeable
- `STRUCTURE_MESSY`: Choppy, unclear
- `STRUCTURE_BAD`: Untradeable

**Scoring**: Strong +5, Usable +2, Messy -2, Bad -5

---

## Layer 4: Pullback Quality
**Function**: `analyze_pullback_quality()`

Evaluates the pullback characteristics:
- `PULLBACK_CLEAN`: Ideal retrace
- `PULLBACK_USABLE`: Acceptable
- `PULLBACK_AGGRESSIVE`: Risky but valid
- `PULLBACK_BAD`: Avoid

**Scoring**: Clean +6, Usable +3, Aggressive -3, Bad -6

---

## Layer 5: Setup Maturity
**Function**: `detect_setup_maturity()`

Timing context (informational, no score impact):
- `SETUP_FORMING`: Early stage
- `SETUP_APPROACHING`: Getting close
- `SETUP_READY`: Optimal entry window
- `SETUP_TRIGGERED`: Entry happening now
- `SETUP_LATE`: Missed optimal entry

---

## Layer 6: Momentum Continuation/RSI
**Function**: `analyze_momentum_behavior()`

RSI-based momentum assessment:
- `MOMENTUM_RUNNER`: High probability runner
- `MOMENTUM_HEALTHY`: Normal bullish momentum
- `MOMENTUM_NEUTRAL`: No clear momentum
- `MOMENTUM_WEAK`: Losing steam

**Scoring**: Runner +3, Healthy +2, Neutral 0, Weak -2

---

## Layer 7: Runner Intelligence
**File**: `runner_intelligence.py`
**Function**: `analyze_runner_intelligence()`

Post-detection analysis for runner probability:
1. RSI Momentum Breakout (>70)
2. Momentum Memory (pullbacks >40)
3. RSI Staircase (peaks equal or higher)
4. Entry Support Protected

**Output**: Runner probability (HIGH/MEDIUM/LOW/NONE)

---

## Signal Filtering

### Cooldown Logic
- 120-minute cooldown per token after alert
- Prevents spam alerts on same token
- Tracked in memory

### Grade Thresholds
- **A+**: Score >= 90, all confirmations
- **A**: Score >= 80, strong setup
- **B+**: Score >= 70, watchlist worthy
- **B**: Score >= 60, forming
- **C**: Score < 60, skip

---

# 8. TELEGRAM ALERT SYSTEM

## Alert Channels

### Main Alert Channel
**Chat ID**: -1003004536161
- Trading alerts (A/A+ grade only)
- Full setup details
- Chart links

### Private Work Chat
**Chat ID**: 972400256 (HEARTBEAT_CHAT_ID)
- Scan monitor messages
- System heartbeats
- Debug information

## Alert Trigger Conditions
```python
SEND_ALERT = (
    score >= 80 AND
    grade in ['A+', 'A'] AND
    not in_cooldown AND
    prime_condition_passed
)
```

## Alert Message Format
```
🎯 WIZTHEORY ALERT

Token: $SYMBOL
Setup: 382 + Flip Zone
Grade: A (Score: 85)

Entry Zone: $0.00123 - $0.00125
Stop Loss: $0.00118

Intelligence:
- Structure: STRONG
- Pullback: CLEAN
- Momentum: HEALTHY
- Runner Prob: MEDIUM

📊 DexScreener | 🐦 Twitter
```

## Scan Monitor Format
```
🔄 JAYCE SCAN CYCLE

Rotation: TOP 1–100
Time: 12:35:00 UTC
Scanned: 100

Coins Scanned:
1. IRAN
2. Distorted
3. Peace
...

Candidates (matched from merged pool):
- SYMBOL — reason

Alerts (matched from merged pool):
- None

Filter Summary:
- Total scanned: 100
- Passed filters: 15
- Candidates: 3
- Alerts: 0
```

---

# 9. INFRASTRUCTURE

## iMac (Local Machine)
- **Role**: Data capture
- **Software**: Chrome + Jayce Extension
- **Requirement**: Must stay on with Chrome running
- **Network**: Sends HTTP POST to VPS

## VPS (DigitalOcean)
- **IP**: 104.236.105.118
- **OS**: Ubuntu 24
- **Location**: NYC region

### Services (systemd)
| Service | Port | Purpose |
|---------|------|---------|
| jayce-scanner | - | Main scanning engine |
| jayce-receiver | 5000 | API for extension data |
| jayce-scraper | - | Legacy (may be disabled) |

### Database
- **File**: `/opt/jayce/data/queue.db`
- **Type**: SQLite
- **Tables**: token_queue

### Key Files
```
/opt/jayce/
├── scanner.py              # Main scanner
├── receiver.py             # Flask API
├── chart_intelligence.py   # 6 intelligence layers
├── runner_intelligence.py  # Runner detection
├── scan_monitor.py         # Telegram monitor
├── flashcard_vision.py     # Vision API
├── impulse_detector.py     # Impulse detection
├── dexscreener_fetcher.py  # Data fetching
├── data/
│   ├── queue.db            # Token queue
│   └── vision_usage.json   # API tracking
├── flashcards/             # 232 training images
├── logs/
│   └── scanner.log         # Main log
└── chrome-extension/       # Extension source
```

## External APIs

### Birdeye API
- **Purpose**: Candle data
- **Key**: f8e954ab5b0d4539a1104a843bd83bdf
- **Rate limit**: Managed with delays

### Anthropic API (Claude)
- **Purpose**: Vision analysis
- **Key**: Stored in .env
- **Usage**: A-grade setups only

### Telegram Bot API
- **Purpose**: Alerts and monitoring
- **Token**: Stored in .env

---

# 10. PERFORMANCE + COSTS

## Scan Frequency
- **Cycle time**: ~4-5 minutes
- **Cycles per hour**: ~12-15
- **Cycles per day**: ~300

## API Usage

### Birdeye
- ~20 candle fetches per cycle
- ~6,000 requests/day
- Free tier may have limits

### Anthropic (Vision)
- Only for A-grade setups
- ~2-5 calls per day typical
- Monthly tracking in vision_usage.json

### DexScreener
- Extension scrapes UI (not API)
- No rate limits for scraping
- API used for candle pairs lookup

## Server Load
- **CPU**: Low (~5-10% average)
- **Memory**: ~500MB for scanner
- **Disk**: Minimal (logs rotate)

## Estimated Monthly Costs
| Item | Cost |
|------|------|
| DigitalOcean VPS | $6-12/month |
| Birdeye API | Free tier |
| Anthropic API | $5-20/month (usage based) |
| Telegram | Free |
| **Total** | **~$15-35/month** |

---

# 11. CURRENT LIMITATIONS

## Extension Dependency
- Requires iMac to be on with Chrome running
- If iMac sleeps, queue data becomes stale
- No cloud-based capture fallback

## Single Point of Failure
- VPS down = no scanning
- No redundancy or failover
- No automatic restart on crash (systemd helps)

## Rate Limiting
- 5-second delay between candle fetches
- Limits throughput to ~12 tokens/minute deep scan
- Only top 20 candidates get deep scan

## Detection Accuracy
- Depends on training data quality
- May miss non-standard setups
- Vision API adds latency

## No Backtesting
- Cannot test strategy on historical data
- No performance metrics tracking
- No win/loss ratio calculation

## Manual Token Refresh
- Extension auto-captures every 10 min
- But still requires iMac to be active
- Queue can be up to 10 minutes stale

---

# 12. FUTURE EXPANSION

## Automated Trading
```
Current: Alert → Manual trade
Future:  Alert → Auto-execute via Jupiter/Raydium
```
- Integrate with Solana wallet
- Set position sizes, stop losses
- Risk management rules

## Predictive Scanning
- ML model trained on historical setups
- Predict setup formation before it completes
- Earlier entry signals

## Enhanced Whale Monitoring
- Real-time whale wallet tracking
- Whale accumulation patterns
- Smart money flow analysis

## Multi-Chain Expansion
- Add Base, Ethereum, BSC
- Same detection logic
- Chain-specific filters

## Performance Analytics
- Track alert outcomes
- Win/loss ratio
- Profit/loss per setup type
- Optimize detection parameters

## Cloud Extension
- Move extension scraping to cloud
- Headless browser on VPS
- Remove iMac dependency
- True 24/7 operation

## Additional Intelligence Layers
- Order flow analysis
- Social sentiment (Twitter/Telegram)
- Holder distribution analysis
- Token age and history scoring

## Mobile App
- Push notifications
- Quick trade execution
- Portfolio tracking
- Setup review interface

---

# APPENDIX: QUICK REFERENCE

## Service Commands
```bash
# Scanner
systemctl status jayce-scanner
systemctl restart jayce-scanner
journalctl -u jayce-scanner -f

# Receiver
systemctl status jayce-receiver
systemctl restart jayce-receiver

# Logs
tail -f /opt/jayce/logs/scanner.log
```

## Queue Commands
```bash
# Check queue status
sqlite3 /opt/jayce/data/queue.db "SELECT source, COUNT(*) FROM token_queue WHERE processed=0 GROUP BY source;"

# View recent tokens
sqlite3 /opt/jayce/data/queue.db "SELECT symbol, source, rank FROM token_queue ORDER BY id DESC LIMIT 20;"

# Clear queue
sqlite3 /opt/jayce/data/queue.db "DELETE FROM token_queue;"
```

## Extension Refresh
1. Download: http://104.236.105.118:5000/download/extension
2. Unzip
3. chrome://extensions → Refresh icon

---

*Documentation generated: March 12, 2026*
*Jayce Bot Version: 4.2*
