from __future__ import annotations

from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_secret
from app.db.session import get_db
from app.models.desktop_client import DesktopClient
from app.models.github_account import GitHubAccount
from app.models.mail_account import MailAccount
from app.models.sync_batch import SyncBatch
from app.models.sync_log import SyncLog
from app.models.web_user import WebUser
from app.schemas.admin import (
    DesktopClientCreateRequest,
    DesktopClientCreateResponse,
    DesktopClientListItem,
)
from app.services.audit import write_audit_log

router = APIRouter(prefix="/admin/desktop-clients", tags=["admin-desktop-clients"])


@router.get("", response_model=list[DesktopClientListItem])
def list_clients(
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DesktopClientListItem]:
    clients = db.query(DesktopClient).order_by(DesktopClient.id.desc()).all()
    return [
        DesktopClientListItem(
            id=client.id,
            name=client.name,
            status=client.status,
            last_seen_at=client.last_seen_at.isoformat() if client.last_seen_at else None,
            last_ip=str(client.last_ip) if client.last_ip else None,
            created_at=client.created_at.isoformat() if client.created_at else None,
        )
        for client in clients
    ]


@router.post("", response_model=DesktopClientCreateResponse)
def create_client(
    payload: DesktopClientCreateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DesktopClientCreateResponse:
    plain_token = token_urlsafe(24)
    client = DesktopClient(
        name=payload.name,
        token_hash=hash_secret(plain_token),
        status="active",
        remark=payload.remark,
    )
    db.add(client)
    db.flush()
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="create_desktop_client",
        target_type="desktop_client",
        target_id=client.id,
        details={"name": payload.name},
    )
    db.commit()
    return DesktopClientCreateResponse(id=client.id, name=client.name, token=plain_token)


@router.delete("/{client_id}")
def delete_client(
    client_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    client = db.query(DesktopClient).filter(DesktopClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="客户端不存在")

    db.query(MailAccount).filter(MailAccount.lease_client_id == client.id).update(
        {
            MailAccount.lease_client_id: None,
            MailAccount.lease_token: None,
            MailAccount.lease_expires_at: None,
        },
        synchronize_session=False,
    )
    db.query(GitHubAccount).filter(GitHubAccount.source_client_id == client.id).update(
        {GitHubAccount.source_client_id: None},
        synchronize_session=False,
    )
    db.query(SyncBatch).filter(SyncBatch.client_id == client.id).update(
        {SyncBatch.client_id: None},
        synchronize_session=False,
    )
    db.query(SyncLog).filter(SyncLog.client_id == client.id).update(
        {SyncLog.client_id: None},
        synchronize_session=False,
    )

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="delete_desktop_client",
        target_type="desktop_client",
        target_id=client.id,
        details={"name": client.name},
    )
    db.delete(client)
    db.commit()
    return {"ok": True}
