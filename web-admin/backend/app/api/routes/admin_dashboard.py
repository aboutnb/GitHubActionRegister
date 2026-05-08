from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.desktop_client import DesktopClient
from app.models.github_account import GitHubAccount
from app.models.mail_account import MailAccount
from app.models.sync_batch import SyncBatch
from app.models.sync_log import SyncLog
from app.models.web_user import WebUser
from app.schemas.admin import DashboardResponse
from app.utils.datetime import format_datetime

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


def _build_day_series(days: int = 7) -> list[datetime]:
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return [today - timedelta(days=offset) for offset in reversed(range(days))]


def _normalize_daily_counts(rows: list[tuple[datetime, int]], day_keys: list[str]) -> dict[str, int]:
    values: dict[str, int] = {}
    for day_value, count in rows:
        day_text = day_value.astimezone().strftime("%Y-%m-%d")
        values[day_text] = count
    return {day_key: values.get(day_key, 0) for day_key in day_keys}


@router.get("/summary", response_model=DashboardResponse)
def summary(
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    total_mail = db.query(func.count(MailAccount.id)).scalar() or 0
    idle_mail = db.query(func.count(MailAccount.id)).filter(MailAccount.status == "idle").scalar() or 0
    registered_mail = db.query(func.count(MailAccount.id)).filter(MailAccount.status == "registered").scalar() or 0
    used_mail = db.query(func.count(MailAccount.id)).filter(MailAccount.status == "used").scalar() or 0
    total_github = db.query(func.count(GitHubAccount.id)).scalar() or 0
    active_github = (
        db.query(func.count(GitHubAccount.id)).filter(GitHubAccount.status == "active").scalar() or 0
    )
    total_clients = db.query(func.count(DesktopClient.id)).scalar() or 0
    active_clients = (
        db.query(func.count(DesktopClient.id)).filter(DesktopClient.status == "active").scalar() or 0
    )
    recent_batches = (
        db.query(SyncBatch).order_by(SyncBatch.id.desc()).limit(5).all()
    )
    recent_audits = (
        db.query(AuditLog).order_by(AuditLog.id.desc()).limit(5).all()
    )
    recent_sync_logs = (
        db.query(SyncLog).order_by(SyncLog.id.desc()).limit(5).all()
    )
    day_series = _build_day_series(7)
    day_keys = [item.strftime("%Y-%m-%d") for item in day_series]
    day_start = day_series[0]
    mail_day = func.date_trunc("day", MailAccount.created_at)
    github_day = func.date_trunc("day", GitHubAccount.created_at)
    sync_day = func.date_trunc("day", SyncLog.created_at)

    mail_rows = (
        db.query(mail_day, func.count(MailAccount.id))
        .filter(MailAccount.created_at >= day_start)
        .group_by(mail_day)
        .all()
    )
    github_rows = (
        db.query(github_day, func.count(GitHubAccount.id))
        .filter(GitHubAccount.created_at >= day_start)
        .group_by(github_day)
        .all()
    )
    sync_rows = (
        db.query(
            sync_day,
            func.coalesce(func.sum(SyncLog.payload_count), 0),
            func.coalesce(func.sum(SyncLog.success_count), 0),
            func.count(SyncLog.id),
        )
        .filter(SyncLog.created_at >= day_start)
        .group_by(sync_day)
        .all()
    )

    mail_daily = _normalize_daily_counts(mail_rows, day_keys)
    github_daily = _normalize_daily_counts(github_rows, day_keys)
    sync_payload_daily: dict[str, int] = {}
    sync_success_daily: dict[str, int] = {}
    sync_count_daily: dict[str, int] = {}
    for day_key in day_keys:
        sync_payload_daily[day_key] = 0
        sync_success_daily[day_key] = 0
        sync_count_daily[day_key] = 0
    for day_value, payload_count, success_count, sync_count in sync_rows:
        key = day_value.astimezone().strftime("%Y-%m-%d")
        sync_payload_daily[key] = int(payload_count or 0)
        sync_success_daily[key] = int(success_count or 0)
        sync_count_daily[key] = int(sync_count or 0)

    return DashboardResponse(
        total_mail_accounts=total_mail,
        idle_mail_accounts=idle_mail,
        registered_mail_accounts=registered_mail,
        used_mail_accounts=used_mail,
        total_github_accounts=total_github,
        active_github_accounts=active_github,
        total_clients=total_clients,
        active_clients=active_clients,
        recent_batches=[
            {
                "batch_no": item.batch_no,
                "batch_type": item.batch_type,
                "source": item.source,
                "created_at": format_datetime(item.created_at),
            }
            for item in recent_batches
        ],
        recent_audits=[
            {
                "action": item.action,
                "target_type": item.target_type,
                "target_id": item.target_id,
                "created_at": format_datetime(item.created_at),
            }
            for item in recent_audits
        ],
        recent_sync_logs=[
            {
                "action": item.action,
                "message": item.message,
                "created_at": format_datetime(item.created_at),
            }
            for item in recent_sync_logs
        ],
        asset_trends=[
            {
                "date": day_key,
                "mail_created": mail_daily[day_key],
                "github_created": github_daily[day_key],
            }
            for day_key in day_keys
        ],
        sync_trends=[
            {
                "date": day_key,
                "sync_requests": sync_payload_daily[day_key],
                "sync_success": sync_success_daily[day_key],
                "sync_runs": sync_count_daily[day_key],
            }
            for day_key in day_keys
        ],
    )
