from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.desktop_client import DesktopClient
from app.models.sync_log import SyncLog
from app.models.web_user import WebUser
from app.schemas.admin import AuditLogListItem, SyncLogListItem
from app.utils.datetime import format_datetime

router = APIRouter(prefix="/admin/logs", tags=["admin-logs"])


@router.get("/sync")
def list_sync_logs(
    action: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    client_map = {
        client.id: client.name for client in db.query(DesktopClient).all()
    }
    query = db.query(SyncLog)
    if action:
        query = query.filter(SyncLog.action == action)
    total = query.count()
    logs = (
        query.order_by(SyncLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        SyncLogListItem(
            id=log.id,
            client_name=client_map.get(log.client_id),
            action=log.action,
            payload_count=log.payload_count,
            success_count=log.success_count,
            failed_count=log.failed_count,
            message=log.message,
            created_at=format_datetime(log.created_at),
        ).model_dump()
        for log in logs
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/audit")
def list_audit_logs(
    target_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(AuditLog)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if action:
        query = query.filter(AuditLog.action == action)

    total = query.count()
    logs = (
        query.order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        AuditLogListItem(
            id=log.id,
            operator_type=log.operator_type,
            operator_id=log.operator_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            details=log.details,
            created_at=format_datetime(log.created_at),
        ).model_dump()
        for log in logs
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
