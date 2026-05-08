from __future__ import annotations

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover
    curl_requests = None

REQUEST_TIMEOUT = 30


def has_curl_requests() -> bool:
    return bool(curl_requests)


def refresh_access_token(
    *,
    token_url: str,
    client_id: str,
    refresh_token: str,
    scope: str,
) -> str:
    if not curl_requests:
        raise RuntimeError("当前环境缺少 OAuth 所需依赖 curl_cffi")
    if not client_id or not refresh_token:
        raise RuntimeError("缺少 client_id 或 refresh_token")

    payload = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if scope:
        payload["scope"] = scope

    response = curl_requests.post(
        token_url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=REQUEST_TIMEOUT,
        impersonate="chrome110",
    )
    if response.status_code != 200:
        raise RuntimeError(f"OAuth 刷新 token 失败: HTTP {response.status_code} {response.text[:240]}")
    data = response.json()
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("OAuth 刷新 token 成功但未返回 access_token")
    return access_token
