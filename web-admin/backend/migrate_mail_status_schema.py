from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    statements = [
        """
        UPDATE asset_center.mail_accounts
        SET status = CASE
            WHEN status = 'registered' THEN 'registered'
            WHEN status = 'disabled' THEN 'disabled'
            ELSE 'idle'
        END
        WHERE status IS DISTINCT FROM CASE
            WHEN status = 'registered' THEN 'registered'
            WHEN status = 'disabled' THEN 'disabled'
            ELSE 'idle'
        END
        """,
        """
        ALTER TABLE asset_center.mail_accounts
        DROP CONSTRAINT IF EXISTS mail_accounts_status_check
        """,
        """
        ALTER TABLE asset_center.mail_accounts
        ADD CONSTRAINT mail_accounts_status_check
        CHECK (status IN ('idle', 'registered', 'disabled'))
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print("mail status schema migrated")


if __name__ == "__main__":
    main()
