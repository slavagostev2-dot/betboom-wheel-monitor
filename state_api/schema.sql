PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL,
  username TEXT NOT NULL DEFAULT '',
  first_name TEXT NOT NULL DEFAULT '',
  last_name TEXT NOT NULL DEFAULT '',
  photo_url TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  blocked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS roles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'user'))
);

CREATE TABLE IF NOT EXISTS notification_preferences (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  preference_key TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, preference_key)
);

CREATE TABLE IF NOT EXISTS wheel_participation (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  wheel_key TEXT NOT NULL,
  joined_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, wheel_key)
);

CREATE TABLE IF NOT EXISTS hidden_wheels (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  wheel_key TEXT NOT NULL,
  hidden_at TEXT NOT NULL,
  expires_at TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, wheel_key)
);

CREATE TABLE IF NOT EXISTS user_settings (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  setting_key TEXT NOT NULL,
  setting_value TEXT NOT NULL,
  PRIMARY KEY (user_id, setting_key)
);

CREATE TABLE IF NOT EXISTS system_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_requests (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  requester_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  requester_chat_id TEXT NOT NULL,
  requester_name TEXT NOT NULL DEFAULT '',
  requester_username TEXT NOT NULL DEFAULT '',
  check_json TEXT NOT NULL DEFAULT '{}',
  destination TEXT NOT NULL DEFAULT '',
  decision_text TEXT NOT NULL DEFAULT '',
  decided_at TEXT,
  decided_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_roles_role ON roles(role);
CREATE INDEX IF NOT EXISTS idx_participation_user_active ON wheel_participation(user_id, active);
CREATE INDEX IF NOT EXISTS idx_hidden_user_active ON hidden_wheels(user_id, active);
CREATE INDEX IF NOT EXISTS idx_source_requests_status ON source_requests(status, created_at);
