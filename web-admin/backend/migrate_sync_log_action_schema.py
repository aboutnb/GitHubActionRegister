from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    statements = [
        """
        ALTER TABLE asset_center.sync_logs
        DROP CONSTRAINT IF EXISTS sync_logs_action_check
        """,
        """
        ALTER TABLE asset_center.sync_logs
        ADD CONSTRAINT sync_logs_action_check
        CHECK (action IN ('pull_mail', 'pull_github', 'push_github', 'push_mail', 'heartbeat'))
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print("sync log action schema migrated")


if __name__ == "__main__":
    main()
