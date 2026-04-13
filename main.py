"""
GitHub 批量注册工具：导入邮箱 → 自动注册 → 人机验证(浏览器内手动) → 自动取码填入 → 自动2FA → 导出结果。
支持选中单个/多个账号注册，支持跳过当前、停止、重试。
"""
from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from typing import Any, Callable, Optional, Tuple

import ttkbootstrap as ttkb

import getmail  # noqa: F401  — 触发 .env/.env.local 加载
from bitbrower import (
    close_browser,
    close_extra_tabs_after_open,
    create_github_ready_browser,
    open_browser,
)
from github_automation import SignupFormError
from getmail import (
    set_current_account,
    get_verification_link_from_inbox,
    get_verification_code_from_inbox,
    register_auth_url_opener,
)
from xiaoshuidi_mail import (
    get_verification_link as xsd_get_link,
    get_verification_code as xsd_get_code,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SEP = "----"
PASSWORD_SUFFIX = "@Git2026"
VERIFICATION_KEYWORD = "github"
VERIFICATION_TOP = 15
# 邮箱验证取件：由界面选择，只取链接或只取验证码（避免自动识别误匹配）
VERIFY_FETCH_LINK = "link"
VERIFY_FETCH_CODE = "code"
DEFAULT_VERIFY_FETCH = VERIFY_FETCH_LINK
CDP_GOTO_NO_TIMEOUT = 0

POLL_RETRY_INTERVAL = 5
POLL_RETRY_MAX = 12
RETRY_BACKOFF = (5, 10, 20)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(APP_ROOT, "output.txt")
FAILED_FILE = os.path.join(APP_ROOT, "failed.txt")
# failed.txt：制表符分隔，可用 Excel「数据-分列」；首行为表头（仅文件为空时写入一次）
FAILED_FILE_HEADER = "时间\t取件方式\t阶段\t邮箱\t原因\n"
_FAILED_FILE_LOCK = threading.Lock()


def _failed_file_has_tsv_header(path: str) -> bool:
    """文件中是否已有表头行（排除仅含批次注释的情况）。"""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("时间\t"):
                return True
    return False
ICON_PATH = os.path.join(APP_ROOT, "assets", "icon.png")

WINDOW_TITLE = "GitHub 批量注册工具"
WINDOW_MINSIZE = (920, 700)
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
STATUS_PARTIAL = "部分完成"
STATUS_FAILED = "失败"
STATUS_SKIPPED = "已跳过"


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
    解析单行账号信息，支持两种格式：
      2段: 邮箱----密码               → 小水滴 API 取件
      4段: 邮箱----密码----clientId----refreshToken → Graph 取件
    """
    line = line.strip()
    if not line:
        return None
    parts = line.split(SEP)
    if len(parts) == 2:
        return {"email": parts[0].strip(), "password": parts[1].strip(), "mode": "xiaoshuidi"}
    if len(parts) == 4:
        return {
            "email": parts[0].strip(), "password": parts[1].strip(),
            "client_id": parts[2].strip(), "refresh_token": parts[3].strip(),
            "mode": "graph",
        }
    return None


def _email_to_username(email: str, max_len: int = 20) -> str:
    return email.split("@")[0].replace(".", "").replace("+", "")[:max_len]


def _profile_name(email: str) -> str:
    return "github-reg-" + email.replace("@", "-")[:20]


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
    *,
    verify_fetch: str = DEFAULT_VERIFY_FETCH,
) -> Tuple[Optional[str], Optional[str]]:
    mode = account.get("mode", "xiaoshuidi")
    if verify_fetch not in (VERIFY_FETCH_LINK, VERIFY_FETCH_CODE):
        verify_fetch = DEFAULT_VERIFY_FETCH
    last_diag = ""
    for attempt, backoff in enumerate(RETRY_BACKOFF):
        if cancel():
            return None, "已取消"
        try:
            if mode == "graph":
                if verify_fetch == VERIFY_FETCH_LINK:
                    link, _, diag = get_verification_link_from_inbox(
                        keyword=VERIFICATION_KEYWORD, top=VERIFICATION_TOP
                    )
                    if link:
                        return link, None
                    last_diag = diag or ""
                else:
                    code, _, diag = get_verification_code_from_inbox(
                        keyword=VERIFICATION_KEYWORD, top=VERIFICATION_TOP
                    )
                    if code:
                        return code, None
                    last_diag = diag or ""
            else:
                email, pwd = account["email"], account["password"]
                if verify_fetch == VERIFY_FETCH_LINK:
                    link, diag = xsd_get_link(
                        email, pwd, keyword=VERIFICATION_KEYWORD
                    )
                    if link:
                        return link, None
                    last_diag = diag or ""
                else:
                    code, diag = xsd_get_code(
                        email, pwd, keyword=VERIFICATION_KEYWORD
                    )
                    if code:
                        return code, None
                    last_diag = diag or ""
        except Exception as e:
            last_diag = str(e)
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
    *,
    verify_fetch: str = DEFAULT_VERIFY_FETCH,
) -> Tuple[Optional[str], Optional[str]]:
    last_diag = ""
    for i in range(POLL_RETRY_MAX):
        if cancel():
            return None, "已取消"
        result, diag = _fetch_verification(
            account, log, cancel, verify_fetch=verify_fetch
        )
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


# ---------------------------------------------------------------------------
# 单个账号流程（后台线程执行，可中断）
# ---------------------------------------------------------------------------

def _run_single_account(
    account: dict[str, str],
    log: Callable[[str], None],
    on_status: Callable[[str], None],
    cancel: Callable[[], bool],
    *,
    verify_fetch: str = DEFAULT_VERIFY_FETCH,
) -> str:
    """
    返回状态: "success" / "partial" / "failed" / "skipped"
    """
    email = account["email"]
    base_pw = account["password"]
    final_pw = base_pw + PASSWORD_SUFFIX
    username = _email_to_username(email)
    mode = account.get("mode", "xiaoshuidi")
    mode_label = "Graph" if mode == "graph" else "小水滴"

    profile_id = ""
    ws = ""

    try:
        if cancel():
            on_status(STATUS_SKIPPED)
            return "skipped"

        # 1. 浏览器
        on_status(STATUS_RUNNING)
        log(f"[{email}] 创建并打开浏览器...")
        if mode == "graph":
            set_current_account(account["refresh_token"], client_id=account.get("client_id"))

        profile = create_github_ready_browser(
            _profile_name(email), platform="https://github.com"
        )
        profile_id = profile.get("id", "")
        if not profile_id:
            raise RuntimeError("创建档案失败：未返回 id")

        open_result = open_browser(profile_id)
        ws = _cdp_ws(open_result)
        if not ws:
            raise RuntimeError("打开浏览器失败：未返回 CDP 地址")
        time.sleep(2)
        close_extra_tabs_after_open(ws, lambda m: log(f"[{email}] {m}"))
        time.sleep(1)
        log(f"[{email}] 浏览器已打开")

        if mode == "graph":
            def _open_auth(auth_url: str) -> None:
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        br = p.chromium.connect_over_cdp(ws)
                        ctx = br.contexts[0] if br.contexts else br.new_context()
                        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                        pg.goto(auth_url, timeout=CDP_GOTO_NO_TIMEOUT)
                except Exception:
                    pass
            register_auth_url_opener(_open_auth)

        if cancel():
            on_status(STATUS_SKIPPED)
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
            elif "username_taken" in e.errors:
                log(f"[{email}] 用户名已被占用，跳过此账号")
                _append_failed_record(
                    email, "用户名已被占用", mode_label=mode_label, stage="注册提交"
                )
            elif "signup_unavailable" in e.errors:
                log(f"[{email}] GitHub 无法创建账号（服务拒绝），跳过此账号")
                _append_failed_record(
                    email,
                    "GitHub无法创建账号（服务拒绝）",
                    mode_label=mode_label,
                    stage="注册提交",
                )
            else:
                log(f"[{email}] 表单校验失败: {e}，跳过此账号")
                _append_failed_record(
                    email, f"表单校验失败: {e}", mode_label=mode_label, stage="注册提交"
                )
            on_status(STATUS_FAILED)
            return "failed"
        if not ok:
            raise RuntimeError("自动注册流程失败")

        if cancel():
            on_status(STATUS_SKIPPED)
            return "skipped"

        # 3. 人机验证（当前默认不自动打码；在浏览器中手动完成后继续）
        on_status(STATUS_CAPTCHA)
        log(f"[{email}] 人机验证（请在浏览器中手动完成）...")
        from github_automation import wait_for_captcha_done
        loop2 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop2)
        try:
            captcha_ok = loop2.run_until_complete(
                wait_for_captcha_done(ws, poll_interval=3.0, max_wait=120.0, log_callback=log, manual_fallback=True)
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
                on_status(STATUS_FAILED)
                return "failed"
            raise
        if not captcha_ok:
            raise RuntimeError("人机验证未通过（超时、验证码 401 拦截或未完成）")

        if cancel():
            on_status(STATUS_SKIPPED)
            return "skipped"

        # 4. 取码 + 填入（链接 / 验证码由界面选择，不自动混试）
        on_status(STATUS_VERIFY)
        vf_label = (
            "验证链接" if verify_fetch == VERIFY_FETCH_LINK else "验证码"
        )
        log(f"[{email}] 轮询邮箱获取验证信息（取件：{vf_label}）...")
        result, diag = _poll_verification(
            account, log, cancel, verify_fetch=verify_fetch
        )

        if cancel():
            on_status(STATUS_SKIPPED)
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
            on_status(STATUS_SKIPPED)
            return "skipped"

        # 5. 2FA
        on_status(STATUS_2FA)
        log(f"[{email}] 等待页面加载后开启 2FA...")
        time.sleep(5)
        active_ws = _ensure_browser(profile_id, ws, log) or ws
        from github_automation import run_enable_2fa_and_get_secret
        loop4 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop4)
        secret = loop4.run_until_complete(
            run_enable_2fa_and_get_secret(active_ws, log_callback=log)
        )

        if secret:
            out_line = f"{email}---{final_pw}---{secret}"
            _append_output(out_line)
            log(f"[{email}] 注册成功！2FA 密钥已获取并导出")
            on_status(STATUS_SUCCESS)
            return "success"
        else:
            log(f"[{email}] 未能获取 2FA 密钥（可能需要手动完成）")
            _append_output(f"{email}---{final_pw}---NO_2FA")
            _append_failed_record(
                email,
                "未获取2FA密钥（页面需手动完成或选择器不匹配）",
                mode_label=mode_label,
                stage="2FA",
            )
            on_status(STATUS_PARTIAL)
            return "partial"

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
        on_status(STATUS_FAILED)
        return "failed"
    finally:
        if profile_id:
            try:
                close_browser(profile_id)
                log(f"[{email}] 已关闭 BitBrowser 窗口")
            except Exception as ex:
                log(f"[{email}] 关闭 BitBrowser 窗口失败: {ex}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class App:
    def __init__(self) -> None:
        self.root = ttkb.Window(
            title=WINDOW_TITLE,
            themename="darkly",
            size=(960, 720),
            minsize=WINDOW_MINSIZE,
        )
        self.accounts: list[dict[str, Any]] = []
        self.running = False
        self.skip_current = False
        self.log_queue: queue.Queue = queue.Queue()
        self.success_count = 0
        self.fail_count = 0
        self._worker_thread: Optional[threading.Thread] = None
        self._icon_photos: list[Any] = []
        self.var_verify_fetch = tk.StringVar(value=DEFAULT_VERIFY_FETCH)

        self._apply_window_icon()
        self._build_ui()
        self._configure_widget_styles()
        self._poll_log()

    # ================================================================
    # UI 构建
    # ================================================================

    def _apply_window_icon(self) -> None:
        if not os.path.isfile(ICON_PATH):
            return
        try:
            from PIL import Image, ImageTk

            master = Image.open(ICON_PATH).convert("RGBA")
            # Retina Dock / 高分屏会把小图强行放大 → 发糊；必须提供足够大的位图。
            # Tk 在 macOS 上会选用合适尺寸，惯例从大到小传入。
            sizes = (1024, 512, 256, 128, 64, 32, 16)
            self._icon_photos = []
            for px in sizes:
                rounded = _icon_rgba_rounded(px, master)
                self._icon_photos.append(ImageTk.PhotoImage(rounded))
            if self._icon_photos:
                self.root.iconphoto(True, *self._icon_photos)
        except Exception:
            self._icon_photos = []

    def _configure_widget_styles(self) -> None:
        sty = ttkb.Style()
        sty.configure("Treeview", rowheight=28)
        sty.configure("Treeview.Heading", font=("", 10, "bold"))

    def _build_ui(self) -> None:
        root = self.root

        # ----- 导入（窗口标题栏已显示应用名，此处不再重复大横幅）-----
        f_import = ttkb.Labelframe(
            root,
            text=f" {ICO['list']} 导入账号 ",
            padding=(12, 10),
            bootstyle="secondary",
        )
        f_import.pack(fill=tk.X, padx=12, pady=(8, 6))

        row_imp = ttkb.Frame(f_import)
        row_imp.pack(fill=tk.X)
        ttkb.Label(
            row_imp,
            text="格式：邮箱----密码（小水滴） 或 邮箱----密码----clientId----refreshToken（Graph）",
            font=FONT_MONO_SM,
            bootstyle="secondary",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttkb.Button(
            row_imp,
            text=f"{ICO['clear']} 清空",
            command=self._clear_all,
            bootstyle="outline-secondary",
            width=11,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttkb.Button(
            row_imp,
            text=f"{ICO['import_file']} 导入文件",
            command=self._import_file,
            bootstyle="info-outline",
            width=12,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttkb.Button(
            row_imp,
            text=f"{ICO['paste']} 粘贴导入",
            command=self._paste_import,
            bootstyle="info-outline",
            width=12,
        ).pack(side=tk.RIGHT)

        # ----- 邮箱验证取件方式（GitHub 邮件：确认链接 vs 数字码）-----
        f_verify = ttkb.Labelframe(
            root,
            text=f" {ICO['key']} 邮箱验证取件 ",
            padding=(12, 8),
            bootstyle="secondary",
        )
        f_verify.pack(fill=tk.X, padx=12, pady=(0, 6))
        row_vf = ttkb.Frame(f_verify)
        row_vf.pack(fill=tk.X)
        ttkb.Radiobutton(
            row_vf,
            text="验证链接（邮件内确认 URL，在浏览器中打开）",
            variable=self.var_verify_fetch,
            value=VERIFY_FETCH_LINK,
            bootstyle="info-toolbutton",
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttkb.Radiobutton(
            row_vf,
            text="验证码（邮件内数字/字符码，自动填入页面）",
            variable=self.var_verify_fetch,
            value=VERIFY_FETCH_CODE,
            bootstyle="info-toolbutton",
        ).pack(side=tk.LEFT)
        ttkb.Label(
            f_verify,
            text="请按实际收到的 GitHub 邮件选择；不要混用，避免解析误判。",
            font=FONT_MONO_SM,
            bootstyle="secondary",
        ).pack(fill=tk.X, pady=(6, 0))

        # ----- 任务列表 -----
        f_table = ttkb.Labelframe(
            root,
            text=f" {ICO['list']} 任务列表 ",
            padding=(8, 8),
            bootstyle="info",
        )
        f_table.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        cols = ("idx", "email", "mode", "status")
        self.tree = ttkb.Treeview(
            f_table,
            columns=cols,
            show="headings",
            height=9,
            bootstyle="dark",
            selectmode="extended",
        )
        self.tree.heading("idx", text="#")
        self.tree.heading("email", text="邮箱")
        self.tree.heading("mode", text="取件")
        self.tree.heading("status", text="状态")
        self.tree.column("idx", width=44, anchor=tk.CENTER, stretch=False)
        self.tree.column("email", width=320, anchor=tk.W, stretch=True)
        self.tree.column("mode", width=88, anchor=tk.CENTER, stretch=False)
        self.tree.column("status", width=108, anchor=tk.CENTER, stretch=False)

        tree_scroll = ttkb.Scrollbar(f_table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        hint = ttkb.Label(
            f_table,
            text="提示：按住 Ctrl / ⌘ 或 Shift 可多选，再点「注册选中」",
            font=("", 9),
            bootstyle="secondary",
        )
        hint.pack(fill=tk.X, pady=(6, 0))

        # ----- 操作栏 -----
        f_actions = ttkb.Frame(root, padding=(12, 6))
        f_actions.pack(fill=tk.X)

        self.btn_run_selected = ttkb.Button(
            f_actions,
            text=f"{ICO['run_sel']} 注册选中",
            command=self._run_selected,
            bootstyle="success",
            width=14,
        )
        self.btn_run_selected.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_run_all = ttkb.Button(
            f_actions,
            text=f"{ICO['run_all']} 全部轮询",
            command=self._run_all,
            bootstyle="primary",
            width=14,
        )
        self.btn_run_all.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_skip = ttkb.Button(
            f_actions,
            text=f"{ICO['skip']} 跳过当前",
            command=self._skip_current,
            bootstyle="warning-outline",
            width=12,
            state=tk.DISABLED,
        )
        self.btn_skip.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = ttkb.Button(
            f_actions,
            text=f"{ICO['stop']} 停止",
            command=self._stop,
            bootstyle="danger-outline",
            width=10,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        ttkb.Button(
            f_actions,
            text=f"{ICO['doc']} 打开导出",
            command=self._open_output,
            bootstyle="info-outline",
            width=12,
        ).pack(side=tk.RIGHT)

        f_stats = ttkb.Frame(f_actions, bootstyle="secondary", padding=(10, 4))
        f_stats.pack(side=tk.RIGHT, padx=(12, 10))
        self.lbl_stats = ttkb.Label(
            f_stats,
            text=f"{ICO['ok']} 成功 0    {ICO['fail']} 失败 0",
            font=FONT_MONO_SM,
            bootstyle="secondary",
        )
        self.lbl_stats.pack()

        # ----- 进度 -----
        f_prog = ttkb.Frame(root, padding=(12, 4, 12, 2))
        f_prog.pack(fill=tk.X)

        self.lbl_current = ttkb.Label(f_prog, text="就绪", font=("", 10, "bold"))
        self.lbl_current.pack(side=tk.LEFT)
        self.lbl_step = ttkb.Label(f_prog, text="", font=FONT_MONO_SM, bootstyle="secondary")
        self.lbl_step.pack(side=tk.RIGHT)

        self.progressbar = ttkb.Progressbar(
            root, mode="determinate", bootstyle="success-striped"
        )
        self.progressbar.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ----- 日志 | 结果 -----
        f_bottom = ttkb.Panedwindow(root, orient=tk.HORIZONTAL)
        f_bottom.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        f_log = ttkb.Labelframe(
            f_bottom,
            text=f" {ICO['log']} 运行日志 ",
            padding=6,
            bootstyle="dark",
        )
        self.log_area = scrolledtext.ScrolledText(
            f_log,
            font=FONT_MONO_SM,
            wrap=tk.WORD,
            bg="#0d1117",
            fg="#c9d1d9",
            insertbackground="#58a6ff",
            selectbackground="#264f78",
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        f_bottom.add(f_log, weight=3)

        f_result = ttkb.Labelframe(
            f_bottom,
            text=f" {ICO['key']} 导出预览（邮箱---密码---2FA） ",
            padding=6,
            bootstyle="success",
        )
        self.result_area = scrolledtext.ScrolledText(
            f_result,
            font=FONT_MONO,
            wrap=tk.WORD,
            bg="#0d1117",
            fg="#3fb950",
            insertbackground="#3fb950",
            selectbackground="#238636",
            relief=tk.FLAT,
            highlightthickness=0,
        )
        self.result_area.pack(fill=tk.BOTH, expand=True)
        f_bottom.add(f_result, weight=2)

        # ----- 底栏状态 -----
        self.lbl_footer = ttkb.Label(
            root,
            text="就绪 · BitBrowser · 人机验证在浏览器内完成 · 邮箱验证请在上方选择链接或验证码取件",
            font=("", 9),
            bootstyle="secondary",
        )
        self.lbl_footer.pack(fill=tk.X, padx=16, pady=(4, 10))

    # ================================================================
    # 日志轮询
    # ================================================================

    def _poll_log(self) -> None:
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if msg is None:
                continue
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
        self.root.after(POLL_INTERVAL_MS, self._poll_log)

    def _log(self, msg: str) -> None:
        self.log_queue.put(msg)

    # ================================================================
    # 账号列表管理
    # ================================================================

    def _refresh_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, acc in enumerate(self.accounts):
            mode_label = "Graph" if acc.get("mode") == "graph" else "小水滴"
            status = acc.get("status", STATUS_PENDING)
            self.tree.insert("", tk.END, iid=str(i), values=(i + 1, acc["email"], mode_label, status))

    def _update_tree_status(self, idx: int, status: str) -> None:
        self.accounts[idx]["status"] = status
        iid = str(idx)
        if self.tree.exists(iid):
            mode_label = "Graph" if self.accounts[idx].get("mode") == "graph" else "小水滴"
            self.tree.item(iid, values=(idx + 1, self.accounts[idx]["email"], mode_label, status))

    def _add_accounts_from_text(self, text: str) -> int:
        added = 0
        for line in text.strip().splitlines():
            parsed = _parse_mail_line(line)
            if parsed:
                parsed["status"] = STATUS_PENDING
                self.accounts.append(parsed)
                added += 1
        if added:
            self._refresh_tree()
        return added

    def _import_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择账号文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            n = self._add_accounts_from_text(content)
            self._log(f"从文件导入 {n} 个账号")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _paste_import(self) -> None:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("提示", "剪贴板为空")
            return
        n = self._add_accounts_from_text(text)
        if n:
            self._log(f"从剪贴板导入 {n} 个账号")
        else:
            messagebox.showwarning("提示", "剪贴板中未找到有效账号格式")

    def _clear_all(self) -> None:
        if self.running:
            messagebox.showwarning("提示", "请先停止当前任务")
            return
        self.accounts.clear()
        self._refresh_tree()
        self._log("已清空账号列表")

    def _open_output(self) -> None:
        if os.path.isfile(OUTPUT_FILE):
            _open_path_default_app(OUTPUT_FILE)
        else:
            messagebox.showinfo("提示", "尚无导出文件")

    # ================================================================
    # 获取选中的账号索引
    # ================================================================

    def _selected_indices(self) -> list[int]:
        return [int(iid) for iid in self.tree.selection()]

    # ================================================================
    # 运行控制
    # ================================================================

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.skip_current = False
        if running:
            self.btn_run_selected.config(state=tk.DISABLED)
            self.btn_run_all.config(state=tk.DISABLED)
            self.btn_skip.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
        else:
            self.btn_run_selected.config(state=tk.NORMAL)
            self.btn_run_all.config(state=tk.NORMAL)
            self.btn_skip.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)

    def _run_selected(self) -> None:
        indices = self._selected_indices()
        if not indices:
            messagebox.showinfo("提示", "请先在列表中选择要注册的账号（可多选：Ctrl/Shift+点击）")
            return
        self._start_work(indices)

    def _run_all(self) -> None:
        pending = [i for i, a in enumerate(self.accounts)
                    if a.get("status") in (STATUS_PENDING, STATUS_FAILED)]
        if not pending:
            messagebox.showinfo("提示", "没有等待注册或失败的账号")
            return
        self._start_work(pending)

    def _skip_current(self) -> None:
        self.skip_current = True
        self._log(">>> 用户请求跳过当前账号，等待当前步骤结束...")

    def _stop(self) -> None:
        self.running = False
        self.skip_current = True
        self._log(">>> 用户请求停止")
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_skip.config(state=tk.DISABLED)

    def _is_cancelled(self) -> bool:
        return not self.running or self.skip_current

    def _start_work(self, indices: list[int]) -> None:
        self.success_count = 0
        self.fail_count = 0
        self.root.after(
            0,
            lambda: self.lbl_stats.config(
                text=f"{ICO['ok']} 成功 0    {ICO['fail']} 失败 0"
            ),
        )
        self.root.after(
            0,
            lambda: self.lbl_footer.config(
                text="任务运行中… 请勿关闭 BitBrowser 窗口"
            ),
        )
        self.root.after(0, lambda: self.progressbar.config(maximum=len(indices), value=0))
        self.log_area.delete("1.0", tk.END)
        _failed_log_batch_start(len(indices))
        self._set_running(True)
        vf = self.var_verify_fetch.get()
        if vf not in (VERIFY_FETCH_LINK, VERIFY_FETCH_CODE):
            vf = DEFAULT_VERIFY_FETCH
        self._worker_thread = threading.Thread(
            target=self._batch_worker, args=(indices, vf), daemon=True
        )
        self._worker_thread.start()

    # ================================================================
    # 批量工作线程
    # ================================================================

    def _batch_worker(self, indices: list[int], verify_fetch: str) -> None:
        total = len(indices)
        for seq, idx in enumerate(indices):
            if not self.running:
                break

            self.skip_current = False
            account = self.accounts[idx]
            email = account["email"]

            self._log(f"\n{'='*55}")
            self._log(f"[{seq + 1}/{total}] 开始: {email} ({'Graph' if account.get('mode') == 'graph' else '小水滴'})")
            self._log(f"{'='*55}")

            self.root.after(0, lambda e=email: self.lbl_current.config(
                text=f"处理中: {e}", bootstyle="warning"
            ))

            def on_status(st: str, _idx=idx) -> None:
                self.root.after(0, lambda: self._update_tree_status(_idx, st))
                self.root.after(0, lambda: self.lbl_step.config(text=st))

            status = _run_single_account(
                account,
                self._log,
                on_status,
                self._is_cancelled,
                verify_fetch=verify_fetch,
            )

            if status == "success":
                self.success_count += 1
                self._add_result(email, status)
            elif status == "partial":
                self.success_count += 1
                self._add_result(email, status)
            elif status == "skipped":
                self._log(f"[{email}] 已跳过")
                self.root.after(0, lambda _i=idx: self._update_tree_status(_i, STATUS_SKIPPED))
            else:
                self.fail_count += 1
                self._add_result(email, status)

            self.root.after(
                0,
                lambda sc=self.success_count, fc=self.fail_count: self.lbl_stats.config(
                    text=f"{ICO['ok']} 成功 {sc}    {ICO['fail']} 失败 {fc}"
                ),
            )
            self.root.after(0, lambda s=seq: self.progressbar.config(value=s + 1))

        self.running = False
        self.root.after(0, self._work_done)

    def _add_result(self, email: str, status: str) -> None:
        if status == "success":
            tag = "[成功]"
        elif status == "partial":
            tag = "[部分]"
        else:
            tag = "[失败]"
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            last = lines[-1].strip() if lines else ""
        except Exception:
            last = ""

        def _insert() -> None:
            self.result_area.insert(tk.END, f"{tag} {email}\n")
            if last:
                self.result_area.insert(tk.END, f"  → {last}\n")
            self.result_area.see(tk.END)

        self.root.after(0, _insert)

    def _work_done(self) -> None:
        self._set_running(False)
        self.lbl_current.config(text="已完成", bootstyle="success")
        self.lbl_step.config(text="")
        self.lbl_footer.config(
            text=f"本轮结束 · 成功 {self.success_count} · 失败 {self.fail_count} · 可继续导入或注册"
        )
        self._log(f"\n任务完成。成功: {self.success_count}，失败: {self.fail_count}")
        if os.path.isfile(OUTPUT_FILE):
            self._log(f"成功结果: {OUTPUT_FILE}")
        if self.fail_count > 0 and os.path.isfile(FAILED_FILE):
            self._log(
                f"失败记录（制表符分隔，含时间/阶段）: {FAILED_FILE}"
            )

    # ================================================================
    # 启动
    # ================================================================

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
