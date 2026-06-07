# JAYCE EXECUTION LOG
## Implementation Record — Paired With Audit Constitution

**Audit reference:** `/opt/jayce/audit/AUDIT_FINAL_2026-05-29.md`
**Execution started:** _[date when first Tier 1 item begins]_
**Current phase:** _[Tier 1 / Baseline Collection / Tier 2 / Tier 3]_

---

# THE NORTH STAR

> **Do NOT make Jayce simpler by making him weaker.**
> **Make Jayce simpler by giving every specialist the same underlying truth.**

# THE GATING QUESTION

Before any threshold change, weight change, or architectural decision:

> **Has it been measured?**

If no → defer until baseline data exists.

# THE ARCHITECTURAL PRINCIPLE

> **Specialists should disagree on interpretation, not on reality.**

---

# EXECUTION DISCIPLINE RULES

1. **One change at a time.** Never bundle.
2. **Backup before any change** — commit to GitHub first.
3. **Verify before proceeding** — each item verified in production before next.
4. **Reference audit finding ID in every commit** — e.g., "fix: cooldown evolution bug (audit 1.A + 6.E)".
5. **Shadow mode where applicable** — run new logic alongside old for comparison.
6. **No "while we're at it" expansions.** Scope discipline.
7. **Two-week minimum baseline collection** after Tier 1 observability lands.
8. **Read-only audit constitution** — this log records changes; the audit stays sealed.

---

# TIER 1 — QUICK WINS

**Status:** ⬜ Not started

## Tier 1.A — Operational Safety

### ✅ 1. logrotate config for /opt/jayce/logs/*.log
- **Audit reference:** 9.B + 9.H
- **Risk:** Zero
- **Purpose:** Prevent disk fill (currently 700MB+ logs growing unbounded)
- **Implementation notes:** Standard logrotate pattern, 100MB max, 5 rotations, daily compression
- **Date completed:** 2026-05-30
- **Verification:** Forced rotation succeeded; scanner kept writing within seconds post-rotation; logrotate.timer active, next trigger Fri 2026-06-05 00:00 UTC
- **Commit hash:** bf864ef (rebased to cea9916)

### ✅ 2. Watchdog coverage extension to jayce-bot + jayce-receiver
- **Audit reference:** 9.G
- **Risk:** Zero
- **Purpose:** Cover the 2 services currently unmonitored (only scanner + scraper monitored)
- **Implementation notes:** Same systemd active check + log silence pattern as existing watchdog
- **Date completed:** 2026-05-30
- **Verification:** bash -n passed; manual run produced no false restarts; all 4 services confirmed active post-patch; cron schedule (*/10) preserved; backup preserved at watchdog.sh.bak.pre-1A2
- **Commit hash:** 9814e4c

## Tier 1.B — Dead Code Removal

### ✅ 3. Fix/remove `should_realer` typo at scanner.py:89
- **Audit reference:** 8.B
- **Risk:** Low (already dead)
- **Decision:** Remove entirely OR fix typo (audit recommends removal)
- **Date completed:** 2026-05-30
- **Verification:** ast.parse syntax check passed both files; zero remaining should_realert references in codebase; active imports (grade_setup, quick_grade_summary) still resolve; jayce-scanner remained active throughout; A+ alert fired during verification confirming system normal
- **Commit hash:** b8e8481
- **🚨 AUDIT CORRECTION:** Audit finding 8.B claimed the function was dead due to a typo ('should_realer' missing final 't') at scanner.py:89. At execution time, the typo was NOT present — the import was correctly spelled 'should_realert'. The function was still genuinely dead (defined, imported, never called), so the cleanup remained valid. This is the first instance of verify-before-execute discipline catching an inaccurate audit claim. The audit constitution remains sealed; corrections live here in the execution log.
### ✅ 4. Remove `determine_setup_by_body_acceptance_OLD`
- **Audit reference:** 3.B
- **Location:** engines.py:908
- **Risk:** Low (never called)
- **Date completed:** 2026-05-30
- **Verification:** ast.parse passed; zero _OLD or calculate_overlap references remain; live function (line 585) intact; import engines clean; jayce-scanner stayed active; 175 lines/7061 chars removed; audit finding 3.B confirmed accurate this time
- **Commit hash:** 02b82b2

### ✅ 5. Remove triple-duplicate 786 gate block
- **Audit reference:** 1.B + 3.F
- **Location:** hybrid_intake.py (lines 612, 632, 666)
- **Risk:** Low (keep one, remove two)
- **Date completed:** 2026-05-30
- **Verification:** ast.parse passed; 786 logic appears exactly once after removal (was 2, now 1); Block C default-pass logic preserved (CRITICAL); hybrid_intake imports cleanly; jayce-scanner stayed active; 19 lines/890 chars removed
- **Commit hash:** ec1484f
- **🚨 CRITICAL AUDIT CORRECTION:** Audit claimed THREE duplicates (lines 612, 632, 666). Verification revealed only TWO blocks are actual duplicates (Block A 611-628 and Block B 630-647, byte-identical). The 'third' block at line 656-657 is NOT a duplicate — it is required default-pass logic for non-786-territory tokens (matches the same pattern used for 382/50/618/underfib gates). Blindly following the audit and removing Block C would have caused a real production regression: the 786 gate would have rejected all non-786 setups instead of letting them pass through. This is the SECOND instance of verify-before-execute discipline catching an audit error — but the FIRST instance where the audit's error would have caused a real production bug. Item 3's audit correction was cosmetic (typo claim); this one was material (would have broken alerts).
### ✅ 6. Remove 786 violent mode RSI<35 override
- **Audit reference:** 6.F
- **Location:** engines.py:1370-1376
- **Risk:** Low (unreachable code path due to whale_required=False)
- **Date completed:** 2026-06-04
- **Verification:** ast.parse passed; unique signature impulse_pct>=150+rsi<35 fully removed; live RSI<35 scoring at line 486 preserved; live violent mode SCORING (rsi<30+volume_contracting) preserved; 618 whale-bypass branch preserved; outer whale_required guard preserved; import engines clean; jayce-scanner stayed active (1954 tokens scanned in cycle); 7 lines/327 chars removed
- **Commit hash:** 3e510b0 (rebased to 788d68a)
- **🔍 DEFERRED OBSERVATION:** Verification revealed the entire CHECK 4 whale_required guard block is currently unreachable for ALL engines (382, 50, 618, 786, underfib) because ENGINE_PARAMS has whale_required=False for every engine. Only the 786 branch was removed per audit 6.F scope. Broader cleanup deliberately deferred to avoid scope creep — whale_required architecture may be intentionally preserved for future re-enabling. Logged for separate consideration during Tier 2 architectural review.

### ✅ 7. Remove MIN_MARKET_CAP=0 dead checks
- **Audit reference:** 1.C
- **Locations:** scanner.py lines 1249, 1322, 1371, 1499
- **Risk:** Low
- **Date completed:** 2026-06-05
- **Verification:** ast.parse passed; 2 dead lines removed (line 1117 commented-out + line 1499 standalone no-op); 3 compound checks preserved at lines 1248/1321/1370 (LIVE liquidity filtering intact); MIN_MARKET_CAP=0 constant preserved at line 404; 5 liq < MIN_LIQUIDITY references intact; jayce-scanner stayed active (696 tokens scanned during cycle); 2 lines/132 chars removed
- **Commit hash:** 74d7f18
- **🚨 MATERIAL AUDIT CORRECTION:** Audit claimed 4 dead checks (lines 1249/1322/1371/1499). Verification revealed only HALF were dead — lines 1249/1322/1371 are COMPOUND checks containing live liq < MIN_LIQUIDITY filtering ($10K minimum). Blind removal would have deleted live liquidity filtering = real production regression. Third instance of verify-before-execute catching an audit error (Item 3: cosmetic; Item 5: material; Item 7: material). Pattern is now clear: audit is a strong roadmap but never gospel.
- **🔍 DEFERRED OBSERVATIONS (2):**
  - (1) MIN_MARKET_CAP=0 at scanner.py:404 OVERRIDES .env value of 100000. Config drift: scanner-disabled while dexscreener_fetcher.py, token_validator.py, quiet_movers.py still enforce MIN_MARKET_CAP=100000. Future decision needed.
  - (2) Market-cap filtering architecture currently disabled but preserved. apply_patches.py records this was deliberate ("DISABLED - valid setups at any market cap"). Future decision needed: re-enable filtering OR fully remove the architecture in a dedicated Tier 2/config cleanup decision.

### 🟡 8. Remove ENGINE_PARAMS.cooldown_hours field [DEFERRED]
- **Audit reference:** 6.D
- **Risk:** Low (hardcoded 4h in is_engine_on_cooldown ignores it anyway)
- **Decision date:** 2026-06-05
- **Status:** DEFERRED (not closed via code removal)
- **Audit accuracy:** Audit finding 6.D is technically ACCURATE — the cooldown_hours field is currently unused under the live hardcoded 4h implementation.
- **Reason for deferral:** Field is dormant config, not true dead code. Encodes doctrinally-aligned per-engine cooldown intent: 382=4h, 50=6h, 618=6h, 786=8h, underfib=6h. These values are not arbitrary — they represent WizTheory setup-specific cooldown philosophy.
- **Historical evidence (smoking gun):** /opt/jayce/backups/wiztheory_hunter_mode_20260317_100142/engines.py:121 shows the field was ONCE LIVE via cooldown_hours = ENGINE_PARAMS.get(engine_...). Field was orphaned when cooldown logic was later simplified to hardcoded 4h. Removing now destroys recoverable architectural intent.
- **Precedent:** Same logic as Item #7 preserving MIN_MARKET_CAP=0 constant for future configurability.
- **Verification queries run (read-only):** 8 diagnostics confirmed (1) field exists in all 5 engine configs, (2) zero external references in active codebase, (3) hardcoded 4h overrides all per-engine values, (4) historical backup proves prior live use.
- **Future decision belongs in Tier 1.D (Cooldown Evolution Fix):** When Tier 1.D executes, explicit decision required: (a) keep hardcoded 4h forever and let field remain dormant config, OR (b) restore per-engine durations by reading params[cooldown_hours] in is_engine_on_cooldown. Either choice is valid; the decision needs the full context of how the cooldown bug is being fixed.
- **Methodology insight:** Items #3-#7 verified dead code that was safely removable. Item #8 establishes the DORMANT CONFIG pattern — items where audit accuracy is technical but removal would destroy future value. New 🟡 DEFERRED status: "Audit finding verified, but execution intentionally postponed because the code still contains architectural value or future design intent."

### ✅ 9. Hunter Mode Signal 5 removal
- **Audit reference:** 4.C + 5.B
- **Location:** hunter_mode.py:117 (rsi_at_high check)
- **Risk:** Low (rsi_at_high never populated, dead)
- **Decision:** Remove entirely OR replace with breakout_peak_rsi check
- **Date completed:** 2026-06-07
- **Verification:** ast.parse passed; Signal 5 block (7 lines) + docstring type reference removed atomically; Signals 1, 2, 3, 4, 6 all preserved with original scoring (25/20/20/15/15); threshold exhaustion_score >= 55 unchanged; max addable score remains 95 (was 95 before — Signal 5 was unreachable); rsi_divergence + rsi_at_high zero references after removal; hunter_mode imports cleanly; jayce-scanner stayed active (live grail token analysis); 368 chars removed total
- **Commit hash:** 6830ce4 (rebased to 0d38303)
- **AUDIT MECHANISM CORRECTION:** Audit findings 4.C + 5.B were both correct in conclusion but slightly off on mechanism. Audit 5.B implied Signal 5 was dead due to unpopulated rsi_at_high variable. Verification revealed the actual mechanism: code uses structure.get("rsi_at_high", rsi) with FALLBACK to current rsi, making the condition mathematically impossible: "if rsi < 60 and rsi > 70" (no value can be both <60 AND >70). Net result identical (Signal 5 never fires) but mechanism distinction matters for understanding similar fallback patterns elsewhere in codebase.
- **Methodology insight:** Cleanest removal in Tier 1.B so far — TWO independent justifications converged: (1) currently dead via impossible condition, (2) doctrinally misaligned (treats RSI as prediction/divergence signal, violating WizTheory RSI=permission-not-prediction rule). Removing covered both technical death AND doctrinal correctness. Closes audit findings 4.C + 5.B.

### ✅ 10. Replace bare excepts in scanner.py
- **Audit reference:** 9.C
- **Locations:** Lines 975, 1471, 1563
- **Implementation:** Add logger.warning or logger.error to each
- **Risk:** Low (only adds observability)
- **Date completed:** 2026-06-07
- **Verification:** ast.parse passed; 0 bare excepts remaining (was 20); except Exception count grew by exactly 20; file size grew by exactly 200 chars (20 * 10 chars of " Exception"); total except count unchanged at 85 (modification not addition); scanner.py structure OK; jayce-scanner stayed active (2482 tokens scanned during patch); heartbeat sent successfully post-change
- **Commit hash:** 3dd4f67
- **🚨 MATERIAL AUDIT CORRECTION (LARGEST COUNT GAP YET):** Audit finding 9.C identified 3 bare excepts (lines 975, 1471, 1563). Verification revealed 20 bare excepts (3 -> 20 = 6.7x gap). All 20 categorized: Network/scraping (8), JSON parsing (2), Font loading (2), Optional bookkeeping (2), Datetime parsing (2), Fib/exhaustion math (2), Telegram (2). NONE inside signal-handling or shutdown paths. Path 2 (full coverage) chosen because splitting into audit-listed-3 vs missed-17 would have been artificial — all 20 are same finding class. Fourth audit correction recorded (1 cosmetic, 3 material).
- **TRANSITION POINT NOTE:** Item #10 represents the transition between pure cleanup (Tier 1.B Dead Code Removal) and defensive reliability improvements. Unlike previous Tier 1.B items which were pure dead-code removal, this change deliberately alters exception-handling semantics by allowing KeyboardInterrupt and SystemExit to propagate correctly instead of being swallowed. For a production service managed by systemd, this is the correct defensive behavior.
- **METHODOLOGY MILESTONE:** This commit completes Tier 1.B. The execution methodology established (Audit → Verify → Execute → Document) has now prevented 2 production regressions (Items #5 and #7), caught 4 audit corrections (Items #3, #5, #7, #10), recorded 3 deferred observations (#6, #7×2), and made 1 architectural deferral (#8). Audit accuracy taxonomy now mature: pure accurate, cosmetic correction, material correction, mechanism correction, dormant config, deferred observation.

## Tier 1.C — Observability Instrumentation (PREREQUISITE TO TIER 2)

### ⬜ 11. ENGINE OVERRIDE rate counter
- **Audit reference:** 9.J (gap), 6.C (mechanism)
- **Location:** scanner.py:3183 (after engine_override = True)
- **Implementation:** `DAILY_METRICS['engine_overrides'] += 1`
- **Purpose:** Quantify pipeline disagreement
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 12. Stale-breakout rejection counter
- **Audit reference:** 4.A + 9.J
- **Location:** breakout_validator.py:189 (the STALE rejection branch)
- **Implementation:** Increment counter in scanner.py via callback or shared state
- **Purpose:** Measure RICH-style continuation losses
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 13. Cooldown-blocked counter
- **Audit reference:** 1.A + 6.E
- **Location:** engines.py:1309 (when is_engine_on_cooldown returns True)
- **Purpose:** Measure setup evolution suppression
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 14. Setup type distribution metrics
- **Audit reference:** 9.J
- **Implementation:** DAILY_METRICS['fires_382'], ['fires_50'], ['fires_618'], ['fires_786'], ['fires_underfib']
- **Purpose:** Verify alert distribution matches expectation
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 15. Grade distribution metrics
- **Audit reference:** 9.J
- **Implementation:** DAILY_METRICS['alerts_A_plus'], ['alerts_A'], ['alerts_B_plus']
- **Purpose:** Track grade composition over time
- **Date completed:** _____
- **Commit hash:** _____

## Tier 1.D — Behavior-Changing Fix (Highest Impact in Tier 1)

### ⬜ 16. Cooldown evolution fix (USER-CONFIRMED CRITICAL BUG)
- **Audit reference:** 1.A + 6.E
- **Location:** engines.py:115-118 (get_cooldown_key)
- **Change:** `return f"{token_address}:{engine_id}"` (include engine_id, was ignored)
- **Risk:** Will increase alert volume (intended — enables setup evolution 382 → 50 → 618 → 786)
- **Doctrine alignment:** Restores WizTheory "one evolving structure" philosophy
- **Verification:** Watch logs for 382 token firing 618 later within 4h (was impossible before)
- **Date completed:** _____
- **Commit hash:** _____

## Tier 1.E — Documentation

### ⬜ 17. Update setup_grader.py docstring to match actual WEIGHTS
- **Audit reference:** SG.A
- **Decision needed:** Either update docstring to reflect RSI 8+5 OR update weights to docstring's 15+10
- **Audit recommendation:** Pick the intended truth, document it explicitly
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 18. Document the 4 alert tiers in scanner.py header
- **Audit reference:** 9.E (VALID tier was missed initially)
- **Implementation:** Header comment block listing WIZTHEORY/CONFIRMED/VALID/FORMING with thresholds
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 19. Document the 3 grading scales explicitly
- **Audit reference:** 8.C
- **Note:** Defer consolidation to Tier 2.E; documentation only here
- **Date completed:** _____
- **Commit hash:** _____

---

# BASELINE COLLECTION PHASE

**Status:** ⬜ Not started
**Trigger:** All Tier 1 items complete
**Minimum duration:** 2 weeks
**Recommended duration:** 4 weeks
**Purpose:** Collect data BEFORE making Tier 2 architectural decisions

## What to track during baseline

| Metric | Source | Why it matters |
|---|---|---|
| ENGINE OVERRIDE rate | counter #11 | Quantifies pipeline disagreement |
| Stale-breakout rejects/day | counter #12 | Measures continuation losses |
| Cooldown-blocked evolution events | counter #13 | Validates 1.D fix impact |
| Setup type distribution | counter #14 | Detects classifier bias |
| Grade distribution | counter #15 | Informs Tier 2.E grade scale decision |
| Total alerts/day | DAILY_METRICS | Volume baseline |
| Vision call frequency | DAILY_METRICS | Vision usage pattern |
| Matcher fallback frequency | DAILY_METRICS | How often Option C activates |

## Baseline review checklist

After 2-4 weeks, review data and answer:

- ⬜ Is ENGINE OVERRIDE rate higher/lower than expected?
- ⬜ Is setup type distribution balanced or skewed?
- ⬜ Is grade distribution healthy (mostly A/A+) or drifted?
- ⬜ Are stale-breakout rejects high (suggesting filter too strict)?
- ⬜ Is cooldown fix (1.D) producing setup evolution events?
- ⬜ Are there patterns suggesting structure-source disagreement?

**Then:** Use this data to inform Tier 2 decisions.

---

# TIER 2 — ARCHITECTURAL CONSOLIDATION

**Status:** ⬜ Locked until Tier 1 + baseline collection complete

⚠️ **Do not begin Tier 2 without baseline data.**

### ⬜ Tier 2.A — Unify Structure Source
- **Audit reference:** 2.A, 2.F, 7.A
- **Goal:** All pipelines use structure_engine.analyze_structure (fractal swings)
- **Baseline data needed:** ENGINE OVERRIDE rate (counter #11) to measure impact
- **Migration:** Shadow mode first, compare, then activate
- **Decision date:** _____

### ⬜ Tier 2.B — RSI Doctrine Standardization
- **Audit reference:** 5.A, 5.C, 5.D
- **Goal:** rsi_memory becomes the only RSI source
- **Baseline data needed:** Grade distribution to measure scoring impact
- **Decision date:** _____

### ⬜ Tier 2.C — Restore PSEF as Hard Gate (or document relaxation)
- **Audit reference:** CT.B
- **Decision:** Restore OR document the relaxation explicitly
- **Baseline data needed:** What % of alerts have PSEF passed in current state?
- **Decision date:** _____

### ⬜ Tier 2.D — Single Decision Function
- **Audit reference:** 8.D
- **Goal:** Replace 7-stage should_alert mutation chain with one function
- **Decision date:** _____

### ⬜ Tier 2.E — Grade Scale Consolidation
- **Audit reference:** 6.B, 8.C, SG.I
- **Decision:** Pick ONE grade scale (setup_grader / engines / scanner / new)
- **Baseline data needed:** Grade distribution at current scales
- **Decision date:** _____

### ⬜ Tier 2.F — Validator Dataclass Unification
- **Audit reference:** 4.D
- **Risk:** None (refactor only)
- **Decision date:** _____

### ⬜ Tier 2.G — combined_score Decision
- **Audit reference:** 8.J
- **Audit recommendation:** Keep dual-track explicitly (BANGERS for high-conviction, combined_score for legacy operational)
- **Decision date:** _____

### ⬜ Tier 2.H — Cache System Consolidation
- **Audit reference:** 2.C
- **Goal:** One cache module, three tiers with explicit TTLs
- **Decision date:** _____

---

# TIER 3 — STRATEGIC EVOLUTION

**Status:** ⬜ Locked until Tier 2 stable

### ⬜ Tier 3.A — The Specialists Voting Model
- **Audit reference:** 7.A, 6.A
- **Goal:** Formalize 3-pipeline architecture with shared primitives + weighted voting
- **Decision date:** _____

### ⬜ Tier 3.B — Outcome Tracking → Calibration Loop
- **Audit reference:** 9.J
- **Goal:** Build feedback loop alert → trade outcome
- **Decision date:** _____

### ⬜ Tier 3.C — Vision-Centric Architecture (when credits restored)
- **Audit reference:** 7.F
- **Decision date:** _____

### ⬜ Tier 3.D — Doctrine Documentation Layer
- **Audit reference:** Doctrine locks
- **Decision date:** _____

### ⬜ Tier 3.E — Alert Topology Refinement
- **Audit reference:** 8.A
- **Decision date:** _____

### ⬜ Tier 3.F — Configuration Centralization
- **Audit reference:** Scattered constants finding
- **Decision date:** _____

---

# CHANGE LOG (chronological)

_Add entries as items complete. Most recent at top._

### YYYY-MM-DD — [Item name]
- **Audit finding:** _____
- **Tier:** _____
- **Commit:** _____
- **Verification:** _____
- **Observations:** _____

---

# DEFERRED DECISIONS

_Things that came up during execution that need future thought. Don't act on them — log them._

| Date | Decision needed | Why deferred | Trigger to revisit |
|---|---|---|---|
| | | | |

---

# DISCIPLINE REMINDERS

When considering any change, ask:

1. **Is this in the current tier?** (If not, log to "Deferred Decisions" and move on.)
2. **Has the impact been measured?** (If not, defer until baseline data exists.)
3. **Does this preserve specialists or weaken them?** (Per North Star principle.)
4. **Have I committed before starting?** (Backup discipline.)
5. **Am I changing one thing or bundling?** (One change at a time.)

When you find yourself wanting to make multiple changes at once, or skip baseline collection, or react to a single bad alert — **come back to this list.**

---

*Execution Log — Living document, updated as Tier 1/2/3 items complete.*
*Audit Constitution — Sealed reference at /opt/jayce/audit/AUDIT_FINAL_2026-05-29.md*
*North Star: Do NOT make Jayce simpler by making him weaker. Make Jayce simpler by giving every specialist the same underlying truth.*
