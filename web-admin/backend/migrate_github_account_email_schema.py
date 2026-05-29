from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE asset_center.github_accounts
                ADD COLUMN IF NOT EXISTS email VARCHAR(255)
                """
            )
        )
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'asset_center'
                      AND table_name = 'github_accounts'
                    """
                )
            )
        }
        email_candidates = []
        for column_name in ("bind_email", "github_login", "email"):
            if column_name in columns:
                email_candidates.append(f"NULLIF({column_name}, '')")
        if email_candidates:
            conn.execute(
                text(
                    f"""
                    UPDATE asset_center.github_accounts
                    SET email = COALESCE({", ".join(email_candidates)})
                    WHERE email IS NULL OR email = ''
                    """
                )
            )
        for statement in (
            """
            UPDATE asset_center.github_accounts
            SET github_username = split_part(email, '@', 1)
            WHERE (github_username IS NULL OR github_username = '') AND email IS NOT NULL
            """,
            """
            UPDATE asset_center.github_accounts
            SET github_username = split_part(github_username, '@', 1)
            WHERE github_username LIKE '%@%'
            """,
            """
            ALTER TABLE asset_center.github_accounts
            ALTER COLUMN email SET NOT NULL
            """,
            """
            ALTER TABLE asset_center.github_accounts
            DROP CONSTRAINT IF EXISTS github_accounts_github_login_key
            """,
            """
            ALTER TABLE asset_center.github_accounts
            DROP CONSTRAINT IF EXISTS github_accounts_email_key
            """,
            """
            ALTER TABLE asset_center.github_accounts
            ADD CONSTRAINT github_accounts_email_key UNIQUE (email)
            """,
            """
            ALTER TABLE asset_center.github_accounts
            DROP COLUMN IF EXISTS bind_email
            """,
            """
            ALTER TABLE asset_center.github_accounts
            DROP COLUMN IF EXISTS github_login
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_github_accounts_email ON asset_center.github_accounts(email)
            """,
        ):
            conn.execute(text(statement))
    print("github account email schema migrated")


if __name__ == "__main__":
    main()
