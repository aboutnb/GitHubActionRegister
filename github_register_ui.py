"""
GitHub 注册流程 UI：填写邮箱账号行 → Start 走流程 → 人工图片验证 → 邮箱验证 → 2FA → 输出 账号---密码---2fa密钥
"""
from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Optional, Tuple

import getmail  # noqa: F401  # 先加载 .env
from bitbrower import create_github_ready_browser, open_browser, get_browser_detail
from getmail import (
    set_current_account,
    get_verification_link_from_inbox,
    get_verification_code_from_inbox,
    register_auth_url_opener,
)

# ---------------------------------------------------------------------------
# 常量（与 ui.py 一致）
# ---------------------------------------------------------------------------

SEP = "----"
PASSWORD_SUFFIX = "@Git2026"
VERIFICATION_KEYWORD = "github"
VERIFICATION_TOP = 15
# 打开验证链接不设超时，等待加载完成（不同代理延迟不同）
CDP_GOTO_NO_TIMEOUT = 0

# UI
WINDOW_TITLE = "GitHub 注册流程"
WINDOW_GEOMETRY = "640x520"
WINDOW_MINSIZE = (480, 400)
POLL_INTERVAL_MS = 200
FONT_CONSOLE = ("Consolas", 10)
FONT_CONSOLE_SMALL = ("Consolas", 9)
FONT_HINT = ("", 8)


def _parse_mail_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """解析单行 邮箱----密码----客户端ID----refresh_token（4 段 ---- 分隔），返回四元组或 None。"""
    line = line.strip()
    if not line:
        return None
    parts = line.split(SEP)
    if len(parts) != 4:
        return None
    return (parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip())


def _run_async_in_thread(coro, log_queue: queue.Queue) -> None:
    """在后台线程中运行 asyncio 协程，日志通过 log_queue 回传主线程。"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    except Exception as e:
        log_queue.put(f"[异常] {e}")
    finally:
        log_queue.put(None)


def _cdp_ws_from_open_result(open_result: dict) -> str:
    """从 open_browser 返回结果拼出 CDP WebSocket URL。"""
    ws = open_result.get("ws") or ""
    if not ws and open_result.get("http"):
        http = open_result.get("http", "")
        pid = open_result.get("pid", "")
        ws = f"ws://{http}/devtools/browser/{pid}"
    return ws


def _email_to_username(email: str, max_len: int = 20) -> str:
    """从邮箱生成 GitHub 用户名（去掉 . 和 +，截断）。"""
    return email.split("@")[0].replace(".", "").replace("+", "")[:max_len]


def _profile_name_from_email(email: str) -> str:
    """从邮箱生成浏览器档案名。"""
    return "github-reg-" + email.replace("@", "-")[:20]


def _ensure_browser_connected(
    profile_id: str,
    current_ws: str,
    log_queue: queue.Queue,
) -> Optional[str]:
    """
    确保浏览器连接可用。若当前 CDP WebSocket 连接失败，尝试重新打开浏览器并返回新的 WebSocket URL。
    成功返回 WebSocket URL，失败返回 None。
    """
    # 先尝试用当前 WebSocket 连接测试
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(current_ws)
            # 如果能连接成功，返回当前 URL
            if browser and browser.contexts:
                return current_ws
    except Exception:
        # 连接失败，尝试重新打开浏览器
        pass

    # 重新打开浏览器
    try:
        log_queue.put("浏览器连接已断开，正在重新打开浏览器...")
        open_result = open_browser(profile_id)
        new_ws = _cdp_ws_from_open_result(open_result)
        if new_ws:
            log_queue.put(f"浏览器已重新打开，新的 CDP 地址: {new_ws}")
            return new_ws
    except Exception as e:
        log_queue.put(f"重新打开浏览器失败: {e}")
        return None

    return None


def run_ui() -> None:
    """启动 GitHub 注册流程图形界面。"""
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_GEOMETRY)
    root.minsize(*WINDOW_MINSIZE)

    profile_id_var = tk.StringVar(value="")
    cdp_ws_var = tk.StringVar(value="")
    result_var = tk.StringVar(value="")
    parsed_account: dict[str, str] = {"email": "", "base_password": ""}
    log_queue: queue.Queue = queue.Queue()

    def poll_log() -> None:
        while True:
            try:
                msg = log_queue.get_nowait()
            except queue.Empty:
                break
            if msg is None:
                continue
            log_area.insert(tk.END, msg + "\n")
            log_area.see(tk.END)
        root.after(POLL_INTERVAL_MS, poll_log)

    def do_start() -> None:
        raw = account_text.get("1.0", tk.END).strip()
        line = raw.replace("\n", "").strip() or raw
        parsed = _parse_mail_line(line) if line else None
        if not parsed:
            messagebox.showwarning(
                "提示",
                "请粘贴完整格式的邮箱账号行（4 段用 ---- 分隔）：\n"
                "邮箱----密码----客户端ID----refresh_token\n"
                "注册与收取验证码均使用此账号。",
            )
            return
        # 第三段为 Outlook/Hotmail 所使用的 Microsoft Entra 应用 client_id，
        # 用于覆盖 .env.local 中的 GRAPH_CLIENT_ID，支持一机多应用。
        email, base_password, client_id, refresh_token = parsed
        set_current_account(refresh_token, client_id=client_id)
        parsed_account["email"] = email
        parsed_account["base_password"] = base_password
        final_password = base_password + PASSWORD_SUFFIX
        username = _email_to_username(email)
        log_area.insert(tk.END, f"已解析账号 {email}，注册与收验证均用此邮箱\n")

        def run() -> None:
            try:
                log_queue.put("1. 创建并打开浏览器...")
                profile = create_github_ready_browser(
                    _profile_name_from_email(email),
                    url="about:blank",
                    platform="https://github.com",
                )
                pid = profile.get("id")
                if not pid:
                    log_queue.put("创建档案失败：未返回 id")
                    root.after(0, lambda: btn_start.config(state=tk.NORMAL))
                    return
                root.after(0, lambda: profile_id_var.set(pid))
                open_result = open_browser(pid)
                ws = _cdp_ws_from_open_result(open_result)
                root.after(0, lambda: cdp_ws_var.set(ws))
                log_queue.put("2. 浏览器已打开，开始自动化注册流程...")

                # 注册 Graph 授权 URL 打开方式：在当前 Bitbrowser 窗口中打开，
                # 避免在本机默认浏览器里用错账号授权成你自己的邮箱。
                def _open_graph_auth_in_current_browser(auth_url: str) -> None:
                    try:
                        from playwright.sync_api import sync_playwright
                        with sync_playwright() as p:
                            browser = p.chromium.connect_over_cdp(ws)
                            context = browser.contexts[0] if browser.contexts else browser.new_context()
                            page = context.pages[0] if context.pages else context.new_page()
                            page.goto(auth_url, timeout=CDP_GOTO_NO_TIMEOUT)
                    except Exception as exc:
                        # 失败时不抛给上层，让 getmail 回退到系统浏览器
                        log_queue.put(f"在指纹浏览器中打开 Graph 授权页失败，将回退系统浏览器: {exc}")

                register_auth_url_opener(_open_graph_auth_in_current_browser)
                from github_automation import run_signup_flow
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    run_signup_flow(ws, email, final_password, username, log_callback=log_queue.put)
                )
                log_queue.put("3. 请在浏览器中完成图片验证，完成后点击「下一步：通过邮箱获取验证」。")
            except Exception as e:
                log_queue.put(f"Start 出错: {e}")
            root.after(0, lambda: btn_start.config(state=tk.NORMAL))

        btn_start.config(state=tk.DISABLED)
        threading.Thread(target=run, daemon=True).start()
        poll_log()

    def do_next_verify() -> None:
        ws = cdp_ws_var.get()
        profile_id = profile_id_var.get()
        if not ws or not profile_id:
            messagebox.showinfo("提示", "请先点击 Start 完成注册步骤")
            return
        log_area.insert(tk.END, "正在从邮箱获取 GitHub 验证信息（链接或验证码）...\n")
        try:
            link, _, diag = get_verification_link_from_inbox(keyword=VERIFICATION_KEYWORD, top=VERIFICATION_TOP)
            if link:
                log_area.insert(tk.END, f"验证链接: {link}\n")
                result_area.delete("1.0", tk.END)
                result_area.insert(tk.END, f"请在此浏览器中打开链接完成验证:\n{link}\n")
                try:
                    # 确保浏览器连接可用（使用临时队列收集日志，然后插入到 log_area）
                    temp_queue = queue.Queue()
                    active_ws = _ensure_browser_connected(profile_id, ws, temp_queue)
                    # 将临时队列中的日志移到 log_area
                    while True:
                        try:
                            msg = temp_queue.get_nowait()
                            if msg:
                                log_area.insert(tk.END, msg + "\n")
                        except queue.Empty:
                            break
                    if active_ws:
                        if active_ws != ws:
                            root.after(0, lambda: cdp_ws_var.set(active_ws))
                        from playwright.sync_api import sync_playwright
                        with sync_playwright() as p:
                            browser = p.chromium.connect_over_cdp(active_ws)
                            if browser.contexts and browser.contexts[0].pages:
                                browser.contexts[0].pages[0].goto(link, timeout=CDP_GOTO_NO_TIMEOUT)
                except Exception as e:
                    log_area.insert(tk.END, f"在浏览器中打开链接失败: {e}\n")
            else:
                # 若未解析到链接，再尝试解析 GitHub 启动码（launch code）
                code, _, diag_code = get_verification_code_from_inbox(
                    keyword=VERIFICATION_KEYWORD,
                    top=VERIFICATION_TOP,
                )
                if code:
                    log_area.insert(tk.END, f"已从邮箱获取 GitHub 验证码（launch code）: {code}\n")
                    result_area.delete("1.0", tk.END)
                    result_area.insert(
                        tk.END,
                        f"请在 GitHub 注册页面输入以下验证码完成验证（GitHub launch code）:\n{code}\n",
                    )
                else:
                    log_area.insert(
                        tk.END,
                        (diag_code or diag or "未在收件箱中找到 GitHub 验证邮件或验证码。") + "\n",
                    )
        except Exception as e:
            log_area.insert(tk.END, f"取件错误: {e}\n")
        log_area.see(tk.END)

    def do_enable_2fa() -> None:
        ws = cdp_ws_var.get()
        profile_id = profile_id_var.get()
        if not ws or not profile_id:
            messagebox.showinfo("提示", "请先点击 Start 完成注册步骤")
            return
        email = parsed_account.get("email") or ""
        base = parsed_account.get("base_password") or ""
        if not email or not base:
            messagebox.showwarning("提示", "请先点击 Start 并粘贴完整格式的邮箱账号行")
            return

        def run() -> None:
            # 确保浏览器连接可用，若断开则重新打开
            active_ws = _ensure_browser_connected(profile_id, ws, log_queue)
            if not active_ws:
                log_queue.put("无法连接到浏览器，请确认浏览器窗口是否已关闭。若已关闭，请重新点击 Start。")
                return

            # 如果重新打开了浏览器，更新 UI 中保存的 WebSocket URL
            if active_ws != ws:
                root.after(0, lambda: cdp_ws_var.set(active_ws))

            from github_automation import run_enable_2fa_and_get_secret
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            secret = loop.run_until_complete(
                run_enable_2fa_and_get_secret(active_ws, log_callback=log_queue.put)
            )
            if secret:
                final_pw = base + PASSWORD_SUFFIX
                out = f"{email}---{final_pw}---{secret}"
                result_var.set(out)
                root.after(0, lambda: result_area.insert(
                    tk.END, "\n最终账号格式（账号---密码---2fa密钥）:\n" + out + "\n"
                ))
                root.after(0, lambda: log_queue.put("2FA 密钥已获取，请按 GitHub 页面提示输入验证码完成启用。"))

        threading.Thread(target=run, daemon=True).start()
        poll_log()

    # ---------- 布局 ----------
    f_input = ttk.LabelFrame(root, text="注册信息（只填一行，注册与收验证均用此账号）", padding=8)
    f_input.pack(fill=tk.X, padx=8, pady=6)
    ttk.Label(f_input, text="粘贴完整格式的邮箱账号行\n格式: 邮箱----密码----客户端ID----refresh_token").pack(
        anchor=tk.W, pady=(0, 4)
    )
    account_text = scrolledtext.ScrolledText(f_input, height=8, font=FONT_CONSOLE, wrap=tk.WORD)
    account_text.pack(fill=tk.X, pady=4)
    ttk.Label(
        f_input,
        text="例: jiache1973@outlook.com----rkov9502----dbc8e03a-xxxx-客户端ID----M.C541_SN1.0.U.-CgYr9X...（4 段用 ---- 分隔）",
        font=FONT_HINT,
        foreground="gray",
    ).pack(anchor=tk.W, pady=(0, 0))

    btn_start = ttk.Button(root, text="Start（创建浏览器并开始注册）", command=do_start)
    btn_start.pack(pady=6)

    f_log = ttk.LabelFrame(root, text="流程日志", padding=6)
    f_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
    log_area = scrolledtext.ScrolledText(f_log, height=6, font=FONT_CONSOLE_SMALL, wrap=tk.WORD)
    log_area.pack(fill=tk.BOTH, expand=True)

    f_actions = ttk.Frame(root, padding=6)
    f_actions.pack(fill=tk.X)
    ttk.Button(f_actions, text="下一步：通过邮箱获取验证", command=do_next_verify).pack(side=tk.LEFT, padx=4)
    ttk.Button(f_actions, text="开启 2FA 并获取密钥", command=do_enable_2fa).pack(side=tk.LEFT, padx=4)

    f_result = ttk.LabelFrame(root, text="结果 / 验证链接 / 最终 账号---密码---2fa", padding=6)
    f_result.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
    result_area = scrolledtext.ScrolledText(f_result, height=6, font=FONT_CONSOLE, wrap=tk.WORD)
    result_area.pack(fill=tk.BOTH, expand=True)

    root.after(POLL_INTERVAL_MS, poll_log)
    root.mainloop()


if __name__ == "__main__":
    run_ui()
