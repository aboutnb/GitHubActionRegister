from __future__ import annotations

from datetime import datetime, timedelta
import json
from uuid import uuid4
from urllib.parse import quote
from urllib import error as urlerror
from urllib import request as urlrequest
from sqlalchemy.orm import Session

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover
    curl_requests = None

from app.models.github_account import GitHubAccount
from app.models.github_health_check_config import GitHubHealthCheckConfig
from app.models.sync_batch import SyncBatch
from app.services.audit import write_audit_log
from app.utils.datetime import format_datetime


DEFAULT_CRON_EXPRESSION = "0 0 1,15 * *"
DEFAULT_ACCOUNTS_PER_PROXY = 15
DEFAULT_TIMEOUT_SECONDS = 10
MAX_ACCOUNTS_PER_PROXY = 20
MIN_CRON_INTERVAL_DAYS = 14
HEALTH_STATUSES = {"unknown", "alive", "not_found", "error"}


class CronExpressionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now().astimezone()


def _build_batch_no() -> str:
    return f"GHHC{_now().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6].upper()}"


def _derive_github_username(email: str | None, github_username: str | None = None) -> str:
    username = str(github_username or "").strip()
    if username:
        return username.split("@", 1)[0].strip()
    email_value = str(email or "").strip()
    if not email_value:
        return ""
    return email_value.split("@", 1)[0].strip()


def _clamp_accounts_per_proxy(value: int | None) -> int:
    try:
        parsed = int(value or DEFAULT_ACCOUNTS_PER_PROXY)
    except (TypeError, ValueError):
        parsed = DEFAULT_ACCOUNTS_PER_PROXY
    return max(1, min(MAX_ACCOUNTS_PER_PROXY, parsed))


def _clamp_timeout(value: int | None) -> int:
    try:
        parsed = int(value or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        parsed = DEFAULT_TIMEOUT_SECONDS
    return max(2, min(60, parsed))


def normalize_proxy_pool(proxy_urls: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in proxy_urls or []:
        for part in str(raw or "").replace(",", "\n").replace(";", "\n").splitlines():
            value = part.strip()
            if not value:
                continue
            if "://" not in value:
                value = f"http://{value}"
            if value not in seen:
                normalized.append(value)
                seen.add(value)
    return normalized


def parse_proxy_pool_text(proxy_pool: str | None) -> list[str]:
    return normalize_proxy_pool((proxy_pool or "").splitlines())


def serialize_proxy_pool(proxy_urls: list[str] | tuple[str, ...] | None) -> str | None:
    normalized = normalize_proxy_pool(list(proxy_urls or []))
    return "\n".join(normalized) if normalized else None


def _parse_cron_number(value: str, minimum: int, maximum: int, field_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CronExpressionError(f"{field_name} 字段包含非法数字：{value}") from exc
    if parsed < minimum or parsed > maximum:
        raise CronExpressionError(f"{field_name} 字段超出范围：{value}")
    return parsed


def _parse_cron_field(field: str, minimum: int, maximum: int, field_name: str) -> set[int]:
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise CronExpressionError(f"{field_name} 字段为空")

        step = 1
        base = token
        if "/" in token:
            base, step_raw = token.split("/", 1)
            step = _parse_cron_number(step_raw, 1, maximum, field_name)

        if base in {"*", "?"}:
            start, end = minimum, maximum
        elif "-" in base:
            start_raw, end_raw = base.split("-", 1)
            start = _parse_cron_number(start_raw, minimum, maximum, field_name)
            end = _parse_cron_number(end_raw, minimum, maximum, field_name)
        else:
            start = _parse_cron_number(base, minimum, maximum, field_name)
            end = maximum if "/" in token else start

        if start > end:
            raise CronExpressionError(f"{field_name} 字段区间无效：{token}")
        values.update(range(start, end + 1, step))

    return values


def get_next_cron_run(cron_expression: str, after: datetime | None = None) -> datetime:
    expression = str(cron_expression or "").strip()
    fields = expression.split()
    if len(fields) != 5:
        raise CronExpressionError("cron 表达式需要 5 段，例如 0 0 1,15 * *")

    minutes = _parse_cron_field(fields[0], 0, 59, "分钟")
    hours = _parse_cron_field(fields[1], 0, 23, "小时")
    days = _parse_cron_field(fields[2], 1, 31, "日期")
    months = _parse_cron_field(fields[3], 1, 12, "月份")
    weekdays = {
        0 if value == 7 else value
        for value in _parse_cron_field(fields[4], 0, 7, "星期")
    }

    cursor = (after or _now()).astimezone()
    candidate = cursor.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        cron_weekday = (candidate.weekday() + 1) % 7
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.day in days
            and candidate.month in months
            and cron_weekday in weekdays
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise CronExpressionError("cron 表达式一年内没有可执行时间")


def validate_cron_interval(cron_expression: str) -> str:
    expression = str(cron_expression or "").strip() or DEFAULT_CRON_EXPRESSION
    first_run = get_next_cron_run(expression, _now())
    second_run = get_next_cron_run(expression, first_run)
    min_interval = timedelta(days=MIN_CRON_INTERVAL_DAYS)
    if second_run - first_run < min_interval:
        raise CronExpressionError("测活频率不能小于半个月，请选择每半个月或每月")
    return expression


def get_health_check_config(db: Session, create: bool = False) -> GitHubHealthCheckConfig | None:
    config = db.query(GitHubHealthCheckConfig).order_by(GitHubHealthCheckConfig.id.asc()).first()
    if config or not create:
        return config
    config = GitHubHealthCheckConfig(
        enabled=False,
        cron_expression=DEFAULT_CRON_EXPRESSION,
        accounts_per_proxy=DEFAULT_ACCOUNTS_PER_PROXY,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        next_run_at=get_next_cron_run(DEFAULT_CRON_EXPRESSION, _now()),
    )
    db.add(config)
    db.flush()
    return config


def _fetch_github_user(
    *,
    username: str,
    proxy_url: str | None,
    timeout_seconds: int,
) -> tuple[str, int | None, str | None]:
    url = f"https://api.github.com/users/{quote(username, safe='')}"
    if curl_requests:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
        try:
            response = curl_requests.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "GitHubAssetCenter/1.0",
                },
                proxies=proxies,
                timeout=timeout_seconds,
                impersonate="chrome110",
            )
        except Exception as exc:
            return "error", None, str(exc)[:300]

        status_code = response.status_code
        if status_code == 404:
            return "not_found", status_code, "GitHub 404 Not Found"
        if status_code != 200:
            return "error", status_code, f"GitHub HTTP {status_code}"
        try:
            body = response.json()
        except Exception:
            body = {}
        if isinstance(body, dict) and str(body.get("login") or "").strip():
            return "alive", status_code, None
        return "error", status_code, f"GitHub HTTP {status_code}: 未返回有效用户信息"

    handlers = []
    if proxy_url:
        handlers.append(urlrequest.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    else:
        # Avoid accidentally using OS-level proxies when the pool is intentionally empty.
        handlers.append(urlrequest.ProxyHandler({}))
    opener = urlrequest.build_opener(*handlers)
    request = urlrequest.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHubAssetCenter/1.0",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status_code = response.getcode()
            raw_body = response.read(1024 * 1024).decode("utf-8", errors="replace")
    except Exception as exc:
        if isinstance(exc, urlerror.HTTPError):
            if exc.code == 404:
                return "not_found", exc.code, "GitHub 404 Not Found"
            return "error", exc.code, f"GitHub HTTP {exc.code}"
        return "error", None, str(exc)[:300]

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        body = {}

    if isinstance(body, dict) and str(body.get("login") or "").strip():
        return "alive", status_code, None
    if status_code == 404:
        return "not_found", status_code, "GitHub 404 Not Found"
    return "error", status_code, f"GitHub HTTP {status_code}: 未返回有效用户信息"


def _query_health_accounts(db: Session, account_ids: list[int] | None) -> list[GitHubAccount]:
    query = db.query(GitHubAccount)
    if account_ids:
        return (
            query.filter(GitHubAccount.id.in_(account_ids))
            .order_by(GitHubAccount.id.asc())
            .all()
        )
    return (
        query.order_by(
            GitHubAccount.health_checked_at.isnot(None),
            GitHubAccount.health_checked_at.asc(),
            GitHubAccount.id.asc(),
        )
        .all()
    )


def perform_github_health_check(
    db: Session,
    *,
    account_ids: list[int] | None = None,
    proxy_urls: list[str] | None = None,
    accounts_per_proxy: int | None = None,
    timeout_seconds: int | None = None,
    source: str = "web",
    current_user_id: int | None = None,
) -> dict:
    accounts = _query_health_accounts(db, account_ids)
    proxies = normalize_proxy_pool(proxy_urls)
    per_proxy = _clamp_accounts_per_proxy(accounts_per_proxy)
    timeout = _clamp_timeout(timeout_seconds)
    proxy_capacity = len(proxies) * per_proxy if proxies else len(accounts)
    accounts_to_check = accounts[:proxy_capacity]
    skipped_accounts = accounts[proxy_capacity:]

    batch = SyncBatch(
        batch_no=_build_batch_no(),
        batch_type="github_health_check",
        source=source,
        total_count=len(accounts),
        success_count=0,
        duplicate_count=0,
        created_by=current_user_id,
    )
    db.add(batch)
    db.flush()

    alive_count = 0
    not_found_count = 0
    error_count = 0
    items: list[dict] = []

    for index, account in enumerate(accounts_to_check):
        proxy_url = proxies[index // per_proxy] if proxies else None
        username = _derive_github_username(account.email, account.github_username)
        checked_at = _now()
        if not username:
            health_status, http_status, health_error = "error", None, "缺少 GitHub 用户名"
        else:
            account.github_username = username
            health_status, http_status, health_error = _fetch_github_user(
                username=username,
                proxy_url=proxy_url,
                timeout_seconds=timeout,
            )

        account.health_status = health_status
        account.health_checked_at = checked_at
        account.health_http_status = http_status
        account.health_error = health_error

        if health_status == "alive":
            alive_count += 1
        elif health_status == "not_found":
            not_found_count += 1
        else:
            error_count += 1

        items.append(
            {
                "id": account.id,
                "email": account.email,
                "github_username": username or None,
                "health_status": health_status,
                "health_http_status": http_status,
                "health_error": health_error,
                "health_checked_at": format_datetime(checked_at),
                "proxy_used": bool(proxy_url),
            }
        )

    for account in skipped_accounts:
        items.append(
            {
                "id": account.id,
                "email": account.email,
                "github_username": _derive_github_username(account.email, account.github_username) or None,
                "health_status": "skipped",
                "health_http_status": None,
                "health_error": "代理池容量不足，本次未测活",
                "health_checked_at": None,
                "proxy_used": False,
            }
        )

    batch.success_count = alive_count
    batch.duplicate_count = len(accounts) - alive_count
    if current_user_id is not None:
        write_audit_log(
            db,
            operator_type="web_user",
            operator_id=current_user_id,
            action="github_health_check",
            target_type="github_account",
            target_id=None,
            details={
                "batch_no": batch.batch_no,
                "total_count": len(accounts),
                "checked_count": len(accounts_to_check),
                "alive_count": alive_count,
                "not_found_count": not_found_count,
                "error_count": error_count,
                "skipped_count": len(skipped_accounts),
                "proxy_count": len(proxies),
                "accounts_per_proxy": per_proxy,
            },
        )

    return {
        "batch_no": batch.batch_no,
        "total_count": len(accounts),
        "checked_count": len(accounts_to_check),
        "alive_count": alive_count,
        "not_found_count": not_found_count,
        "error_count": error_count,
        "skipped_count": len(skipped_accounts),
        "items": items,
    }
