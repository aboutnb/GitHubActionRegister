from pathlib import Path

from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    schema_file = Path(__file__).resolve().parent / "sql" / "schema.sql"
    sql = schema_file.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print("database initialized")


if __name__ == "__main__":
    main()
