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

### ✅ 8. ENGINE_PARAMS.cooldown_hours field [RESOLVED via Item #16]
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
- **🎯 RESOLUTION via Tier 1.D (Item #16, commit cdf8487, 2026-06-11):** The deferred decision is now made. Chose option (b): RESTORE per-engine durations. ENGINE_PARAMS.cooldown_hours is no longer dormant — it is the AUTHORITATIVE per-engine cooldown duration source. The is_engine_on_cooldown function now reads ENGINE_PARAMS.get(engine_id, {}).get("cooldown_hours", 4) instead of hardcoded cooldown_hours = 4. The doctrinally-aligned per-engine values (382=4h, 50=6h, 618=6h, 786=8h, underfib=6h) are now LIVE behavior.
- **CLOSURE TYPE — RESOLVED, NOT REMOVED:** Original Item #8 framing (audit 6.D) called for REMOVING the field as dead code. The deferred decision identified it as DORMANT CONFIG with future architectural value. Tier 1.D resolved it by REVIVING rather than REMOVING — the opposite of the original audit suggestion, but the better outcome. The field encoded doctrinally-correct per-engine cooldown intent; that intent is now executing in production.
- **VALIDATES THE DORMANT CONFIG PATTERN:** This is the proof that the 🟡 DEFERRED status (introduced for Item #8) was the correct methodology. Had we removed the field per the audit suggestion in Tier 1.B, we would have destroyed the architectural intent that Tier 1.D needed three audits and a decision memo to recreate. Dormant config deserves preservation when removal would destroy recoverable design intent.
- **AUDIT 6.D NOW DOUBLY CLOSED:** First by deferral preserving the field, second by Tier 1.D making the field authoritative. The methodology that prevented premature removal is the same methodology that enabled correct resolution.
- **NO ADDITIONAL CODE CHANGE FOR THIS ITEM:** The code change happened in commit cdf8487 (Item #16). This entry is documentation-only closure noting that the deferred decision is now resolved.
- **STATUS LIFECYCLE:** ⬜ open → 🟡 deferred (2026-06-05) → ✅ resolved (2026-06-11 via Tier 1.D)

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

### ✅ 11. ENGINE OVERRIDE rate counter
- **Audit reference:** 9.J (gap), 6.C (mechanism)
- **Location:** scanner.py:3183 (after engine_override = True)
- **Implementation:** `DAILY_METRICS['engine_overrides'] += 1`
- **Purpose:** Quantify pipeline disagreement
- **Date completed:** 2026-06-07
- **Verification:** ast.parse passed (176 top-level statements); 4 atomic changes verified in correct positions (DAILY_METRICS init, reset_metrics dict branch, counter increment block, cycle log extension); ENGINE OVERRIDE decision logic untouched (8 invariants checked); jayce-scanner restarted cleanly; CYCLE #1 post-restart completed without errors; cycle log now shows: 📊 Scanned: 40 | Engines: 0 | Vision: 0 | Flashcards: 0 | Alerts: 0 | Overrides: 0; no tracebacks during validation; file size growth +896 chars
- **Commit hash:** 4d0248f
- **CRITICAL PATCH DETAIL:** Reset logic in reset_metrics_if_new_day required an additional dict-handling branch ("elif isinstance(DAILY_METRICS[key], dict): DAILY_METRICS[key] = {}"). Without this, midnight reset would overwrite dict counters to 0 (integer) and crash on next increment with TypeError. This is now part of the Tier 1.C pattern for any future dict-based counters.
- **NEW METHODOLOGY NOTE (Tier 1.C):** Observability items require service restart to validate. Disk-level syntax verification is insufficient because counters only prove themselves when live code is loaded. Established pattern: AST validation → systemctl restart → wait for cycle log → verify new format → THEN commit. This adds ~30-60 seconds to each Tier 1.C item compared to Tier 1.B but provides operational confidence before commit.
- **TIER TRANSITION MARKED:** Item #11 is the first Tier 1.C item. Tier 1.B was pure cleanup (removing dead/duplicate code, defensive coding). Tier 1.C is additive instrumentation. Same execution discipline, different work texture: no removal, no behavior change, only measurement. Required to gather baseline data before Tier 1.D cooldown evolution fix.

### ✅ 12. Stale-breakout rejection counter
- **Audit reference:** 4.A + 9.J
- **Location:** breakout_validator.py:189 (the STALE rejection branch)
- **Implementation:** Increment counter in scanner.py via callback or shared state
- **Purpose:** Measure RICH-style continuation losses
- **Date completed:** 2026-06-07
- **Verification:** ast.parse passed (176 top-level statements unchanged); 3 atomic changes verified in correct positions (DAILY_METRICS init lines 509-510, cycle log line 722, increment block lines 2854-2873); breakout_validator.py UNTOUCHED (git status clean); jayce-scanner restarted cleanly; CYCLE #1 post-restart completed in 419.5s with 40 tokens, no errors from new code; cycle log live: "📊 Scanned: 40 | Engines: 1 | Vision: 0 | Flashcards: 0 | Alerts: 0 | Overrides: 1 | Stale: 5"; file size growth +1059 chars
- **Commit hash:** aed589b
- **ARCHITECTURE NOTE (Option A chosen):** Counter lives in scanner.py only. breakout_validator.py NOT modified. Validator already returns structured dict with reason field, scanner already consumes that reason. Detection via string-match "if Stale breakout in reason" on the existing flow — no cross-module coupling, no new imports, no callback hooks, no architectural debt. This pattern (consumer-side instrumentation when producer already returns structured data) is now established for any future Tier 1.C items where a counter spans modules.
- **FIRST PRODUCTION DATA POINT:** Cycle #1 post-restart captured 5 stale rejections out of 40 tokens scanned (12.5% stale-rejection rate). Live validation observed Bountywork rejected at 844 candles past ATH (bucket 501-1000). This rate confirms the audit prediction that stale-breakout rejection is a meaningful continuation killer — not an edge case. Bucket distribution data over next 2-4 weeks will inform Tier 2 architectural decisions about the 100-candle threshold calibration.
- **METHODOLOGY VALIDATION:** Same Tier 1.C pattern as Item #11: AST → restart → wait for cycle log → verify both counters live → commit. Counter design (total + per-dimension dict) reused. No new methodology needed; established Tier 1.C patterns held.

### ✅ 13. Cooldown-blocked counter
- **Audit reference:** 1.A + 6.E
- **Location:** engines.py:1309 (when is_engine_on_cooldown returns True)
- **Purpose:** Measure setup evolution suppression
- **Date completed:** 2026-06-08
- **Verification:** ast.parse passed both files (engines.py 30 top-level statements, scanner.py 176 unchanged); 9 atomic changes verified in correct positions; is_engine_on_cooldown function body identical to pre-patch (all 4 invariants confirmed: signature, get_cooldown_key call, hardcoded 4h, return logic); Vision cooldown system (System B) untouched at scanner.py:2675-2682; jayce-scanner restarted cleanly; ~4.5 hours of production data accumulated; cycle log live: "Scanned: 799 | ... | Overrides: 3 | Stale: 105 | EngCool: 330"; engines.py +1130 chars; scanner.py +1180 chars
- **Commit hash:** f4a80e9
- **ARCHITECTURE NOTE (Solution C chosen):** Module-local tracker in engines.py + accessor function exposed to scanner.py. NO DAILY_METRICS import in engines.py. Captures cooldown blocks even when run_detection() returns None (all engines blocked for token). This was the critical edge case — attaching counters to engine_result would have lost the most valuable signal. Pattern: engines.py owns its own state (_LAST_RUN_COOLDOWN_BLOCKS), exposes via get_last_run_cooldown_blocks() returning a copy, scanner.py consumes after each run_detection() call at both call sites.
- **TWO COOLDOWN SYSTEMS DOCUMENTED:** This item revealed scanner.py has TWO different "cooldown" systems running in parallel: (System A) Engine cooldown in engines.py:1158 — what this counter tracks, related to Tier 1.D. (System B) Vision API cooldown in scanner.py:2680 — preventing duplicate Vision API calls, tracked by existing misleadingly-named DAILY_METRICS["blocked_cooldown"] counter. Counter B was preserved as-is (rename out of scope) but documented for future Tier 2 cleanup.
- **FIRST PRODUCTION DATA (~4.5 hours runtime):** 799 tokens scanned, 330 EngCool blocks captured (~12 blocks per 100 tokens). This is the BASELINE for Tier 1.D. Current key is {token}:STRUCTURE, meaning one cooldown blocks ALL FIVE engines for a token. Tier 1.D will change key to {token}:{engine_id}, allowing per-engine cooldowns. Expected post-fix outcome: EngCool drops significantly because cooldowns become engine-specific instead of structure-wide. That delta IS the measurement of whether setup evolution (382→50→618→786) is being unlocked. This is exactly the architectural signal Tier 1.C exists to capture.
- **METHODOLOGY EXTENSION:** First Tier 1.C item touching two files atomically. New pattern established: when measurement spans modules, use producer-side module-local state + accessor function + consumer-side aggregation. Preserves module boundaries. Reusable for any future cross-module observability item.

### ✅ 14. Setup type distribution metrics
- **Audit reference:** 9.J
- **Implementation:** DAILY_METRICS['fires_382'], ['fires_50'], ['fires_618'], ['fires_786'], ['fires_underfib']
- **Purpose:** Verify alert distribution matches expectation
- **Date completed:** 2026-06-09
- **Verification:** ast.parse passed (176 top-level statements unchanged); 4 atomic changes verified in correct positions (DAILY_METRICS lines 528-529, Path 1 increment 3596-3600, Path 2 increment 3863-3867, daily summary blocks 709-725); existing engine_NNN detection counters preserved; ENGINE DETECTIONS section preserved; ALERTS SENT section preserved; ERRORS section preserved; cycle log width unchanged (deliberately); jayce-scanner restarted cleanly; cycle log post-restart confirmed loaded patched code; file size growth +1937 chars
- **Commit hash:** 42e8b9b (single commit; functionality + bullet normalization)
- **ARCHITECTURE NOTE (alert-time vs detection):** Existing engine_NNN counters (engine_382, engine_50, engine_618, engine_786, engine_underfib) track DETECTION at engines.py:1722-1747 and are preserved. Item #14 adds DIFFERENT counters tracking ALERT-FIRE distribution. These answer different questions: "what did engines find?" vs "what reached Telegram?". Both surfaces are valid; they capture different stages of the pipeline.
- **TWO ALERT-FIRE PATHS INSTRUMENTED:** Path 1 (main WizTheory alert) uses bangers_result["wiz_setup_type"] + bangers_result["grade"]. Path 2 (whale FORMING alert) uses engine_result["engine_id"] + engine_result["grade"]. Different field sources because the two paths consume different result dicts. Each path captures exactly what was IN its alert message.
- **ENGINE OVERRIDE NOTE:** When ENGINE OVERRIDE fires (Item #11 path), it modifies bangers_result["grade"] and ["score"] but NOT bangers_result["wiz_setup_type"]. So Path 1 records BANGERS classification at alert time. This was deliberate — we measure what was ACTUALLY in the alert message, not what some upstream engine thought. An override-disagreement counter (comparing wiz_setup_type to engine_result.engine_id) is a candidate future Tier 2 observability item.
- **METHODOLOGY EXTENSION:** First Tier 1.C item where heredoc-paste UTF-8 corruption was detected and corrected during validation (bullet chars became hyphens). Pattern established: use \u2022 Unicode escape rather than literal bullet chars in heredoc Python scripts to avoid future encoding issues on mobile/SSH terminals. The bullet correction was applied in the same execution session and merged into the same commit (42e8b9b) — cleaner than separate commits when the issue is heredoc artifact rather than separate concern.
- **PRODUCTION DATA:** Setup distribution counters won't accumulate visible values until an alert actually fires. Given current Vision-billing-limited operation (low alert rate), real data accumulation may take 1-7 days. Counters initialize at 0 and the alert-fire paths are wired to increment. Daily summary will show distribution once alerts begin firing.

### ✅ 15. Grade distribution metrics
- **Audit reference:** 9.J
- **Implementation:** DAILY_METRICS['alerts_A_plus'], ['alerts_A'], ['alerts_B_plus']
- **Purpose:** Track grade composition over time
- **Date completed:** 2026-06-11
- **Commit hash:** 42e8b9b (satisfied by Item #14 — no separate code change required)
- **CLOSURE TYPE — DOCUMENTATION ONLY:** This is the first Tier 1 item closed without code change. Item #14 (Tier 1.C.14) commit 42e8b9b already implemented alert-time grade distribution via DAILY_METRICS["setup_alerts_by_grade"]. Item #15 was originally pre-defined in EXECUTION_LOG with flat-key implementation (DAILY_METRICS["alerts_A_plus"], ["alerts_A"], ["alerts_B_plus"]), but Item #14 implemented a dict-based counter instead. Both designs satisfy the same audit intent (track alert-time grade distribution under audit reference 9.J). The dict-based pattern is strictly better.
- **WHY DICT-BASED PATTERN WAS CHOSEN OVER FLAT KEYS:** (1) future-proof — handles A+, A, B+, B, C, D, Unknown, or any new grade without code changes; (2) one DAILY_METRICS field instead of 4-5; (3) consistent with the Tier 1.C dict-counter pattern already established in Items #11 (engine_overrides_by_setup + by_grade), #12 (stale_breakout_by_candles_bucket), #13 (engine_cooldown_blocks_by_engine); (4) Unknown fallback prevents KeyError on unexpected grade strings; (5) daily summary rendering is functionally identical to flat-keys.
- **DATA SURFACE — ALREADY LIVE IN PRODUCTION:** Counter increments at 4 locations (2 per alert path × 2 paths). Path 1 (main WizTheory alert, scanner.py:3599-3600): bangers_result["grade"]. Path 2 (whale FORMING alert, scanner.py:3866-3867): engine_result["grade"]. Daily summary block at scanner.py:720-725 (<b>ALERTS BY GRADE</b> with A+/A/B+/B/Unknown rows).
- **NO DUPLICATE COUNTERS CREATED:** Per Tier 1.C discipline, adding alerts_A_plus/alerts_A/alerts_B_plus would duplicate every alert event's grade in two counter families. This was deliberately avoided. setup_alerts_by_grade is the single source of truth for alert-time grade distribution.
- **DEFERRED TO TIER 2 — GRADE PIPELINE DRIFT:** Detection-time grade distribution (grades as they come out of engines.py run_detection, BEFORE BANGERS scoring and ENGINE OVERRIDE) is NOT covered by any Tier 1.C counter. This would let Tier 2 measure how grades drift across pipeline stages (detection → override → alert). Deferred as a Tier 2 observability candidate after baseline data collection determines if the drift signal is actionable. Not part of Item #15 scope per audit framing.
- **AUDIT FINDING 9.J STATUS:** Closed by Items #11 + #12 + #13 + #14 + #15. Five distinct observability counters now live in production tracking different pipeline aspects (ENGINE OVERRIDE rate, stale breakout rejections, engine cooldown blocks, setup distribution at alert time, grade distribution at alert time). 9.J was the umbrella observability finding; all sub-aspects now closed.
- **TIER 1.C COMPLETE:** Items #11-#15 all closed. Observability layer fully built. Tier 1.D (cooldown evolution fix) is now UNBLOCKED — baseline EngCool counter (Item #13) ready to measure pre-fix vs post-fix behavior.

## Tier 1.D — Behavior-Changing Fix (Highest Impact in Tier 1)

### ✅ 16. Cooldown evolution fix (USER-CONFIRMED CRITICAL BUG)
- **Audit reference:** 1.A + 6.E
- **Location:** engines.py:115-118 (get_cooldown_key)
- **Change:** `return f"{token_address}:{engine_id}"` (include engine_id, was ignored)
- **Risk:** Will increase alert volume (intended — enables setup evolution 382 → 50 → 618 → 786)
- **Doctrine alignment:** Restores WizTheory "one evolving structure" philosophy
- **Verification:** Watch logs for 382 token firing 618 later within 4h (was impossible before)
- **Date completed:** 2026-06-11
- **Verification:** ast.parse passed (engines.py 30 top-level statements unchanged); 2 functions modified, 6 untouched; get_cooldown_key now returns f"{token_address}:{engine_id}"; is_engine_on_cooldown uses ENGINE_PARAMS.get(engine_id, {}).get("cooldown_hours", 4); all 10 invariants preserved including scanner.py untouched, set_engine_cooldown call site at engines.py:1609 untouched, ENGINE OVERRIDE logic untouched, Item #13 EngCool instrumentation untouched; jayce-scanner restarted cleanly at 07:56:15 UTC; first post-restart cycle log showed EngCool reset 240 → 0 confirming patched code loaded; no tracebacks; file size growth +534 chars
- **Commit hash:** cdf8487 (single commit closing Items #16 + #8)
- **ARCHITECTURE NOTE (Option B.2):** Per-engine cooldown key with per-engine duration. Closes both the key-format bug (audit 1.A) and the dormant config (audit 6.D, Item 1.B.8) in one atomic commit. Doctrinally aligned with WizTheory — each fib zone (382/50/618/786/underfib) is a distinct actionable opportunity, not a stage of one monolithic structure.
- **PRE-FIX BASELINE (LOCKED):** EngCool 240 over 29 cycles (~8.3 blocks per cycle). Theoretical model: ~80 blocks per engine trigger (5 engines × 16 rescans during 4h window). Engines triggered today: 4 total. Setup evolution: verified SUPPRESSED by code-grounded analysis + EngCool data + audit.
- **POST-FIX BEHAVIOR (HOUR 0):** EngCool: 0 (in-memory state reset on restart). Service active. Cycle log format unchanged. Patched code confirmed loaded via first cycle.
- **POST-FIX EXPECTATIONS (24h+):** EngCool should accumulate at ~5x slower rate per trigger because each cooldown blocks 1 engine instead of all 5. The smoking-gun proof of setup evolution: ANY single token appearing in setup_alerts_by_type (Item #14) for multiple engine_ids within 24h. Per-engine cooldown durations: 382=4h, 50=6h, 618=6h, 786=8h, underfib=6h.
- **VOLUME MITIGATION READY:** If alert volume becomes too high once Vision billing restored, ENGINE_PARAMS.cooldown_hours is now LIVE and tunable without code changes. grade_threshold also tunable per engine. No emergency rollback needed for volume management.
- **CODE-COMMENT CONTRADICTION RESOLVED:** Pre-fix comment claimed token-level cooldown allowed setup evolution. Runtime behavior was the opposite. Post-fix code and comments now align: per-engine cooldowns truly do allow setup evolution. The lie is now the truth.
- **AUDIT 1.A CLOSED:** Cooldown blocks setup evolution (HIGH CONFIRMED BUG) — fully resolved. Audit Section 1 has 4 findings total (1.A-1.D); 1.A was the most consequential.
- **AUDIT 6.D CLOSED:** cooldown_hours config dead code (MEDIUM) — now live and authoritative. Per-engine cooldown_hours from ENGINE_PARAMS dict.
- **AUDIT 6.E CLOSED:** Umbrella observability gap — completed via Items #11-15 (Tier 1.C) which built the measurement layer, plus Item #16 (Tier 1.D) which is the first measurement target.
- **METHODOLOGY MILESTONE:** First behavior-changing fix in Tier 1 executed cleanly using same verify-before-execute discipline. 9-diagnostic verification phase prevented premature patching based on EXECUTION_LOG framing alone — surfaced the code-comment contradiction and revealed cooldown-on-detection vs cooldown-on-alert architectural question. Tier 1.C counters (Items #11-15) gave us the EngCool baseline needed to measure the impact. This is the pattern Tier 2 architectural decisions should follow.

## Tier 1.E — Documentation

### ✅ 17. Update setup_grader.py docstring to match actual WEIGHTS
- **Audit reference:** SG.A
- **Decision needed:** Either update docstring to reflect RSI 8+5 OR update weights to docstring's 15+10
- **Audit recommendation:** Pick the intended truth, document it explicitly
- **Date completed:** 2026-06-11
- **Verification:** ast.parse passed (17 top-level statements unchanged); 4 documentation changes verified in correct positions; all 8 behavioral invariants confirmed preserved (WEIGHTS values, ALERT_MIN_GRADE, ALERT_MIN_SCORE); all 6 stale claims confirmed removed; file size growth +441 chars; no restart required (documentation-only)
- **Commit hash:** a26b3b2
- **VERIFICATION RESULT — Path A confirmed (pure documentation drift):** Git history shows setup_grader.py was created in commit 0da5dfc (April 2026 v2.0 rewrite) with rsi_memory=8 and rsi_expansion=5 from the start. No prior version with 15/10 exists in git. Backup setup_grader.py.bak.pre-1B3 also shows 8/5. The WEIGHTS values are the authoritative WizTheory truth — the docstring was design notes never synced after implementation.
- **THE FOUR-LAYER CONTRADICTION:** (1) Top docstring claimed RSI 15/10 totaling 100, (2) WEIGHTS dict had 8/5 totaling 88, (3) WEIGHTS inline comments lied about 15/10, (4) actual math didn't add to 100. All four corrected in one atomic patch.
- **FIXES APPLIED:** (1) Top docstring updated to 8/5/88 with calibration explanation, (2) WEIGHTS inline comments corrected to "8 points"/"5 points", (3) Section header comment expanded to clarify per-Wiz.sol calibration and max=88.
- **TIER 2 OBSERVATION CAPTURED — 97% THRESHOLD MATH:** The verification surfaced an architectural insight beyond documentation drift. ALERT_MIN_SCORE = 85 against max=88 means alerts require 85/88 = ~96.6% of available points. Examples: 80/88 (90.9%) rejected, 84/88 (95.5%) rejected, 85/88 (96.6%) accepted. This is intentionally strict per WizTheory "only the best entries" philosophy and likely contributes to Jayce's low alert frequency independent of Vision API constraints. NOT addressed in Tier 1.E (documentation cleanup only); captured for Tier 2 calibration review.
- **TIER 2 CANDIDATE OBSERVATION:** "Future calibration review — evaluate whether maintaining an 88-point scale with an 85-point threshold remains aligned with intended alert frequency, or whether either the weight totals or threshold should be normalized for interpretability."
- **METHODOLOGY NOTE — NO RESTART NEEDED:** First Tier 1.E item closed. Documentation changes don't affect runtime (docstring/comments are inert text). Tier 1.E items can land without service interruption — distinct from Tier 1.C (observability, required restart) and Tier 1.D (behavior change, required restart). This pattern can be applied to remaining Items #18 and #19.
- **METHODOLOGY VALIDATION:** Same verify-before-execute discipline as Items #5 and #7. Audit framed it as docstring drift; verification confirmed it was pure documentation without behavior implications. Git history + backup files + zero prior alternatives = high confidence the 8+5 calibration is intentional truth.

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
