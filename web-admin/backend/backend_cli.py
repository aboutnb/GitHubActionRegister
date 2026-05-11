from __future__ import annotations

import argparse
import os

import uvicorn

from create_admin import main as create_admin_main
from create_database import main as create_database_main
from init_db import main as init_db_main
from migrate_mail_status_schema import main as migrate_mail_status_schema_main


def prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WEB_ADMIN_SERVE_FRONTEND", "true")
    env.setdefault("WEB_ADMIN_APP_ENV", "production")
    env.setdefault("WEB_ADMIN_DOCS_ENABLED", "false")
    env.setdefault("WEB_ADMIN_COOKIE_SECURE", "false")
    os.environ.update(env)
    return env


def prepare_runtime() -> None:
    create_database_main()
    init_db_main()
    migrate_mail_status_schema_main()
    create_admin_main()


def serve_runtime(env: dict[str, str]) -> None:
    host = env.get("WEB_ADMIN_HOST", "0.0.0.0")
    port = int(env.get("WEB_ADMIN_PORT", "18700"))
    workers = int(env.get("WEB_ADMIN_WORKERS", "1"))
    log_level = env.get("WEB_ADMIN_LOG_LEVEL", "info")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run web-admin backend")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["prepare", "serve"],
        help="prepare=initialize database/admin, serve=start web api",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = prepare_env()
    if args.command == "prepare":
        prepare_runtime()
        return
    serve_runtime(env)


if __name__ == "__main__":
    main()
