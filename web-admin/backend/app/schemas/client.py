from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class PullGitHubItem(BaseModel):
    github_account_id: int
    email: str
    github_username: str | None = None
    github_password: str
    totp_secret: str | None = None
    two_fa_enabled: bool = False


class PullGitHubResponse(BaseModel):
    items: list[PullGitHubItem]


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
    model_config = ConfigDict(extra="allow")

    email: str | None = None
    github_username: str | None = None
    github_password: str
    totp_secret: str
    recovery_codes: list[str] = Field(default_factory=list)
    bind_mail_account_id: int | None = None
    lease_token: str | None = None
    update_existing: bool = False


class PushGitHubRequest(BaseModel):
    batch_name: str
    items: list[PushGitHubItem]


class PushGitHubResponse(BaseModel):
    batch_no: str
    success_count: int
    duplicate_count: int
    updated_count: int = 0


class HeartbeatRequest(BaseModel):
    client_name: str


class HeartbeatResponse(BaseModel):
    ok: bool
    server_time: str
