from __future__ import annotations

import os
import sys
from pathlib import Path


def backend_dir() -> Path:
    if getattr(sys, "frozen", False):
        configured = os.environ.get("WEB_ADMIN_BACKEND_DIR")
        if configured:
            return Path(configured).resolve()
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return backend_dir()


def project_dir() -> Path:
    return backend_dir().parent


def env_file() -> Path:
    return backend_dir() / ".env"


def schema_file() -> Path:
    return bundle_dir() / "sql" / "schema.sql"
