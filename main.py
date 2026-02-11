"""
GitHub 注册流程入口：代理校验 → 创建/打开高仿真浏览器 → 取件查验证邮件。

必须先加载 .env / .env.local（通过导入 getmail 完成），再使用 bitbrower / getmail。
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

# 先加载环境变量（.env.local 覆盖 .env），供 bitbrower / getmail 使用
import getmail  # noqa: F401

from bitbrower import (
    check_proxy_ip,
    close_browser,
    create_github_ready_browser,
    open_browser,
)
from getmail import (
    get_verification_link_from_inbox,
    get_verification_code_from_inbox,
)

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------
DEFAULT_PROFILE_NAME = "github-signup"
DEFAULT_SIGNUP_URL = "https://github.com/signup"
DEFAULT_PLATFORM_URL = "https://github.com"
VERIFICATION_MAIL_TOP = 15
VERIFICATION_KEYWORD = "github"


# ---------------------------------------------------------------------------
# 流程步骤（单步函数便于测试与复用）
# ---------------------------------------------------------------------------

def _step_check_proxy() -> bool:
    """校验 Starry 代理出口 IP，与浏览器内环境一致以降低风控。"""
    print("1. 校验 Starry 代理出口 IP...")
    try:
        info = check_proxy_ip()
        print(f"   出口 IP: {info.get('ip')} | {info.get('city')}, {info.get('country')}")
        return True
    except Exception as e:
        print(f"   代理校验失败: {e}（请确认 Starry 配置与网络）")
        return False


def _step_create_and_open_browser(
    profile_name: str = DEFAULT_PROFILE_NAME,
    url: str = DEFAULT_SIGNUP_URL,
    platform: str = DEFAULT_PLATFORM_URL,
) -> Optional[str]:
    """
    创建面向 GitHub 的高仿真浏览器档案并打开。
    成功返回 profile_id，失败返回 None。
    """
    print("2. 创建 GitHub 注册用浏览器档案...")
    try:
        profile = create_github_ready_browser(
            profile_name,
            url=url,
            platform=platform,
        )
        profile_id = profile.get("id")
        if not profile_id:
            raise RuntimeError("创建档案未返回 id")
        print(f"   档案 id: {profile_id}")
    except Exception as e:
        print(f"   创建失败: {e}（请确认 Bitbrowser 已启动且 API/Token 正确）")
        return None

    print("3. 打开浏览器...")
    try:
        open_result = open_browser(profile_id)
        print(f"   已打开，CDP: {open_result.get('http')}")
        return profile_id
    except Exception as e:
        print(f"   打开失败: {e}")
        return None


def _step_poll_verification_link(
    keyword: str = VERIFICATION_KEYWORD,
    top: int = VERIFICATION_MAIL_TOP,
) -> Optional[str]:
    """用 Graph 轮询收件箱取 GitHub 验证链接或验证码。成功返回链接/验证码字符串，未找到或异常返回 None（异常会打印）。"""
    print("5. 轮询邮箱（Graph）查找 GitHub 验证链接或验证码...")
    try:
        link, _, diag = get_verification_link_from_inbox(keyword=keyword, top=top)
        if link:
            print(f"   找到验证链接: {link}")
            return link

        # 若未解析到链接，再尝试解析 GitHub 启动码（launch code）
        code, _, diag_code = get_verification_code_from_inbox(keyword=keyword, top=top)
        if code:
            print(f"   找到 GitHub 验证码（launch code）: {code}")
            return code

        print(f"   {diag_code or diag or '未在最近邮件中找到'}，可稍后运行 python main.py -m 再次轮询。")
        return None
    except Exception as e:
        print(f"   取件出错: {e}")
        return None


def run_github_signup_flow(
    profile_name: str = DEFAULT_PROFILE_NAME,
    keep_browser_open: bool = True,
    url: str = DEFAULT_SIGNUP_URL,
    platform: str = DEFAULT_PLATFORM_URL,
    poll_mail: bool = True,
) -> bool:
    """
    完整流程：校验代理 → 创建并打开 GitHub 注册用浏览器 → 提示在浏览器中注册
    → 可选轮询邮箱取验证链接。

    :param profile_name: Bitbrowser 档案名称
    :param keep_browser_open: 流程结束后是否保持浏览器打开
    :param url: 浏览器启动时打开的 URL
    :param platform: 平台 URL（用于图标等）
    :param poll_mail: 是否在打开浏览器后轮询邮箱取验证链接
    :return: 流程是否成功执行到结束（不含取件是否找到链接）
    """
    _step_check_proxy()

    profile_id = _step_create_and_open_browser(
        profile_name=profile_name,
        url=url,
        platform=platform,
    )
    if not profile_id:
        return False

    print("4. 请在弹出的浏览器中完成 GitHub 注册（填写邮箱等）。")
    print("   若需查收验证邮件，请在本终端按提示操作。")

    if poll_mail:
        _step_poll_verification_link()

    if keep_browser_open:
        print("   浏览器保持打开，用完后可在代码中调用 close_browser(profile_id) 或手动关闭。")
    else:
        try:
            close_browser(profile_id)
            print("   浏览器已关闭。")
        except Exception as e:
            print(f"   关闭浏览器时出错: {e}")

    return True


def run_mail_only(
    keyword: str = VERIFICATION_KEYWORD,
    top: int = VERIFICATION_MAIL_TOP,
) -> Optional[str]:
    """
    仅轮询邮箱取 GitHub 验证信息（验证链接或 launch code 验证码），供脚本调用。
    优先返回验证链接，若无链接则返回验证码；未找到返回 None，异常时抛出。
    """
    link, _, _ = get_verification_link_from_inbox(keyword=keyword, top=top)
    if link:
        return link
    code, _, _ = get_verification_code_from_inbox(keyword=keyword, top=top)
    return code


def run_ui() -> None:
    """启动 GitHub 注册流程 UI（填邮箱 → Start → 人工验证 → 邮箱验证 → 2FA → 输出）。"""
    from github_register_ui import run_ui as _run_ui
    _run_ui()


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GitHub 注册流程：代理校验 → 创建/打开浏览器 → 取件查验证邮件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py               # 完整流程（代理 → 创建浏览器 → 打开 → 轮询邮箱）
  python main.py --ui          # 启动图形界面
  python main.py -m            # 仅轮询邮箱取 GitHub 验证链接
  python main.py --profile my   # 使用档案名 my
  python main.py --no-keep      # 流程结束后关闭浏览器
        """.strip(),
    )
    parser.add_argument(
        "-u", "--ui",
        action="store_true",
        help="启动 GitHub 注册流程图形界面",
    )
    parser.add_argument(
        "-m", "--mail-only",
        action="store_true",
        help="仅轮询邮箱取 GitHub 验证链接",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE_NAME,
        metavar="NAME",
        help=f"浏览器档案名称（默认: {DEFAULT_PROFILE_NAME}）",
    )
    parser.add_argument(
        "--no-keep",
        action="store_true",
        dest="keep_browser_open",
        help="流程结束后关闭浏览器（默认保持打开）",
    )
    return parser.parse_args()


def main() -> int:
    """命令行入口，返回进程退出码。"""
    args = _parse_args()

    if args.ui:
        run_ui()
        return 0

    if args.mail_only:
        try:
            # 命令行模式下优先打印验证链接，其次打印 GitHub 验证码（launch code）
            link, _, diag = get_verification_link_from_inbox(
                keyword=VERIFICATION_KEYWORD,
                top=VERIFICATION_MAIL_TOP,
            )
            if link:
                print("验证链接:", link)
            else:
                code, _, diag_code = get_verification_code_from_inbox(
                    keyword=VERIFICATION_KEYWORD,
                    top=VERIFICATION_MAIL_TOP,
                )
                if code:
                    print("GitHub 验证码（launch code）:", code)
                else:
                    print(diag_code or diag or "未找到包含 github 的验证邮件或验证码。")
            return 0
        except Exception as e:
            print("Error:", e, file=sys.stderr)
            return 1

    success = run_github_signup_flow(
        profile_name=args.profile,
        keep_browser_open=args.keep_browser_open,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
