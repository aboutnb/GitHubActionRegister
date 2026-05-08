from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Optional

import requests


REQUEST_TIMEOUT = 30
REMOTE_BATCH_LIMIT = 100

CODE_RE = re.compile(r"\b(\d{6,8})\b")
HREF_RE = re.compile(r'href\s*=\s*["\']?(https?://[^\s"\'<>]+)', re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\"'\\)]+")


def _normalize_base_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("未配置客户端 API 地址")
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url


def _build_client_headers(api_token: str) -> dict[str, str]:
    token = (api_token or "").strip()
    if not token:
        raise RuntimeError("未配置客户端 API Token")
    return {"X-Api-Token": token}


def _parse_json_response(resp: requests.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"客户端 API 返回了无法解析的响应: HTTP {resp.status_code}") from exc

    if resp.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        raise RuntimeError(str(detail or f"客户端 API 请求失败: HTTP {resp.status_code}"))
    return data if isinstance(data, dict) else {}


def _build_raw_line(item: dict[str, Any]) -> str:
    email = str(item.get("email") or "").strip()
    password = str(item.get("password") or "").strip()
    receive_mode = str(item.get("receive_mode") or "").strip().lower()
    client_id = str(item.get("client_id") or "").strip()
    access_token = str(item.get("access_token") or "").strip()

    if receive_mode == "official" and client_id and access_token:
        return f"{email}----{password}----{client_id}----{access_token}"
    if client_id and access_token:
        return f"{email}----{password}----{client_id}----{access_token}"
    return f"{email}----{password}"


def pull_remote_mail_accounts(
    *,
    base_url: str,
    api_token: str,
    limit: int = 10,
    fetch_all: bool = False,
) -> list[dict[str, Any]]:
    base = _normalize_base_url(base_url)
    headers = _build_client_headers(api_token)
    batch_limit = REMOTE_BATCH_LIMIT if fetch_all else max(1, min(int(limit or 10), REMOTE_BATCH_LIMIT))

    items: list[dict[str, Any]] = []
    while True:
        resp = requests.get(
            f"{base}/client/mail-accounts/pull",
            headers=headers,
            params={"limit": batch_limit},
            timeout=REQUEST_TIMEOUT,
        )
        data = _parse_json_response(resp)
        batch = data.get("items") or []
        if not isinstance(batch, list):
            raise RuntimeError("客户端 API 返回的邮箱列表格式不正确")

        for item in batch:
            if not isinstance(item, dict):
                continue
            account = dict(item)
            account["source"] = "remote"
            account["raw"] = _build_raw_line(account)
            account["status"] = "等待"
            items.append(account)

        if not fetch_all or len(batch) < batch_limit:
            break
    return items


def get_remote_mail_info(
    *,
    base_url: str,
    account: dict[str, Any],
    sender: str | None = None,
) -> dict[str, Any]:
    base = _normalize_base_url(base_url)
    params: dict[str, Any] = {}

    mail_account_id = account.get("mail_account_id")
    if mail_account_id:
        params["mail_account_id"] = mail_account_id
    else:
        params["name"] = str(account.get("email") or "").strip()
        params["pwd"] = str(account.get("password") or "").strip()
        params["receive_mode"] = str(account.get("receive_mode") or "").strip() or "official"
        client_id = str(account.get("client_id") or "").strip()
        access_token = str(account.get("access_token") or "").strip()
        if client_id:
            params["client_id"] = client_id
        if access_token:
            params["token"] = access_token

    if sender:
        params["sender"] = sender

    resp = requests.get(
        f"{base}/client/mail/getMailInfo",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_json_response(resp)


def get_remote_verification_info(
    *,
    base_url: str,
    account: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    try:
        data = get_remote_mail_info(base_url=base_url, account=account)
    except Exception as exc:
        return None, f"客户端 API 取件异常: {exc}"

    if data.get("status") != 1:
        return None, str(data.get("message") or "未找到邮件")

    mail = data.get("message") or {}
    if not isinstance(mail, dict):
        return None, "客户端 API 返回的邮件数据格式不正确"

    subject = str(mail.get("subject") or "")
    sender = str(mail.get("sender") or "")
    content = str(mail.get("content") or mail.get("content_text") or "").replace("&amp;", "&")

    if "github" not in subject.lower() and "github" not in sender.lower():
        return None, f"最新邮件不是 GitHub 的（主题: {subject}，发件人: {sender}）"

    text = subject + "\n" + content
    for match in CODE_RE.finditer(text):
        return match.group(1), None

    for url in HREF_RE.findall(content):
        if "github.com" in url and ("account_verifications" in url or "verify" in url or "confirm" in url):
            return url, None

    for url in URL_RE.findall(content):
        if "github.com" in url and ("account_verifications" in url or "verify" in url or "confirm" in url):
            return url, None

    return None, f"邮件已取到，但未提取到 GitHub 验证码或验证链接（主题: {subject}）"


def push_github_result(
    *,
    base_url: str,
    api_token: str,
    github_login: str,
    github_password: str,
    totp_secret: str,
    bind_mail_account_id: int | None = None,
    bind_email: str | None = None,
    lease_token: str | None = None,
) -> dict[str, Any]:
    base = _normalize_base_url(base_url)
    headers = _build_client_headers(api_token)
    batch_name = f"desktop-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    payload = {
        "batch_name": batch_name,
        "items": [
            {
                "github_login": github_login,
                "github_username": github_login,
                "github_password": github_password,
                "totp_secret": totp_secret or "",
                "recovery_codes": [],
                "bind_mail_account_id": bind_mail_account_id,
                "bind_email": bind_email,
                "lease_token": lease_token,
            }
        ],
    }
    resp = requests.post(
        f"{base}/client/github-accounts/push",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_json_response(resp)
