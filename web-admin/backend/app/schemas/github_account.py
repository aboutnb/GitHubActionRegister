from __future__ import annotations

from pydantic import BaseModel


class GitHubAccountListItem(BaseModel):
    id: int
    github_login: str
    github_username: str | None = None
    bind_email: str | None = None
    two_fa_enabled: bool
    status: str
    github_password: str | None = None
    totp_secret: str | None = None
    source_client_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_exported_at: str | None = None
    recovery_codes: list[str] = []
    remark: str | None = None


class GitHubAccountExportItem(BaseModel):
    github_login: str
    github_username: str | None = None
    github_password: str
    totp_secret: str
    bind_email: str | None = None


class GitHubAccountCredentialResponse(BaseModel):
    github_password: str
    totp_secret: str
    recovery_codes: list[str] = []


class GitHubAccountExportResponse(BaseModel):
    batch_no: str
    total_count: int
    success_count: int
    items: list[GitHubAccountExportItem]


class GitHubAccountImportItem(BaseModel):
    github_login: str
    github_password: str
    totp_secret: str
    github_username: str | None = None
    bind_email: str | None = None
    remark: str | None = None
    raw_line: str | None = None


class GitHubAccountImportRequest(BaseModel):
    items: list[GitHubAccountImportItem]


class GitHubAccountImportResponse(BaseModel):
    total_count: int
    success_count: int
    duplicate_count: int
    batch_no: str


class GitHubAccountCreateRequest(BaseModel):
    github_login: str
    github_username: str | None = None
    github_password: str
    totp_secret: str
    recovery_codes: list[str] = []
    bind_email: str | None = None
    status: str = "active"
    two_fa_enabled: bool = True
    remark: str | None = None


class GitHubAccountUpdateRequest(BaseModel):
    github_login: str
    github_username: str | None = None
    github_password: str | None = None
    totp_secret: str | None = None
    recovery_codes: list[str] | None = None
    bind_email: str | None = None
    status: str
    two_fa_enabled: bool
    remark: str | None = None
