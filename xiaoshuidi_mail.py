"""
小水滴微软邮箱 API 取件服务。
接口文档: https://api.7gemail.com/apiDoc/getMailInfo

传入邮箱账号+密码，调用 API 获取最新邮件，从 HTML 正文中提取验证码或验证链接。
"""
from __future__ import annotations

import re
import sys
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

API_URL = "https://api.bujidian.com/getMailInfo"
REQUEST_TIMEOUT = 30

# 6-8 位纯数字验证码
CODE_RE = re.compile(r"\b(\d{6,8})\b")
# HTML href 中的链接
HREF_RE = re.compile(r'href\s*=\s*["\']?(https?://[^\s"\'<>]+)', re.IGNORECASE)
# 纯文本中的链接
URL_RE = re.compile(r"https?://[^\s<>\"'\\)]+")


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------

def get_mail(
    name: str,
    pwd: str,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
) -> dict[str, Any]:
    """
    调用小水滴 API 获取邮箱最新一封邮件（收件箱+垃圾箱）。

    :return: {"subject", "sender", "send_time_utc", "send_time_beijing", "content"}
    :raises RuntimeError: API 返回失败
    """
    params: dict[str, str] = {"name": name, "pwd": pwd}
    if sender:
        params["sender"] = sender
    if subject:
        params["subject"] = subject

    resp = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != 1:
        raise RuntimeError(f"小水滴取件失败: {data.get('message', '未知错误')}")
    return data["message"]


def get_verification_info(
    name: str,
    pwd: str,
    keyword: str = "github",
) -> tuple[Optional[str], Optional[str]]:
    """
    一次 API 调用，从 GitHub 邮件中提取验证码或验证链接。

    流程：
      1. 调用小水滴 API（sender=github.com）获取最新邮件
      2. 从 content（HTML）中提取 6-8 位数字验证码
      3. 若无验证码，提取 github.com/account_verifications 链接

    :return: (code_or_link, diagnostic)
    """
    # 不传 sender 过滤，避免 API 精确匹配导致找不到邮件
    try:
        mail = get_mail(name, pwd)
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"小水滴 API 请求异常: {e}"

    subj = mail.get("subject") or ""
    sender = (mail.get("sender") or "").lower()
    content = (mail.get("content") or "").replace("&amp;", "&")

    # 确认是 GitHub 邮件
    if "github" not in subj.lower() and "github" not in sender:
        return None, (
            f"最新邮件不是 GitHub 的"
            f"（主题: {subj}，发件人: {mail.get('sender')}）"
        )

    # 优先提取验证码：从 subject + content 中找 6-8 位数字
    text = subj + "\n" + content
    for m in CODE_RE.finditer(text):
        return m.group(1), None

    # 其次提取验证链接：从 href 属性中找 github.com 验证链接
    for url in HREF_RE.findall(content):
        if "github.com" in url and ("account_verifications" in url or "verify" in url or "confirm" in url):
            return url, None

    # 兜底：从纯文本中找
    for url in URL_RE.findall(content):
        if "github.com" in url and ("account_verifications" in url or "verify" in url or "confirm" in url):
            return url, None

    return None, (
        f"小水滴取到 GitHub 邮件但未提取到验证码或链接"
        f"（主题: {subj}）"
    )


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="小水滴邮箱取件工具")
    parser.add_argument("--name", required=True, help="邮箱账号")
    parser.add_argument("--pwd", required=True, help="邮箱密码")
    parser.add_argument("--sender", help="按发件人过滤")
    parser.add_argument("--subject", help="按主题模糊匹配")
    parser.add_argument("--verify", action="store_true",
                        help="提取 GitHub 验证信息（验证码或链接）")
    args = parser.parse_args()

    if args.verify:
        result, diag = get_verification_info(args.name, args.pwd)
        if result:
            print("验证信息:", result)
        else:
            print(diag or "未找到验证信息", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            info = get_mail(args.name, args.pwd,
                            sender=args.sender, subject=args.subject)
            print(f"主题: {info.get('subject')}")
            print(f"发件人: {info.get('sender')}")
            print(f"时间(UTC): {info.get('send_time_utc')}")
            print(f"时间(北京): {info.get('send_time_beijing')}")
            print(f"正文:\n{info.get('content')}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
