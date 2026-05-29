from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_text, encrypt_text
from app.models.desktop_client import DesktopClient
from app.models.github_account import GitHubAccount
from app.models.github_credential import GitHubCredential
from app.models.mail_account import MailAccount
from app.models.mail_credential import MailCredential
from app.models.sync_batch import SyncBatch
from app.models.sync_log import SyncLog
from app.schemas.client import PullMailItem, PushGitHubItem, PushMailItem
from app.services.account_linking import (
    find_mail_account_by_email,
    reconcile_mail_account_status,
    sync_github_account_binding,
    sync_mail_status_from_github_refs,
)
from app.services.audit import write_audit_log


def pull_mail_accounts(
    db: Session,
    client: DesktopClient,
    limit: int,
    receive_mode: str | None = None,
) -> list[PullMailItem]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(minutes=settings.mail_lease_minutes)
    normalized_mode = str(receive_mode or "").strip().lower()
    query = (
        db.query(MailAccount)
        .join(MailAccount.credential)
        .filter(MailAccount.status == "idle")
        .filter(
            (MailAccount.lease_expires_at.is_(None))
            | (MailAccount.lease_expires_at <= now)
        )
        .order_by(MailAccount.id.asc())
    )
    if normalized_mode in {"official", "xiaoshuidi"}:
        query = query.filter(MailCredential.receive_mode == normalized_mode)
    accounts = query.limit(limit).all()

    items: list[PullMailItem] = []
    for account in accounts:
        credential = account.credential
        if not credential:
            continue
        lease_token = uuid4().hex
        account.lease_client_id = client.id
        account.lease_token = lease_token
        account.lease_expires_at = lease_until
        items.append(
            PullMailItem(
                mail_account_id=account.id,
                email=account.email,
                password=decrypt_text(credential.password_enc),
                receive_mode=credential.receive_mode,
                client_id=credential.client_id,
                access_token=credential.access_token,
                lease_token=lease_token,
            )
        )

    db.add(
        SyncLog(
            client_id=client.id,
            action="pull_mail",
            request_id=uuid4().hex,
            payload_count=len(items),
            success_count=len(items),
            failed_count=0,
            message=(
                f"Pulled {len(items)} mail accounts"
                + (f" [{normalized_mode}]" if normalized_mode else "")
            ),
        )
    )
    db.flush()
    return items


def push_github_accounts(
    db: Session,
    client: DesktopClient,
    batch_name: str,
    items: list[PushGitHubItem],
) -> tuple[str, int, int]:
    request_id = uuid4().hex
    batch = SyncBatch(
        batch_no=f"GH{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        batch_type="github_push",
        client_id=client.id,
        source="desktop",
        total_count=len(items),
        success_count=0,
        duplicate_count=0,
    )
    db.add(batch)
    db.flush()

    success_count = 0
    duplicate_count = 0
    for item in items:
        exists = (
            db.query(GitHubAccount)
            .filter(GitHubAccount.github_login == item.github_login)
            .first()
        )
        if exists:
            duplicate_count += 1
            continue

        mail_account = None
        if item.bind_mail_account_id:
            mail_account = db.query(MailAccount).filter(MailAccount.id == item.bind_mail_account_id).first()
            if mail_account and item.lease_token and mail_account.lease_token != item.lease_token:
                continue

        account = GitHubAccount(
            github_login=item.github_login,
            github_username=item.github_username,
            bind_mail_account_id=item.bind_mail_account_id,
            bind_email=item.bind_email,
            source_client_id=client.id,
            source_batch_id=batch.id,
            status="active",
            two_fa_enabled=bool(item.totp_secret),
        )
        db.add(account)
        db.flush()
        sync_github_account_binding(db, account)

        credential = GitHubCredential(
            github_account_id=account.id,
            github_password_enc=encrypt_text(item.github_password),
            totp_secret_enc=encrypt_text(item.totp_secret),
            recovery_codes_enc=encrypt_text("\n".join(item.recovery_codes)) if item.recovery_codes else None,
        )
        db.add(credential)

        if mail_account:
            mail_account.lease_token = None
            mail_account.lease_expires_at = None
            reconcile_mail_account_status(db, mail_account)

        write_audit_log(
            db=db,
            operator_type="desktop_client",
            operator_id=client.id,
            action="push_github_account",
            target_type="github_account",
            target_id=account.id,
            details={"github_login": item.github_login, "batch_name": batch_name},
        )
        success_count += 1

        sync_mail_status_from_github_refs(
            db,
            mail_account_ids=([item.bind_mail_account_id] if item.bind_mail_account_id else []),
            emails=[item.bind_email, item.github_login],
        )

    batch.success_count = success_count
    batch.duplicate_count = duplicate_count
    db.add(
        SyncLog(
            client_id=client.id,
            action="push_github",
            request_id=request_id,
            payload_count=len(items),
            success_count=success_count,
            failed_count=len(items) - success_count - duplicate_count,
            message=f"Pushed {success_count} github accounts from {batch_name}",
        )
    )
    return batch.batch_no, success_count, duplicate_count


def push_mail_accounts(
    db: Session,
    client: DesktopClient,
    batch_name: str,
    items: list[PushMailItem],
) -> tuple[str, int, int]:
    request_id = uuid4().hex
    batch = SyncBatch(
        batch_no=f"MAIL{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        batch_type="mail_push",
        client_id=client.id,
        source="desktop",
        total_count=len(items),
        success_count=0,
        duplicate_count=0,
    )
    db.add(batch)
    db.flush()

    success_count = 0
    duplicate_count = 0
    seen_emails: set[str] = set()
    for item in items:
        normalized_email = str(item.email or "").strip().casefold()
        normalized_mode = str(item.receive_mode or "").strip().lower()
        if not normalized_email:
            continue
        if normalized_mode not in {"official", "xiaoshuidi"}:
            continue
        if normalized_email in seen_emails:
            duplicate_count += 1
            continue
        seen_emails.add(normalized_email)

        exists = find_mail_account_by_email(db, item.email)
        if exists:
            duplicate_count += 1
            continue

        account = MailAccount(
            email=item.email.strip(),
            status="idle",
            remark=item.remark,
        )
        db.add(account)
        db.flush()

        db.add(
            MailCredential(
                mail_account_id=account.id,
                password_enc=encrypt_text(item.password),
                receive_mode=normalized_mode,
                client_id=item.client_id,
                access_token=item.access_token,
                raw_line=item.raw_line,
            )
        )
        reconcile_mail_account_status(db, account)

        write_audit_log(
            db=db,
            operator_type="desktop_client",
            operator_id=client.id,
            action="push_mail_account",
            target_type="mail_account",
            target_id=account.id,
            details={"email": account.email, "batch_name": batch_name, "receive_mode": normalized_mode},
        )
        success_count += 1

    batch.success_count = success_count
    batch.duplicate_count = duplicate_count
    db.add(
        SyncLog(
            client_id=client.id,
            action="push_mail",
            request_id=request_id,
            payload_count=len(items),
            success_count=success_count,
            failed_count=len(items) - success_count - duplicate_count,
            message=f"Pushed {success_count} mail accounts from {batch_name}",
        )
    )
    return batch.batch_no, success_count, duplicate_count
