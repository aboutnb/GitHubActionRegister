from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GitHubAccountListItem(BaseModel):
    id: int
    email: str
    github_username: str | None = None
    two_fa_enabled: bool
    status: str
    github_password: str | None = None
    totp_secret: str | None = None
    source_client_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_exported_at: str | None = None
    health_status: str = "unknown"
    health_checked_at: str | None = None
    health_http_status: int | None = None
    health_error: str | None = None
    recovery_codes: list[str] = []
    remark: str | None = None


class GitHubAccountExportItem(BaseModel):
    email: str
    github_password: str
    totp_secret: str


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
    model_config = ConfigDict(extra="allow")

    email: str | None = None
    github_password: str
    totp_secret: str
    github_username: str | None = None
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
    model_config = ConfigDict(extra="allow")

    email: str | None = None
    github_username: str | None = None
    github_password: str
    totp_secret: str
    recovery_codes: list[str] = []
    status: str = "active"
    two_fa_enabled: bool = True
    remark: str | None = None


class GitHubAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    email: str | None = None
    github_username: str | None = None
    github_password: str | None = None
    totp_secret: str | None = None
    recovery_codes: list[str] | None = None
    status: str
    two_fa_enabled: bool
    remark: str | None = None


class GitHubHealthCheckRunRequest(BaseModel):
    account_ids: list[int] | None = None
    use_saved_config: bool = True
    proxy_urls: list[str] = Field(default_factory=list)
    accounts_per_proxy: int | None = Field(default=None, ge=1, le=20)
    timeout_seconds: int | None = Field(default=None, ge=2, le=60)


class GitHubHealthCheckResultItem(BaseModel):
    id: int
    email: str
    github_username: str | None = None
    health_status: str
    health_http_status: int | None = None
    health_error: str | None = None
    health_checked_at: str | None = None
    proxy_used: bool = False


class GitHubHealthCheckRunResponse(BaseModel):
    batch_no: str
    total_count: int
    checked_count: int
    alive_count: int
    not_found_count: int
    error_count: int
    skipped_count: int
    items: list[GitHubHealthCheckResultItem] = []


class GitHubHealthCheckConfigRequest(BaseModel):
    enabled: bool = False
    cron_expression: str = "0 0 1,15 * *"
    proxy_urls: list[str] = Field(default_factory=list)
    accounts_per_proxy: int = Field(default=15, ge=1, le=20)
    timeout_seconds: int = Field(default=10, ge=2, le=60)


class GitHubHealthCheckConfigResponse(BaseModel):
    enabled: bool
    cron_expression: str
    proxy_urls: list[str] = []
    accounts_per_proxy: int
    timeout_seconds: int
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_batch_no: str | None = None
