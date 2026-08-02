-- Delivery-safe trigger state.
--
-- The original flow marked an alert 'triggered' BEFORE publishing, so a
-- Telegram failure permanently consumed the alert and the notification was
-- lost. This column adds an intermediate claim so the flow becomes:
--
--   active (claim IS NULL)
--     -> claimed  (trigger_claimed_at set, status still 'active')
--        -> delivered (status='triggered', trigger_message_id recorded)
--        -> released  (claim cleared, retried next cycle)
--
-- The claim UPDATE is conditional on status='active' AND trigger_claimed_at IS
-- NULL, so it is atomic under SQLite's write lock: two workers cannot both
-- claim the same alert, and an undelivered alert is never lost.
ALTER TABLE price_alerts ADD COLUMN trigger_claimed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_price_alerts_claim
  ON price_alerts(status, trigger_claimed_at);
