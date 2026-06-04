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

### ⬜ 2. Watchdog coverage extension to jayce-bot + jayce-receiver
- **Audit reference:** 9.G
- **Risk:** Zero
- **Purpose:** Cover the 2 services currently unmonitored (only scanner + scraper monitored)
- **Implementation notes:** Same systemd active check + log silence pattern as existing watchdog
- **Date completed:** _____
- **Verification:** _____
- **Commit hash:** _____

## Tier 1.B — Dead Code Removal

### ⬜ 3. Fix/remove `should_realer` typo at scanner.py:89
- **Audit reference:** 8.B
- **Risk:** Low (already dead)
- **Decision:** Remove entirely OR fix typo (audit recommends removal)
- **Date completed:** _____
- **Verification:** _____
- **Commit hash:** _____

### ⬜ 4. Remove `determine_setup_by_body_acceptance_OLD`
- **Audit reference:** 3.B
- **Location:** engines.py:908
- **Risk:** Low (never called)
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 5. Remove triple-duplicate 786 gate block
- **Audit reference:** 1.B + 3.F
- **Location:** hybrid_intake.py (lines 612, 632, 666)
- **Risk:** Low (keep one, remove two)
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 6. Remove 786 violent mode RSI<35 override
- **Audit reference:** 6.F
- **Location:** engines.py:1370-1376
- **Risk:** Low (unreachable code path due to whale_required=False)
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 7. Remove MIN_MARKET_CAP=0 dead checks
- **Audit reference:** 1.C
- **Locations:** scanner.py lines 1249, 1322, 1371, 1499
- **Risk:** Low
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 8. Remove ENGINE_PARAMS.cooldown_hours field
- **Audit reference:** 6.D
- **Risk:** Low (hardcoded 4h in is_engine_on_cooldown ignores it anyway)
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 9. Hunter Mode Signal 5 removal
- **Audit reference:** 4.C + 5.B
- **Location:** hunter_mode.py:117 (rsi_at_high check)
- **Risk:** Low (rsi_at_high never populated, dead)
- **Decision:** Remove entirely OR replace with breakout_peak_rsi check
- **Date completed:** _____
- **Commit hash:** _____

### ⬜ 10. Replace bare excepts in scanner.py
- **Audit reference:** 9.C
- **Locations:** Lines 975, 1471, 1563
- **Implementation:** Add logger.warning or logger.error to each
- **Risk:** Low (only adds observability)
- **Date completed:** _____
- **Commit hash:** _____

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
