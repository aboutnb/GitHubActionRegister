import os
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def _to_admin_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise SystemExit("仅支持 PostgreSQL 自动建库")
    if not parsed.hostname:
        raise SystemExit("数据库地址无效")
    username = parsed.username or "postgres"
    password = parsed.password or ""
    host = parsed.hostname
    port = parsed.port or 5432
    admin_database = os.environ.get("WEB_ADMIN_DATABASE_ADMIN_DATABASE", "postgres")
    return f"postgresql+psycopg://{username}:{password}@{host}:{port}/{admin_database}"


def main() -> None:
    settings = get_settings()
    if not settings.database_admin_url:
        raise SystemExit("WEB_ADMIN_DATABASE_ADMIN_URL 未配置，无法自动建库")

    parsed = urlparse(settings.database_url or "")
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise SystemExit("仅支持 PostgreSQL 自动建库")
    if not parsed.path or parsed.path == "/":
        raise SystemExit("WEB_ADMIN_DATABASE_URL 未配置数据库名")
    target_database = parsed.path.lstrip("/")

    engine = create_engine(settings.database_admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :name"),
            {"name": target_database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target_database}"'))
            print(f"created database: {target_database}")
        else:
            print(f"database already exists: {target_database}")


if __name__ == "__main__":
    main()
