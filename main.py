"""
GitHub Register：导入邮箱 → 自动注册 → 人机验证(浏览器内手动) → 自动取码填入 → 自动2FA → 导出结果。
支持选中单个/多个账号注册，支持跳过当前、停止、重试。
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import subprocess
import sys
import multiprocessing
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional, Tuple

# 这一行必须在所有其他初始化之前调用，解决打包后的闪现重启问题
if __name__ == "__main__":
    multiprocessing.freeze_support()

from ui_qt import run_qt_app

# ---------------------------------------------------------------------------
# 环境加载（.env.local 覆盖 .env，供代理/BitBrowser/验证码等配置）
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    # 打包后不自动加载 .env，除非它放在 EXE 目录下
    _base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_base, ".env"))
    load_dotenv(os.path.join(_base, ".env.local"), override=True)
except ImportError:
    pass

from bitbrower import (
    check_bitbrowser_alive,
    check_bitbrowser_alive_with_config,
    close_browser,
    delete_browser,
    close_extra_tabs_after_open,
    create_github_ready_browser,
    open_browser,
)
from github_automation import SignupFormError
from xiaoshuidi_mail import get_verification_info as xsd_get_verify
from proxy_config import (
    get_app_config,
    get_proxy_config,
    save_config as save_proxy_config,
    test_proxy_connectivity,
    to_bitbrowser_proxy,
)
from web_admin_client import (
    get_remote_verification_info,
    pull_remote_mail_accounts,
    push_github_result,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SEP = "----"
PASSWORD_SUFFIX = "@Git2026"
CDP_GOTO_NO_TIMEOUT = 0

POLL_RETRY_INTERVAL = 5
POLL_RETRY_MAX = 12
RETRY_BACKOFF = (5, 10, 20)

def _get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_ROOT = _get_base_path()
OUTPUT_FILE = os.path.join(APP_ROOT, "output.txt")
FAILED_FILE = os.path.join(APP_ROOT, "failed.txt")
# 纯净失败账号导出（仅 邮箱----密码；不含任何日志/时间/原因/批次分隔）
FAILED_ACCOUNTS_FILE = os.path.join(APP_ROOT, "failed_accounts.txt")
UI_PREFS_FILE = os.path.join(APP_ROOT, ".ui_prefs.json")
# failed.txt：制表符分隔，可用 Excel「数据-分列」；首行为表头（仅文件为空时写入一次）
FAILED_FILE_HEADER = "时间\t取件方式\t阶段\t邮箱\t原因\n"
_FAILED_FILE_LOCK = threading.Lock()
_OUTPUT_FILE_LOCK = threading.Lock()


def _get_success_emails() -> set[str]:
    """从 ok.txt 和 output.txt 中提取所有成功注册的邮箱。"""
    emails = set()
    for path in [OUTPUT_FILE, os.path.join(APP_ROOT, "ok.txt")]:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # 分割符可能是 --- 或 ----
                        parts = re.split(r"---+", line)
                        if parts and "@" in parts[0]:
                            emails.add(parts[0].strip())
            except Exception:
                pass
    return emails


def deduplicate_failed_accounts() -> int:
    """从 failed_accounts.txt 中移除已经在成功列表中的账号。"""
    success_emails = _get_success_emails()
    if not os.path.isfile(FAILED_ACCOUNTS_FILE):
        return 0

    remaining_lines = []
    removed_count = 0
    with _FAILED_FILE_LOCK:
        try:
            with open(FAILED_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    parts = re.split(r"---+", raw)
                    email = parts[0].strip() if parts else ""
                    if email and email in success_emails:
                        removed_count += 1
                        continue
                    remaining_lines.append(line)

            with open(FAILED_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                f.writelines(remaining_lines)
        except Exception:
            pass
    return removed_count


def _failed_file_has_tsv_header(path: str) -> bool:
    """文件中是否已有表头行（排除仅含批次注释的情况）。"""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("时间\t"):
                return True
    return False
def _get_resource_path(relative_path):
    """ 获取资源绝对路径（兼容开发与打包后的 _MEIPASS） """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

ICON_PATH = _get_resource_path(os.path.join("assets", "icon.png"))

WINDOW_TITLE = "GitHub Register"
# Qt 版本由 ui_qt 控制窗口尺寸；这里保留常量给业务/显示文案使用
WINDOW_MINSIZE = (1120, 760)
POLL_INTERVAL_MS = 150
FONT_MONO = ("Consolas", 10)
FONT_MONO_SM = ("Consolas", 9)

# 按钮 / 分区用 Unicode 符号（跨平台不依赖额外图标字体）
ICO = {
    "import_file": "📂",
    "paste": "📋",
    "clear": "🗑",
    "run_sel": "▶",
    "run_all": "⏩",
    "skip": "⏭",
    "stop": "⏹",
    "doc": "📄",
    "list": "📋",
    "log": "📜",
    "key": "🔑",
    "ok": "✓",
    "fail": "✗",
}

STATUS_PENDING = "等待"
STATUS_RUNNING = "进行中"
STATUS_CAPTCHA = "人机验证"
STATUS_VERIFY = "取码验证"
STATUS_2FA = "获取2FA"
STATUS_SUCCESS = "成功"
STATUS_NO_2FA = "未开启2FA"
STATUS_PARTIAL = "部分完成"
STATUS_FAILED = "失败"
STATUS_SKIPPED = "已跳过"
STATUS_REGISTERED = "已注册"
STATUS_USERNAME_TAKEN = "用户名占用"
STATUS_SERVICE_REFUSED = "服务拒绝"


def _keep_window_statuses() -> set[str]:
    cfg = get_app_config()
    raw = cfg.get("keepWindowStatuses", [])
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    return set()


def _icon_rgba_rounded(size: int, source: Any) -> Any:
    """
    缩放为 size×size 并施加圆角透明遮罩，避免直角方块在 macOS Dock / 任务栏上显得突兀。
    多尺寸由调用方生成后一并交给 Tk iconphoto，便于高分屏与各端缩放。
    """
    from PIL import ImageChops, ImageDraw, Image

    src = source.convert("RGBA")
    if src.size != (size, size):
        im = src.resize((size, size), Image.Resampling.LANCZOS)
    else:
        im = src.copy()
    w, h = im.size
    r = max(2, int(min(w, h) * 0.22))
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    alpha = im.split()[3]
    im.putalpha(ImageChops.multiply(alpha, mask))
    return im


def _open_path_default_app(path: str) -> None:
    """用系统默认程序打开文件（macOS / Windows / Linux）。"""
    path = os.path.abspath(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------

def _parse_mail_line(line: str) -> Optional[dict[str, str]]:
    """
    解析单行账号信息（小水滴 API 取件）。
    以 ---- 分割，取前两段作为邮箱和密码，其余忽略。
    """
    raw_line = (line or "").strip()
    if not raw_line:
        return None
    parts = raw_line.split(SEP)
    if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
        # raw: 保留导入原始整行（可能含 UUID/token 等后续段），用于失败纯净导出
        return {"email": parts[0].strip(), "password": parts[1].strip(), "raw": raw_line}
    return None


def _pull_remote_accounts_for_ui(options: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = get_app_config()
    merged = dict(cfg)
    merged.update(options or {})
    base_url = str(merged.get("webAdminBaseUrl") or "").strip()
    api_token = str(merged.get("webAdminClientToken") or "").strip()
    fetch_all = str(merged.get("remoteFetchMode") or "count") == "all"
    limit = int(merged.get("remoteFetchCount") or 10)
    if not base_url:
        raise RuntimeError("请先在系统设置或导入弹窗中填写客户端 API 地址")
    if not api_token:
        raise RuntimeError("请先在系统设置或导入弹窗中填写客户端 API Token")
    return pull_remote_mail_accounts(
        base_url=base_url,
        api_token=api_token,
        limit=limit,
        fetch_all=fetch_all,
    )


def _email_to_username(email: str, max_len: int = 20) -> str:
    return email.split("@")[0].replace(".", "").replace("+", "")[:max_len]


def _profile_name(email: str) -> str:
    return email.replace("@", "-")[:20]


def _cdp_ws(open_result: dict) -> str:
    ws = open_result.get("ws") or ""
    if not ws and open_result.get("http"):
        ws = f"ws://{open_result['http']}/devtools/browser/{open_result.get('pid', '')}"
    return ws


# ---------------------------------------------------------------------------
# 取件封装（带重试 + 可中断）
# ---------------------------------------------------------------------------

def _fetch_verification(
    account: dict[str, str],
    log: Callable[[str], None],
    cancel: Callable[[], bool],
) -> Tuple[Optional[str], Optional[str]]:
    last_diag = ""
    for attempt, backoff in enumerate(RETRY_BACKOFF):
        if cancel():
            return None, "已取消"
        try:
            email, pwd = account["email"], account["password"]
            source = str(account.get("source") or "local").strip().lower()
            receive_mode = str(account.get("receive_mode") or "").strip().lower()
            if source == "remote":
                result, diag = get_remote_verification_info(
                    base_url=str(get_app_config().get("webAdminBaseUrl") or ""),
                    account=account,
                )
            elif receive_mode == "official":
                result, diag = get_remote_verification_info(
                    base_url=str(get_app_config().get("webAdminBaseUrl") or ""),
                    account=account,
                )
            else:
                result, diag = xsd_get_verify(email, pwd)
            if result:
                return result, None
            last_diag = diag or ""
            log(f"取件返回: {diag}")
        except Exception as e:
            last_diag = str(e)
            log(f"取件异常: {e}")
        if attempt < len(RETRY_BACKOFF) - 1:
            log(f"取件未成功，{backoff}s 后重试 ({attempt + 2}/{len(RETRY_BACKOFF)})...")
            for _ in range(backoff):
                if cancel():
                    return None, "已取消"
                time.sleep(1)
    return None, last_diag


def _poll_verification(
    account: dict[str, str],
    log: Callable[[str], None],
    cancel: Callable[[], bool],
) -> Tuple[Optional[str], Optional[str]]:
    last_diag = ""
    for i in range(POLL_RETRY_MAX):
        if cancel():
            return None, "已取消"
        result, diag = _fetch_verification(account, log, cancel)
        if result:
            return result, None
        last_diag = diag or last_diag
        if i < POLL_RETRY_MAX - 1:
            log(f"第 {i + 1} 轮取件未果，{POLL_RETRY_INTERVAL}s 后继续...")
            for _ in range(POLL_RETRY_INTERVAL):
                if cancel():
                    return None, "已取消"
                time.sleep(1)
    return None, last_diag


# ---------------------------------------------------------------------------
# 浏览器连接
# ---------------------------------------------------------------------------

def _ensure_browser(profile_id: str, current_ws: str, log: Callable[[str], None]) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            br = p.chromium.connect_over_cdp(current_ws)
            if br and br.contexts:
                return current_ws
    except Exception:
        pass
    try:
        log("浏览器连接断开，正在重新打开...")
        result = open_browser(profile_id)
        ws = _cdp_ws(result)
        if ws:
            log("浏览器已重新打开")
            time.sleep(1)
            close_extra_tabs_after_open(ws, log)
            return ws
    except Exception as e:
        log(f"重新打开浏览器失败: {e}")
    return None


# ---------------------------------------------------------------------------
# 文件导出
# ---------------------------------------------------------------------------

def _append_output(line: str) -> None:
    with _OUTPUT_FILE_LOCK:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _append_failed_record(
    email: str,
    reason: str,
    *,
    mode_label: str,
    stage: str,
) -> None:
    """写入一条结构化失败记录（线程安全）。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reason_one = (reason or "").replace("\n", " ").replace("\r", " ").strip()
    row = f"{ts}\t{mode_label}\t{stage}\t{email}\t{reason_one}\n"
    with _FAILED_FILE_LOCK:
        need_header = not _failed_file_has_tsv_header(FAILED_FILE)
        with open(FAILED_FILE, "a", encoding="utf-8") as f:
            if need_header:
                f.write(FAILED_FILE_HEADER)
            f.write(row)


def _failed_log_batch_start(account_count: int) -> None:
    """每轮任务开始时写入批次分隔行（注释行，便于与旧版纯文本区分）。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"# ----- 批次开始 {ts} | 本批账号数: {account_count} -----\n"
    with _FAILED_FILE_LOCK:
        with open(FAILED_FILE, "a", encoding="utf-8") as f:
            f.write(line)


def _append_failed_account_plain(*, raw_line: str, fallback_email: str = "", fallback_password: str = "") -> None:
    """
    纯净失败账号导出：严格按导入原始整行输出（一行一个），不夹杂任何日志内容。
    线程安全；写入前按整行或邮箱去重（支持多轮批次同一批账号跑两遍的场景）。
    """
    raw = (raw_line or "").replace("\r", " ").replace("\n", " ").strip()
    if not raw:
        email = (fallback_email or "").strip()
        password = (fallback_password or "").strip()
        if not email or not password:
            return
        raw = f"{email}{SEP}{password}"
    # 提取邮箱用于去重
    email_for_dedup = raw.split(SEP)[0].strip() if SEP in raw else raw.strip()

    # 如果该邮箱已经成功，则不写入失败列表
    success_emails = _get_success_emails()
    if email_for_dedup in success_emails:
        return

    with _FAILED_FILE_LOCK:
        # 去重：整行匹配 或 邮箱匹配则跳过写入
        if os.path.isfile(FAILED_ACCOUNTS_FILE):
            try:
                with open(FAILED_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    for existing_line in f:
                        existing_line = existing_line.strip()
                        if not existing_line:
                            continue
                        if existing_line == raw:
                            return
                        existing_email = existing_line.split(SEP)[0].strip() if SEP in existing_line else ""
                        if existing_email and existing_email == email_for_dedup:
                            return
            except Exception:
                pass
        with open(FAILED_ACCOUNTS_FILE, "a", encoding="utf-8") as f:
            f.write(raw + "\n")


# ---------------------------------------------------------------------------
# 单个账号流程（后台线程执行，可中断）
# ---------------------------------------------------------------------------

def _run_single_account(
    account: dict[str, str],
    log: Callable[[str], None],
    on_status: Callable[[str], None],
    cancel: Callable[[], bool],
) -> str:
    """
    返回状态: "success" / "partial" / "failed" / "skipped"
    """
    email = account["email"]
    base_pw = account["password"]
    final_pw = base_pw + PASSWORD_SUFFIX
    username = _email_to_username(email)
    receive_mode = str(account.get("receive_mode") or "xiaoshuidi").strip().lower()
    mode_label = "官方" if receive_mode == "official" else "小水滴"

    profile_id = ""
    ws = ""
    result_status = "failed"
    final_ui_status = STATUS_FAILED
    export_failed_plain = False
    raw_import_line = str(account.get("raw") or "")

    try:
        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 1. 前置检测 + 创建并打开浏览器
        on_status(STATUS_RUNNING)

        bb_ok, bb_msg = check_bitbrowser_alive()
        if not bb_ok:
            raise RuntimeError(f"BitBrowser 不可用: {bb_msg}")

        # 创建 + 打开整体重试（最多 3 次）
        MAX_RETRIES = 3
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log(f"[{email}] 创建并打开浏览器... ({attempt}/{MAX_RETRIES})")
                
                # 获取当前最新的代理配置
                proxy_cfg = get_proxy_config()
                bit_proxy = to_bitbrowser_proxy(proxy_cfg)
                
                profile = create_github_ready_browser(
                    _profile_name(email), 
                    platform="https://github.com",
                    proxy_settings=bit_proxy
                )
                profile_id = profile.get("id", "")
                if not profile_id:
                    raise RuntimeError("创建档案失败：未返回 id")

                open_result = open_browser(profile_id)
                ws = _cdp_ws(open_result)
                if not ws:
                    raise RuntimeError("打开浏览器失败：未返回 CDP 地址")
                break
            except Exception as e:
                last_err = e
                # 失败则清理本次创建的档案
                if profile_id:
                    try:
                        delete_browser(profile_id)
                    except Exception:
                        pass
                    profile_id = ""
                if attempt < MAX_RETRIES:
                    wait_s = 3 * attempt
                    log(f"[{email}] 创建/打开失败: {e}，{wait_s}s 后重试...")
                    time.sleep(wait_s)
                else:
                    raise RuntimeError(f"创建/打开浏览器连续 {MAX_RETRIES} 次失败: {last_err}")

        time.sleep(2)
        close_extra_tabs_after_open(ws, lambda m: log(f"[{email}] {m}"))
        time.sleep(1)
        log(f"[{email}] 浏览器已打开")

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 2. 自动注册
        log(f"[{email}] 开始自动注册流程...")
        from github_automation import run_signup_flow
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ok = loop.run_until_complete(
                run_signup_flow(ws, email, final_pw, username, log_callback=log)
            )
        except SignupFormError as e:
            if "email_taken" in e.errors:
                log(f"[{email}] 邮箱已被注册，跳过此账号")
                _append_failed_record(
                    email, "邮箱已被注册", mode_label=mode_label, stage="注册提交"
                )
                final_ui_status = STATUS_REGISTERED
                on_status(final_ui_status)
                # 已注册账号不可重试，不写入纯净失败列表
            elif "username_taken" in e.errors:
                log(f"[{email}] 用户名已被占用，跳过此账号")
                _append_failed_record(
                    email, "用户名已被占用", mode_label=mode_label, stage="注册提交"
                )
                final_ui_status = STATUS_USERNAME_TAKEN
                on_status(final_ui_status)
                export_failed_plain = True
            elif "signup_unavailable" in e.errors:
                log(f"[{email}] GitHub 无法创建账号（服务拒绝），跳过此账号")
                _append_failed_record(
                    email,
                    "GitHub无法创建账号（服务拒绝）",
                    mode_label=mode_label,
                    stage="注册提交",
                )
                final_ui_status = STATUS_SERVICE_REFUSED
                on_status(final_ui_status)
                export_failed_plain = True
            else:
                log(f"[{email}] 表单校验失败: {e}，跳过此账号")
                _append_failed_record(
                    email, f"表单校验失败: {e}", mode_label=mode_label, stage="注册提交"
                )
                final_ui_status = STATUS_FAILED
                on_status(final_ui_status)
                export_failed_plain = True
            return "failed"
        if not ok:
            raise RuntimeError("自动注册流程失败")

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 3. 人机验证（当前默认不自动打码；在浏览器中手动完成后继续）
        on_status(STATUS_CAPTCHA)
        log(f"[{email}] 人机验证（请在浏览器中手动完成）...")
        from github_automation import wait_for_captcha_done
        loop2 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop2)
        try:
            captcha_ok = loop2.run_until_complete(
                wait_for_captcha_done(ws, poll_interval=3.0, max_wait=150.0, log_callback=log, manual_fallback=True)
            )
        except SignupFormError as e:
            if "signup_unavailable" in e.errors:
                log(f"[{email}] GitHub 无法创建账号（服务拒绝），跳过此账号")
                _append_failed_record(
                    email,
                    "GitHub无法创建账号（服务拒绝）",
                    mode_label=mode_label,
                    stage="人机验证",
                )
                final_ui_status = STATUS_SERVICE_REFUSED
                on_status(final_ui_status)
                export_failed_plain = True
                return "failed"
            raise
        if not captcha_ok:
            raise RuntimeError("人机验证未通过（超时、验证码 401 拦截或未完成）")

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 4. 取码 + 填入（链接 / 验证码由界面选择，不自动混试）
        on_status(STATUS_VERIFY)
        log(f"[{email}] 轮询邮箱获取验证信息（小水滴取件）...")
        result, diag = _poll_verification(account, log, cancel)

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        if result:
            if result.startswith("http"):
                log(f"[{email}] 获取到验证链接，在浏览器中打开...")
                try:
                    active_ws = _ensure_browser(profile_id, ws, log) or ws
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        br = p.chromium.connect_over_cdp(active_ws)
                        if br.contexts and br.contexts[0].pages:
                            br.contexts[0].pages[0].goto(result, timeout=CDP_GOTO_NO_TIMEOUT)
                    ws = active_ws
                except Exception as e:
                    log(f"[{email}] 打开验证链接失败: {e}")
            else:
                log(f"[{email}] 获取到验证码: {result}，自动填入...")
                from github_automation import fill_verification_code
                active_ws = _ensure_browser(profile_id, ws, log) or ws
                loop3 = asyncio.new_event_loop()
                asyncio.set_event_loop(loop3)
                loop3.run_until_complete(
                    fill_verification_code(active_ws, result, log_callback=log)
                )
                ws = active_ws
        else:
            log(f"[{email}] 未获取到验证信息: {diag}")
            raise RuntimeError(f"取件失败: {diag}")

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 5. 登录 GitHub
        log(f"[{email}] 等待页面跳转...")
        time.sleep(5)
        active_ws = _ensure_browser(profile_id, ws, log) or ws
        from github_automation import run_login
        loop_login = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_login)
        login_ok = loop_login.run_until_complete(
            run_login(active_ws, email, final_pw, log_callback=log)
        )
        ws = active_ws
        if not login_ok:
            log(f"[{email}] 登录失败")
            raise RuntimeError("GitHub 登录失败")

        if cancel():
            final_ui_status = STATUS_SKIPPED
            on_status(final_ui_status)
            return "skipped"

        # 6. 2FA
        on_status(STATUS_2FA)
        log(f"[{email}] 登录成功，开始开启 2FA...")
        time.sleep(3)
        active_ws = _ensure_browser(profile_id, ws, log) or ws
        from github_automation import run_enable_2fa_and_get_secret
        loop4 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop4)
        secret = loop4.run_until_complete(
            run_enable_2fa_and_get_secret(active_ws, email=email, log_callback=log)
        )

        if secret:
            out_line = f"{email}---{final_pw}---{secret}"
            _append_output(out_line)
            log(f"[{email}] 注册成功！2FA 密钥已获取并导出")
            _try_push_github_result(
                account=account,
                github_login=username,
                github_password=final_pw,
                totp_secret=secret,
                log=log,
            )
            final_ui_status = STATUS_SUCCESS
            on_status(final_ui_status)
            result_status = "success"
            return "success"
        else:
            log(f"[{email}] 注册成功，但未能开启 2FA（可能需要手动完成）")
            _append_output(f"{email}---{final_pw}---NO_2FA")
            _try_push_github_result(
                account=account,
                github_login=username,
                github_password=final_pw,
                totp_secret="",
                log=log,
            )
            final_ui_status = STATUS_NO_2FA
            on_status(final_ui_status)
            result_status = "success"
            return "success"

    except Exception as e:
        log(f"[{email}] 流程失败: {e}")
        stage_guess = "流程异常"
        err_s = str(e)
        if "取件失败" in err_s or "取件" in err_s:
            stage_guess = "邮箱取件"
        elif "人机验证" in err_s or "captcha" in err_s.lower():
            stage_guess = "人机验证"
        elif "自动注册" in err_s:
            stage_guess = "注册提交"
        elif "CDP" in err_s or "浏览器" in err_s or "BitBrowser" in err_s:
            stage_guess = "浏览器"
        _append_failed_record(email, err_s, mode_label=mode_label, stage=stage_guess)
        final_ui_status = STATUS_FAILED
        on_status(final_ui_status)
        result_status = "failed"
        export_failed_plain = True
        return "failed"
    finally:
        # 纯净失败账号导出（不影响原 failed.txt 结构化日志）
        if export_failed_plain:
            try:
                _append_failed_account_plain(
                    raw_line=raw_import_line,
                    fallback_email=email,
                    fallback_password=base_pw,
                )
            except Exception:
                pass
        if profile_id:
            try:
                keep_statuses = _keep_window_statuses()
                keep_profile = final_ui_status in keep_statuses
                try:
                    close_browser(profile_id)
                    time.sleep(2)
                except Exception:
                    pass

                if keep_profile:
                    log(f"[{email}] 命中保留档案策略（状态: {final_ui_status}），已关闭窗口并保留 BitBrowser 档案")
                else:
                    try:
                        delete_browser(profile_id)
                        log(f"[{email}] 已根据清理策略关闭窗口并删除 BitBrowser 档案（状态: {final_ui_status}）")
                    except Exception as ex1:
                        log(f"[{email}] 首次删除档案失败: {ex1}，3s 后重试...")
                        time.sleep(3)
                        try:
                            delete_browser(profile_id)
                            log(f"[{email}] 重试删除档案成功")
                        except Exception as ex2:
                            log(f"[{email}] 重试删除档案仍失败: {ex2}")
            except Exception as ex:
                log(f"[{email}] 清理 BitBrowser 档案失败: {ex}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _open_output_ui() -> None:
    if os.path.isfile(OUTPUT_FILE):
        _open_path_default_app(OUTPUT_FILE)
    else:
        print("提示：尚无导出文件")


def _try_push_github_result(
    *,
    account: dict[str, Any],
    github_login: str,
    github_password: str,
    totp_secret: str,
    log: Callable[[str], None],
) -> None:
    cfg = get_app_config()
    if not cfg.get("pushGithubResult"):
        return
    if not totp_secret and not cfg.get("pushGithubWithout2fa", True):
        log("已关闭“未开启 2FA 也回传”，本次不回传管理中心")
        return
    base_url = str(cfg.get("webAdminBaseUrl") or "").strip()
    api_token = str(cfg.get("webAdminClientToken") or "").strip()
    if not base_url or not api_token:
        log("未配置客户端 API 地址或 Token，跳过回传")
        return
    try:
        push_github_result(
            base_url=base_url,
            api_token=api_token,
            github_login=github_login,
            github_password=github_password,
            totp_secret=totp_secret,
            bind_mail_account_id=account.get("mail_account_id"),
            bind_email=account.get("email"),
            lease_token=account.get("lease_token"),
        )
        if totp_secret:
            log("已回传 GitHub 成品账号到管理中心")
        else:
            log("已回传无 2FA 的成功账号到管理中心")
    except Exception as exc:
        log(f"回传管理中心失败: {exc}")


def main():
    return run_qt_app(
        window_title=WINDOW_TITLE,
        output_file=OUTPUT_FILE,
        failed_file=FAILED_FILE,
        failed_accounts_file=FAILED_ACCOUNTS_FILE,
        parse_mail_line=_parse_mail_line,
        run_one=_run_single_account,
        open_output=_open_output_ui,
        failed_batch_start=_failed_log_batch_start,
        deduplicate_failed=deduplicate_failed_accounts,
        get_app_cfg=get_app_config,
        get_proxy_cfg=get_proxy_config,
        save_proxy_cfg=save_proxy_config,
        test_proxy_conn=test_proxy_connectivity,
        test_bb_conn=check_bitbrowser_alive_with_config,
        pull_remote_accounts=_pull_remote_accounts_for_ui,
        icon_path=ICON_PATH, # 传递图标路径
    )


if __name__ == "__main__":
    sys.exit(main())
