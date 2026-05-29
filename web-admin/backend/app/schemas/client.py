from __future__ import annotations

from pydantic import BaseModel, Field


class PullMailItem(BaseModel):
    mail_account_id: int
    email: str
    password: str
    receive_mode: str | None = None
    client_id: str | None = None
    access_token: str | None = None
    lease_token: str


class PullMailResponse(BaseModel):
    items: list[PullMailItem]


class PushMailItem(BaseModel):
    email: str
    password: str
    receive_mode: str
    raw_line: str | None = None
    client_id: str | None = None
    access_token: str | None = None
    remark: str | None = None


class PushMailRequest(BaseModel):
    batch_name: str
    items: list[PushMailItem]


class PushMailResponse(BaseModel):
    batch_no: str
    success_count: int
    duplicate_count: int


class PushGitHubItem(BaseModel):
    github_login: str
    github_username: str | None = None
    github_password: str
    totp_secret: str
    recovery_codes: list[str] = Field(default_factory=list)
    bind_mail_account_id: int | None = None
    bind_email: str | None = None
    lease_token: str | None = None


class PushGitHubRequest(BaseModel):
    batch_name: str
    items: list[PushGitHubItem]


class PushGitHubResponse(BaseModel):
    batch_no: str
    success_count: int
    duplicate_count: int


class HeartbeatRequest(BaseModel):
    client_name: str


class HeartbeatResponse(BaseModel):
    ok: bool
    server_time: str
