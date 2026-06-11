PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS proxies (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  server TEXT NOT NULL,             -- "http://host:port" or "socks5://host:port"
  username TEXT,
  password TEXT,                    -- stored locally in plaintext (see README)
  geo_hint TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,        -- "desktop-fresh", "mobile-fresh", ...
  device TEXT NOT NULL DEFAULT 'desktop',      -- 'desktop' | 'mobile'
  persistence TEXT NOT NULL DEFAULT 'fresh',   -- 'fresh' | 'returning'
  auth TEXT NOT NULL DEFAULT 'anon',           -- 'anon' | 'logged_in'
  proxy_id INTEGER REFERENCES proxies(id),
  storage_state_path TEXT,
  user_data_dir TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  is_baseline INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  site TEXT NOT NULL,
  url TEXT NOT NULL,
  external_event_id TEXT,
  name TEXT,
  venue TEXT,
  event_date TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(site, url)
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id),
  trials INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
  started_at TEXT,
  finished_at TEXT,
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  profile_id INTEGER NOT NULL REFERENCES profiles(id),
  trial INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|ok|blocked|error
  extraction_method TEXT,                  -- 'api_intercept'|'embedded_json'|'dom'
  error TEXT,
  capture_dir TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id),
  external_listing_id TEXT,
  section TEXT,
  row TEXT,
  quantity INTEGER,
  match_key TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(event_id, match_key)
);

CREATE TABLE IF NOT EXISTS prices (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
  listing_id INTEGER NOT NULL REFERENCES listings(id),
  list_price REAL,
  fees REAL,
  all_in_price REAL,
  currency TEXT DEFAULT 'USD',
  listing_url TEXT,
  raw_json TEXT,
  UNIQUE(snapshot_id, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_prices_listing ON prices(listing_id);
CREATE INDEX IF NOT EXISTS idx_prices_snapshot ON prices(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run ON snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_listings_event ON listings(event_id);
