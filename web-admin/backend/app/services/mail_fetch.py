from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas.mail import MailMessageItem
from app.services.official_mail import fetch_official_mail_messages

XIAOSHUIDI_API_URL = "https://api.bujidian.com/getMailInfo"
REQUEST_TIMEOUT = 30

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
BLOCK_TAG_RE = re.compile(
    r"</?(?:br|p|div|tr|li|td|th|table|h[1-6]|section|article)\b[^>]*>",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
INLINE_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINE_RE = re.compile(r"\n{3,}")


def fetch_mail_messages(
    *,
    email: str,
    password: str,
    receive_mode: str | None,
    client_id: str | None = None,
    access_token: str | None = None,
) -> dict[str, object]:
    mode = (receive_mode or "").strip().lower()
    if mode == "xiaoshuidi":
        return _fetch_xiaoshuidi_messages(email=email, password=password)
    if mode == "official":
        return fetch_official_mail_messages(
            email=email,
            password=password,
            client_id=client_id,
            refresh_token=access_token,
        )
    raise ValueError("当前邮箱未配置正确的收件方式")


def fetch_latest_mail_info(
    *,
    email: str,
    password: str,
    receive_mode: str | None,
    client_id: str | None = None,
    access_token: str | None = None,
    sender: str | None = None,
) -> dict[str, object]:
    result = fetch_mail_messages(
        email=email,
        password=password,
        receive_mode=receive_mode,
        client_id=client_id,
        access_token=access_token,
    )
    messages = list(result.get("messages") or [])
    provider = str(result.get("provider") or "")
    mode = (receive_mode or "").strip().lower() or None
    sender_filter = (sender or "").strip().lower()
    if sender_filter:
        messages = [
            item for item in messages
            if (item.sender or "").strip().lower() == sender_filter
        ]
    if not messages:
        if sender_filter:
            note = f"未找到发件人为 {sender} 的邮件"
        else:
            note = str(result.get("note") or "暂无邮件")
        return {
            "status": 0,
            "message": note,
            "provider": provider or None,
            "receive_mode": mode,
        }

    message = messages[0]
    content_html = message.content_html or ""
    content_text = message.content_text or ""
    return {
        "status": 1,
        "message": {
            "id": message.id,
            "send_time_utc": message.received_at_utc,
            "send_time_beijing": message.received_at_beijing,
            "subject": message.subject,
            "sender": message.sender,
            "receiver": message.recipient,
            "content": content_html or content_text or None,
            "content_text": content_text or None,
        },
        "provider": provider or None,
        "receive_mode": mode,
    }


def _fetch_xiaoshuidi_messages(*, email: str, password: str) -> dict[str, object]:
    payload = _request_xiaoshuidi_latest_message(email=email, password=password)
    message = _normalize_xiaoshuidi_message(payload=payload, recipient=email)
    messages = [message] if message else []
    note = "小水滴接口当前仅返回最新一封邮件（最新邮件会从收件箱和垃圾箱中获取）。"
    if not messages:
        note = "当前未取到邮件。小水滴接口只支持返回最新一封邮件，请确认该邮箱最近是否已收到邮件。"
    return {
        "provider": "xiaoshuidi",
        "supports_history": False,
        "note": note,
        "messages": messages,
    }


def _request_xiaoshuidi_latest_message(*, email: str, password: str) -> dict | None:
    query = urlencode({"name": email, "pwd": password})
    request = Request(f"{XIAOSHUIDI_API_URL}?{query}", method="GET")
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if detail:
            raise RuntimeError(f"小水滴取件接口请求失败: HTTP {exc.code} {detail[:200]}") from exc
        raise RuntimeError(f"小水滴取件接口请求失败: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"小水滴取件接口连接失败: {exc.reason}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("小水滴取件接口返回了无法解析的响应") from exc

    if data.get("status") == 1:
        payload = data.get("message") or {}
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("小水滴取件接口返回的邮件数据格式不正确")

    provider_message = str(data.get("message") or data.get("msg") or "未知错误").strip()
    if _looks_like_no_mail(provider_message):
        return None
    raise RuntimeError(f"小水滴取件失败: {provider_message}")


def _normalize_xiaoshuidi_message(*, payload: dict | None, recipient: str) -> MailMessageItem | None:
    if not payload:
        return None

    subject = str(payload.get("subject") or "").strip() or None
    sender = str(payload.get("sender") or "").strip() or None
    received_at_utc = str(payload.get("send_time_utc") or "").strip() or None
    received_at_beijing = str(payload.get("send_time_beijing") or "").strip() or None
    content_html = str(payload.get("content") or "").strip() or None
    content_text = _html_to_text(content_html or "")
    content_preview = _build_preview(content_text=content_text, subject=subject, sender=sender)

    id_source = "|".join(
        [
            recipient,
            received_at_utc or "",
            received_at_beijing or "",
            subject or "",
            sender or "",
        ]
    )
    message_id = f"xsd-{hashlib.sha1(id_source.encode('utf-8')).hexdigest()[:16]}"

    return MailMessageItem(
        id=message_id,
        received_at_utc=received_at_utc,
        received_at_beijing=received_at_beijing,
        subject=subject,
        sender=sender,
        recipient=recipient,
        content_preview=content_preview,
        content_text=content_text or None,
        content_html=content_html,
    )


def _build_preview(*, content_text: str, subject: str | None, sender: str | None) -> str | None:
    source = content_text or subject or sender or ""
    if not source:
        return None
    compact = " ".join(source.split())
    if len(compact) <= 140:
        return compact
    return f"{compact[:137]}..."


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    text = SCRIPT_STYLE_RE.sub(" ", value)
    text = BLOCK_TAG_RE.sub("\n", text)
    text = TAG_RE.sub(" ", text)
    text = unescape(text).replace("\xa0", " ")
    text = INLINE_SPACE_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def _looks_like_no_mail(message: str) -> bool:
    lowered = message.lower()
    return any(
        keyword in lowered
        for keyword in (
            "暂无邮件",
            "暂无此邮件",
            "没有邮件",
            "未找到邮件",
            "找不到邮件",
            "mail not found",
            "no mail",
        )
    )
