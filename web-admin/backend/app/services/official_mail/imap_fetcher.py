from __future__ import annotations

import imaplib
from email.utils import parsedate_to_datetime

from .models import OfficialFetchedMessage, OfficialMailAccount
from .oauth import refresh_access_token
from .text_utils import decode_email_header, ensure_email_message, extract_imap_body

REQUEST_TIMEOUT = 30
IMAP_PORT = 993
IMAP_OLD_HOST = "outlook.office365.com"
IMAP_NEW_HOST = "outlook.live.com"
LIVE_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
CONSUMERS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
IMAP_SEARCH_MAILBOXES = [
    "INBOX",
    "Junk",
    "Junk Email",
    "Junk E-mail",
    "Spam",
    "Deleted Items",
    "Trash",
    "Clutter",
    "Archive",
]


def fetch_official_via_imap(
    account: OfficialMailAccount,
    *,
    host: str,
    use_oauth: bool,
) -> list[OfficialFetchedMessage]:
    conn = imaplib.IMAP4_SSL(host, IMAP_PORT, timeout=REQUEST_TIMEOUT)
    try:
        if use_oauth and account.has_oauth:
            try:
                token_url = LIVE_TOKEN_URL if host == IMAP_OLD_HOST else CONSUMERS_TOKEN_URL
                scope = "" if host == IMAP_OLD_HOST else "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
                access_token = refresh_access_token(
                    token_url=token_url,
                    client_id=account.client_id or "",
                    refresh_token=account.refresh_token or "",
                    scope=scope,
                )
                auth_string = f"user={account.email}\x01auth=Bearer {access_token}\x01\x01"
                conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
            except Exception:
                if account.password and host == IMAP_OLD_HOST:
                    conn.login(account.email, account.password)
                else:
                    raise
        else:
            conn.login(account.email, account.password)

        messages: list[OfficialFetchedMessage] = []
        seen_ids: set[str] = set()
        for mailbox in IMAP_SEARCH_MAILBOXES:
            try:
                status, _ = conn.select(mailbox, readonly=True)
                if status != "OK":
                    continue
                status, data = conn.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    continue

                ids = data[0].split()
                for msg_id in ids[-20:][::-1]:
                    message = fetch_imap_message(conn, msg_id)
                    if not message:
                        continue
                    dedupe_key = message.id or f"{mailbox}:{msg_id.decode(errors='ignore')}"
                    if dedupe_key in seen_ids:
                        continue
                    seen_ids.add(dedupe_key)
                    messages.append(message)
            except Exception:
                continue
        return messages
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def fetch_imap_message(conn: imaplib.IMAP4_SSL, msg_id: bytes) -> OfficialFetchedMessage | None:
    status, data = conn.fetch(msg_id, "(RFC822)")
    if status != "OK" or not data:
        return None

    raw = b""
    for part in data:
        if isinstance(part, tuple) and len(part) > 1:
            raw = part[1]
            break
    if not raw:
        return None

    msg = ensure_email_message(raw)
    subject = decode_email_header(msg.get("Subject", ""))
    sender = decode_email_header(msg.get("From", ""))
    recipients = [
        value
        for value in (
            decode_email_header(msg.get("To", "")),
            decode_email_header(msg.get("Delivered-To", "")),
            decode_email_header(msg.get("X-Original-To", "")),
        )
        if value
    ]
    body = extract_imap_body(msg)
    received_at = None
    received_timestamp = 0
    date_str = decode_email_header(msg.get("Date", ""))
    try:
        if date_str:
            received_at = parsedate_to_datetime(date_str)
            received_timestamp = int(received_at.timestamp())
    except Exception:
        pass

    return OfficialFetchedMessage(
        id=msg.get("Message-ID", "") or "",
        subject=subject,
        sender=sender,
        recipients=recipients,
        body=body,
        received_at=received_at,
        received_timestamp=received_timestamp,
    )
