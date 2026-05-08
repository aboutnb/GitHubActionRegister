from __future__ import annotations

import email
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from html import unescape

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
BLOCK_TAG_RE = re.compile(
    r"</?(?:br|p|div|tr|li|td|th|table|h[1-6]|section|article)\b[^>]*>",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
INLINE_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINE_RE = re.compile(r"\n{3,}")


def decode_email_header(header: str) -> str:
    if not header:
        return ""
    parts: list[str] = []
    for chunk, encoding in decode_header(header):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts).strip()


def html_to_text(value: str) -> str:
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


def extract_imap_body(msg) -> str:
    texts: list[str] = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if "<html" in text.lower():
            text = html_to_text(text)
        texts.append(text)
    combined = " ".join(texts)
    return re.sub(r"\s+", " ", unescape(combined)).strip()


def build_preview(*, content_text: str, subject: str | None, sender: str | None) -> str | None:
    source = content_text or subject or sender or ""
    if not source:
        return None
    compact = " ".join(source.split())
    if len(compact) <= 140:
        return compact
    return f"{compact[:137]}..."


def pick_recipient(recipients: list[str], *, fallback: str) -> str:
    for value in recipients:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return fallback


def format_received_at_utc(value: datetime | None) -> str | None:
    if not value:
        return None
    dt = _ensure_tz(value).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_received_at_beijing(value: datetime | None) -> str | None:
    if not value:
        return None
    beijing = timezone(timedelta(hours=8))
    dt = _ensure_tz(value).astimezone(beijing)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure_email_message(raw: bytes):
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return email.message_from_bytes(raw)


def _ensure_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
