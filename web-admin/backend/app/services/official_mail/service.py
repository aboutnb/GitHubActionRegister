from __future__ import annotations

import hashlib
import logging

from app.schemas.mail import MailMessageItem

from .graph_fetcher import fetch_official_via_graph_api
from .imap_fetcher import IMAP_OLD_HOST, IMAP_NEW_HOST, fetch_official_via_imap
from .models import OfficialFetchedMessage, OfficialMailAccount
from .oauth import has_curl_requests
from .text_utils import (
    build_preview,
    format_received_at_beijing,
    format_received_at_utc,
    pick_recipient,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTLOOK_CLIENT_ID = "24d9a0ed-8787-4584-883c-2fd79308940a"


def fetch_official_mail_messages(
    *,
    email: str,
    password: str,
    client_id: str | None,
    refresh_token: str | None,
) -> dict[str, object]:
    account = OfficialMailAccount(
        email=email.strip().lower(),
        password=password,
        client_id=(client_id or DEFAULT_OUTLOOK_CLIENT_ID).strip() or None,
        refresh_token=(refresh_token or "").strip() or None,
    )
    if not account.password and not account.has_oauth:
        raise ValueError("官方收件缺少密码或 OAuth 凭证")

    errors: list[str] = []
    fetchers: list[tuple[str, callable[[], list[OfficialFetchedMessage]]]] = []
    if account.has_oauth and has_curl_requests():
        fetchers.extend(
            [
                ("graph_api", lambda: fetch_official_via_graph_api(account)),
                ("imap_new", lambda: fetch_official_via_imap(account, host=IMAP_NEW_HOST, use_oauth=True)),
            ]
        )
    if account.password or account.has_oauth:
        fetchers.append(
            ("imap_old", lambda: fetch_official_via_imap(account, host=IMAP_OLD_HOST, use_oauth=account.has_oauth))
        )

    for provider_name, fetcher in fetchers:
        try:
            raw_messages = fetcher()
            normalized = normalize_official_messages(raw_messages, recipient=email, provider=provider_name)
            note = (
                "官方收件支持返回多封邮件，当前展示最近邮件列表；已自动尝试 Graph API / IMAP 取件。"
                if normalized
                else "官方收件当前未取到邮件，请确认该邮箱最近是否已收到邮件。"
            )
            return {
                "provider": provider_name,
                "supports_history": True,
                "note": note,
                "messages": normalized,
            }
        except Exception as exc:
            logger.warning("[%s] official provider %s failed: %s", email, provider_name, exc)
            errors.append(f"{provider_name}: {exc}")

    raise RuntimeError("官方收件失败: " + "; ".join(errors or ["未找到可用的取件方式"]))


def normalize_official_messages(
    messages: list[OfficialFetchedMessage],
    *,
    recipient: str,
    provider: str,
) -> list[MailMessageItem]:
    sorted_messages = sorted(
        list(messages),
        key=lambda item: item.received_timestamp or 0,
        reverse=True,
    )
    items: list[MailMessageItem] = []
    for message in sorted_messages[:20]:
        content_text = (message.body or "").strip() or None
        items.append(
            MailMessageItem(
                id=message.id
                or f"{provider}-{hashlib.sha1((message.subject + message.sender + str(message.received_timestamp)).encode('utf-8')).hexdigest()[:16]}",
                received_at_utc=format_received_at_utc(message.received_at),
                received_at_beijing=format_received_at_beijing(message.received_at),
                subject=message.subject or None,
                sender=message.sender or None,
                recipient=pick_recipient(message.recipients, fallback=recipient),
                content_preview=build_preview(
                    content_text=content_text or "",
                    subject=message.subject or None,
                    sender=message.sender or None,
                ),
                content_text=content_text,
                content_html=None,
            )
        )
    return items
