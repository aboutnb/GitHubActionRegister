from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import decrypt_text, encrypt_text
from app.db.session import get_db
from app.models.github_account import GitHubAccount
from app.models.mail_account import MailAccount
from app.models.mail_credential import MailCredential
from app.models.sync_batch import SyncBatch
from app.models.web_user import WebUser
from app.schemas.mail import (
    MailAccountCreateRequest,
    MailAccountCredentialResponse,
    MailFetchResponse,
    MailAccountImportRequest,
    MailAccountImportResponse,
    MailAccountListItem,
    MailAccountUpdateRequest,
)
from app.schemas.bulk import BulkDeleteRequest, BulkStatusUpdateRequest
from app.services.audit import write_audit_log
from app.services.account_linking import find_mail_account_by_email, reconcile_mail_account_status
from app.services.mail_fetch import fetch_mail_messages
from app.utils.datetime import format_datetime

router = APIRouter(prefix="/admin/mail-accounts", tags=["admin-mail-accounts"])

MAIL_STATUS_OPTIONS = {"idle", "registered", "disabled"}


def parse_mail_payload(
    *,
    receive_mode: str | None,
    email: str | None,
    password: str | None,
    raw_line: str | None,
) -> dict:
    if receive_mode not in {"official", "xiaoshuidi"}:
        raise HTTPException(status_code=400, detail="请选择正确的收件方式")

    if raw_line:
        parts = [part for part in raw_line.strip().split("----") if part != ""]
        if receive_mode == "official":
            if len(parts) != 4:
                raise HTTPException(
                    status_code=400,
                    detail="官方收件格式应为：邮箱----密码----account_id----token",
                )
            parsed_email, parsed_password, client_id, access_token = parts
            return {
                "email": parsed_email,
                "password": parsed_password,
                "receive_mode": "official",
                "client_id": client_id,
                "access_token": access_token,
                "raw_line": raw_line,
            }

        if len(parts) < 4:
            raise HTTPException(
                status_code=400,
                detail="小水滴收件格式应为：邮箱----密码----...----account_id----token",
            )
        parsed_email, parsed_password = parts[0], parts[1]
        client_id, access_token = parts[-2], parts[-1]
        return {
            "email": parsed_email,
            "password": parsed_password,
            "receive_mode": "xiaoshuidi",
            "client_id": client_id,
            "access_token": access_token,
            "raw_line": raw_line,
        }

    if not email or not password:
        raise HTTPException(status_code=400, detail="缺少邮箱或密码")
    return {
        "email": email,
        "password": password,
        "receive_mode": receive_mode,
        "client_id": None,
        "access_token": None,
        "raw_line": None,
    }

def compose_mail_raw_line(
    *,
    email: str,
    password: str,
    client_id: str | None,
    access_token: str | None,
) -> str | None:
    if not client_id or not access_token:
        return None
    return f"{email}----{password}----{client_id}----{access_token}"


def _normalize_account_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _unique_mail_account_exists(db: Session, email: str | None) -> MailAccount | None:
    return find_mail_account_by_email(db, email)


def _count_github_refs_for_mail_account(db: Session, account: MailAccount) -> int:
    normalized_email = _normalize_account_key(account.email)
    return (
        db.query(func.count(GitHubAccount.id))
        .filter(
            (GitHubAccount.bind_mail_account_id == account.id)
            | (func.lower(GitHubAccount.email) == normalized_email)
        )
        .scalar()
        or 0
    )


def normalize_mail_status(value: str | None) -> str:
    status = str(value or "idle").strip().lower() or "idle"
    if status not in MAIL_STATUS_OPTIONS:
        raise HTTPException(status_code=400, detail="邮箱状态不正确")
    return status


def normalize_mail_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_mail_status(value)


@router.get("")
def list_mail_accounts(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    receive_mode: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_order: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(MailAccount).outerjoin(MailCredential, MailCredential.mail_account_id == MailAccount.id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            MailAccount.email.ilike(like)
            | MailCredential.client_id.ilike(like)
            | MailAccount.remark.ilike(like)
        )
    if status:
        normalized_status = normalize_mail_status_filter(status)
        query = query.filter(MailAccount.status == normalized_status)
    if receive_mode:
        normalized_mode = str(receive_mode).strip().lower()
        if normalized_mode in {"official", "xiaoshuidi"}:
            query = query.filter(MailCredential.receive_mode == normalized_mode)

    total = query.with_entities(func.count(MailAccount.id.distinct())).scalar() or 0
    sort_map = {
        "email": MailAccount.email,
        "status": MailAccount.status,
        "receive_mode": MailCredential.receive_mode,
        "client_id": MailCredential.client_id,
        "updated_at": MailAccount.updated_at,
    }
    sort_column = sort_map.get(sort_by or "", MailAccount.id)
    sort_direction = desc if sort_order == "descend" else lambda column: column
    rows = (
        query
        .order_by(sort_direction(sort_column), MailAccount.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        MailAccountListItem(
            id=account.id,
            email=account.email,
            receive_mode=account.credential.receive_mode if account.credential else None,
            client_id=account.credential.client_id if account.credential else None,
            access_token=account.credential.access_token if account.credential else None,
            has_access_token=bool(account.credential.access_token) if account.credential else False,
            raw_line=account.credential.raw_line if account.credential else None,
            status=account.status,
            password=decrypt_text(account.credential.password_enc) if account.credential else None,
            updated_at=format_datetime(account.updated_at),
            remark=account.remark,
        ).model_dump()
        for account in rows
    ]
    if items:
        write_audit_log(
            db,
            operator_type="web_user",
            operator_id=_.id,
            action="list_mail_account_credentials",
            target_type="mail_account",
            target_id=None,
            details={
                "page": page,
                "page_size": page_size,
                "count": len(items),
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )
        db.commit()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/import", response_model=MailAccountImportResponse)
def import_mail_accounts(
    payload: MailAccountImportRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailAccountImportResponse:
    batch = SyncBatch(
        batch_no=f"MAIL{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        batch_type="mail_import",
        source="web",
        total_count=len(payload.items),
        success_count=0,
        duplicate_count=0,
        created_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    success_count = 0
    duplicate_count = 0
    seen_emails: set[str] = set()
    for item in payload.items:
        parsed = parse_mail_payload(
            receive_mode=payload.receive_mode,
            email=item.email,
            password=item.password,
            raw_line=item.raw_line,
        )
        normalized_email = _normalize_account_key(parsed["email"])
        if normalized_email in seen_emails:
            duplicate_count += 1
            continue
        seen_emails.add(normalized_email)
        exists = _unique_mail_account_exists(db, parsed["email"])
        if exists:
            duplicate_count += 1
            continue
        account = MailAccount(
            email=parsed["email"],
            status="idle",
            remark=item.remark,
        )
        db.add(account)
        db.flush()
        db.add(
            MailCredential(
                mail_account_id=account.id,
                password_enc=encrypt_text(parsed["password"]),
                receive_mode=parsed["receive_mode"],
                client_id=parsed["client_id"],
                access_token=parsed["access_token"],
                raw_line=parsed["raw_line"],
            )
        )
        reconcile_mail_account_status(db, account)
        write_audit_log(
            db,
            operator_type="web_user",
            operator_id=current_user.id,
            action="import_mail_account",
            target_type="mail_account",
            target_id=account.id,
            details={"email": parsed["email"], "receive_mode": parsed["receive_mode"]},
        )
        success_count += 1

    batch.success_count = success_count
    batch.duplicate_count = duplicate_count
    db.commit()
    return MailAccountImportResponse(
        total_count=len(payload.items),
        success_count=success_count,
        duplicate_count=duplicate_count,
        batch_no=batch.batch_no,
    )


@router.post("", response_model=MailAccountListItem)
def create_mail_account(
    payload: MailAccountCreateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailAccountListItem:
    parsed = parse_mail_payload(
        receive_mode=payload.receive_mode,
        email=payload.email,
        password=payload.password,
        raw_line=payload.raw_line,
    )
    exists = _unique_mail_account_exists(db, parsed["email"])
    if exists:
        raise HTTPException(status_code=400, detail="邮箱已存在")

    account = MailAccount(
        email=parsed["email"],
        status=normalize_mail_status(payload.status),
        remark=payload.remark,
    )
    db.add(account)
    db.flush()
    db.add(
        MailCredential(
            mail_account_id=account.id,
            password_enc=encrypt_text(parsed["password"]),
            receive_mode=parsed["receive_mode"],
            client_id=parsed["client_id"] or payload.client_id,
            access_token=parsed["access_token"] or payload.access_token,
            raw_line=parsed["raw_line"]
            or compose_mail_raw_line(
                email=parsed["email"],
                password=parsed["password"],
                client_id=parsed["client_id"] or payload.client_id,
                access_token=parsed["access_token"] or payload.access_token,
            ),
        )
    )
    reconcile_mail_account_status(db, account)
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="create_mail_account",
        target_type="mail_account",
        target_id=account.id,
        details={"email": parsed["email"], "receive_mode": parsed["receive_mode"]},
    )
    db.commit()
    db.refresh(account)
    return MailAccountListItem(
        id=account.id,
        email=account.email,
        receive_mode=parsed["receive_mode"],
        client_id=parsed["client_id"] or payload.client_id,
        access_token=parsed["access_token"] or payload.access_token,
        has_access_token=bool(parsed["access_token"] or payload.access_token),
        raw_line=parsed["raw_line"]
        or compose_mail_raw_line(
            email=parsed["email"],
            password=parsed["password"],
            client_id=parsed["client_id"] or payload.client_id,
            access_token=payload.access_token,
        ),
        status=account.status,
        password=parsed["password"],
        updated_at=format_datetime(account.updated_at),
        remark=account.remark,
    )


@router.put("/{account_id}", response_model=MailAccountListItem)
def update_mail_account(
    account_id: int,
    payload: MailAccountUpdateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailAccountListItem:
    account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="邮箱不存在")

    duplicate = (
        db.query(MailAccount)
        .filter(func.lower(MailAccount.email) == _normalize_account_key(payload.email), MailAccount.id != account_id)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="邮箱已存在")

    account.email = payload.email
    account.status = normalize_mail_status(payload.status)
    account.remark = payload.remark
    credential = account.credential
    if payload.password:
        if not credential:
            credential = MailCredential(
                mail_account_id=account.id,
                password_enc=encrypt_text(payload.password),
            )
            db.add(credential)
        else:
            credential.password_enc = encrypt_text(payload.password)
    if payload.receive_mode:
        credential.receive_mode = payload.receive_mode
    if payload.client_id is not None:
        credential.client_id = payload.client_id or None
    if payload.access_token is not None:
        credential.access_token = payload.access_token or None
    if payload.raw_line:
        parsed = parse_mail_payload(
            receive_mode=payload.receive_mode or credential.receive_mode,
            email=payload.email,
            password=payload.password or decrypt_text(credential.password_enc),
            raw_line=payload.raw_line,
        )
        account.email = parsed["email"]
        credential.password_enc = encrypt_text(parsed["password"])
        credential.receive_mode = parsed["receive_mode"]
        credential.client_id = parsed["client_id"]
        credential.access_token = parsed["access_token"]
        credential.raw_line = parsed["raw_line"]
    elif credential:
        current_password = decrypt_text(credential.password_enc)
        credential.raw_line = compose_mail_raw_line(
            email=account.email,
            password=current_password,
            client_id=credential.client_id,
            access_token=credential.access_token,
        )
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="update_mail_account",
        target_type="mail_account",
        target_id=account.id,
        details={"email": payload.email},
    )
    db.commit()
    db.refresh(account)
    return MailAccountListItem(
        id=account.id,
        email=account.email,
        receive_mode=account.credential.receive_mode if account.credential else None,
        client_id=account.credential.client_id if account.credential else None,
        access_token=account.credential.access_token if account.credential else None,
        has_access_token=bool(account.credential.access_token) if account.credential else False,
        raw_line=account.credential.raw_line if account.credential else None,
        status=account.status,
        password=decrypt_text(account.credential.password_enc) if account.credential else None,
        updated_at=format_datetime(account.updated_at),
        remark=account.remark,
    )


@router.delete("/{account_id}")
def delete_mail_account(
    account_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="邮箱不存在")

    bind_count = _count_github_refs_for_mail_account(db, account)
    if bind_count > 0:
        raise HTTPException(status_code=400, detail="该邮箱已绑定 GitHub 账号，不能删除")

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="delete_mail_account",
        target_type="mail_account",
        target_id=account.id,
        details={"email": account.email},
    )
    db.delete(account)
    db.commit()
    return {"message": "deleted"}


@router.get("/{account_id}/credential", response_model=MailAccountCredentialResponse)
def get_mail_account_credential(
    account_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailAccountCredentialResponse:
    account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not account or not account.credential:
        raise HTTPException(status_code=404, detail="邮箱凭证不存在")

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="view_mail_credential",
        target_type="mail_account",
        target_id=account.id,
        details={"email": account.email},
    )
    db.commit()
    from app.core.security import decrypt_text

    return MailAccountCredentialResponse(password=decrypt_text(account.credential.password_enc))


@router.get("/{account_id}/messages", response_model=MailFetchResponse)
def fetch_mail_account_messages(
    account_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailFetchResponse:
    account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not account or not account.credential:
        raise HTTPException(status_code=404, detail="邮箱凭证不存在")

    receive_mode = account.credential.receive_mode
    password = decrypt_text(account.credential.password_enc)
    try:
        result = fetch_mail_messages(
            email=account.email,
            password=password,
            receive_mode=receive_mode,
            client_id=account.credential.client_id if account.credential else None,
            access_token=account.credential.access_token if account.credential else None,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="fetch_mail_messages",
        target_type="mail_account",
        target_id=account.id,
        details={
            "email": account.email,
            "receive_mode": receive_mode,
            "provider": result["provider"],
            "message_count": len(result["messages"]),
        },
    )
    db.commit()
    return MailFetchResponse(
        account_id=account.id,
        email=account.email,
        receive_mode=receive_mode,
        provider=str(result["provider"]),
        supports_history=bool(result["supports_history"]),
        note=str(result["note"]) if result.get("note") else None,
        messages=result["messages"],
    )


@router.post("/bulk-status")
def bulk_update_mail_status(
    payload: BulkStatusUpdateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    normalized_status = normalize_mail_status(payload.status)
    updated = (
        db.query(MailAccount)
        .filter(MailAccount.id.in_(payload.ids))
        .update({MailAccount.status: normalized_status}, synchronize_session=False)
    )
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="bulk_update_mail_status",
        target_type="mail_account",
        target_id=None,
        details={"ids": payload.ids, "status": normalized_status},
    )
    db.commit()
    return {"updated": updated}


@router.post("/bulk-delete")
def bulk_delete_mail_accounts(
    payload: BulkDeleteRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    accounts = db.query(MailAccount).filter(MailAccount.id.in_(payload.ids)).all()
    deletable_ids = []
    for account in accounts:
        bind_count = _count_github_refs_for_mail_account(db, account)
        if bind_count == 0:
            deletable_ids.append(account.id)
    deleted = 0
    if deletable_ids:
        deleted = (
            db.query(MailAccount)
            .filter(MailAccount.id.in_(deletable_ids))
            .delete(synchronize_session=False)
        )
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="bulk_delete_mail_accounts",
        target_type="mail_account",
        target_id=None,
        details={"ids": deletable_ids},
    )
    db.commit()
    return {"deleted": deleted}
