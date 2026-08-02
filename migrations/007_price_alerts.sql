CREATE TABLE IF NOT EXISTS price_alerts (
  id INTEGER PRIMARY KEY,
  creator_user_id TEXT NOT NULL,
  source_chat_id TEXT NOT NULL,
  destination_chat_id TEXT NOT NULL,
  contract_address TEXT NOT NULL,
  token_name TEXT NOT NULL,
  token_symbol TEXT NOT NULL,
  pair_address TEXT NOT NULL,
  price_source TEXT NOT NULL,
  current_price TEXT NOT NULL,
  target_price TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
  previous_checked_price TEXT,
  last_checked_price TEXT,
  created_at TEXT NOT NULL,
  last_successful_check_at TEXT,
  triggered_at TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'triggered', 'deleted', 'error')),
  error_status TEXT,
  trigger_message_id TEXT,
  created_command_text TEXT NOT NULL,
  source_update_id TEXT,
  UNIQUE(source_chat_id, source_update_id)
);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(status, destination_chat_id);
CREATE INDEX IF NOT EXISTS idx_price_alerts_contract ON price_alerts(contract_address, status);
CREATE INDEX IF NOT EXISTS idx_price_alerts_history ON price_alerts(created_at DESC, status);

CREATE TABLE IF NOT EXISTS price_alert_update_claims (
  id INTEGER PRIMARY KEY,
  source_chat_id TEXT NOT NULL,
  source_update_id TEXT NOT NULL,
  claimed_at TEXT NOT NULL,
  UNIQUE(source_chat_id, source_update_id)
);

CREATE TABLE IF NOT EXISTS price_alert_clear_confirmations (
  id INTEGER PRIMARY KEY,
  requester_user_id TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(requester_user_id, chat_id)
);
