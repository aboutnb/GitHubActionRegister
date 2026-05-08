from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class OfficialMailAccount:
    email: str
    password: str
    client_id: str | None = None
    refresh_token: str | None = None

    @property
    def has_oauth(self) -> bool:
        return bool(self.client_id and self.refresh_token)


@dataclass
class OfficialFetchedMessage:
    id: str
    subject: str
    sender: str
    recipients: list[str]
    body: str
    received_at: datetime | None
    received_timestamp: int
