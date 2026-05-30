# JAYCE FULL SYSTEM AUDIT — COMPLETE
## WizTheory Engine / Jayce Scanner Architectural Audit

**Started:** May 26, 2026
**Completed:** May 29, 2026
**Status:** ✅ ALL 10 SECTIONS COMPLETE + 2 interludes
**Methodology:** Code-grounded, no patches during audit, sequential, brutally honest
**Outcome:** Complete blueprint for Jayce's evolution into a multi-specialist WizTheory intelligence system

---

# THE AUDIT'S CENTRAL FINDING

> **Jayce is not broken. Jayce is powerful but fragmented.**
>
> The future Jayce is shared primitives underneath, multiple specialists on top. All pipelines inherit the same truth. Each specialist contributes a perspective. Scanner.py becomes a thin alert layer that honors doctrine instead of silently overwriting it.
>
> **The architectural principle:** Do NOT make Jayce simpler by making him weaker. Make Jayce simpler by giving every specialist the same underlying truth.

---

# TABLE OF CONTENTS

- [The Defining Architectural Truths](#truths)
- [Section 1 — Discovery / Intake](#section-1)
- [Section 2 — Candle & Structure](#section-2)
- [Section 3 — Setup Classification](#section-3)
- [Section 4 — Validator Layer](#section-4)
- [Section 5 — RSI & Momentum Philosophy](#section-5)
- [Section 6 — Engine Layer](#section-6)
- [Section 7 — Visual Intelligence Layer](#section-7)
- [Setup Grader Deep-Dive (interlude)](#setup-grader)
- [Setup Grader Consumer Trace (interlude)](#consumer-trace)
- [Section 8 — Alert Layer (The Parliament)](#section-8)
- [Section 9 — Logging / Monitoring / Safety](#section-9)
- [Section 10 — Architecture Review (The Synthesis)](#section-10)
- [Master Severity Table](#severity)
- [Doctrine Locks](#doctrine)

---

# THE DEFINING ARCHITECTURAL TRUTHS <a name="truths"></a>

## Truth 1: Additive Architecture Pattern

**Jayce evolved via ADDITIVE architecture — new systems were layered on top of old ones instead of replacing them.**

Confirmed across: classifiers, structure analyzers, breakout detectors, caches, validators, RSI systems, orchestration paths, calculate_rsi implementations, grading scales, cooldown systems, alert paths, tracking systems.

## Truth 2: Three Parallel Grading Pipelines

| Pipeline | Structure Source | Swing Algo | RSI Philosophy | Grade Thresholds | Age |
|---|---|---|---|---|---|
| **engines** | engines.analyze_structure | max/min (naïve) | legacy + divergence | A=75, A+=85 | OLDER |
| **bangers** | structure_engine.analyze_structure | fractal (lookback=3) | rsi_memory (doctrine) | A=85, A+=95 | NEWER |
| **impulse_detector** | internal | wick-cluster | peak_rsi (aligned) | (boolean) | MIDDLE |

**Root cause of disagreement:** Three pipelines use three DIFFERENT structure sources → they see DIFFERENT swing highs/lows → different impulse legs → different everything.

**They disagree on chart REALITY, not just opinion.**

## Truth 3: Scanner.py IS the Parliament

The actual final authority over alerts is **not** any pipeline — it's the reconciliation logic inside scanner.py. The pipelines produce opinions; scanner.py issues verdicts.

- 7 should_alert mutations across the alert lifecycle
- 3 emergent grading scales (engines / setup_grader / scanner)
- 3 independent cooldown systems
- 4 separate alert paths (WIZTHEORY / CONFIRMED / VALID / FORMING)
- PSEF doctrine silently dropped by scanner mutations
- setup_grader's strict triple-gate effectively decorative

**The fix is NOT to delete pipelines.** It's SHARED PRIMITIVES underneath multiple analytical perspectives.

---

# SECTION 1 — DISCOVERY / INTAKE <a name="section-1"></a>

## Architecture Map

```
DexScreener (3 URLs: TRENDING max200, VOL_5M max50, VOL_1H max50)
        ↓ filtered: minLiq=10000, minMarketCap=100000, minAge=1
vps_scraper.py (Playwright, 300s interval, Webshare proxy)
        ↓
queue.db.token_queue (SQLite)
        ↓
scanner.py:fetch_volume_from_queue (line 349) [WHERE processed=0]
        ↓
hybrid_intake.py (Stage 2: metadata score, top 60 / Stage 3: gates)
        ↓
engines.run_detection
```

## Filter cascade

- **dexscreener_fetcher.py:** MIN_LIQUIDITY=10000, MIN_MARKET_CAP=100000, MIN_AGE_HOURS=1
- **scanner.py:** MIN_MARKET_CAP=0 (DISABLED), MIN_LIQUIDITY=10000, MIN_COIN_AGE_HOURS=3, MIN_CANDLES=12

## Stage 3 gate computation

| Gate | Territory | Criteria |
|---|---|---|
| passes_382fz_gate | 28-45% retrace | (ath_breakout OR major_high_break) AND has_valid_flip_zone AND expansion ≥ 60% |
| passes_50fz_gate | 40-60% retrace | (ath_breakout OR major_high_break) AND has_valid_flip_zone AND expansion ≥ 60% |
| passes_618fz_gate | 55-70% retrace | (ath_breakout OR major_high_break) AND has_valid_flip_zone AND expansion ≥ 60% |
| passes_786fz_gate | 68-82% retrace | (ath_breakout OR major_high_break) AND has_valid_flip_zone AND expansion ≥ 100% |
| passes_underfib_gate | ≥40% retrace | (ath_breakout OR major_high_break) AND has_valid_flip_zone AND expansion ≥ 60% |

## Critical Findings (Section 1)

- **1.A** Cooldown blocks setup evolution (HIGH, CONFIRMED BUG)
- **1.B** Triple-duplicate 786 gate block (LOW)
- **1.C** MIN_MARKET_CAP=0 dead checks (LOW)
- **1.D** Age filter mismatch (LOW, intentional defense-in-depth)

---

# SECTION 2 — CANDLE & STRUCTURE <a name="section-2"></a>

## Architecture Map

**Candle fetching (candle_provider.py):**
- Primary: Birdeye (TOKEN address) | Fallback: GeckoTerminal (PAIR address)
- Daily Birdeye cap: 5000 | Gecko 429 cooldown: 60s

**Structure analyzers (FIVE+ parallel systems):**
1. `engines.analyze_structure` — naïve max/min swings
2. `impulse_detector.measure_expansion` — wick-cluster impulse
3. `psef.find_swings` (lookback=3 fractal)
4. `structure_engine.analyze_structure` — fractal, used by bangers
5. `bangers_pipeline` orchestration

**Breakout detection (TWO parallel systems):**
1. `breakout_validator.validate_breakout` — historical resistance + 30% expansion
2. `impulse_detector.detect_breakout` — 50-candle wick-cluster

**Cache systems (THREE with mismatched TTLs):**
| Cache | Tier1 | Tier2 | Tier3 |
|---|---|---|---|
| cache_tiers.py | 90s | 240s | 720s |
| candle_cache.py | NEVER | 90s | 120s |
| candle_provider legacy CANDLE_CACHE | 30min | — | — |

## Critical Findings (Section 2)

- **2.A** 5+ parallel structure detection systems (HIGH)
- **2.B** structure_engine.py CORRECTED to LIVE (used by bangers_pipeline)
- **2.C** Three cache systems with mismatched TTLs (MEDIUM)
- **2.E** queue.processed NEVER set to 1 (MEDIUM)
- **2.F** engines.analyze_structure uses naïve max/min (HIGH) — breaks continuation
- **2.G** Two breakout detectors with different philosophies (HIGH)
- **2.H** run_detection 2 call sites (LOW — intentional)
- **2.J** psef.find_swings is 3rd swing detection copy (MEDIUM)
- **2.K** structural_prescan + hybrid_intake sequential (LOW)
- **2.L** Structure primitives duplicated across 5 modules (HIGH)

---

# SECTION 3 — SETUP CLASSIFICATION <a name="section-3"></a>

## Two competing classifiers

**Classifier A — impulse_detector.py (FIB-CLASS)**
- Wick-based match → body acceptance override
- Cannot classify Under-Fib (explicitly skips UNDER_FIB)

**Classifier B — engines.py (BODY-ROUTE)**
- Sophisticated multi-step (fib levels, deepest wick retrace, body-percentile FZ, boundary rule, confidence 0-100)
- Special 382 handling
- Drives engine selection via engine_order reordering

## Body acceptance override

`body_recommended = (engine_id == recommended_setup AND confidence ≥ 50)` — overrides wick retrace range.

## Three generations of body-acceptance code

| Location | Status |
|---|---|
| engines.py:585 determine_setup_by_body_acceptance | LIVE |
| engines.py:908 determine_setup_by_body_acceptance_OLD | DEAD |
| impulse_detector.py:592 analyze_body_acceptance | LIVE (different file) |

## Critical Findings (Section 3)

- **3.A** Two competing classifiers (HIGH)
- **3.B** determine_setup_by_body_acceptance_OLD dead code (LOW)
- **3.C** pseudo_overlap is proximity not overlap (LOW)
- **3.D** Body override threshold of 50 is sensitive (MEDIUM)
- **3.E** Hybrid gates vs engine ranges mismatch (LOW)
- **3.F** Triple-duplicate 786 block (LOW)
- **3.G** Two analyze_body_acceptance functions in different files (HIGH)
- **3.H** Classifier A cannot classify Under-Fib (architectural)
- **3.I** MIXED-DEPTH warning doesn't gate alerts (MEDIUM)

---

# SECTION 4 — VALIDATOR LAYER <a name="section-4"></a>

## Validator Inventory

| File | Setup | Entry function |
|---|---|---|
| three_eighty_two.py | 382 + Flip Zone | validate_382 |
| fifty_bounce.py | 50 + Flip Zone | validate_50_bounce |
| six_eighteen.py | 618 + Flip Zone | validate_618 |
| seven_eighty_six.py | 786 + Flip Zone | validate_786 |
| under_fib.py | Under-Fib | validate_under_fib |
| hunter_mode.py | Shared | detect_expansion_exhaustion |
| breakout_validator.py | Pre-gate | validate_breakout |

ValidationResult dataclass redefined 5x (duplicated across all validators).

## Hunter Mode signal map

| Signal | Threshold | Points | Status |
|---|---|---|---|
| 1: rejection_wick | upper_wick > body × 1.5 | 25 | REAL |
| 2: bearish_at_high | close < open | 20 | REAL |
| 3: volume_spike | volume > 2× avg | 20 | REAL |
| 4: pullback_started | price < swing_high × 0.97 | 15 | **AUTO-FIRES** |
| 5: rsi_divergence | rsi_at_high > 70 AND current < 60 | 15 | **DEAD** |
| 6: consecutive_red | 2+ red candles | 15 | REAL |

**Threshold (post-Sprint A):** exhaustion_score ≥ 55

## Stale-breakout filter (THE CONTINUATION KILLER)

**breakout_validator.py:187:** `MAX_CANDLES_SINCE_ATH = 100` (on 5m candles = ~8.3 hours).

Any setup where ATH > 8.3h ago = INSTANT REJECT.

## Critical Findings (Section 4)

- **4.A** Stale-breakout cap kills continuation setups (HIGH — RICH bug)
- **4.B** Signal 4 free 15 points (MEDIUM, partially addressed by Sprint A)
- **4.C** Signal 5 dead code (LOW)
- **4.D** ValidationResult dataclass duplicated 5x (LOW)
- **4.E** validate_50_bounce different signature (LOW)
- **4.F** Hunter Mode is PRIMARY for 382+50 (architectural)
- **4.G** 618/786 don't use Hunter Mode (architectural)
- **4.I** Validator layer weights not uniform (LOW)

---

# SECTION 5 — RSI & MOMENTUM PHILOSOPHY <a name="section-5"></a>

## The doctrinal anchor (bot.py:2133-2229)

```
RSI is NEVER a signal, prediction tool, or overbought/oversold indicator.
RSI is ONLY momentum memory and permission.

RSI ZONES:
  > 50: Momentum supports continuation
  40-50: Momentum intact
  < 40: Momentum damage
  < 30: Trend integrity compromised (NOT "oversold")

Order: Structure → RSI Permission → Divergence (ALWAYS LAST)
```

## Six calculate_rsi implementations

| File | Returns | Used by |
|---|---|---|
| engines.py:178 | single float | engines.analyze_structure |
| impulse_detector.py:102 | list | impulse_detector + Peak RSI |
| psef.py:32 | list | psef.gate_4_rsi |
| rsi_memory.py:35 | list | bangers_pipeline |
| runner_intelligence.py:40 | list | UNCLEAR |
| chart_intelligence.py:870 | list | chart_intelligence |

## RSI usage classification

**🟢 ALIGNED:** bot.py philosophy, rsi_memory.py, psef.py Gate 4, chart_intelligence.py momentum tiers, Peak RSI infrastructure

**🟡 SOFT-GATING:** engines.py:484-488 RSI score tiers, engines.py:1372 impulse+RSI combo gate

**🔴 MISALIGNED:** engines.py:494,546,560 rsi_divergence as primary signal; hunter_mode.py:117 Signal 5 (DEAD)

## Critical Findings (Section 5)

- **5.A** Six calculate_rsi implementations (MEDIUM)
- **5.B** Signal 5 misaligned (LOW — dead)
- **5.C** rsi_divergence used as primary signal in engines.py (MEDIUM)
- **5.D** engines.py RSI thresholds predate doctrine (MEDIUM)
- **5.E** PSEF Gate 4 philosophically clean (WIN)
- **5.F** rsi_memory.py doctrinal twin in code (WIN)
- **5.G** Peak RSI infrastructure aligned (WIN)
- **5.H** chart_intelligence.py tiers match doctrine (WIN)
- **5.I** Three "Phase 1 + Phase 2" implementations converge (WIN)

---

# SECTION 6 — ENGINE LAYER <a name="section-6"></a>

## ENGINE_PARAMS (STRICT_MODE=false confirmed in .env)

| Engine | retracement_min | retracement_max | impulse_min | invalidation_fib | grade_threshold | whale_required |
|---|---|---|---|---|---|---|
| 382 | 30 | 40 | 30 | 0.50 | 70 | False |
| 50 | 40 | 55 | 50 | 0.618 | 70 | False |
| 618 | 50 | 65 | 60 | 0.786 | 70 | False |
| 786 | 70 | 80 | 100 | 0.786 | 75 | False |
| underfib | 55 | 85 | 60 | 0.90 | 70 | False |

## run_detection 16-step orchestration

```
1. analyze_structure(candles)
2. Add gate flags from token to structure
3. check_whale_activity → has_whale
4. determine_setup_by_body_acceptance → body_routing
5. Reorder engine_order with recommended_setup first
6. For each engine_id:
   a. Check cooldown (BUGGED: hardcoded 4h, token-only scope)
   b. CHECK 1: Retracement range OR body override (confidence ≥50)
   c. CHECK 2: Impulse minimum
   d. CHECK 3: Invalidation price below key fib
   e. CHECK 4: Whale required (mostly DEAD)
   f. CHECK 5: Under-fib special pass
   g. Call setup validator
   h. Flashcard analysis + grade boost
   i. Grade threshold check
   j. Build engine_result dict
7. Return max(results, key='score')
8. set_engine_cooldown
```

## The cooldown bug

```python
def get_cooldown_key(token_address, engine_id):
    return f"{token_address}:STRUCTURE"  # engine_id IGNORED

def is_engine_on_cooldown(token_address, engine_id):
    cooldown_hours = 4  # HARDCODED — ignores ENGINE_PARAMS.cooldown_hours
```

**Intent:** allow setup evolution.
**Implementation:** blocks ALL engines for 4h once ANY one fires.

## ENGINE OVERRIDE mechanism

```python
if engine_result['grade'] in ['A+', 'A'] AND bangers['grade'] not in ['A+', 'A']:
    bangers['grade'] = engine_grade
    bangers['score'] = max(engine_score, bangers['score'])
    if engine_grade == 'A+': new_score = max(new_score, 95)
    elif engine_grade == 'A': new_score = max(new_score, 85)
    bangers['engine_override'] = True
```

## Score → Grade mismatch between pipelines

| Grade | engines.py | bangers |
|---|---|---|
| A+ | 85 | 95 |
| A | 75 | 85 |
| B | 65 | 65 |

A 76-point score = A in engines = B+ in bangers. Drives override frequency.

## Critical Findings (Section 6)

- **6.A** THREE pipelines, not two (HIGH — architectural correction)
- **6.B** engines.py vs bangers grade thresholds differ (HIGH)
- **6.C** ENGINE OVERRIDE is healthy reconciliation (WIN)
- **6.D** Cooldown_hours config is dead code (MEDIUM)
- **6.E** Cooldown blocks setup evolution (HIGH — CONFIRMED BUG)
- **6.F** 786 violent mode RSI<35 override is DEAD code (LOW)
- **6.G** STRICT_MODE=false confirmed (audit confirmation)
- **6.H** 13+ sequential quality checks before alert
- **6.I** Three different impulse_min definitions (MEDIUM)
- **6.J** Override score floor inflates scores to 85/95 (LOW)

---

# SECTION 7 — VISUAL INTELLIGENCE LAYER <a name="section-7"></a>

## THE CRITICAL FINDING: Three structure sources

**bangers_pipeline.py:18:** `from structure_engine import analyze_structure`

| Pipeline | Structure Source | Swing Algorithm |
|---|---|---|
| engines | engines.analyze_structure | max/min (naïve) |
| bangers | structure_engine.analyze_structure | fractal (lookback=3) |
| impulse_detector | internal | wick-cluster |

**They see different swing highs/lows on the same chart.**
**They disagree on REALITY before they disagree on PHILOSOPHY.**

This is the architectural root of ENGINE OVERRIDE frequency.

## BANGERS pipeline composition

```
run_bangers_analysis():
  STEP 1: structure_engine.analyze_structure → trend, swings (FRACTAL), BOS, structure_grade
  STEP 2: rsi_memory.analyze_rsi_full → RSI_MEMORY_INTACT, BREAKOUT_PRESSURE, RUNNER_MODE
  STEP 3: candle_intelligence.analyze_candles → tagged candles, character summary
  STEP 4: flashcard pattern matching
  STEP 5: setup_grader.grade_setup → final BANGERS grade + score + should_alert
```

## Matcher architecture (setup_matcher_adapter.py)

**Current status:** SHADOW MODE for normal operation, ACTIVE GATE via Vision Fallback Option C when Vision unavailable.

## Vision integration

- DAILY_VISION_CAP = 250
- VISION_MIN_GRADE = 'B' (gates Vision calls)
- VISION_WEIGHT = 0.20 (advisory)
- VISION_COOLDOWN_MINUTES = 45
- Graceful $0 degradation working

## Critical Findings (Section 7)

- **7.A** THREE different structure sources (HIGH — the root cause)
- **7.B** structure_engine.py NOT dead (corrects Section 2.B)
- **7.C** Matcher more live than "shadow" suggests (MEDIUM)
- **7.D** Flashcard grade boost can change alert outcomes (MEDIUM)
- **7.E** Philosophical inversion: newer overridden by older (HIGH)
- **7.F** Vision properly positioned (WIN)
- **7.G** setup_grader.py is BANGERS final grader
- **7.H** candle_intelligence.py LIVE via bangers (correction)
- **7.I** Three alert types exist (covered in Section 8 — actually 4)

---

# SETUP GRADER DEEP-DIVE <a name="setup-grader"></a>

## File: /opt/jayce/setup_grader.py (350 lines)

**Used by:** bangers_pipeline.py:21

## Weighting (docstring vs actual)

| Component | Docstring | Actual Code | Match? |
|---|---|---|---|
| PSEF | 20 | 20 | ✓ |
| Structure | 30 | 30 | ✓ |
| RSI Memory | 15 | **8** | ✗ (half) |
| RSI Expansion | 10 | **5** | ✗ (half) |
| Candle Quality | 15 | 15 | ✓ |
| Flashcard | 10 | 10 | ✓ |
| **Total max** | **100** | **88** | drift |

## Actual weight percentages (of 88 max)

- PSEF: 22.7%
- Structure: 34.1% ← PRIMARY
- RSI Memory: 9.1% (intended 15%)
- RSI Expansion: 5.7% (intended 10%)
- Candle Quality: 17.0%
- Flashcard: 11.4%

## RSI doctrine alignment (cleanest in codebase)

setup_grader.score_rsi uses ONLY:
- `RSI_MEMORY_INTACT`
- `memory_grade`
- `RSI_RUNNER_MODE`
- `RSI_BREAKOUT_PRESSURE`

**ZERO usage of:** divergence, hard thresholds, reversal logic, overbought/oversold.

## BANGERS alert condition (triple gate)

```python
should_alert = (grade in ['A+','A'] AND score >= 85 AND psef_passed)
```

**BANGERS is STRUCTURALLY STRICTER than engines.**

## Critical Findings (Deep-Dive)

- **SG.A** Weights don't match docstring (RSI underweighted) (MEDIUM)
- **SG.B** `rejection_count` is dead variable (LOW)
- **SG.C** BANGERS is stricter than engines (triple gate) (HIGH)
- **SG.D** Two flashcard scoring systems run in parallel (MEDIUM)
- **SG.E** BANGERS RSI is cleanest doctrinal implementation (WIN)
- **SG.F** Structure is BANGERS' dominant signal (34%)
- **SG.G** PSEF reinforces RSI doctrine doubly (WIN)
- **SG.H** should_realert exists but live status unclear (resolved Section 8.B — DEAD)
- **SG.I** Grade thresholds differ from engines (HIGH)

---

# SETUP GRADER CONSUMER TRACE <a name="consumer-trace"></a>

## The Question

Is setup_grader.py central authority or partially sidelined?

## Import Map

- `bangers_pipeline.py:21` — imports grade_setup, quick_grade_summary
- `scanner.py:89` — imports grade_setup, quick_grade_summary, should_realer **[TYPO]**

**Only ONE file calls grade_setup():** `bangers_pipeline.py:119`

## The Definitive Answer

**Setup_grader produces the FIRST opinion, but scanner.py overrides its should_alert decision multiple times downstream.**

setup_grader.py is:
- ✅ Central as the scoring brain (grade, score, breakdown)
- ✅ Central as the RSI doctrine implementation
- ✅ Central as the structure-weighting authority
- ❌ Bypassed for the actual firing decision
- ❌ PSEF gate dropped by scanner
- ❌ Score threshold relaxed by scanner (85 → 80)

**BANGERS the PIPELINE is central. BANGERS the ALERT DECISION AUTHORITY is partially sidelined.**

## Critical Findings (Consumer Trace)

- **CT.A** setup_grader's should_alert overwritten 4+ times in scanner (HIGH)
- **CT.B** PSEF hard gate silently dropped by scanner (HIGH — direct doctrine violation)
- **CT.C** Score threshold lowered from 85 to 80 by scanner (HIGH)
- **CT.D** should_realert import has typo → DEAD (LOW, but bug)
- **CT.E** BANGERS-as-data-structure central, BANGERS-as-decision-logic sidelined (HIGH)
- **CT.F** Vision Fallback Option C can veto positive bangers decision (architectural)

---

# SECTION 8 — ALERT LAYER (THE PARLIAMENT) <a name="section-8"></a>

## THREE+ ALERT PATHS (actually 4 — VALID was missed initially)

### Path 1: WIZTHEORY (BANGERS path)
- Source: bangers_result['should_alert'] (after 5+ mutations)
- Sender: TELEGRAM_CHAT_ID (main channel)
- Dedup: f"WIZTHEORY_{setup_type}", 2hr cooldown
- Extra: Ticker collision check, inline DexScreener button

### Path 2: CONFIRMED (combined_score ≥ 70)
- Uses engine_result + combined_score
- Routes via send_alert() to TELEGRAM_CHAT_ID
- Dedup: f"CONFIRMED_{setup_name}"

### Path 3: VALID (combined_score ≥ 55) — was initially missed
- Uses engine_result + combined_score
- Routes via send_alert() to TELEGRAM_CHAT_ID
- Dedup: 9-hour cooldown (DEDUP_VALID_HOURS)
- Emoji: 🟡

### Path 4: FORMING (combined_score ≥ 40)
- Uses engine_result + combined_score
- Routes to FORMING_CHAT_ID (= HEARTBEAT_CHAT_ID by design)
- Dedup: f"FORMING_{setup_name}"

**ALL of CONFIRMED/VALID/FORMING bypass BANGERS entirely.**

## The 7-Stage should_alert Lifecycle (WIZTHEORY path)

```
Stage 0 — setup_grader.grade_setup() initial
   Formula: grade in ['A+','A'] AND score >= 85 AND psef_passed
   ↓
Stage 1 — scanner.py:3158-3159 (Intel Bonus recalc)
   Formula: grade in ['A','A+'] AND new_score >= 80
   PSEF: DROPPED, Threshold: 80
   ↓
Stage 2 — scanner.py:3182 (ENGINE OVERRIDE)
   Formula: new_score >= 80
   PSEF: DROPPED, Threshold: 80
   ↓
Stage 3 — scanner.py:3287 (Post-override Impulse Bonus)
   ↓
Stage 4 — scanner.py:3389-3390 (Post-Vision)
   ↓
Stage 5 — scanner.py:3424 (Vision Fallback CAUTION) — does NOT modify
   ↓
Stage 6 — scanner.py:3432 (Vision Fallback REJECT) — HARD VETO
   ↓
Stage 7 — scanner.py:3462 (Final gate)
```

## Vision Fallback Three-Tier Triage

| Tier | Condition | should_alert |
|---|---|---|
| ALLOWED | Quality A/B + Confidence HIGH | unchanged |
| CAUTION | Quality C + Confidence MED/HIGH | unchanged (fires with flag) |
| REJECT | Anything else OR no matcher | **set to False** |

## The Three Grading Scales

| Grade | engines.py | scanner.py mutations | setup_grader.py |
|---|---|---|---|
| A+ | ≥ 85 | ≥ 95 | ≥ 95 |
| A | ≥ 75 | ≥ 80 | ≥ 85 |
| B+ | (none) | ≥ 75 | ≥ 75 |
| B | ≥ 65 | ≥ 65 | ≥ 65 |
| C | ≥ 55 | (none) | ≥ 50 |
| D | < 55 | < 65 | < 50 |

## should_realert — DEFINITIVELY DEAD

```python
# scanner.py:89
from setup_grader import grade_setup, quick_grade_summary, should_realer  # TYPO
```

Missing final `t`. Import fails silently (in try/except). Dead.

## Three Independent Cooldown Systems

| System | Storage | Scope | Duration | Status |
|---|---|---|---|---|
| engines.ENGINE_COOLDOWNS | In-memory | Token-level (engine_id ignored) | 4h hardcoded | BROKEN |
| alert_tracker | jayce_memory.db | {address}:{alert_type} | 120 min | WORKING |
| VISION_COOLDOWN_CACHE | In-memory | Per-token, with override conditions | 45 min | WORKING |

## Critical Findings (Section 8)

- **8.A** Three independent alert paths bypass each other (HIGH) — actually 4
- **8.B** should_realert dead due to typo (HIGH)
- **8.C** Three grading scales emergent (HIGH)
- **8.D** should_alert mutated 7 times (HIGH)
- **8.E** Three independent cooldown systems (MEDIUM)
- **8.F** FORMING/CONFIRMED/VALID bypass BANGERS doctrine (HIGH)
- **8.G** Vision Fallback Option C three-tier triage (WIN)
- **8.H** Alert rejection logging (WIN)
- **8.I** Ticker collision check is WIZTHEORY-only (LOW)
- **8.J** combined_score is 4th scoring system (MEDIUM)
- **8.K** FORMING_CHAT_ID = HEARTBEAT_CHAT_ID by design (LOW)

---

# SECTION 9 — LOGGING / MONITORING / SAFETY <a name="section-9"></a>

## combined_score formula (RESOLVED)

```python
def calculate_setup_score(engine_score, vision_confidence, pattern_score):
    return (ENGINE_WEIGHT * engine_score) + (VISION_WEIGHT * vision_confidence) + (PATTERN_WEIGHT * pattern_score)
```

| Weight | Value |
|---|---|
| ENGINE_WEIGHT | 0.55 |
| VISION_WEIGHT | 0.20 |
| PATTERN_WEIGHT | 0.25 |

## Alert tier thresholds (RESOLVED)

```python
def get_alert_tier(score):
    if score >= 70: return ('CONFIRMED', '🟢', DEDUP_CONFIRMED_HOURS=24)
    elif score >= 55: return ('VALID', '🟡', DEDUP_VALID_HOURS=9)
    elif score >= 40: return ('FORMING', '🔵', DEDUP_FORMING_HOURS)
    return (None, None, None)
```

## Watchdog architecture

- **Script:** /opt/jayce/watchdog.sh
- **Cron:** `*/10 * * * *` (every 10 minutes)
- **Monitors:** jayce-scanner + jayce-scraper (15-min silence → restart)
- **NOT monitored:** jayce-bot + jayce-receiver

## Heartbeat

- Function: send_heartbeat(cycle_time)
- Interval: every HEARTBEAT_INTERVAL_MINUTES (default 10)
- Destination: HEARTBEAT_CHAT_ID (private channel)

## Six parallel tracking systems

| System | Storage | Purpose |
|---|---|---|
| DAILY_METRICS dict | In-memory | Current-day counters |
| daily_audit module | Disk | Persistent daily stats |
| vision_audit module | vision_audit.jsonl | Per-Vision-call audit |
| alert_tracker | jayce_memory.db | was_alert_sent + log_alert |
| ops_helpers | Disk | ops_log_* |
| jayce.db | SQLite | Main bot state |

## CRITICAL: Log files growing UNBOUNDED

```
scanner.log    560 MB
bot.log        124 MB
visibility.log 6.6 MB
volume_scraper 8.6 MB
vision_audit   601 KB
Total: ~700 MB
```

**No FileHandler. No RotatingFileHandler. No log rotation. Operational time bomb.**

## Silent except patterns (3 bare excepts)

- Line 975: `except:`
- Line 1471: `except:`
- Line 1563: `except: pass` (fully silent)

## Critical Findings (Section 9)

- **9.A** FORMING_CHAT_ID = HEARTBEAT_CHAT_ID by design (LOW)
- **9.B** Logs growing UNBOUNDED (HIGH)
- **9.C** Silent except patterns in scanner (MEDIUM)
- **9.D** Six parallel tracking systems (MEDIUM)
- **9.E** Four alert tiers exist, not three
- **9.F** combined_score formula resolved (informational)
- **9.G** Watchdog only covers 2 of 4 services (MEDIUM)
- **9.H** No log rotation = operational time bomb (HIGH)
- **9.I** Watchdog reactive not proactive (architectural)
- **9.J** Multiple observability gaps (HIGH)
- **9.K** Daily summary system clean (WIN)
- **9.L** Heartbeat system clean (WIN)
- **9.M** Vision audit JSONL active (WIN)

---

# SECTION 10 — ARCHITECTURE REVIEW (THE SYNTHESIS) <a name="section-10"></a>

## 10.1 The Target Architecture

The future Jayce is a multi-specialist WizTheory intelligence system:

```
                              DATA LAYER (unchanged, healthy)
        DexScreener → Playwright → queue.db → hybrid_intake
                              │
                              ▼
                       SHARED PRIMITIVES LAYER
                ┌──────────────────────────────────┐
                │  ONE structure source            │
                │  ONE fib anchoring system        │
                │  ONE RSI doctrine                │
                │  ONE grade scale                 │
                │  ONE alert decision rule         │
                └──────────────────────────────────┘
                              │
                              ▼
                   MULTI-SPECIALIST INTELLIGENCE
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
   engines              bangers                impulse_detector
   "validator-heavy     "doctrine/behavior     "pattern/signature
    structure           specialist"            specialist"
    specialist"
                              │
                              ▼
                   PLUS visual senior analysts:
              matcher (historical visual memory)
              Vision (optional high-level analyst)
                              │
                              ▼
                   UNIFIED DECISION LAYER
                              │
                              ▼
                   SIMPLIFIED ALERT LAYER
                              │
                              ▼
                   INSTRUMENTED OBSERVABILITY
```

## 10.2 KEEP / CONSOLIDATE / REMOVE / ADD

### ✅ KEEP — Doctrine-aligned, healthy

- 3-pipeline philosophy (specialists voting model)
- bangers_pipeline orchestration
- rsi_memory.py
- PSEF Gate 4 (2-phase RSI)
- chart_intelligence.py momentum tiers
- Peak RSI infrastructure
- Vision Fallback Option C
- ENGINE OVERRIDE concept (criteria need fixing, not the concept)
- Daily summary + heartbeat + structured log_error
- Vision audit JSONL
- Setup-type-keyed alert dedup
- Vision cooldown with overrides
- Watchdog for scanner+scraper
- Alert rejection logging
- Ticker collision check
- matcher as historical visual memory
- Vision as optional senior analyst

### 🔄 CONSOLIDATE — Multiple implementations, same purpose

- Structure detection: 5+ implementations → ONE shared (structure_engine fractal)
- calculate_rsi: 6 implementations → ONE shared
- Body-acceptance: 2 functions in 2 files → ONE
- Grade scales: 3 emergent → ONE documented
- Cache systems: 3 with mismatched TTLs → unified tier-based
- Tracking systems: 6 parallel → 1-2 authoritative
- Cooldown systems: keep 3 BUT fix engine cooldown semantics
- Alert paths: 4 (WIZTHEORY/CONFIRMED/VALID/FORMING) → documented criteria for each
- Scoring systems: keep BANGERS for high-conviction + combined_score for legacy operational
- Validator dataclasses: 5 copies → shared base
- Body acceptance threshold: pick one, apply everywhere

### ❌ REMOVE — Dead code + drift

- determine_setup_by_body_acceptance_OLD
- Hunter Mode Signal 5 (rsi_at_high)
- 786 violent mode RSI<35 override
- Triple-duplicate 786 gate block
- MIN_MARKET_CAP=0 dead checks
- ENGINE_PARAMS.cooldown_hours field
- `should_realer` typo at scanner.py:89
- `rejection_count` in candle scoring
- Bare except patterns (975, 1471, 1563)

### 📊 ADD — Observability (PREREQUISITE to Tier 2)

- logrotate config for /opt/jayce/logs/*.log
- ENGINE OVERRIDE rate counter
- Pipeline disagreement quantification
- Setup type distribution metric
- Grade distribution analytics
- Stale-breakout rejection counter
- Cooldown-blocked alerts counter
- Watchdog for jayce-bot + jayce-receiver
- Outcome tracking (long-term, Tier 3)

## 10.3 The Shared Primitives Strategy

### Primitive 1 — Structure Source
**Target:** ONE structure source used by every pipeline
**Recommendation:** Standardize on structure_engine.analyze_structure (fractal swings, lookback=3)

### Primitive 2 — RSI Doctrine
**Target:** rsi_memory becomes the standard
**Migration:** All calculate_rsi functions → thin wrappers around rsi_memory

### Primitive 3 — Fib Anchoring
**Target:** Single compute_fib_levels(structure) function, all pipelines call it

### Primitive 4 — Grade Scale
**Decision:** Defer until Tier 1 observability provides baseline data

### Primitive 5 — Alert Decision Rule
**Target:** ONE documented function, no 7-stage mutation chain

### Primitive 6 — Scoring Foundation
**Recommendation:** Keep dual-track explicitly:
- BANGERS for WIZTHEORY (doctrine-aligned, high conviction)
- combined_score for FORMING/VALID/CONFIRMED (legacy operational)

## 10.4 TIER 1 — Quick Wins (this week, no risk)

### Tier 1.A — Operational safety
1. logrotate config for /opt/jayce/logs/*.log
2. Watchdog coverage extension to jayce-bot + jayce-receiver

### Tier 1.B — Dead code removal
3. Fix/remove `should_realer` typo at scanner.py:89
4. Remove dead code blocks (5 specific items)
5. Hunter Mode Signal 5 removal
6. Replace bare excepts in scanner.py with logged versions

### Tier 1.C — Observability instrumentation (PREREQUISITE TO TIER 2)
7. ENGINE OVERRIDE rate counter
8. Stale-breakout rejection counter
9. Cooldown-blocked counter
10. Setup type distribution metrics
11. Grade distribution metrics

### Tier 1.D — Cooldown bug fix (HIGH IMPACT, low risk)
12. Fix get_cooldown_key to include engine_id (enables setup evolution)

### Tier 1.E — Documentation
13. Update setup_grader.py docstring to match actual WEIGHTS
14. Document the 4 alert tiers in scanner.py header
15. Document the 3 grading scales OR consolidate (Tier 2)

**Tier 1 timeline:** 1 week. **Risk:** Minimal.

## 10.5 TIER 2 — Architectural Consolidation (this month, moderate risk)

### Tier 2.A — Unify Structure Source
All pipelines use structure_engine.analyze_structure

### Tier 2.B — RSI Doctrine Standardization
rsi_memory becomes the only RSI source

### Tier 2.C — Restore PSEF as Hard Gate (or document relaxation)

### Tier 2.D — Single Decision Function
Replace 7-stage should_alert chain

### Tier 2.E — Grade Scale Consolidation
Use Tier 1 baseline data to inform decision

### Tier 2.F — Validator Dataclass Unification

### Tier 2.G — combined_score Decision
**Recommendation:** Keep dual-track explicitly

### Tier 2.H — Cache System Consolidation

**Tier 2 timeline:** 1 month. **Risk:** Moderate.

## 10.6 TIER 3 — Future Evolution (this quarter+, strategic)

### Tier 3.A — The Specialists Voting Model
Formalize 3-pipeline architecture as designed multi-perspective system

### Tier 3.B — Outcome Tracking → Calibration Loop
Build feedback loop from alert → trade outcome

### Tier 3.C — Vision-Centric Architecture
When credits restored, Vision becomes equal voter

### Tier 3.D — Doctrine Documentation Layer
Every architectural decision traceable to WizTheory doctrine

### Tier 3.E — Alert Topology Refinement
Document or simplify the 4-tier alert system

### Tier 3.F — Configuration Centralization
All thresholds, weights, gates in one config layer

## 10.7 The Doctrine Restoration Plan

| Doctrine Point | Status | Restoration |
|---|---|---|
| Setup evolution 382 → 50 → 618 → 786 | Blocked by cooldown bug | Tier 1.D |
| RSI as permission, not prediction | Partially honored | Tier 2.B |
| Structure first | Strongly honored, drift in scanner | Tier 2.C |
| Strict alert quality | scanner relaxed | Tier 2.E |
| Flip zone language | No violations found | Verify in Tier 1 docs |
| Multiple specialists voting | Currently accidentally fragmented | Tier 2.A + Tier 3.A |

## 10.8 The Observability-First Principle

**We cannot reliably measure whether Tier 2 or Tier 3 changes improve the system without baseline data.**

**Therefore:** Tier 1.C (observability) is BLOCKING for Tier 2 decisions.

Order matters:
1. Tier 1 (1 week): Operational safety + dead code + observability
2. Run 2-4 weeks with new observability collecting baseline
3. Tier 2 (1 month): Architectural consolidation with measurable impact
4. Tier 3 (ongoing): Strategic evolution informed by data

**Do not skip the baseline collection period.**

## 10.9 What We Would Rebuild

### KEEP from current Jayce
- 3-pipeline philosophy (after fixing shared primitives)
- BANGERS' grading composition
- rsi_memory.py's mode system
- Vision Fallback Option C three-tier triage
- Dedup/cooldown architecture conceptually
- Alert rejection logging
- Watchdog + heartbeat

### REDESIGN
- Single shared structure primitives layer
- One decision function (not 7-stage chain)
- One grade scale documented
- Clear separation: high-conviction vs early-signal alerts
- Built-in observability from day 1
- Built-in log rotation
- Configuration centralized

### REMOVE forever
- Naïve max/min swing detection
- rsi_divergence as primary signal
- PSEF silent drop
- 6 parallel tracking systems (keep 2)
- 3 grading scales (keep 1)
- Dead code everywhere
- Bare except patterns

### ADD
- Outcome tracking
- Setup evolution tracking
- Pipeline disagreement quantification
- Calibration loop based on outcomes
- Doctrine traceability

**The ideal Jayce is BANGERS' architectural philosophy applied universally with shared primitives. Engines and impulse_detector become specialists that contribute perspective on the same underlying chart reality. Scanner.py is a thin alert layer that respects setup_grader's strict logic OR explicitly relaxes it with documented reasoning.**

## 10.10 The Migration Path

**Week 1: Tier 1 Quick Wins**
- Day 1: logrotate + watchdog extension
- Day 2: Fix cooldown bug (biggest behavior change)
- Day 3: Add observability counters (critical prerequisite)
- Day 4-5: Dead code removal
- Day 6-7: Documentation pass + bare except fixes

**Weeks 2-3: Baseline Collection**
- Observability metrics collect baseline data
- No code changes
- Watch override rate, distributions, evolution rate

**Week 4: Tier 2 Decisions**
- Review baseline data
- Make informed decisions on grade scale, PSEF restoration, structure migration

**Weeks 5-8: Tier 2 Execution**
- Week 5: Shared structure primitives
- Week 6: RSI doctrine standardization
- Week 7: Decision function unification
- Week 8: Validator dataclass + cache consolidation

**Months 2-3: Stabilization + Monitoring**

**Quarter 2+: Tier 3 Strategic**
- Outcome tracking
- Specialists voting formalization
- Vision-centric architecture
- Configuration centralization

## 10.11 Risk Management

1. Backup before any change (commit to GitHub)
2. One change at a time
3. Verify before proceeding
4. Shadow mode where applicable
5. Observability first
6. Doctrine alignment review per change
7. No "while we're at it" expansions

## 10.12 The Architectural Truth

> **Jayce is structurally fragmented but operationally functional.** Multiple generations of doctrine-aligned and legacy code coexist through additive architecture. The newer BANGERS pipeline produces excellent grades but its strict alert decisions are silently overridden by scanner.py's looser parliament logic. Three pipelines disagree on chart reality because they use different structure sources. The visual intelligence layer (Vision/matcher/flashcards) is the healthiest part architecturally. The observability layer prevents data-driven calibration.
>
> **The fix isn't tearing down — it's introducing shared primitives that let the multi-specialist architecture work as designed.**

## 10.13 The Architectural Principle

> **Do NOT make Jayce simpler by making him weaker.**
> **Make Jayce simpler by giving every specialist the same underlying truth.**

---

# MASTER SEVERITY TABLE <a name="severity"></a>

## HIGH severity

| Finding | Section |
|---|---|
| Cooldown blocks setup evolution | 1.A + 6.E |
| 5+ parallel structure detection systems | 2.A |
| engines.analyze_structure naïve max/min | 2.F |
| Two breakout detectors different philosophies | 2.G |
| Filter chain duplicate primitives | 2.L |
| Two competing classifiers | 3.A |
| Two body-acceptance functions | 3.G |
| Stale-breakout cap kills continuation | 4.A |
| THREE pipelines | 6.A |
| engines vs bangers grade thresholds | 6.B + SG.I |
| THREE structure sources (root cause) | 7.A |
| Newer overridden by older | 7.E |
| BANGERS stricter than engines | SG.C |
| setup_grader should_alert overwritten 4x | CT.A |
| PSEF dropped silently by scanner | CT.B |
| Score threshold 85→80 | CT.C |
| BANGERS decision sidelined | CT.E |
| Three alert paths bypass each other (actually 4) | 8.A |
| should_realert dead due to typo | 8.B |
| Three grading scales emergent | 8.C |
| should_alert mutated 7 times | 8.D |
| FORMING/CONFIRMED/VALID bypass BANGERS | 8.F |
| Logs growing unbounded | 9.B + 9.H |
| Multiple observability gaps | 9.J |

## MEDIUM severity

| Finding | Section |
|---|---|
| Three cache systems mismatched TTLs | 2.C |
| queue.processed never set | 2.E |
| psef.find_swings 3rd swing detection | 2.J |
| Body acceptance override threshold (50) | 3.D |
| MIXED-DEPTH warning doesn't gate | 3.I |
| Signal 4 free 15 points | 4.B |
| Six calculate_rsi implementations | 5.A |
| rsi_divergence primary signal in engines | 5.C |
| engines RSI predates doctrine | 5.D |
| Cooldown_hours config dead code | 6.D |
| Three different impulse_min definitions | 6.I |
| Matcher more live than "shadow" | 7.C |
| Flashcard grade boost changes outcomes | 7.D |
| Weights don't match docstring | SG.A |
| Two flashcard scoring systems | SG.D |
| Vision Fallback can veto bangers | CT.F |
| Three independent cooldown systems | 8.E |
| combined_score is 4th scoring system | 8.J |
| Silent except patterns in scanner | 9.C |
| Six parallel tracking systems | 9.D |
| Watchdog only covers 2 of 4 services | 9.G |

## LOW severity

| Finding | Section |
|---|---|
| run_detection 2 call sites (intentional) | 2.H |
| structural_prescan + hybrid_intake sequential | 2.K |
| structure_engine CORRECTED to LIVE | 2.B |
| determine_setup_by_body_acceptance_OLD dead | 3.B |
| Triple-duplicate 786 gate block | 1.B + 3.F |
| MIN_MARKET_CAP dead checks | 1.C |
| Age filter mismatch | 1.D |
| pseudo_overlap is proximity | 3.C |
| Hybrid gates vs engine ranges mismatch | 3.E |
| Signal 5 dead code | 4.C + 5.B |
| ValidationResult duplicated 5x | 4.D |
| validate_50_bounce signature difference | 4.E |
| Validator layer weights not uniform | 4.I |
| 786 violent mode RSI<35 DEAD | 6.F |
| Override score floor inflates scores | 6.J |
| `rejection_count` dead variable | SG.B |
| Ticker collision WIZTHEORY-only | 8.I |
| FORMING_CHAT_ID = HEARTBEAT_CHAT_ID | 8.K + 9.A |

## WINS (preserve in cleanup)

| Finding | Section |
|---|---|
| PSEF Gate 4 philosophically clean | 5.E |
| rsi_memory.py mirrors doctrine | 5.F |
| Peak RSI infrastructure aligned | 5.G |
| chart_intelligence.py tiers match doctrine | 5.H |
| Three "Phase 1 + Phase 2" convergence | 5.I |
| ENGINE OVERRIDE healthy reconciliation | 6.C |
| Vision properly positioned | 7.F |
| BANGERS RSI cleanest doctrinal | SG.E |
| PSEF doubly reinforces RSI doctrine | SG.G |
| Vision Fallback Option C triage | 8.G |
| Alert rejection logging | 8.H |
| Daily summary system clean | 9.K |
| Heartbeat system clean | 9.L |
| Vision audit JSONL active | 9.M |
| Watchdog detects frozen services | 9.3 |
| Structured log_error counters | 9.10 |

---

# DOCTRINE LOCKS <a name="doctrine"></a>

User philosophy preserved through audit:

- Setup evolution 382 → 50 → 618 → 786 must be allowed (cooldown bug must be fixed)
- RSI = permission/momentum-memory, NEVER prediction/reversal/divergence-predictor
- Under-Fib labels: "Under-618 Flip Zone" / "Under-786 Flip Zone"
- Flip zone = "flip zone" never "neckline"
- Future architecture = shared primitives under multiple analytical perspectives (NOT delete pipelines)
- BANGERS appears to be the doctrine-aligned core; consolidation likely means engines adopting bangers' primitives
- Vision/matcher/flashcard architecture is healthy — graceful degradation, advisory not dominant
- 618/786 fib-break philosophy vs 382/50 Hunter-Mode-exhaustion philosophy is INTENTIONAL and correct

## The Architectural Principle (final)

> **Do NOT make Jayce simpler by making him weaker.**
> **Make Jayce simpler by giving every specialist the same underlying truth.**

---

# WHAT THE AUDIT ACCOMPLISHED

- Mapped every layer of the system code-grounded
- Identified 70+ findings across HIGH/MEDIUM/LOW/WIN severity
- Resolved the BANGERS-as-decision-authority question definitively
- Found the architectural root cause (three structure sources)
- Quantified the philosophical inversion (newer overridden by older)
- Identified operational time bombs (log rotation, silent failures)
- Discovered combined_score's role and formula
- Found the VALID alert tier (initially missed)
- Mapped the 7-stage should_alert lifecycle
- Documented the three grading scales
- Identified all dead code paths
- Established the doctrine reference points
- Built the Tier 1/2/3 execution blueprint

## What this audit enables

**Pre-audit state:** "I don't know why my bot does what it does sometimes."
**Post-audit state:** "I have a complete blueprint for evolving my bot toward doctrine alignment."

---

# THE PHASE TRANSITION

**This document marks the end of MAPPING MODE and the beginning of EXECUTION MODE.**

The audit is complete. The blueprint is preserved. Tier 1 begins when ready.

Going forward, this document is a **reference roadmap**, not a working document. Each Tier 1/2/3 item references its findings here. As items complete, mark them done. The audit becomes the constitution of Jayce's evolution.

---

*Audit completed: May 29, 2026*
*Final commit: After Section 10*
*Architectural principle: Do not make Jayce simpler by making him weaker. Make Jayce simpler by giving every specialist the same underlying truth.*
