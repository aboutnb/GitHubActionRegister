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
from bitbrower import create_github_ready_browser, open_browser
from getmail import set_current_account, get_verification_link_from_inbox

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
    """解析单行 邮箱----密码----第3段----refresh_token（4 段 ---- 分隔），返回四元组或 None。第3段为邮箱相关标识，程序不使用。"""
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
                "邮箱----密码----第3段----refresh_token\n"
                "注册与收取验证码均使用此账号。",
            )
            return
        email, base_password, _third, refresh_token = parsed  # 第三段是邮箱相关标识，OAuth 的 client_id 用 .env.local 的 GRAPH_CLIENT_ID
        set_current_account(refresh_token)
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
        if not ws:
            messagebox.showinfo("提示", "请先点击 Start 完成注册步骤")
            return
        log_area.insert(tk.END, "正在从邮箱获取 GitHub 验证链接...\n")
        try:
            link, _, diag = get_verification_link_from_inbox(keyword=VERIFICATION_KEYWORD, top=VERIFICATION_TOP)
            if link:
                log_area.insert(tk.END, f"验证链接: {link}\n")
                result_area.delete("1.0", tk.END)
                result_area.insert(tk.END, f"请在此浏览器中打开链接完成验证:\n{link}\n")
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        browser = p.chromium.connect_over_cdp(ws)
                        if browser.contexts and browser.contexts[0].pages:
                            browser.contexts[0].pages[0].goto(link, timeout=CDP_GOTO_NO_TIMEOUT)
                except Exception:
                    pass
            else:
                log_area.insert(tk.END, (diag or "未在收件箱中找到 GitHub 验证邮件。") + "\n")
        except Exception as e:
            log_area.insert(tk.END, f"取件错误: {e}\n")
        log_area.see(tk.END)

    def do_enable_2fa() -> None:
        ws = cdp_ws_var.get()
        if not ws:
            messagebox.showinfo("提示", "请先完成上一步并在浏览器中完成邮箱验证")
            return
        email = parsed_account.get("email") or ""
        base = parsed_account.get("base_password") or ""
        if not email or not base:
            messagebox.showwarning("提示", "请先点击 Start 并粘贴完整格式的邮箱账号行")
            return

        def run() -> None:
            from github_automation import run_enable_2fa_and_get_secret
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            secret = loop.run_until_complete(
                run_enable_2fa_and_get_secret(ws, log_callback=log_queue.put)
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
    ttk.Label(f_input, text="粘贴完整格式的邮箱账号行\n格式: 邮箱----密码----第3段----refresh_token").pack(
        anchor=tk.W, pady=(0, 4)
    )
    account_text = scrolledtext.ScrolledText(f_input, height=8, font=FONT_CONSOLE, wrap=tk.WORD)
    account_text.pack(fill=tk.X, pady=4)
    ttk.Label(
        f_input,
        text="例: jiache1973@outlook.com----rkov9502----dbc8e03a-xxx----M.C541_SN1.0.U.-CgYr9X...（4 段用 ---- 分隔）",
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
