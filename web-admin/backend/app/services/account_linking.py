from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.github_account import GitHubAccount
from app.models.mail_account import MailAccount


def normalize_account_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def find_mail_account_by_email(db: Session, email: str | None) -> MailAccount | None:
    normalized_email = normalize_account_key(email)
    if not normalized_email:
        return None
    return (
        db.query(MailAccount)
        .filter(func.lower(MailAccount.email) == normalized_email)
        .first()
    )


def sync_github_account_binding(db: Session, github_account: GitHubAccount) -> None:
    if github_account.bind_mail_account_id:
        bound_account = db.query(MailAccount).filter(MailAccount.id == github_account.bind_mail_account_id).first()
        if bound_account:
            normalized_bound_email = normalize_account_key(bound_account.email)
            if not github_account.email:
                github_account.email = bound_account.email
            elif normalize_account_key(github_account.email) != normalized_bound_email:
                github_account.bind_mail_account_id = None

    if github_account.bind_mail_account_id:
        return

    mail_account = find_mail_account_by_email(db, github_account.email)
    if mail_account:
        github_account.bind_mail_account_id = mail_account.id


def reconcile_mail_account_status(db: Session, mail_account: MailAccount) -> str:
    current_status = (mail_account.status or "idle").strip().lower()
    if current_status == "disabled":
        return mail_account.status

    normalized_email = normalize_account_key(mail_account.email)
    has_registered_reference = bool(
        db.query(GitHubAccount.id)
        .filter(
            or_(
                GitHubAccount.bind_mail_account_id == mail_account.id,
                func.lower(GitHubAccount.email) == normalized_email,
            )
        )
        .first()
        if normalized_email
        else db.query(GitHubAccount.id)
        .filter(GitHubAccount.bind_mail_account_id == mail_account.id)
        .first()
    )

    if has_registered_reference:
        mail_account.status = "registered"
        mail_account.lease_client_id = None
        mail_account.lease_token = None
        mail_account.lease_expires_at = None
    else:
        mail_account.status = "idle"
    return mail_account.status


def sync_mail_status_from_github_refs(
    db: Session,
    *,
    mail_account_ids: Iterable[int | None] = (),
    emails: Iterable[str | None] = (),
) -> None:
    affected_ids: set[int] = {int(item) for item in mail_account_ids if item}

    for email in emails:
        mail_account = find_mail_account_by_email(db, email)
        if mail_account:
            affected_ids.add(mail_account.id)

    if not affected_ids:
        return

    for mail_id in affected_ids:
        mail_account = db.query(MailAccount).filter(MailAccount.id == mail_id).first()
        if mail_account:
            reconcile_mail_account_status(db, mail_account)
