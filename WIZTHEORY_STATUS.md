# WIZTHEORY HUNTER MODE - SYSTEM STATUS
## Last Updated: March 17, 2026

---

## SYSTEM ARCHITECTURE

### Services Running:
- jayce-scanner (main scanner loop)
- jayce-bot (Telegram alerts + training)
- jayce-scraper (volume data)
- jayce-receiver (extension queue)

### Key Files:
- /opt/jayce/scanner.py - Main scanner
- /opt/jayce/hybrid_intake.py - Stage 2-3 pipeline
- /opt/jayce/engines.py - Engine routing + validator calls
- /opt/jayce/flashcard_analysis.py - Pattern matching
- /opt/jayce/setup_validators/ - All 5 validators + hunter_mode.py

---

## HUNTER MODE ALERT TIMING

| Setup | Alert Trigger | NOT Waiting For |
|-------|--------------|-----------------|
| 382 | Exhaustion from expansion high | Price at 382 |
| 50 | Exhaustion from expansion high | Price at 50 |
| 618 | Broke 382 + FZ aligned at 618 | Price at 618 |
| 786 | Broke 50 + FZ aligned at 786 | Price at 786 |
| Under-Fib | Broke fib gate + fresh zone below | Zone touch |

---

## FLASHCARD STATUS
- Total: 252 flashcards (as of March 17, 2026)
- 382 + Flip Zone: 53
- 50 + Flip Zone: 52
- 618 + Flip Zone: 68
- 786 + Flip Zone: 37
- Under-Fib Flip Zone: 42

Training saves to: /opt/jayce/data/jayce_training_dataset.json

---

## VALIDATOR INTELLIGENCE LAYERS

### 382 + Flip Zone:
1. exhaustion (Hunter Mode trigger)
2. flip_zone
3. expansion (>= 30%)
4. pullback_depth
5. structure
6. volume
+ whale_conviction (bonus)

### 50 + Flip Zone:
1. exhaustion (Hunter Mode trigger)
2. impulse (>= 48%)
3. clean_impulse
4. pullback_started
5. controlled_pullback
6. flip_zone

### 618 + Flip Zone:
1. hunter_approach (broke 382 + FZ at 618)
2. expansion (>= 60%)
3. flip_zone
4. pullback_depth
5. structure
+ whale_conviction (bonus)

### 786 + Flip Zone:
1. hunter_approach (broke 50 + FZ at 786)
2. expansion (>= 100%)
3. flip_zone
4. pullback_depth
5. structure
+ whale_conviction (bonus)

### Under-Fib:
1. flip_zone (below fib)
2. zone_freshness
3. expansion (>= 60%)
4. pullback_depth (>= 40%)
5. alert_timing (broke fib gate)
6. structure

---

## VPS ACCESS
- IP: 104.236.105.118
- User: root
