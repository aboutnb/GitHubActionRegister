CREATE SCHEMA IF NOT EXISTS asset_center;

CREATE TABLE IF NOT EXISTS asset_center.web_users (
  id BIGSERIAL PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role VARCHAR(32) NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
  status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.desktop_clients (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(128) NOT NULL UNIQUE,
  token_hash TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  last_seen_at TIMESTAMPTZ,
  last_ip INET,
  remark TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.mail_accounts (
  id BIGSERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  status VARCHAR(32) NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'leased', 'registered', 'used', 'disabled')),
  lease_client_id BIGINT REFERENCES asset_center.desktop_clients(id),
  lease_token VARCHAR(128),
  lease_expires_at TIMESTAMPTZ,
  remark TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.mail_credentials (
  mail_account_id BIGINT PRIMARY KEY REFERENCES asset_center.mail_accounts(id) ON DELETE CASCADE,
  password_enc TEXT NOT NULL,
  receive_mode TEXT,
  client_id TEXT,
  access_token TEXT,
  raw_line TEXT,
  imap_config JSONB,
  smtp_config JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.sync_batches (
  id BIGSERIAL PRIMARY KEY,
  batch_no VARCHAR(64) NOT NULL UNIQUE,
  batch_type VARCHAR(32) NOT NULL CHECK (batch_type IN ('mail_import', 'github_push', 'github_export')),
  client_id BIGINT REFERENCES asset_center.desktop_clients(id),
  source VARCHAR(32) NOT NULL CHECK (source IN ('web', 'desktop')),
  total_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  created_by BIGINT REFERENCES asset_center.web_users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.github_accounts (
  id BIGSERIAL PRIMARY KEY,
  github_login VARCHAR(255) NOT NULL UNIQUE,
  github_username VARCHAR(255),
  bind_mail_account_id BIGINT REFERENCES asset_center.mail_accounts(id),
  bind_email VARCHAR(255),
  source_client_id BIGINT REFERENCES asset_center.desktop_clients(id),
  source_batch_id BIGINT REFERENCES asset_center.sync_batches(id),
  status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'sold', 'locked', 'unknown')),
  two_fa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  remark TEXT,
  last_exported_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.github_credentials (
  github_account_id BIGINT PRIMARY KEY REFERENCES asset_center.github_accounts(id) ON DELETE CASCADE,
  github_password_enc TEXT NOT NULL,
  totp_secret_enc TEXT NOT NULL,
  recovery_codes_enc TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.sync_logs (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT REFERENCES asset_center.desktop_clients(id),
  action VARCHAR(32) NOT NULL CHECK (action IN ('pull_mail', 'push_github', 'heartbeat')),
  request_id VARCHAR(64),
  payload_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_center.audit_logs (
  id BIGSERIAL PRIMARY KEY,
  operator_type VARCHAR(32) NOT NULL CHECK (operator_type IN ('web_user', 'desktop_client')),
  operator_id BIGINT NOT NULL,
  action VARCHAR(64) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id BIGINT,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mail_accounts_status ON asset_center.mail_accounts(status);
CREATE INDEX IF NOT EXISTS idx_mail_accounts_lease_expires_at ON asset_center.mail_accounts(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_github_accounts_status ON asset_center.github_accounts(status);
CREATE INDEX IF NOT EXISTS idx_github_accounts_bind_mail ON asset_center.github_accounts(bind_mail_account_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_client_created ON asset_center.sync_logs(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON asset_center.audit_logs(target_type, target_id, created_at DESC);
