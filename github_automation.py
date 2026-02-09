"""
GitHub 注册浏览器自动化：通过 CDP 连接 Bitbrowser，仿真人操作、打字机输入、完成注册与 2FA 流程。
"""
from __future__ import annotations

import asyncio
import random
import re
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# 配置常量：延迟与超时（放慢并加大随机，降低「异常活动」判定）
# ---------------------------------------------------------------------------
TYPE_DELAY_MS = (140, 320)       # 打字机每字延迟（毫秒）
HUMAN_PAUSE_MS = (800, 2200)     # 步与步之间停顿
SCROLL_PAUSE_MS = (300, 900)     # 滚动后短暂停顿

# 页面导航不设时长，等待加载完成（不同代理 IP 延迟差异大）
NAV_NO_TIMEOUT = 0
# 先用 commit 避免重定向时 net::ERR_ABORTED，再单独等待 dom/load
NAV_WAIT_UNTIL = "commit"
LOAD_STATE_THEN = "domcontentloaded"
SELECTOR_TIMEOUT = 10000         # 选择器等待超时
SHORT_TIMEOUT = 3000            # 可选控件短超时

# URL
URL_GITHUB = "https://github.com"
URL_GITHUB_SIGNUP = "https://github.com/signup"
URL_GITHUB_SECURITY = "https://github.com/settings/security"
URL_GITHUB_2FA_SETUP = "https://github.com/settings/two_factor_authentication/setup"

# 选择器（集中维护，便于应对 GitHub 前端变更）
SEL_EMAIL = 'input[id="email"], input[name="user[email]"], input[type="email"]'
SEL_PASSWORD = 'input[id="password"], input[name="user[password]"], input[type="password"]'
SEL_USERNAME = (
    'input[id="login"], input[name="user[login]"], '
    'input[placeholder*="username"], input[placeholder*="用户名"]'
)
SEL_SIGNUP_LINK = 'a[href="/signup"], a[href*="signup"]:not([href*="login"])'
SEL_COUNTRY_BTN = (
    'button:has-text("Country"), button:has-text("Region"), '
    '[data-testid="country-select"], summary:has-text("Country"), '
    'summary:has-text("Region"), [aria-haspopup="listbox"]'
)
SEL_OPT_OUT = 'input[id="opt_in"][value="no"], input[value="no"][name*="opt"]'
SEL_CREATE_ACCOUNT = (
    'button[type="submit"]:has-text("Create account"), '
    'button:has-text("Create account"), button:has-text("创建")'
)
COUNTRY_LABELS = ["United States of America", "United States", "China", "China (中国)"]


def _rand_ms(bounds: tuple[int, int]) -> float:
    """在 bounds (min_ms, max_ms) 内随机毫秒数，返回秒数供 asyncio.sleep。"""
    return random.uniform(*bounds) / 1000.0


async def _human_delay(bounds_ms: tuple[int, int] = HUMAN_PAUSE_MS) -> None:
    """仿真人停顿（异步，不阻塞事件循环）。"""
    await asyncio.sleep(_rand_ms(bounds_ms))


async def _typewriter(
    page,
    selector: str,
    text: str,
    delay_bounds_ms: tuple[int, int] = TYPE_DELAY_MS,
) -> None:
    """打字机输入：带随机间隔与偶尔停顿，更像真人。"""
    el = await page.query_selector(selector)
    if not el:
        raise ValueError(f"Element not found: {selector}")
    await el.click()
    await asyncio.sleep(random.uniform(0.3, 0.8))
    for i, c in enumerate(text):
        await page.keyboard.type(c, delay=random.randint(*delay_bounds_ms))
        if (i + 1) % random.randint(4, 8) == 0:
            await asyncio.sleep(random.uniform(0.15, 0.5))
    await asyncio.sleep(random.uniform(0.2, 0.5))


async def _click_continue_button(page) -> bool:
    """点「Continue」按钮，跳过「Continue with Google/Apple」。"""
    buttons = await page.query_selector_all(
        'button[type="submit"], button:has-text("Continue"), button:has-text("继续")'
    )
    for btn in buttons:
        label = (await btn.inner_text() or "").strip()
        if any(x in label for x in ("Google", "Apple", "谷歌", "苹果")):
            continue
        if "Continue" in label or "继续" in label:
            await btn.click()
            return True
    return False


async def _connect_and_get_page(playwright, cdp_ws_url: str):
    """
    通过 CDP 连接浏览器，返回 (browser, page)。
    只使用第一个标签页，不关闭任何标签，避免误关窗口。
    调用方需在 async with async_playwright() 内使用，以保证 playwright 生命周期。
    """
    browser = await playwright.chromium.connect_over_cdp(cdp_ws_url)
    contexts = browser.contexts
    if not contexts:
        return browser, None
    pages = contexts[0].pages
    page = pages[0] if pages else await contexts[0].new_page()
    return browser, page


# ---------------------------------------------------------------------------
# 注册流程：分步实现，便于阅读与单步调试
# ---------------------------------------------------------------------------

async def _step_search_github_and_go(page, log: Callable[[str], None]) -> bool:
    """在当前标签地址栏输入 github 并回车，用浏览器默认搜索，再从结果里进 GitHub（同一标签）。"""
    log("在地址栏搜索 github...")
    await page.keyboard.press("Control+l")
    await asyncio.sleep(random.uniform(0.2, 0.5))
    for c in "github":
        await page.keyboard.type(c, delay=random.randint(*TYPE_DELAY_MS))
        if random.random() < 0.15:
            await asyncio.sleep(random.uniform(0.1, 0.25))
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await page.keyboard.press("Enter")
    await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
    await _human_delay((1000, 1800))

    await page.evaluate("window.scrollBy(0, 120)")
    await _human_delay((400, 900))

    log("从搜索结果进入 GitHub（当前标签）...")
    gh_links = await page.query_selector_all('a[href*="github.com"]')
    gh_href = None
    for node in gh_links:
        href = await node.get_attribute("href")
        if not href or "signup" in href or "login" in href:
            continue
        if "github.com" in href:
            if href.strip("/").endswith("github.com") or "/github.com/" in href:
                gh_href = href
                break
    if not gh_href and gh_links:
        gh_href = await gh_links[0].get_attribute("href")
    target = gh_href or URL_GITHUB
    await page.goto(target, wait_until=NAV_WAIT_UNTIL, timeout=NAV_NO_TIMEOUT)
    await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
    await _human_delay((800, 1500))

    if "github.com" not in page.url:
        log(f"未进入 GitHub（当前: {page.url}），请重试")
        return False
    return True


async def _step_go_to_signup(page, log: Callable[[str], None]) -> bool:
    """若未在注册页则点 Sign up 进入；已在则直接通过。"""
    if "github.com/signup" in page.url:
        await _human_delay((600, 1200))
        return True
    await page.evaluate("window.scrollBy(0, 200)")
    await _human_delay((600, 1400))
    await page.evaluate("window.scrollBy(0, -80)")
    await _human_delay((400, 900))

    log("进入注册页...")
    signup_link = await page.query_selector(SEL_SIGNUP_LINK)
    if signup_link:
        await signup_link.scroll_into_view_if_needed()
        await _human_delay((300, 700))
        await signup_link.click()
    else:
        await page.goto(URL_GITHUB_SIGNUP, wait_until=NAV_WAIT_UNTIL, timeout=NAV_NO_TIMEOUT)
    await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
    await _human_delay((1000, 2200))

    if "github.com/signup" not in page.url:
        log(f"未进入 GitHub 注册页（当前: {page.url})")
        return False
    return True


async def _step_fill_signup_form(
    page,
    email: str,
    password: str,
    username: str,
    log: Callable[[str], None],
) -> bool:
    """填写注册表单：邮箱 → 密码 → 用户名；可选国家、邮件偏好。"""
    log("填写邮箱...")
    await page.wait_for_selector(SEL_EMAIL, timeout=SELECTOR_TIMEOUT, state="visible")
    await _typewriter(page, SEL_EMAIL, email)
    await _human_delay((800, 2000))
    if await _click_continue_button(page):
        await asyncio.sleep(random.uniform(1.8, 3.2))

    log("填写密码（原密码+@Git2026）...")
    await page.wait_for_selector(SEL_PASSWORD, timeout=8000, state="visible")
    await _typewriter(page, SEL_PASSWORD, password)
    await _human_delay((800, 2000))
    if await _click_continue_button(page):
        await asyncio.sleep(random.uniform(1.8, 3.2))

    log("填写用户名...")
    await page.wait_for_selector(SEL_USERNAME, timeout=8000, state="visible")
    await _typewriter(page, SEL_USERNAME, username)
    await _human_delay((1000, 2500))

    await page.evaluate("window.scrollBy(0, 350)")
    await _human_delay((1200, 2800))

    # 国家/地区（可选，失败可手动选）
    try:
        country_btn = await page.wait_for_selector(SEL_COUNTRY_BTN, timeout=SHORT_TIMEOUT, state="visible")
        if country_btn:
            await country_btn.scroll_into_view_if_needed()
            await country_btn.click(timeout=8000)
            await asyncio.sleep(0.5)
        for label in COUNTRY_LABELS:
            opt = await page.query_selector(
                f'li:has-text("{label}"), [role="option"]:has-text("{label}"), a:has-text("{label}")'
            )
            if opt:
                await opt.scroll_into_view_if_needed()
                await opt.click(timeout=5000)
                await _human_delay((200, 500))
                break
    except Exception:
        pass

    try:
        no_sel = await page.wait_for_selector(SEL_OPT_OUT, timeout=2000, state="visible")
        if no_sel:
            await no_sel.scroll_into_view_if_needed()
            await no_sel.click(timeout=5000)
    except Exception:
        pass
    await _human_delay((500, 1200))
    return True


async def _step_submit_signup(page, log: Callable[[str], None]) -> bool:
    """提交前停顿 2–5 秒后点击创建账号。"""
    await _human_delay((2000, 5000))
    log("点击创建账号...")
    try:
        create_btn = await page.wait_for_selector(
            SEL_CREATE_ACCOUNT, timeout=15000, state="visible"
        )
        await create_btn.scroll_into_view_if_needed()
        await create_btn.click(timeout=15000)
    except Exception:
        await page.keyboard.press("Enter")
    await asyncio.sleep(2)
    log("已提交注册；若出现图片验证请在浏览器中人工完成，完成后在 UI 点击「下一步：通过邮箱获取验证」。")
    return True


async def run_signup_flow(
    cdp_ws_url: str,
    email: str,
    password: str,
    username: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    在已打开的浏览器中执行：地址栏搜 github → 从结果点进 GitHub → 进入注册页 → 打字机填写 → 提交。
    password 应为「原密码+@Git2026」的完整密码。
    log_callback(msg) 用于向 UI 输出日志；可为 None。
    """
    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser, page = await _connect_and_get_page(p, cdp_ws_url)
        except Exception as e:
            log(f"CDP 连接失败: {e}")
            return False
        if not page:
            log("未获取到浏览器 context")
            return False

        try:
            if not await _step_search_github_and_go(page, log):
                return False
            if not await _step_go_to_signup(page, log):
                return False
            await _step_fill_signup_form(page, email, password, username, log)
            await _step_submit_signup(page, log)
            return True
        except Exception as e:
            log(f"自动化异常: {e}")
            return False


# ---------------------------------------------------------------------------
# 2FA：从页面解析 TOTP secret
# ---------------------------------------------------------------------------

OTP_SECRET_PATTERNS = [
    (re.compile(r"secret=([A-Z2-7]+)", re.I), 1),
    (re.compile(r'data-secret="([^"]+)"'), 1),
    (re.compile(r"otpauth://[^?]+\?[^\s'\"]*secret=([A-Z2-7]+)"), 1),
]


def _extract_otp_secret_from_page(html_or_text: str) -> str:
    """从 GitHub 2FA 设置页或 otpauth URL 中解析 TOTP 密钥。"""
    for pattern, group in OTP_SECRET_PATTERNS:
        m = pattern.search(html_or_text)
        if m:
            return m.group(group).strip()
    return ""


async def run_enable_2fa_and_get_secret(
    cdp_ws_url: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    在已登录的浏览器中：打开 GitHub Settings → 2FA 设置页，
    从页面中解析 TOTP secret 并返回。若需输入当前密码或验证码，由人工在浏览器中完成。
    """
    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser, page = await _connect_and_get_page(p, cdp_ws_url)
        except Exception as e:
            log(f"CDP 连接失败: {e}")
            return ""
        if not page:
            return ""

        try:
            log("打开 GitHub 2FA 设置页...")
            await page.goto(URL_GITHUB_SECURITY, wait_until=NAV_WAIT_UNTIL, timeout=NAV_NO_TIMEOUT)
            await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
            await asyncio.sleep(1.5)

            enable_btn = await page.query_selector(
                'button:has-text("Enable two-factor"), a:has-text("Enable two-factor"), '
                'button:has-text("Two-factor")'
            )
            if enable_btn:
                await enable_btn.click()
                await asyncio.sleep(1)
            await page.goto(URL_GITHUB_2FA_SETUP, wait_until=NAV_WAIT_UNTIL, timeout=NAV_NO_TIMEOUT)
            await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
            await asyncio.sleep(1.5)

            content = await page.content()
            secret = _extract_otp_secret_from_page(content)
            if secret:
                log("已解析 2FA 密钥（请按页面提示完成验证以启用）")
                return secret
            text = await page.inner_text("body")
            return _extract_otp_secret_from_page(text) or ""
        except Exception as e:
            log(f"2FA 步骤异常: {e}")
            return ""
