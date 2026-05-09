from __future__ import annotations

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    total_mail_accounts: int
    idle_mail_accounts: int
    registered_mail_accounts: int
    used_mail_accounts: int
    total_github_accounts: int
    active_github_accounts: int
    total_clients: int
    active_clients: int
    recent_batches: list[dict] = []
    recent_audits: list[dict] = []
    recent_sync_logs: list[dict] = []
    asset_trends: list[dict] = []
    sync_trends: list[dict] = []


class DesktopClientListItem(BaseModel):
    id: int
    name: str
    status: str
    last_seen_at: str | None = None
    last_ip: str | None = None
    created_at: str | None = None


class DesktopClientCreateRequest(BaseModel):
    name: str
    remark: str | None = None


class DesktopClientCreateResponse(BaseModel):
    id: int
    name: str
    token: str


class SyncLogListItem(BaseModel):
    id: int
    client_name: str | None = None
    action: str
    payload_count: int
    success_count: int
    failed_count: int
    message: str | None = None
    created_at: str | None = None


class SyncBatchListItem(BaseModel):
    id: int
    batch_no: str
    batch_type: str
    source: str
    client_name: str | None = None
    total_count: int
    success_count: int
    duplicate_count: int
    created_at: str | None = None


class AuditLogListItem(BaseModel):
    id: int
    operator_type: str
    operator_id: int
    action: str
    target_type: str
    target_id: int | None = None
    details: dict | None = None
    created_at: str | None = None


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
