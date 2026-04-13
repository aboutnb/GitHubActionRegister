"""
小水滴微软邮箱 API 取件服务。
接口文档: https://api.7gemail.com/apiDoc/getMailInfo

无需 OAuth 授权，仅需邮箱账号+密码即可获取最新邮件（收件箱+垃圾箱）。
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

VERIFICATION_LINK_KEYWORDS = (
    "verify", "confirm", "token", "signup", "email",
    "verification", "verif",
)
LINK_RE = re.compile(r"https?://[^\s<>\"'\\)]+")
HREF_URL_RE = re.compile(r'href\s*=\s*["\']?(https?://[^\s"\'<>]+)["\']?', re.IGNORECASE)
URL_TRAILING_PUNCTUATION = ".,;:!?)\"'"

LAUNCH_CODE_KEYWORDS = (
    "launch code",
    "code below",
    "your github launch code",
)
LAUNCH_CODE_RE = re.compile(r"\b(\d{6,8})\b")


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "").replace("\n", "").replace("\r", "")


def _strip_trailing(url: str) -> str:
    return url.rstrip(URL_TRAILING_PUNCTUATION)


def _is_verification_url(url: str) -> bool:
    if not url or "github.com" not in url:
        return False
    if url.count("https://") + url.count("http://") != 1:
        return False
    return any(k in url for k in VERIFICATION_LINK_KEYWORDS)


def _extract_launch_code(text: str) -> Optional[str]:
    t = (text or "").lower()
    if not any(k in t for k in LAUNCH_CODE_KEYWORDS):
        return None
    for m in LAUNCH_CODE_RE.finditer(text or ""):
        code = m.group(1)
        if code and code.isdigit():
            return code
    return None


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
    获取邮箱最新一封邮件（收件箱+垃圾箱）。

    :param name: 邮箱账号
    :param pwd: 邮箱密码
    :param sender: 可选，按发件人过滤
    :param subject: 可选，按主题模糊匹配
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


def get_verification_link(
    name: str,
    pwd: str,
    keyword: str = "github",
) -> tuple[Optional[str], Optional[str]]:
    """
    获取邮箱最新的 GitHub 验证链接。

    :return: (link, diagnostic)。找到时 diagnostic 为 None；未找到时 link 为 None。
    """
    try:
        mail = get_mail(name, pwd, sender="github.com")
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"小水滴 API 请求异常: {e}"

    content = mail.get("content") or ""
    subj = (mail.get("subject") or "").lower()
    sndr = (mail.get("sender") or "").lower()

    if not (keyword.lower() in subj or keyword.lower() in content.lower() or "github.com" in sndr):
        return None, (
            f"小水滴取到最新邮件，但与 '{keyword}' 无关"
            f"（主题: {mail.get('subject')}，发件人: {mail.get('sender')}）"
        )

    text = _normalize_text(content.replace("&amp;", "&"))
    for url in LINK_RE.findall(text):
        u = _strip_trailing(url.replace("&amp;", "&"))
        if _is_verification_url(u):
            return u, None
    for url in HREF_URL_RE.findall(text):
        u = _strip_trailing(url.replace("&amp;", "&"))
        if _is_verification_url(u):
            return u, None

    return None, f"小水滴取到 GitHub 邮件，但未解析出验证链接（主题: {mail.get('subject')}）"


def get_verification_code(
    name: str,
    pwd: str,
    keyword: str = "github",
) -> tuple[Optional[str], Optional[str]]:
    """
    获取邮箱最新的 GitHub 验证码（launch code，6-8 位数字）。

    :return: (code, diagnostic)。找到时 diagnostic 为 None；未找到时 code 为 None。
    """
    try:
        mail = get_mail(name, pwd, sender="github.com")
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"小水滴 API 请求异常: {e}"

    content = mail.get("content") or ""
    subj = (mail.get("subject") or "").lower()
    sndr = (mail.get("sender") or "").lower()

    if not (keyword.lower() in subj or keyword.lower() in content.lower() or "github.com" in sndr):
        return None, (
            f"小水滴取到最新邮件，但与 '{keyword}' 无关"
            f"（主题: {mail.get('subject')}，发件人: {mail.get('sender')}）"
        )

    combined = (mail.get("subject") or "") + "\n" + content
    code = _extract_launch_code(combined)
    if code:
        return code, None

    return None, f"小水滴取到 GitHub 邮件，但未解析出验证码（主题: {mail.get('subject')}）"


def get_verification_info(
    name: str,
    pwd: str,
    keyword: str = "github",
) -> tuple[Optional[str], Optional[str]]:
    """
    获取 GitHub 验证信息（优先验证链接，其次验证码）。

    :return: (link_or_code, diagnostic)
    """
    link, diag = get_verification_link(name, pwd, keyword=keyword)
    if link:
        return link, None
    code, diag_code = get_verification_code(name, pwd, keyword=keyword)
    if code:
        return code, None
    return None, diag_code or diag


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
                        help="提取 GitHub 验证信息（链接或验证码）")
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
            print(f"正文: {info.get('content')}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
