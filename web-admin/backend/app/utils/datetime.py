from __future__ import annotations

from datetime import datetime


def format_datetime(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
