from __future__ import annotations

from datetime import datetime

from .models import OfficialFetchedMessage, OfficialMailAccount
from .oauth import curl_requests, refresh_access_token

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_MESSAGE_FOLDERS = ["inbox", "junkemail", "deleteditems", "archive"]
COMMON_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
REQUEST_TIMEOUT = 30


def fetch_official_via_graph_api(account: OfficialMailAccount) -> list[OfficialFetchedMessage]:
    if not curl_requests:
        raise RuntimeError("当前环境缺少 Graph API 所需依赖 curl_cffi")
    if not account.has_oauth:
        raise RuntimeError("Graph API 需要 client_id 和 refresh_token")

    access_token = refresh_access_token(
        token_url=COMMON_TOKEN_URL,
        client_id=account.client_id or "",
        refresh_token=account.refresh_token or "",
        scope="https://graph.microsoft.com/.default",
    )

    messages: list[OfficialFetchedMessage] = []
    seen_ids: set[str] = set()
    for folder in GRAPH_MESSAGE_FOLDERS:
        response = curl_requests.get(
            f"{GRAPH_API_BASE}/me/mailFolders/{folder}/messages",
            params={
                "$top": 20,
                "$select": "id,subject,from,toRecipients,receivedDateTime,isRead,hasAttachments,bodyPreview,body",
                "$orderby": "receivedDateTime desc",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Prefer": "outlook.body-content-type='text'",
            },
            timeout=REQUEST_TIMEOUT,
            impersonate="chrome110",
        )
        if response.status_code == 401:
            raise RuntimeError("Graph API 鉴权失败，client_id 或 refresh_token 可能无效")
        if response.status_code != 200:
            continue

        for item in response.json().get("value", []):
            message = parse_graph_message(item)
            if not message or not message.id or message.id in seen_ids:
                continue
            seen_ids.add(message.id)
            messages.append(message)
    return messages


def parse_graph_message(item: dict) -> OfficialFetchedMessage | None:
    sender = item.get("from", {}).get("emailAddress", {}).get("address", "")
    recipients = [
        recipient.get("emailAddress", {}).get("address", "")
        for recipient in item.get("toRecipients", [])
        if recipient.get("emailAddress", {}).get("address", "")
    ]

    received_at = None
    received_timestamp = 0
    date_str = item.get("receivedDateTime", "")
    try:
        if date_str:
            received_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            received_timestamp = int(received_at.timestamp())
    except Exception:
        pass

    body_info = item.get("body", {}) or {}
    body = body_info.get("content", "") or item.get("bodyPreview", "")
    return OfficialFetchedMessage(
        id=item.get("id", "") or "",
        subject=item.get("subject", "") or "",
        sender=sender,
        recipients=recipients,
        body=body,
        received_at=received_at,
        received_timestamp=received_timestamp,
    )
