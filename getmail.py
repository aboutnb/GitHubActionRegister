"""
使用 Microsoft Graph 读取 Outlook/Hotmail 邮件。
需在 .env.local 中配置 GRAPH_CLIENT_SECRET 等，并完成一次浏览器授权。
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# 环境加载（.env.local 覆盖 .env）
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        base = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(base, ".env"))
        load_dotenv(os.path.join(base, ".env.local"), override=True)
    except ImportError:
        pass


_load_dotenv()

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "507b3879-29db-41fb-9c09-d080180c6ae9")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "consumers")
# 必须与 Azure 应用注册里「重定向 URI」完全一致（不能混用 localhost 与 127.0.0.1）
GRAPH_REDIRECT_URI = os.environ.get("GRAPH_REDIRECT_URI", "http://localhost:8400/callback")
# Mail.Read 收件；User.Read 用于 /me 显示当前取信邮箱（诊断用）
GRAPH_SCOPES = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read offline_access"

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".graph_tokens.json")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

OAUTH_CALLBACK_HOST = "127.0.0.1"
OAUTH_CALLBACK_PORT = 8400
OAUTH_SERVER_TIMEOUT = 2.0
OAUTH_WAIT_STEP_SEC = 5
OAUTH_WAIT_MAX_STEPS = 24
OAUTH_WAIT_PROGRESS_STEP = 6

REQUEST_TIMEOUT = 30
TOKEN_REQUEST_TIMEOUT = (10, 20)  # connect, read

# 单次登录回调状态（模块级，供回调线程与主线程同步）
_auth_code: Optional[str] = None
_auth_error: Optional[str] = None
_auth_done = threading.Event()

# 同进程内复用 access_token，避免多次 refresh 导致 401（如先 list_messages 再 get_message 再 /me）
_cached_access_token: Optional[str] = None

# 可由上层（如 github_register_ui）注册一个回调，将 OAuth 授权 URL 在指定浏览器中打开
_auth_url_opener: Optional[callable] = None


def register_auth_url_opener(func: callable) -> None:
    """
    注册一个用于打开 OAuth 授权 URL 的回调。
    若未注册，则默认使用系统浏览器 webbrowser.open。

    典型用法：在 GitHub 注册流程中，将 Graph 授权页在 Bitbrowser 指纹浏览器里打开：

        from getmail import register_auth_url_opener

        def _open_in_ws(url: str) -> None:
            ...  # 用 playwright + CDP 在现有页面中 goto(url)

        register_auth_url_opener(_open_in_ws)
    """
    global _auth_url_opener
    _auth_url_opener = func


# ---------------------------------------------------------------------------
# OAuth 回调 HTTP 处理
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """处理 OAuth 重定向回调，路径含 callback 即视为回调。"""

    def do_GET(self) -> None:
        global _auth_code, _auth_error
        parsed = urlparse(self.path)
        if "callback" not in (parsed.path or ""):
            self._send(200, b"<body>Waiting for login redirect... If you already logged in, check the terminal.</body>")
            return
        qs = parse_qs(parsed.query)
        _auth_code = (qs.get("code") or [None])[0]
        _auth_error = (qs.get("error") or [None])[0]
        _auth_done.set()
        if _auth_code:
            print("Callback received, exchanging code for tokens...")
        if _auth_error:
            self._send(200, f"<body>Login failed: {_auth_error}. Close this page.</body>".encode("utf-8"))
        else:
            self._send(200, b"<body>Login OK. You can close this page and return to the terminal.</body>")

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Token 读写
# ---------------------------------------------------------------------------

def _load_tokens() -> Optional[dict[str, Any]]:
    if not os.path.isfile(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# token 文件只存 refresh_token / access_token / expires_in / tenant_id / client_id，
# 不存 client_secret（来自 .env.local）
_TOKEN_KEYS = frozenset({"refresh_token", "access_token", "expires_in", "tenant_id", "client_id"})


def _save_tokens(data: dict[str, Any]) -> None:
    merged: dict[str, Any] = {}
    if os.path.isfile(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                merged = json.load(f) or {}
        except Exception:
            pass
    merged.update(data)
    merged = {k: v for k, v in merged.items() if k in _TOKEN_KEYS}
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)


def set_current_account(
    refresh_token: str,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> None:
    """
    将指定 refresh_token 设为当前取信账号（写入本地 token 文件）。
    client_secret 只用 .env.local 里的 GRAPH_CLIENT_SECRET，不写入 token 文件。
    client_id 可通过此函数传入并写入 token 文件，用于覆盖默认的 GRAPH_CLIENT_ID，
    便于一台机器上针对不同邮箱使用不同的 Entra 应用。
    """
    payload: dict[str, Any] = {"refresh_token": refresh_token, "access_token": None, "expires_in": None}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if client_id:
        payload["client_id"] = client_id
    _save_tokens(payload)


def _token_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
) -> str:
    """用授权 code 换取 access_token，并持久化 refresh_token。"""
    print("Posting to Microsoft token endpoint...", flush=True)
    resp = requests.post(
        _token_url(tenant_id),
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": GRAPH_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=TOKEN_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in"),
    }
    if tokens.get("refresh_token"):
        _save_tokens(tokens)
    print("Token saved.", flush=True)
    return data["access_token"]


def _refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
) -> str:
    """用 refresh_token 刷新 access_token 并写回文件。"""
    resp = requests.post(
        _token_url(tenant_id),
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or refresh_token,
        "expires_in": data.get("expires_in"),
    }
    _save_tokens(tokens)
    return data["access_token"]


def _build_auth_url(client_id: str, tenant_id: str) -> str:
    """构造 OAuth 授权 URL。"""
    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": GRAPH_REDIRECT_URI,
        "scope": GRAPH_SCOPES,
        "response_mode": "query",
    }
    base = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    return base + "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in auth_params.items())


def _run_callback_server_until_done() -> None:
    """在后台线程启动本地 HTTP 服务，直到收到回调或超时。"""
    server = HTTPServer((OAUTH_CALLBACK_HOST, OAUTH_CALLBACK_PORT), _CallbackHandler)
    server.socket.settimeout(OAUTH_SERVER_TIMEOUT)

    def serve() -> None:
        while not _auth_done.is_set():
            try:
                server.handle_request()
            except (socket.timeout, OSError, BrokenPipeError):
                pass
        try:
            server.shutdown()
        except Exception:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()


def get_access_token() -> str:
    """
    获取用于调用 Graph 的 access_token。
    优先用本地缓存的 refresh_token 刷新；若无则启动本地服务，打开浏览器让用户登录一次，再交换 code。
    """
    saved = _load_tokens() or {}
    # client_secret 只用 .env.local，tokens.json 里不存、不读。
    # client_id 优先使用 token 文件中持久化的 client_id（来自 UI 粘贴行的第3段），
    # 若不存在则退回 .env.local 中的 GRAPH_CLIENT_ID。
    client_id = saved.get("client_id") or GRAPH_CLIENT_ID
    tenant_id = saved.get("tenant_id") or GRAPH_TENANT_ID
    client_secret = GRAPH_CLIENT_SECRET

    if not client_secret:
        raise ValueError(
            "Set env GRAPH_CLIENT_SECRET (client secret from Entra app registration). "
            "Do not commit the secret to Git."
        )
    global _cached_access_token
    if _cached_access_token and str(_cached_access_token).strip():
        return _cached_access_token
    if saved and saved.get("refresh_token"):
        try:
            token = _refresh_access_token(
                saved["refresh_token"], client_id, client_secret, tenant_id
            )
            if token and str(token).strip():
                _cached_access_token = token
                return token
            # refresh 返回了空 token，当作失败，走重新登录
        except Exception:
            _cached_access_token = None
            pass

    global _auth_code, _auth_error
    _auth_code = None
    _auth_error = None
    _auth_done.clear()

    url = _build_auth_url(client_id, tenant_id)
    _run_callback_server_until_done()
    # 脱敏显示：只显示前 8 位，方便在 Azure 里确认是「.env.local 里 GRAPH_CLIENT_ID 对应的应用」
    _mask = (client_id[:8] + "-****") if client_id and len(client_id) >= 8 else "****"
    print("Opening browser for Microsoft sign-in and consent...")
    print("当前使用的应用 client_id（.env.local 中 GRAPH_CLIENT_ID）：", _mask)
    print("若报 redirect_uri invalid，请在 Azure 里找到该应用，在「身份验证」→ 重定向 URI 中添加下面这行（一字不差）：")
    print("  ", GRAPH_REDIRECT_URI)
    print("若浏览器未自动打开，可复制下面完整 URL 手动打开：")
    print(url)
    print()
    # 若上层注册了自定义打开函数（例如在 Bitbrowser 指纹浏览器中打开），优先使用
    if _auth_url_opener:
        try:
            _auth_url_opener(url)
        except Exception as e:
            print(f"自定义授权页打开函数出错，将退回系统浏览器: {e}")
            webbrowser.open(url)
    else:
        webbrowser.open(url)

    for i in range(OAUTH_WAIT_MAX_STEPS):
        _auth_done.wait(timeout=OAUTH_WAIT_STEP_SEC)
        if _auth_done.is_set():
            break
        if (i + 1) % OAUTH_WAIT_PROGRESS_STEP == 0 and i > 0:
            print("Still waiting for redirect (complete sign-in in browser, or paste the URL above)...")

    time.sleep(0.3)
    if _auth_code:
        print("Exchanging code for tokens...", flush=True)
        token = _exchange_code_for_tokens(_auth_code, client_id, client_secret, tenant_id)
        if not token or not str(token).strip():
            raise RuntimeError("Microsoft 未返回有效 access_token，请重试。")
        _cached_access_token = token
        return token
    if _auth_error:
        raise RuntimeError(f"Login failed: {_auth_error}. Check redirect URI and app permissions.")
    raise RuntimeError(
        "No login callback received in 120s. Complete sign-in in the browser or try again."
    )


# ---------------------------------------------------------------------------
# Graph API 请求与邮件接口
# ---------------------------------------------------------------------------

def _request(
    method: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """携带 access_token 请求 Graph API。"""
    token = get_access_token()
    if not token or not str(token).strip():
        raise RuntimeError(
            "Access token 为空（refresh 可能失败或 refresh_token 与当前 .env.local 的 GRAPH_CLIENT_ID 不匹配）。"
            "请删除 .graph_tokens.json 后重新运行，在浏览器中重新登录。"
        )
    url = GRAPH_BASE + path
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    resp = requests.request(method, url, params=params, headers=h, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    if resp.text:
        return resp.json()
    return None


def get_current_account_email() -> str:
    """当前取信账号的邮箱地址（用于确认是否与注册邮箱一致）。若 401/网络异常则返回说明文字不抛错。"""
    try:
        me = _request("GET", "/me", params={"$select": "mail,userPrincipalName"})
        if not me:
            return ""
        return (me.get("mail") or me.get("userPrincipalName") or "").strip()
    except Exception as e:
        err = str(e).strip()
        # 401：当前 token 可能未包含 User.Read（旧 token 或首次只勾了 Mail.Read）。需重新登录拿新 token。
        if "401" in err or "Unauthorized" in err:
            return "(当前 token 无 User.Read，无法显示邮箱；收件正常。若 Azure 已勾 User.Read，请删除 .graph_tokens.json 后重新运行并登录，新 token 即可显示)"
        return f"(获取失败: {err})"


def list_messages(
    top: int = 25,
    folder: str = "inbox",
    select: Optional[str] = None,
    order_by: str = "receivedDateTime desc",
) -> dict[str, Any]:
    """
    列出当前用户邮箱中的邮件。
    :param top: 返回条数，1–1000
    :param folder: 文件夹，如 inbox、sentitems
    :param select: 要返回的字段
    :param order_by: 排序
    :return: 含 value 列表的 dict
    """
    path = f"/me/mailFolders/{folder}/messages"
    params: dict[str, Any] = {"$top": top, "$orderby": order_by}
    if select:
        params["$select"] = select
    return _request("GET", path, params=params) or {"value": []}


def get_message(message_id: str) -> dict[str, Any]:
    """获取单封邮件详情（含正文）。"""
    result = _request("GET", f"/me/messages/{message_id}")
    return result or {}


def get_inbox(top: int = 25) -> dict[str, Any]:
    """获取收件箱最近邮件。"""
    return list_messages(
        top=top,
        folder="inbox",
        select="id,subject,sender,receivedDateTime,isRead,bodyPreview",
        order_by="receivedDateTime desc",
    )


# 验证链接匹配：URL 中需含 github.com 且含下列任一关键词（放宽以兼容不同邮件模板）
VERIFICATION_LINK_KEYWORDS = (
    "verify", "confirm", "token", "signup", "email",
    "verification", "verif",  # verification link
)
LINK_RE = re.compile(r"https?://[^\s<>\"'\\)]+")
# 备用：从 HTML href 里直接提 URL（应对被引号或折行拆开的情况）
HREF_URL_RE = re.compile(r'href\s*=\s*["\']?(https?://[^\s"\'<>]+)["\']?', re.IGNORECASE)
# URL 尾随标点（从提取结果末尾剥掉，避免打开链接 404）
URL_TRAILING_PUNCTUATION = ".,;:!?)\"'"

# GitHub 启动码（launch code）匹配：典型邮件为：
#   "Here's your GitHub launch code! ... Continue signing up for GitHub by entering the code below: 38347135"
# 仅在来自 *@github.com 且正文/摘要中含 launch code / code below 等关键字时，提取 6–8 位纯数字。
LAUNCH_CODE_KEYWORDS = (
    "launch code",
    "code below",
    "your github launch code",
)
LAUNCH_CODE_RE = re.compile(r"\b(\d{6,8})\b")


def _normalize_text_for_url_extract(text: str) -> str:
    """去掉换行等，便于匹配被 HTML 折行拆开的同一 URL（不删空格，避免合并两条 URL）。"""
    return text.replace("\r\n", "").replace("\n", "").replace("\r", "")


def _strip_trailing_punctuation(url: str) -> str:
    """去掉 URL 末尾常见标点，避免浏览器打开失败。"""
    return url.rstrip(URL_TRAILING_PUNCTUATION)


def _extract_launch_code(text: str) -> Optional[str]:
    """
    从文本中提取 GitHub 启动码（6–8 位数字）。
    仅在包含 launch code 相关关键词时才尝试，避免误把时间戳等当成验证码。
    """
    t = (text or "").lower()
    if not any(k in t for k in LAUNCH_CODE_KEYWORDS):
        return None
    # 在原始大小写文本中找数字，避免 lower() 影响
    for m in LAUNCH_CODE_RE.finditer(text or ""):
        code = m.group(1)
        if code and code.isdigit():
            return code
    return None


def _is_single_verification_url(url: str) -> bool:
    """判断是否为单一有效验证链接（避免换行合并导致两条 URL 拼成一条）。"""
    if not url or "github.com" not in url:
        return False
    if url.count("https://") + url.count("http://") != 1:
        return False
    return any(k in url for k in VERIFICATION_LINK_KEYWORDS)


def get_verification_link_from_inbox(
    keyword: str = "github",
    top: int = 25,
) -> tuple[Optional[str], Optional[dict[str, Any]], Optional[str]]:
    """
    从收件箱中查找包含 keyword 或发件人为 *@github.com 的邮件，从正文/摘要中提取验证链接。
    :return: (link, mail_item, diagnostic)。找到链接时 diagnostic 为 None；
            未找到时 diagnostic 为说明文字（含当前取信邮箱、扫描数、匹配数），便于排查是否用错邮箱或提取失败。
    """
    data = list_messages(
        top=top,
        folder="inbox",
        select="id,subject,bodyPreview,sender",
        order_by="receivedDateTime desc",
    )
    messages = data.get("value") or []
    total = len(messages)
    matched = 0
    for m in messages:
        subject = (m.get("subject") or "").lower()
        preview = (m.get("bodyPreview") or "").lower()
        sender = ((m.get("sender") or {}).get("emailAddress") or {}).get("address") or ""
        sender = sender.lower()
        if not (
            keyword.lower() in subject
            or keyword.lower() in preview
            or "github.com" in sender
        ):
            continue
        matched += 1
        text = _normalize_text_for_url_extract((m.get("bodyPreview") or "").replace("&amp;", "&"))
        for url in LINK_RE.findall(text):
            u = _strip_trailing_punctuation(url.replace("&amp;", "&"))
            if _is_single_verification_url(u):
                return u, m, None
        try:
            full = get_message(m["id"])
            body = (full.get("body") or {}).get("content") or ""
            body_norm = _normalize_text_for_url_extract(body.replace("&amp;", "&"))
            for url in LINK_RE.findall(body_norm):
                u = _strip_trailing_punctuation(url.replace("&amp;", "&"))
                if _is_single_verification_url(u):
                    return u, m, None
            # 正文可能是 HTML，用 href 再扫一遍
            for url in HREF_URL_RE.findall(body_norm):
                u = _strip_trailing_punctuation(url.replace("&amp;", "&"))
                if _is_single_verification_url(u):
                    return u, m, None
        except Exception:
            pass
    current_email = get_current_account_email()
    if matched == 0:
        diag = f"当前取信邮箱: {current_email or '(无法获取)'}；收件箱已扫描 {total} 封，其中来自/含 github 的 0 封。请确认注册时填写的邮箱是否为此邮箱。"
    else:
        diag = f"当前取信邮箱: {current_email or '(无法获取)'}；收件箱已扫描 {total} 封，其中来自/含 github 的 {matched} 封，但未从中解析出验证链接（可能邮件格式或链接位置不同）。"
    return None, None, diag


def get_verification_code_from_inbox(
    keyword: str = "github",
    top: int = 25,
) -> tuple[Optional[str], Optional[dict[str, Any]], Optional[str]]:
    """
    从收件箱中查找 GitHub 注册邮件中的「launch code」验证码（如 38347135）。
    典型邮件结构：

        Here's your GitHub launch code!
        Continue signing up for GitHub by entering the code below:
        38347135

    :return: (code, mail_item, diagnostic)。找到 code 时 diagnostic 为 None；
             未找到时 diagnostic 为说明文字，便于排查是否用错邮箱或提取失败。
    """
    data = list_messages(
        top=top,
        folder="inbox",
        select="id,subject,bodyPreview,sender",
        order_by="receivedDateTime desc",
    )
    messages = data.get("value") or []
    total = len(messages)
    matched = 0
    for m in messages:
        subject = (m.get("subject") or "").lower()
        preview = (m.get("bodyPreview") or "").lower()
        sender = ((m.get("sender") or {}).get("emailAddress") or {}).get("address") or ""
        sender = sender.lower()
        if not (
            keyword.lower() in subject
            or keyword.lower() in preview
            or "github.com" in sender
        ):
            continue
        matched += 1

        # 先从 bodyPreview 中尝试提取
        code = _extract_launch_code(m.get("bodyPreview") or "")
        if code:
            return code, m, None

        # 若失败，再拉取完整正文（HTML/文本均可），拼接预览一并搜索
        try:
            full = get_message(m["id"])
            body = (full.get("body") or {}).get("content") or ""
            combined = (m.get("bodyPreview") or "") + "\n" + body
            code = _extract_launch_code(combined)
            if code:
                return code, full, None
        except Exception:
            pass

    current_email = get_current_account_email()
    if matched == 0:
        diag = f"当前取信邮箱: {current_email or '(无法获取)'}；收件箱已扫描 {total} 封，其中来自/含 github 的 0 封。请确认注册时填写的邮箱是否为此邮箱。"
    else:
        diag = f"当前取信邮箱: {current_email or '(无法获取)'}；收件箱已扫描 {total} 封，其中来自/含 github 的 {matched} 封，但未从中解析出 GitHub 启动码（launch code）。"
    return None, None, diag


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not GRAPH_CLIENT_SECRET:
        print("Set GRAPH_CLIENT_SECRET in .env.local", file=sys.stderr)
        sys.exit(1)
    try:
        data = get_inbox(top=5)
        for msg in data.get("value", []):
            s = msg.get("sender", {}).get("emailAddress", {})
            print(msg.get("receivedDateTime"), s.get("address"), msg.get("subject"))
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)
