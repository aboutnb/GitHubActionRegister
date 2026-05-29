from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.security import decrypt_text
from app.db.session import get_db
from app.models.desktop_client import DesktopClient
from app.models.mail_account import MailAccount
from app.models.mail_credential import MailCredential
from app.schemas.client import (
    HeartbeatRequest,
    HeartbeatResponse,
    PullGitHubResponse,
    PullMailResponse,
    PushGitHubRequest,
    PushGitHubResponse,
    PushMailRequest,
    PushMailResponse,
)
from app.schemas.mail import SingleMailInfoResponse
from app.services.mail_fetch import fetch_latest_mail_info
from app.services.sync import pull_github_accounts, pull_mail_accounts, push_github_accounts, push_mail_accounts

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/mail-accounts/pull", response_model=PullMailResponse)
def pull_mail(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    receive_mode: str | None = Query(default=None),
    client: DesktopClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> PullMailResponse:
    client.last_seen_at = datetime.now(timezone.utc)
    if request.client:
        client.last_ip = request.client.host
    items = pull_mail_accounts(db, client, limit=limit, receive_mode=receive_mode)
    db.commit()
    return PullMailResponse(items=items)


@router.get("/github-accounts/pull", response_model=PullGitHubResponse)
def pull_github(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    two_fa_enabled: bool | None = Query(default=None),
    client: DesktopClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> PullGitHubResponse:
    client.last_seen_at = datetime.now(timezone.utc)
    if request.client:
        client.last_ip = request.client.host
    items = pull_github_accounts(db, client, limit=limit, two_fa_enabled=two_fa_enabled)
    db.commit()
    return PullGitHubResponse(items=items)


@router.post("/github-accounts/push", response_model=PushGitHubResponse)
def push_github(
    payload: PushGitHubRequest,
    request: Request,
    client: DesktopClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> PushGitHubResponse:
    client.last_seen_at = datetime.now(timezone.utc)
    if request.client:
        client.last_ip = request.client.host
    batch_no, success_count, duplicate_count, updated_count = push_github_accounts(
        db,
        client=client,
        batch_name=payload.batch_name,
        items=payload.items,
    )
    db.commit()
    return PushGitHubResponse(
        batch_no=batch_no,
        success_count=success_count,
        duplicate_count=duplicate_count,
        updated_count=updated_count,
    )


@router.post("/mail-accounts/push", response_model=PushMailResponse)
def push_mail(
    payload: PushMailRequest,
    request: Request,
    client: DesktopClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> PushMailResponse:
    client.last_seen_at = datetime.now(timezone.utc)
    if request.client:
        client.last_ip = request.client.host
    batch_no, success_count, duplicate_count = push_mail_accounts(
        db,
        client=client,
        batch_name=payload.batch_name,
        items=payload.items,
    )
    db.commit()
    return PushMailResponse(
        batch_no=batch_no,
        success_count=success_count,
        duplicate_count=duplicate_count,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    client: DesktopClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    client.last_seen_at = datetime.now(timezone.utc)
    if request.client:
        client.last_ip = request.client.host
    db.commit()
    return HeartbeatResponse(ok=True, server_time=datetime.now(timezone.utc).isoformat())


@router.get("/mail/getMailInfo", response_model=SingleMailInfoResponse)
def get_mail_info(
    request: Request,
    mail_account_id: int | None = Query(default=None, ge=1),
    name: str | None = Query(default=None),
    pwd: str | None = Query(default=None),
    sender: str | None = Query(default=None),
    receive_mode: str | None = Query(default="official"),
    client_id: str | None = Query(default=None),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SingleMailInfoResponse:
    email = (name or "").strip()
    password = (pwd or "").strip()
    resolved_mode = (receive_mode or "").strip() or "official"
    resolved_client_id = (client_id or "").strip() or None
    resolved_token = (token or "").strip() or None
    sender_filter = (sender or "").strip() or None

    if mail_account_id is not None:
        account = db.query(MailAccount).filter(MailAccount.id == mail_account_id).first()
        if not account or not account.credential:
            raise HTTPException(status_code=404, detail="邮箱凭证不存在")

        credential = account.credential
        email = account.email
        password = decrypt_text(credential.password_enc)
        resolved_mode = credential.receive_mode or resolved_mode
        resolved_client_id = credential.client_id or resolved_client_id
        resolved_token = credential.access_token or resolved_token
    elif email and (resolved_mode == "official" or not resolved_mode):
        credential_row = (
            db.query(MailCredential)
            .join(MailAccount, MailCredential.mail_account_id == MailAccount.id)
            .filter(MailAccount.email == email)
            .first()
        )
        if credential_row:
            resolved_mode = credential_row.receive_mode or resolved_mode
            if not resolved_client_id:
                resolved_client_id = credential_row.client_id
            if not resolved_token:
                resolved_token = credential_row.access_token

    if not email or not password:
        raise HTTPException(status_code=400, detail="请提供 name 和 pwd，或传入 mail_account_id")

    try:
        result = fetch_latest_mail_info(
            email=email,
            password=password,
            receive_mode=resolved_mode,
            client_id=resolved_client_id,
            access_token=resolved_token,
            sender=sender_filter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.commit()
    return SingleMailInfoResponse(**result)
