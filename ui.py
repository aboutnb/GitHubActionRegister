"""
邮箱账号管理 UI：粘贴 Hotmail/Outlook 账号行，解析后设为当前取信账号或拉取收件箱。
单行格式：email----password----第3段----refresh_token（4 段用 ---- 分隔；应用 client_id 在 .env.local 配置）
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import List, Optional, Tuple

import getmail  # noqa: F401  # 先加载 .env
from getmail import set_current_account, get_inbox, get_verification_link_from_inbox

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SEP = "----"
VERIFICATION_KEYWORD = "github"
VERIFICATION_TOP = 15
INBOX_TOP = 20
SUBJECT_PREVIEW_LEN = 60

WINDOW_TITLE = "Hotmail/Outlook 账号 · 取信"
WINDOW_GEOMETRY = "720x560"
WINDOW_MINSIZE = (520, 400)
POLL_INTERVAL_MS = 300
FONT_CONSOLE = ("Consolas", 10)
FONT_LABEL = ("", 10)
FONT_STATUS = ("", 9)


def parse_account_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """解析单行，返回 (email, password, client_id, refresh_token) 或 None。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(SEP)
    if len(parts) != 4:
        return None
    return (parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip())


def parse_accounts(text: str) -> List[Tuple[str, str, str, str]]:
    """解析多行，返回 [(email, password, client_id, refresh_token), ...]。"""
    result: List[Tuple[str, str, str, str]] = []
    for line in text.splitlines():
        acc = parse_account_line(line)
        if acc:
            result.append(acc)
    return result


def run_ui() -> None:
    """启动邮箱账号管理 / 取信图形界面。"""
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_GEOMETRY)
    root.minsize(*WINDOW_MINSIZE)

    accounts: List[Tuple[str, str, str, str]] = []
    result_queue: queue.Queue = queue.Queue()

    def _poll_result() -> None:
        try:
            while True:
                out_text = result_queue.get_nowait()
                result_area.delete("1.0", tk.END)
                result_area.insert(tk.END, out_text)
                status_var.set(
                    f"已解析 {len(accounts)} 个账号" if accounts
                    else "粘贴上方格式的账号行，点击「解析账号」"
                )
        except queue.Empty:
            pass
        root.after(POLL_INTERVAL_MS, _poll_result)

    def on_parse() -> None:
        nonlocal accounts
        raw = text_paste.get("1.0", tk.END)
        accounts = parse_accounts(raw)
        listbox.delete(0, tk.END)
        for email, *_ in accounts:
            listbox.insert(tk.END, email)
        if accounts:
            status_var.set(f"已解析 {len(accounts)} 个账号")
        else:
            status_var.set("未解析到有效行，格式：email----password----第3段----refresh_token")

    def on_set_current() -> None:
        sel = listbox.curselection()
        if not sel or not accounts:
            messagebox.showinfo("提示", "请先粘贴并解析，再选中一个账号")
            return
        idx = sel[0]
        email, _pw, _third, refresh_token = accounts[idx]  # 第三段非 OAuth client_id，应用 client_id 来自 .env.local
        try:
            set_current_account(refresh_token)
            status_var.set(f"已设为当前账号: {email}（后续拉取收件箱/查验证链接将用此邮箱）")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def on_get_inbox() -> None:
        status_var.set("拉取收件箱中…（若弹出浏览器登录，请在浏览器内完成，窗口会保持响应）")
        result_area.delete("1.0", tk.END)
        result_area.insert(tk.END, "请稍候…\n")

        def work() -> None:
            try:
                data = get_inbox(top=INBOX_TOP)
                out = ["【以下为当前取信账号的收件箱；若非注册用邮箱，请先选中该邮箱行并点「设为当前账号」】", ""]
                for m in data.get("value", []):
                    addr = (m.get("sender") or {}).get("emailAddress", {}).get("address", "")
                    subj = (m.get("subject") or "")[:SUBJECT_PREVIEW_LEN]
                    out.append(f"{m.get('receivedDateTime')} | {addr} | {subj}")
                out_text = "\n".join(out) if out else "收件箱为空"
            except Exception as e:
                out_text = f"Error: {e}"
            result_queue.put(out_text)

        threading.Thread(target=work, daemon=True).start()

    def on_get_verification() -> None:
        status_var.set("查找 GitHub 验证邮件中…（若需登录，请在浏览器内完成）")
        result_area.delete("1.0", tk.END)
        result_area.insert(tk.END, "请稍候…\n")

        def work() -> None:
            try:
                link, _, diag = get_verification_link_from_inbox(keyword=VERIFICATION_KEYWORD, top=VERIFICATION_TOP)
                out_text = link if link else (diag or "未找到包含 github 的验证邮件")
            except Exception as e:
                out_text = f"Error: {e}"
            result_queue.put(out_text)

        threading.Thread(target=work, daemon=True).start()

    # ---------- 布局 ----------
    frame_help = ttk.Frame(root, padding=6)
    frame_help.pack(fill=tk.X)
    ttk.Label(
        frame_help,
        text="每行格式：邮箱----密码----第3段----refresh_token（4 段用 ---- 分隔）",
        font=FONT_LABEL,
    ).pack(anchor=tk.W)
    ttk.Label(
        frame_help,
        text="⚠ 取信/查验证链接用的是「当前账号」。若看到的是你自己个人邮箱的邮件，请选中注册用邮箱那一行 → 点「设为当前账号」→ 再拉取或查验证。",
        font=FONT_LABEL,
        foreground="darkred",
    ).pack(anchor=tk.W)

    ttk.Label(root, text="粘贴账号行：").pack(anchor=tk.W, padx=6, pady=(6, 0))
    text_paste = scrolledtext.ScrolledText(root, height=5, font=FONT_CONSOLE, wrap=tk.WORD)
    text_paste.pack(fill=tk.X, padx=6, pady=4)

    frame_mid = ttk.Frame(root, padding=6)
    frame_mid.pack(fill=tk.BOTH, expand=True)
    ttk.Button(frame_mid, text="解析账号", command=on_parse).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(frame_mid, text="已解析账号（选中后点「设为当前」再取信）：").pack(side=tk.LEFT, padx=(8, 0))
    listbox = tk.Listbox(frame_mid, height=4, font=FONT_CONSOLE, selectmode=tk.SINGLE)
    listbox.pack(fill=tk.BOTH, expand=True, pady=4)

    frame_btn = ttk.Frame(root, padding=6)
    frame_btn.pack(fill=tk.X)
    ttk.Button(frame_btn, text="设为当前账号", command=on_set_current).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(frame_btn, text="拉取收件箱", command=on_get_inbox).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(frame_btn, text="查 GitHub 验证链接", command=on_get_verification).pack(side=tk.LEFT, padx=(0, 8))

    ttk.Label(root, text="结果：").pack(anchor=tk.W, padx=6, pady=(6, 0))
    result_area = scrolledtext.ScrolledText(root, height=8, font=FONT_CONSOLE, wrap=tk.WORD)
    result_area.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    status_var = tk.StringVar(value="粘贴上方格式的账号行，点击「解析账号」")
    ttk.Label(root, textvariable=status_var, font=FONT_STATUS).pack(anchor=tk.W, padx=6, pady=(0, 6))

    root.after(POLL_INTERVAL_MS, _poll_result)
    root.mainloop()


if __name__ == "__main__":
    run_ui()
