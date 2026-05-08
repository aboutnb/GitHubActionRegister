from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    statements = [
        """
        ALTER TABLE asset_center.mail_credentials
        ADD COLUMN IF NOT EXISTS receive_mode TEXT,
        ADD COLUMN IF NOT EXISTS client_id TEXT,
        ADD COLUMN IF NOT EXISTS access_token TEXT,
        ADD COLUMN IF NOT EXISTS raw_line TEXT
        """,
        """
        UPDATE asset_center.mail_credentials
        SET
          receive_mode = COALESCE(receive_mode, extra_config->>'receive_mode'),
          client_id = COALESCE(client_id, extra_config->>'client_id', extra_config->>'platform_account_id'),
          access_token = COALESCE(access_token, extra_config->>'access_token'),
          raw_line = COALESCE(raw_line, extra_config->>'raw_line')
        WHERE extra_config IS NOT NULL
        """,
        """
        ALTER TABLE asset_center.mail_credentials
        DROP COLUMN IF EXISTS extra_config
        """,
        """
        ALTER TABLE asset_center.mail_accounts
        DROP COLUMN IF EXISTS provider
        """,
        """
        ALTER TABLE asset_center.mail_accounts
        DROP COLUMN IF EXISTS last_used_at
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print("mail schema migrated")


if __name__ == "__main__":
    main()
