from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    statements = [
        """
        ALTER TABLE asset_center.sync_batches
        DROP CONSTRAINT IF EXISTS sync_batches_batch_type_check
        """,
        """
        ALTER TABLE asset_center.sync_batches
        ADD CONSTRAINT sync_batches_batch_type_check
        CHECK (batch_type IN ('mail_import', 'mail_push', 'github_push', 'github_export', 'github_health_check'))
        """,
        """
        ALTER TABLE asset_center.sync_batches
        DROP CONSTRAINT IF EXISTS sync_batches_source_check
        """,
        """
        ALTER TABLE asset_center.sync_batches
        ADD CONSTRAINT sync_batches_source_check
        CHECK (source IN ('web', 'desktop', 'scheduler'))
        """,
        """
        ALTER TABLE asset_center.github_accounts
        ADD COLUMN IF NOT EXISTS health_status VARCHAR(32) NOT NULL DEFAULT 'unknown'
        """,
        """
        ALTER TABLE asset_center.github_accounts
        ADD COLUMN IF NOT EXISTS health_checked_at TIMESTAMPTZ
        """,
        """
        ALTER TABLE asset_center.github_accounts
        ADD COLUMN IF NOT EXISTS health_http_status INTEGER
        """,
        """
        ALTER TABLE asset_center.github_accounts
        ADD COLUMN IF NOT EXISTS health_error TEXT
        """,
        """
        ALTER TABLE asset_center.github_accounts
        DROP CONSTRAINT IF EXISTS github_accounts_health_status_check
        """,
        """
        ALTER TABLE asset_center.github_accounts
        ADD CONSTRAINT github_accounts_health_status_check
        CHECK (health_status IN ('unknown', 'alive', 'not_found', 'error'))
        """,
        """
        CREATE TABLE IF NOT EXISTS asset_center.github_health_check_configs (
          id BIGSERIAL PRIMARY KEY,
          enabled BOOLEAN NOT NULL DEFAULT FALSE,
          cron_expression VARCHAR(64) NOT NULL DEFAULT '0 0 1,15 * *',
          proxy_pool TEXT,
          accounts_per_proxy INTEGER NOT NULL DEFAULT 15,
          timeout_seconds INTEGER NOT NULL DEFAULT 10,
          last_run_at TIMESTAMPTZ,
          next_run_at TIMESTAMPTZ,
          last_batch_no VARCHAR(64),
          updated_by BIGINT REFERENCES asset_center.web_users(id),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        ALTER TABLE asset_center.github_health_check_configs
        ALTER COLUMN cron_expression SET DEFAULT '0 0 1,15 * *'
        """,
        """
        UPDATE asset_center.github_health_check_configs
        SET cron_expression = '0 0 1,15 * *',
            next_run_at = NULL
        WHERE cron_expression IN ('*/10 * * * *', '*/15 * * * *', '*/30 * * * *', '0 * * * *', '0 0 * * *', '0 8 * * *')
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_github_accounts_health_status ON asset_center.github_accounts(health_status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_github_accounts_health_checked_at ON asset_center.github_accounts(health_checked_at)
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print("github health schema migrated")


if __name__ == "__main__":
    main()
