from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.security import decrypt_text, encrypt_text
from app.db.session import get_db
from app.models.desktop_client import DesktopClient
from app.models.github_account import GitHubAccount
from app.models.github_credential import GitHubCredential
from app.models.sync_batch import SyncBatch
from app.models.web_user import WebUser
from app.schemas.github_account import (
    GitHubAccountCreateRequest,
    GitHubAccountCredentialResponse,
    GitHubAccountExportItem,
    GitHubHealthCheckConfigRequest,
    GitHubHealthCheckConfigResponse,
    GitHubHealthCheckRunRequest,
    GitHubHealthCheckRunResponse,
    GitHubAccountImportRequest,
    GitHubAccountImportResponse,
    GitHubAccountExportResponse,
    GitHubAccountListItem,
    GitHubAccountUpdateRequest,
)
from app.schemas.bulk import BulkDeleteRequest, BulkStatusUpdateRequest
from app.services.audit import write_audit_log
from app.services.account_linking import sync_github_account_binding, sync_mail_status_from_github_refs
from app.services.github_health_check import (
    DEFAULT_ACCOUNTS_PER_PROXY,
    DEFAULT_CRON_EXPRESSION,
    DEFAULT_TIMEOUT_SECONDS,
    CronExpressionError,
    get_health_check_config,
    get_next_cron_run,
    normalize_proxy_pool,
    parse_proxy_pool_text,
    perform_github_health_check,
    serialize_proxy_pool,
    validate_cron_interval,
)
from app.utils.datetime import format_datetime

router = APIRouter(prefix="/admin/github-accounts", tags=["admin-github-accounts"])


def _build_export_batch_no() -> str:
    return f"GHEX{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6].upper()}"


def _to_export_item(account: GitHubAccount) -> GitHubAccountExportItem | None:
    if not account.credential:
        return None
    secret = decrypt_text(account.credential.totp_secret_enc)
    return GitHubAccountExportItem(
        email=account.email,
        github_password=decrypt_text(account.credential.github_password_enc),
        totp_secret=secret or "NO_2FA",
    )


def _split_recovery_codes(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.splitlines() if item.strip()]


def _normalize_import_secret(value: str | None) -> tuple[str, bool]:
    secret = str(value or "").strip()
    if not secret or secret.upper() == "NO_2FA":
        return "", False
    return secret, True


def _normalize_account_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _derive_github_username(email: str | None, github_username: str | None = None) -> str:
    username = str(github_username or "").strip()
    if username:
        return username.split("@", 1)[0].strip()
    email_value = str(email or "").strip()
    if not email_value:
        return ""
    return email_value.split("@", 1)[0].strip()


def _payload_email(payload) -> str:
    legacy_login = None
    extra = getattr(payload, "__pydantic_extra__", None)
    if isinstance(extra, dict):
        legacy_login = extra.get("github_login")
    return str(getattr(payload, "email", None) or legacy_login or "").strip()


def _sync_related_mail_accounts(
    db: Session,
    *,
    account: GitHubAccount,
    previous_emails: Iterable[str | None] = (),
) -> None:
    sync_mail_status_from_github_refs(
        db,
        mail_account_ids=([account.bind_mail_account_id] if account.bind_mail_account_id else []),
        emails=[account.email, *previous_emails],
    )


def _find_github_account_by_email(db: Session, email: str | None, exclude_id: int | None = None) -> GitHubAccount | None:
    normalized_email = _normalize_account_key(email)
    if not normalized_email:
        return None
    query = db.query(GitHubAccount).filter(func.lower(GitHubAccount.email) == normalized_email)
    if exclude_id is not None:
        query = query.filter(GitHubAccount.id != exclude_id)
    return query.first()


def _record_export_batch(
    *,
    db: Session,
    current_user: WebUser,
    accounts: list[GitHubAccount],
    exported_items: list[GitHubAccountExportItem],
    audit_action: str,
    audit_details: dict,
) -> str:
    now = datetime.now(timezone.utc)
    batch = SyncBatch(
        batch_no=_build_export_batch_no(),
        batch_type="github_export",
        source="web",
        total_count=len(accounts),
        success_count=len(exported_items),
        duplicate_count=0,
        created_by=current_user.id,
    )
    db.add(batch)
    for account in accounts:
        if account.credential:
            account.last_exported_at = now
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action=audit_action,
        target_type="github_account",
        target_id=None,
        details={
            **audit_details,
            "batch_no": batch.batch_no,
            "total_count": len(accounts),
            "success_count": len(exported_items),
        },
    )
    return batch.batch_no


def _to_list_item(
    account: GitHubAccount,
    *,
    source_client_name: str | None = None,
) -> GitHubAccountListItem:
    credential = account.credential
    return GitHubAccountListItem(
        id=account.id,
        email=account.email,
        github_username=account.github_username,
        two_fa_enabled=account.two_fa_enabled,
        status=account.status,
        github_password=decrypt_text(credential.github_password_enc) if credential else None,
        totp_secret=decrypt_text(credential.totp_secret_enc) if credential else None,
        source_client_name=source_client_name,
        created_at=format_datetime(account.created_at),
        updated_at=format_datetime(account.updated_at),
        last_exported_at=format_datetime(account.last_exported_at),
        health_status=account.health_status,
        health_checked_at=format_datetime(account.health_checked_at),
        health_http_status=account.health_http_status,
        health_error=account.health_error,
        recovery_codes=_split_recovery_codes(
            credential.recovery_codes_enc and decrypt_text(credential.recovery_codes_enc)
        )
        if credential
        else [],
        remark=account.remark,
    )


def _to_health_config_response(config) -> GitHubHealthCheckConfigResponse:
    return GitHubHealthCheckConfigResponse(
        enabled=config.enabled,
        cron_expression=config.cron_expression,
        proxy_urls=parse_proxy_pool_text(config.proxy_pool),
        accounts_per_proxy=config.accounts_per_proxy,
        timeout_seconds=config.timeout_seconds,
        last_run_at=format_datetime(config.last_run_at),
        next_run_at=format_datetime(config.next_run_at),
        last_batch_no=config.last_batch_no,
    )


@router.get("")
def list_github_accounts(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    two_fa_enabled: bool | None = Query(default=None),
    age_bucket: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_order: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = (
        db.query(GitHubAccount)
        .options(joinedload(GitHubAccount.credential))
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            GitHubAccount.email.ilike(like)
            | GitHubAccount.github_username.ilike(like)
            | GitHubAccount.remark.ilike(like)
        )
    if status:
        query = query.filter(GitHubAccount.status == status)
    if health_status:
        query = query.filter(GitHubAccount.health_status == health_status)
    if two_fa_enabled is not None:
        query = query.filter(GitHubAccount.two_fa_enabled == two_fa_enabled)
    if age_bucket:
        now = datetime.now(timezone.utc)
        if age_bucket == "new":
            query = query.filter(GitHubAccount.created_at >= now - timedelta(days=7))
        elif age_bucket == "7d_plus":
            query = query.filter(
                GitHubAccount.created_at < now - timedelta(days=7),
                GitHubAccount.created_at >= now - timedelta(days=30),
            )
        elif age_bucket == "30d_plus":
            query = query.filter(GitHubAccount.created_at < now - timedelta(days=30))

    total = query.count()
    sort_map = {
        "email": GitHubAccount.email,
        "github_username": GitHubAccount.github_username,
        "two_fa_enabled": GitHubAccount.two_fa_enabled,
        "status": GitHubAccount.status,
        "health_status": GitHubAccount.health_status,
        "health_checked_at": GitHubAccount.health_checked_at,
        "source_client_name": GitHubAccount.source_client_id,
        "created_at": GitHubAccount.created_at,
        "updated_at": GitHubAccount.updated_at,
        "last_exported_at": GitHubAccount.last_exported_at,
    }
    sort_column = sort_map.get(sort_by or "", GitHubAccount.id)
    sort_direction = desc if sort_order == "descend" else lambda column: column
    accounts = (
        query.order_by(sort_direction(sort_column), GitHubAccount.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    client_map = {
        client.id: client.name for client in db.query(DesktopClient).all()
    }
    items = [
        _to_list_item(account, source_client_name=client_map.get(account.source_client_id)).model_dump()
        for account in accounts
    ]
    if items:
        write_audit_log(
            db,
            operator_type="web_user",
            operator_id=_.id,
            action="list_github_account_credentials",
            target_type="github_account",
            target_id=None,
            details={
                "page": page,
                "page_size": page_size,
                "count": len(items),
                "sort_by": sort_by,
                "sort_order": sort_order,
                "two_fa_enabled": two_fa_enabled,
                "age_bucket": age_bucket,
                "health_status": health_status,
            },
        )
        db.commit()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/export", response_model=GitHubAccountExportResponse)
def export_github_accounts(
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountExportResponse:
    accounts = (
        db.query(GitHubAccount)
        .options(joinedload(GitHubAccount.credential))
        .filter(GitHubAccount.status == "active")
        .order_by(GitHubAccount.id.asc())
        .limit(200)
        .all()
    )
    result = [item for account in accounts if (item := _to_export_item(account))]
    batch_no = _record_export_batch(
        db=db,
        current_user=current_user,
        accounts=accounts,
        exported_items=result,
        audit_action="export_github_accounts",
        audit_details={"scope": "active", "limit": 200},
    )
    db.commit()
    return GitHubAccountExportResponse(
        batch_no=batch_no,
        total_count=len(accounts),
        success_count=len(result),
        items=result,
    )


@router.get("/health-check/config", response_model=GitHubHealthCheckConfigResponse)
def get_github_health_check_config(
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubHealthCheckConfigResponse:
    config = get_health_check_config(db, create=True)
    if config and not config.next_run_at:
        config.next_run_at = get_next_cron_run(config.cron_expression, datetime.now().astimezone())
    db.commit()
    db.refresh(config)
    return _to_health_config_response(config)


@router.put("/health-check/config", response_model=GitHubHealthCheckConfigResponse)
def update_github_health_check_config(
    payload: GitHubHealthCheckConfigRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubHealthCheckConfigResponse:
    cron_expression = str(payload.cron_expression or "").strip() or DEFAULT_CRON_EXPRESSION
    proxy_urls = normalize_proxy_pool(payload.proxy_urls)
    try:
        cron_expression = validate_cron_interval(cron_expression)
        next_run_at = get_next_cron_run(cron_expression, datetime.now().astimezone())
    except CronExpressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = get_health_check_config(db, create=True)
    config.enabled = payload.enabled
    config.cron_expression = cron_expression
    config.proxy_pool = serialize_proxy_pool(proxy_urls)
    config.accounts_per_proxy = payload.accounts_per_proxy or DEFAULT_ACCOUNTS_PER_PROXY
    config.timeout_seconds = payload.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    config.next_run_at = next_run_at
    config.updated_by = current_user.id

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="update_github_health_check_config",
        target_type="github_health_check_config",
        target_id=config.id,
        details={
            "enabled": config.enabled,
            "cron_expression": config.cron_expression,
            "proxy_count": len(proxy_urls),
            "accounts_per_proxy": config.accounts_per_proxy,
            "timeout_seconds": config.timeout_seconds,
        },
    )
    db.commit()
    db.refresh(config)
    return _to_health_config_response(config)


@router.post("/health-check/run", response_model=GitHubHealthCheckRunResponse)
def run_github_health_check(
    payload: GitHubHealthCheckRunRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubHealthCheckRunResponse:
    proxy_urls = normalize_proxy_pool(payload.proxy_urls)
    accounts_per_proxy = payload.accounts_per_proxy
    timeout_seconds = payload.timeout_seconds
    if payload.use_saved_config:
        config = get_health_check_config(db, create=True)
        if not proxy_urls:
            proxy_urls = parse_proxy_pool_text(config.proxy_pool)
        accounts_per_proxy = accounts_per_proxy or config.accounts_per_proxy
        timeout_seconds = timeout_seconds or config.timeout_seconds

    result = perform_github_health_check(
        db,
        account_ids=payload.account_ids,
        proxy_urls=proxy_urls,
        accounts_per_proxy=accounts_per_proxy,
        timeout_seconds=timeout_seconds,
        source="web",
        current_user_id=current_user.id,
    )
    db.commit()
    return GitHubHealthCheckRunResponse(**result)


@router.post("/import", response_model=GitHubAccountImportResponse)
def import_github_accounts(
    payload: GitHubAccountImportRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountImportResponse:
    total_count = len(payload.items)
    success_count = 0
    duplicate_count = 0
    batch = SyncBatch(
        batch_no=_build_export_batch_no(),
        batch_type="github_export",
        source="web",
        total_count=total_count,
        success_count=0,
        duplicate_count=0,
        created_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    seen_emails: set[str] = set()
    for item in payload.items:
        email = _payload_email(item)
        normalized_email = _normalize_account_key(email)
        if not normalized_email:
            continue
        if normalized_email in seen_emails:
            duplicate_count += 1
            continue
        seen_emails.add(normalized_email)
        exists = _find_github_account_by_email(db, email)
        if exists:
            duplicate_count += 1
            continue

        secret, two_fa_enabled = _normalize_import_secret(item.totp_secret)
        account = GitHubAccount(
            email=email,
            github_username=_derive_github_username(email, item.github_username),
            source_batch_id=batch.id,
            status="active",
            two_fa_enabled=two_fa_enabled,
            remark=item.remark,
        )
        db.add(account)
        db.flush()
        sync_github_account_binding(db, account)
        db.add(
            GitHubCredential(
                github_account_id=account.id,
                github_password_enc=encrypt_text(item.github_password),
                totp_secret_enc=encrypt_text(secret),
                recovery_codes_enc=None,
            )
        )
        _sync_related_mail_accounts(db, account=account)
        success_count += 1

    batch.success_count = success_count
    batch.duplicate_count = duplicate_count
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="import_github_accounts",
        target_type="github_account",
        target_id=None,
        details={
            "batch_no": batch.batch_no,
            "total_count": total_count,
            "success_count": success_count,
            "duplicate_count": duplicate_count,
        },
    )
    db.commit()
    return GitHubAccountImportResponse(
        total_count=total_count,
        success_count=success_count,
        duplicate_count=duplicate_count,
        batch_no=batch.batch_no,
    )


@router.post("", response_model=GitHubAccountListItem)
def create_github_account(
    payload: GitHubAccountCreateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountListItem:
    email = _payload_email(payload)
    if not email:
        raise HTTPException(status_code=400, detail="请输入邮箱")
    exists = _find_github_account_by_email(db, email)
    if exists:
        raise HTTPException(status_code=400, detail="邮箱已存在")

    account = GitHubAccount(
        email=email,
        github_username=_derive_github_username(email, payload.github_username),
        status=payload.status,
        two_fa_enabled=payload.two_fa_enabled,
        remark=payload.remark,
    )
    db.add(account)
    db.flush()
    sync_github_account_binding(db, account)
    db.add(
        GitHubCredential(
            github_account_id=account.id,
            github_password_enc=encrypt_text(payload.github_password),
            totp_secret_enc=encrypt_text(payload.totp_secret),
            recovery_codes_enc=encrypt_text("\n".join(payload.recovery_codes)) if payload.recovery_codes else None,
        )
    )
    _sync_related_mail_accounts(db, account=account)
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="create_github_account",
        target_type="github_account",
        target_id=account.id,
        details={"email": email},
    )
    db.commit()
    db.refresh(account)
    return _to_list_item(account, source_client_name=None)


@router.put("/{account_id}", response_model=GitHubAccountListItem)
def update_github_account(
    account_id: int,
    payload: GitHubAccountUpdateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountListItem:
    account = db.query(GitHubAccount).options(joinedload(GitHubAccount.credential)).filter(
        GitHubAccount.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="GitHub 账号不存在")

    email = _payload_email(payload)
    if not email:
        raise HTTPException(status_code=400, detail="请输入邮箱")
    duplicate = _find_github_account_by_email(db, email, exclude_id=account_id)
    if duplicate:
        raise HTTPException(status_code=400, detail="邮箱已存在")

    previous_emails = [account.email]
    account.email = email
    account.github_username = _derive_github_username(email, payload.github_username)
    account.bind_mail_account_id = None
    account.status = payload.status
    account.two_fa_enabled = payload.two_fa_enabled
    account.remark = payload.remark

    credential = account.credential
    if not credential:
        if not payload.github_password or not payload.totp_secret:
            raise HTTPException(status_code=400, detail="缺少凭证信息")
        credential = GitHubCredential(
            github_account_id=account.id,
            github_password_enc=encrypt_text(payload.github_password),
            totp_secret_enc=encrypt_text(payload.totp_secret),
            recovery_codes_enc=encrypt_text("\n".join(payload.recovery_codes)) if payload.recovery_codes else None,
        )
        db.add(credential)
    else:
        if payload.github_password:
            credential.github_password_enc = encrypt_text(payload.github_password)
        if payload.totp_secret:
            credential.totp_secret_enc = encrypt_text(payload.totp_secret)
        if payload.recovery_codes is not None:
            credential.recovery_codes_enc = (
                encrypt_text("\n".join(payload.recovery_codes)) if payload.recovery_codes else None
            )

    sync_github_account_binding(db, account)
    _sync_related_mail_accounts(db, account=account, previous_emails=previous_emails)

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="update_github_account",
        target_type="github_account",
        target_id=account.id,
        details={"email": email},
    )
    db.commit()
    db.refresh(account)
    client_name = None
    if account.source_client_id:
        client = db.query(DesktopClient).filter(DesktopClient.id == account.source_client_id).first()
        client_name = client.name if client else None
    return _to_list_item(account, source_client_name=client_name)


@router.delete("/{account_id}")
def delete_github_account(
    account_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    account = db.query(GitHubAccount).filter(GitHubAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="GitHub 账号不存在")

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="delete_github_account",
        target_type="github_account",
        target_id=account.id,
        details={"email": account.email},
    )
    db.delete(account)
    _sync_related_mail_accounts(db, account=account)
    db.commit()
    return {"message": "deleted"}


@router.get("/{account_id}/credential", response_model=GitHubAccountCredentialResponse)
def get_github_account_credential(
    account_id: int,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountCredentialResponse:
    account = (
        db.query(GitHubAccount)
        .options(joinedload(GitHubAccount.credential))
        .filter(GitHubAccount.id == account_id)
        .first()
    )
    if not account or not account.credential:
        raise HTTPException(status_code=404, detail="GitHub 凭证不存在")

    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="view_github_credential",
        target_type="github_account",
        target_id=account.id,
        details={"email": account.email},
    )
    db.commit()
    return GitHubAccountCredentialResponse(
        github_password=decrypt_text(account.credential.github_password_enc),
        totp_secret=decrypt_text(account.credential.totp_secret_enc),
        recovery_codes=_split_recovery_codes(
            account.credential.recovery_codes_enc and decrypt_text(account.credential.recovery_codes_enc)
        ),
    )


@router.post("/bulk-status")
def bulk_update_github_status(
    payload: BulkStatusUpdateRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    updated = (
        db.query(GitHubAccount)
        .filter(GitHubAccount.id.in_(payload.ids))
        .update({GitHubAccount.status: payload.status}, synchronize_session=False)
    )
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="bulk_update_github_status",
        target_type="github_account",
        target_id=None,
        details={"ids": payload.ids, "status": payload.status},
    )
    db.commit()
    return {"updated": updated}


@router.post("/bulk-delete")
def bulk_delete_github_accounts(
    payload: BulkDeleteRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    accounts = db.query(GitHubAccount).filter(GitHubAccount.id.in_(payload.ids)).all()
    for account in accounts:
        db.delete(account)
    db.flush()
    for account in accounts:
        _sync_related_mail_accounts(db, account=account)
    deleted = len(accounts)
    write_audit_log(
        db,
        operator_type="web_user",
        operator_id=current_user.id,
        action="bulk_delete_github_accounts",
        target_type="github_account",
        target_id=None,
        details={"ids": payload.ids},
    )
    db.commit()
    return {"deleted": deleted}


@router.post("/bulk-export", response_model=GitHubAccountExportResponse)
def bulk_export_github_accounts(
    payload: BulkDeleteRequest,
    current_user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GitHubAccountExportResponse:
    accounts = (
        db.query(GitHubAccount)
        .options(joinedload(GitHubAccount.credential))
        .filter(GitHubAccount.id.in_(payload.ids))
        .order_by(GitHubAccount.id.asc())
        .all()
    )
    result = [item for account in accounts if (item := _to_export_item(account))]
    batch_no = _record_export_batch(
        db=db,
        current_user=current_user,
        accounts=accounts,
        exported_items=result,
        audit_action="bulk_export_github_accounts",
        audit_details={"ids": payload.ids},
    )
    db.commit()
    return GitHubAccountExportResponse(
        batch_no=batch_no,
        total_count=len(accounts),
        success_count=len(result),
        items=result,
    )
