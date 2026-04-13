"""
GitHub 注册浏览器自动化：通过 CDP 连接 Bitbrowser，仿真人操作、打字机输入、完成注册与 2FA 流程。
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# 配置常量：延迟与超时（放慢并加大随机，降低「异常活动」判定）
# ---------------------------------------------------------------------------
TYPE_DELAY_MS = (140, 320)       # 打字机每字延迟（毫秒）
HUMAN_PAUSE_MS = (800, 2200)     # 步与步之间停顿

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
    'button[data-optimizely-event="click.signup_continue.create"]:visible, '
    'button[type="submit"]:has-text("Create account"), '
    'button:has-text("Create account"), '
    'input[type="submit"][value*="Create"], '
    'button:has-text("创建账号"), button:has-text("创建")'
)
COUNTRY_LABELS = ["United States of America", "United States", "China", "China (中国)"]

# 表单校验错误检测
JS_DETECT_FORM_ERRORS = """() => {
    const text = document.body.innerText || '';
    const errors = [];
    if (/email.*already.*associated|邮箱.*已.*关联|already.*account/i.test(text))
        errors.push('email_taken');
    if (/username.*not.*available|用户名.*不可用|is not available/i.test(text))
        errors.push('username_taken');
    if (/password.*too.*short|密码.*太短|at least.*characters/i.test(text) &&
        /password/i.test(text) && document.querySelector('input[type="password"]:invalid'))
        errors.push('password_invalid');
    if (/fill out this field|请填写此字段/i.test(text))
        errors.push('field_required');
    // GitHub 服务端拒绝创建账号（非表单字段校验）
    if (/we couldn't create your account|we could not create your account/i.test(text) ||
        /unable to complete your signup at this time/i.test(text))
        errors.push('signup_unavailable');
    return errors;
}"""

# 结构化检测：优先从输入框错误/role=alert 中提取 email 相关错误文本
JS_DETECT_EMAIL_ERROR_STRUCTURED = """() => {
    const out = {found: false, text: ''};
    const email = document.querySelector('input[id="email"], input[name="user[email]"], input[type="email"]');
    if (email) {
        const ariaInvalid = (email.getAttribute('aria-invalid') || '').toLowerCase();
        if (ariaInvalid === 'true') out.found = true;

        const desc = (email.getAttribute('aria-describedby') || '').trim();
        if (desc) {
            for (const id of desc.split(/\\s+/)) {
                const node = document.getElementById(id);
                const t = ((node && (node.innerText || node.textContent)) || '').trim();
                if (t) {
                    out.found = true;
                    out.text += (out.text ? ' | ' : '') + t;
                }
            }
        }
    }

    const alerts = document.querySelectorAll('[role="alert"], .flash-error, .error, .error-message');
    for (const a of alerts) {
        const t = ((a.innerText || a.textContent) || '').trim();
        if (t && /email|邮箱/i.test(t)) {
            out.found = true;
            out.text += (out.text ? ' | ' : '') + t;
        }
    }
    return out;
}"""


class SignupFormError(Exception):
    """表单校验错误（邮箱已注册、用户名已占用等），应跳过当前账号。"""
    def __init__(self, errors: list[str], message: str = ""):
        self.errors = errors
        super().__init__(message or f"表单校验错误: {', '.join(errors)}")


EMAIL_TAKEN_PATTERNS = [
    re.compile(r"email.*already.*associated", re.I),
    re.compile(r"already.*account", re.I),
    re.compile(r"邮箱.*已.*关联", re.I),
    re.compile(r"邮箱.*已.*注册", re.I),
]


def _looks_like_email_taken(text: str) -> bool:
    if not text:
        return False
    for p in EMAIL_TAKEN_PATTERNS:
        if p.search(text):
            return True
    return False


def _should_trace_signup_url(url: str) -> bool:
    u = (url or "").lower()
    if "github.com" not in u:
        return False
    return any(x in u for x in ("/signup", "/join", "/sessions", "/account_verifications", "/verify"))


@dataclass
class _NetEvent:
    kind: str  # "response" | "requestfailed"
    url: str
    method: str = ""
    status: int = 0
    content_type: str = ""
    body_excerpt: str = ""
    error_text: str = ""


class SignupNetworkTrace:
    def __init__(self, max_events: int = 30) -> None:
        self._events: deque[_NetEvent] = deque(maxlen=max_events)

    def snapshot(self) -> list[_NetEvent]:
        return list(self._events)

    def note_request_failed(self, request, error_text: str = "") -> None:
        try:
            url = request.url
            if not _should_trace_signup_url(url):
                return
            self._events.append(
                _NetEvent(
                    kind="requestfailed",
                    url=url,
                    method=(request.method or ""),
                    error_text=error_text or "",
                )
            )
        except Exception:
            pass

    async def note_response(self, response) -> None:
        try:
            url = response.url
            if not _should_trace_signup_url(url):
                return
            req = response.request
            headers = response.headers or {}
            ct = (headers.get("content-type") or headers.get("Content-Type") or "")[:120]

            excerpt = ""
            if "json" in ct.lower() or "text" in ct.lower() or "javascript" in ct.lower() or ct == "":
                try:
                    txt = await response.text()
                    if txt:
                        txt = txt.replace("\r", " ").replace("\n", " ")
                        excerpt = txt[:1200]
                except Exception:
                    excerpt = ""

            self._events.append(
                _NetEvent(
                    kind="response",
                    url=url,
                    method=(req.method or "") if req else "",
                    status=int(response.status or 0),
                    content_type=ct,
                    body_excerpt=excerpt,
                )
            )
        except Exception:
            pass

    def detect_email_taken_from_network(self) -> Optional[_NetEvent]:
        for ev in reversed(self._events):
            if ev.kind != "response":
                continue
            if ev.status and ev.status >= 400 and _looks_like_email_taken(ev.body_excerpt):
                return ev
        for ev in reversed(self._events):
            if ev.kind == "response" and _looks_like_email_taken(ev.body_excerpt):
                return ev
        return None


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
    """
    点「Continue」按钮，跳过「Continue with Google/Apple」和「Create account」等非 Continue 按钮。
    GitHub 当前注册页为单页表单，可能没有分步 Continue 按钮；此函数在无匹配时安全返回 False。
    """
    buttons = await page.query_selector_all(
        'button[type="submit"], button:has-text("Continue"), button:has-text("继续")'
    )
    for btn in buttons:
        label = (await btn.inner_text() or "").strip()
        if any(x in label.lower() for x in ("google", "apple", "谷歌", "苹果")):
            continue
        if any(x in label.lower() for x in ("create", "创建")):
            continue
        if "Continue" in label or "继续" in label:
            await btn.click()
            return True
    return False


CDP_CONNECT_RETRIES = 3
CDP_CONNECT_BACKOFF = (3, 5, 10)


async def _connect_and_get_page(playwright, cdp_ws_url: str, close_extra_tabs: bool = False):
    """
    通过 CDP 连接浏览器，返回 (browser, page)。
    close_extra_tabs=True 时关闭多余标签页（只保留第一个），减少流量消耗。
    内置重试：网络不稳定时自动重连（最多 3 次）。
    """
    last_err = None
    for attempt in range(CDP_CONNECT_RETRIES):
        try:
            browser = await playwright.chromium.connect_over_cdp(cdp_ws_url)
            contexts = browser.contexts
            if not contexts:
                return browser, None
            pages = contexts[0].pages
            page = pages[0] if pages else await contexts[0].new_page()

            if close_extra_tabs and len(pages) > 1:
                for extra in pages[1:]:
                    try:
                        await extra.close()
                    except Exception:
                        pass

            return browser, page
        except Exception as e:
            last_err = e
            if attempt < CDP_CONNECT_RETRIES - 1:
                wait = CDP_CONNECT_BACKOFF[attempt]
                await asyncio.sleep(wait)

    raise RuntimeError(f"CDP 连接失败（重试 {CDP_CONNECT_RETRIES} 次）: {last_err}")


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
    """
    填写注册表单：邮箱 → 密码 → 用户名；可选国家、邮件偏好。
    兼容两种页面模式：
      - 单页表单（当前 GitHub 默认）：所有字段在同一页，最后统一提交
      - 分步表单：每个字段填完后点 Continue 进入下一步
    """
    log("填写邮箱...")
    await page.wait_for_selector(SEL_EMAIL, timeout=SELECTOR_TIMEOUT, state="visible")
    await _typewriter(page, SEL_EMAIL, email)
    await _human_delay((800, 2000))

    # 先点一下邮箱输入框之外的空白区域，触发前端校验（如果有的话）
    await page.keyboard.press("Tab")
    await _human_delay((500, 1200))

    # 分步模式下点 Continue（单页模式会安全返回 False）
    if await _click_continue_button(page):
        await asyncio.sleep(random.uniform(1.8, 3.2))

    log("填写密码（原密码+@Git2026）...")
    try:
        await page.wait_for_selector(SEL_PASSWORD, timeout=8000, state="visible")
    except Exception:
        log("密码框等待超时，尝试向下滚动...")
        await page.evaluate("window.scrollBy(0, 200)")
        await page.wait_for_selector(SEL_PASSWORD, timeout=8000, state="visible")
    await _typewriter(page, SEL_PASSWORD, password)
    await _human_delay((800, 2000))
    await page.keyboard.press("Tab")
    await _human_delay((500, 1200))

    if await _click_continue_button(page):
        await asyncio.sleep(random.uniform(1.8, 3.2))

    log("填写用户名...")
    try:
        await page.wait_for_selector(SEL_USERNAME, timeout=8000, state="visible")
    except Exception:
        log("用户名框等待超时，尝试向下滚动...")
        await page.evaluate("window.scrollBy(0, 200)")
        await page.wait_for_selector(SEL_USERNAME, timeout=8000, state="visible")
    await _typewriter(page, SEL_USERNAME, username)
    await _human_delay((1000, 2500))
    await page.keyboard.press("Tab")
    await _human_delay((600, 1500))

    await page.evaluate("window.scrollBy(0, 350)")
    await _human_delay((1200, 2800))

    # 国家/地区（可选，失败可手动选）
    try:
        country_btn = await page.wait_for_selector(SEL_COUNTRY_BTN, timeout=SHORT_TIMEOUT, state="visible")
        if country_btn:
            await country_btn.scroll_into_view_if_needed()
            await _human_delay((300, 700))
            await country_btn.click(timeout=8000)
            await asyncio.sleep(0.8)
        for label in COUNTRY_LABELS:
            opt = await page.query_selector(
                f'li:has-text("{label}"), [role="option"]:has-text("{label}"), '
                f'a:has-text("{label}"), button:has-text("{label}")'
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

    await page.evaluate("window.scrollBy(0, 200)")
    await _human_delay((500, 1200))
    return True


async def _step_submit_signup(
    page,
    log: Callable[[str], None],
    net_trace: Optional[SignupNetworkTrace] = None,
) -> bool:
    """提交前停顿 2–5 秒后点击创建账号，多种策略确保按钮被实际触发。"""
    await _human_delay((2000, 5000))
    log("点击创建账号...")

    clicked = False

    # 策略 1: 用选择器定位 "Create account" 按钮
    try:
        create_btn = await page.wait_for_selector(
            SEL_CREATE_ACCOUNT, timeout=15000, state="visible"
        )
        if create_btn:
            await create_btn.scroll_into_view_if_needed()
            await _human_delay((300, 800))

            is_disabled = await create_btn.is_disabled()
            if is_disabled:
                log("Create account 按钮暂时为 disabled，等待可用...")
                await page.wait_for_function(
                    """(sel) => {
                        const btn = document.querySelector(sel.split(',')[0].trim())
                            || [...document.querySelectorAll('button')]
                                .find(b => b.textContent.includes('Create account'));
                        return btn && !btn.disabled;
                    }""",
                    SEL_CREATE_ACCOUNT,
                    timeout=20000,
                )
                await asyncio.sleep(0.5)

            await create_btn.click(timeout=15000)
            clicked = True
            log("已通过选择器点击 Create account 按钮")
    except Exception as e:
        log(f"选择器点击失败: {e}，尝试备用方案...")

    # 策略 2: 用 JS 遍历所有按钮，找到含 "Create account" 文本的按钮并 click()
    if not clicked:
        try:
            result = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, input[type="submit"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').trim();
                    if (text.includes('Create account') || text.includes('创建')) {
                        btn.scrollIntoView({block: 'center'});
                        btn.click();
                        return text;
                    }
                }
                return null;
            }""")
            if result:
                clicked = True
                log(f"已通过 JS click 点击按钮: {result}")
        except Exception as e:
            log(f"JS click 失败: {e}")

    # 策略 3: 提交表单
    if not clicked:
        try:
            await page.evaluate("""() => {
                const form = document.querySelector('form');
                if (form) { form.submit(); return true; }
                return false;
            }""")
            clicked = True
            log("已通过 form.submit() 提交表单")
        except Exception:
            pass

    # 策略 4: 回车键
    if not clicked:
        log("所有点击方式均失败，尝试按 Enter 提交...")
        await page.keyboard.press("Enter")

    # 提交后等待页面响应，多轮检测表单校验错误
    # GitHub 的错误提示可能是异步渲染的，需要轮询几次
    for check_round in range(4):
        await asyncio.sleep(2)
        try:
            # 证据 1：网络响应确认（优先）
            if net_trace:
                ev = net_trace.detect_email_taken_from_network()
                if ev:
                    log(f"表单校验失败: 邮箱已被注册（网络响应确认，status={ev.status}）")
                    log(f"  ↳ {ev.method} {ev.url}")
                    if ev.content_type:
                        log(f"  ↳ content-type: {ev.content_type}")
                    if ev.body_excerpt:
                        log(f"  ↳ body-excerpt: {ev.body_excerpt[:260]}")
                    raise SignupFormError(["email_taken"], "邮箱已被注册")

            # 证据 2：结构化 DOM 提示（优先于全文本）
            structured = await page.evaluate(JS_DETECT_EMAIL_ERROR_STRUCTURED)
            if structured and structured.get("found"):
                t = (structured.get("text") or "").strip()
                if _looks_like_email_taken(t):
                    log("表单校验失败: 邮箱已被注册（DOM 结构化提示）")
                    if t:
                        log(f"  ↳ {t[:260]}")
                    raise SignupFormError(["email_taken"], "邮箱已被注册")

            form_errors = await page.evaluate(JS_DETECT_FORM_ERRORS)
            if form_errors:
                # ⚠️ 兜底检测（JS_DETECT_FORM_ERRORS）存在误判风险：
                # - email_taken 只有在“网络证据”或“结构化 DOM 提示”确认后才算真
                # - 否则降级移除 email_taken，避免因为全页 innerText 命中而跳过
                if "email_taken" in form_errors:
                    confirmed = False
                    if net_trace and net_trace.detect_email_taken_from_network():
                        confirmed = True
                    if not confirmed:
                        try:
                            structured2 = await page.evaluate(JS_DETECT_EMAIL_ERROR_STRUCTURED)
                            t2 = ((structured2 or {}).get("text") or "").strip()
                            if _looks_like_email_taken(t2):
                                confirmed = True
                        except Exception:
                            pass

                    if not confirmed:
                        log("检测到疑似 email_taken（全文本兜底命中），但未被网络/结构化 DOM 确认，已忽略该项以避免误判。")
                        form_errors = [e for e in form_errors if e != "email_taken"]

                error_msgs = {
                    "email_taken": "邮箱已被注册",
                    "username_taken": "用户名已被占用",
                    "password_invalid": "密码不符合要求",
                    "field_required": "有必填字段未填写",
                    "signup_unavailable": "GitHub 暂时无法完成注册",
                }
                if form_errors:
                    desc = "、".join(error_msgs.get(e, e) for e in form_errors)
                    log(f"表单校验失败: {desc}")
                    # 若有网络取证信息，失败时顺带打印最近请求摘要，便于定位“到底请求发没发/回了什么”
                    if net_trace:
                        try:
                            snap = net_trace.snapshot()[-10:]
                            if snap:
                                log("最近网络事件摘要(最多10条):")
                                for ev in snap:
                                    if ev.kind == "response":
                                        log(f"  ↳ resp {ev.status} {ev.method} {ev.url}")
                                    else:
                                        log(f"  ↳ req_failed {ev.method} {ev.url} {ev.error_text}")
                        except Exception:
                            pass
                    raise SignupFormError(form_errors, desc)
        except SignupFormError:
            raise
        except Exception:
            pass

        url_after = page.url.lower()
        if "signup" not in url_after or "captcha" in url_after or "verify" in url_after:
            log("已提交注册，页面已进入验证阶段。")
            return True

        # 检查验证码 iframe 是否真的可见触发了（而非仅预埋）
        try:
            iframe_info = await page.evaluate(JS_DETECT_CAPTCHA_IFRAME)
            if iframe_info and iframe_info.get("found") and iframe_info.get("visible"):
                log("验证码 iframe 已触发，表单提交成功。")
                return True
        except Exception:
            pass

    log("已尝试提交，但页面可能仍在注册页。请检查浏览器中是否有表单校验错误（如用户名重复、密码不符要求等）。")
    return True


async def run_signup_flow(
    cdp_ws_url: str,
    email: str,
    password: str,
    username: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    在已打开的浏览器中执行注册流程：
    直接导航到 signup 页 → 打字机填写 → 提交。
    跳过搜索引擎中转，减少不必要的页面加载和流量消耗。
    """
    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser, page = await _connect_and_get_page(p, cdp_ws_url, close_extra_tabs=True)
        except Exception as e:
            log(f"CDP 连接失败: {e}")
            return False
        if not page:
            log("未获取到浏览器 context")
            return False

        try:
            # 导航到注册页（带重试，防止网络抖动导致 TLS 断开）
            nav_ok = False
            for nav_attempt in range(3):
                try:
                    log("直接导航到 GitHub 注册页...")
                    await page.goto(URL_GITHUB_SIGNUP, wait_until=NAV_WAIT_UNTIL, timeout=NAV_NO_TIMEOUT)
                    await page.wait_for_load_state(LOAD_STATE_THEN, timeout=NAV_NO_TIMEOUT)
                    nav_ok = True
                    break
                except Exception as e:
                    err_msg = str(e).lower()
                    if "disconnect" in err_msg or "tls" in err_msg or "socket" in err_msg or "net::" in err_msg:
                        wait = [3, 6, 10][nav_attempt]
                        log(f"网络连接中断，{wait}s 后重试导航 ({nav_attempt + 2}/3)...")
                        await asyncio.sleep(wait)
                    else:
                        raise

            if not nav_ok:
                log("多次导航均失败，流程中止")
                return False

            await _human_delay((1500, 3000))

            if "github.com/signup" not in page.url:
                log(f"未进入 GitHub 注册页（当前: {page.url}），尝试备用方式...")
                if not await _step_go_to_signup(page, log):
                    return False

            await _step_fill_signup_form(page, email, password, username, log)

            net_trace = SignupNetworkTrace(max_events=30)

            def _on_response(resp) -> None:
                try:
                    asyncio.create_task(net_trace.note_response(resp))
                except Exception:
                    pass

            def _on_request_failed(req) -> None:
                try:
                    failure = None
                    try:
                        failure = req.failure
                    except Exception:
                        failure = None
                    err_text = ""
                    if failure:
                        err_text = (failure.get("errorText") or "") if isinstance(failure, dict) else ""
                    net_trace.note_request_failed(req, error_text=err_text)
                except Exception:
                    pass

            page.on("response", _on_response)
            page.on("requestfailed", _on_request_failed)

            await _step_submit_signup(page, log, net_trace=net_trace)
            await _raise_if_signup_unavailable(page, log)
            return True
        except SignupFormError:
            raise
        except Exception as e:
            log(f"自动化异常: {e}")
            return False


# ---------------------------------------------------------------------------
# 验证码自动填入
# ---------------------------------------------------------------------------

SEL_CODE_INPUT = (
    'input[id="code"], input[name="code"], input[placeholder*="code"], '
    'input[placeholder*="Enter code"], input[placeholder*="验证码"], '
    'input[type="text"][autocomplete="one-time-code"]'
)
SEL_VERIFY_BUTTON = (
    'button[type="submit"]:has-text("Verify"), button:has-text("Verify"), '
    'button:has-text("验证"), button[type="submit"]:has-text("Enter code")'
)

CAPTCHA_WAIT_INITIAL = 5

# 是否允许在浏览器中手动完成人机验证（默认关闭；关闭时仅短时轮询页面是否自动进入下一步）
CAPTCHA_MANUAL_WAIT = os.environ.get("CAPTCHA_MANUAL_WAIT", "").lower() in (
    "1",
    "true",
    "yes",
)
CAPTCHA_WAIT_APPEAR_MAX = 45
CAPTCHA_APPEAR_CHECK_INTERVAL = 2

# 验证码资源被 CDN/代理拦截（HTTP 401）时：累计次数达到阈值立即结束人机验证，主流程会失败并进入下一账号。
# 默认 1 = 首次 401 即放弃本账号，避免长时间空等；设为 0 可关闭此行为（仅打日志不提前结束）。
def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name, "") or "").strip())
    except ValueError:
        return default


CAPTCHA_401_ABORT_AFTER = _env_int("CAPTCHA_401_ABORT_AFTER", 1)
# 检测到 401 后尽快结束等待：sleep 拆成该粒度以便轮询 abort 标志（秒）
CAPTCHA_401_SLEEP_CHUNK = 0.15

# 已为哪些 Playwright Page 挂上验证码 HTTP 诊断（避免重复注册 listener）
_CAPTCHA_HTTP_DIAG_PAGE_IDS: set[int] = set()


def _attach_captcha_resource_http_diag(
    page,
    log: Callable[[str], None],
    state: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    监听 Arkose/OctoCaptcha 相关响应：若出现 HTTP 401，图片/脚本往往无法加载。
    将累计次数写入 state['captcha_401_total']，供达到阈值时提前结束等待。
    """
    if state is None:
        state = {
            "captcha_401_total": 0,
            "captcha_401_logged": set(),
            "captcha_401_abort_requested": False,
        }
    else:
        state.setdefault("captcha_401_total", 0)
        state.setdefault("captcha_401_logged", set())
        state.setdefault("captcha_401_abort_requested", False)

    try:
        pid = id(page)
        if pid in _CAPTCHA_HTTP_DIAG_PAGE_IDS:
            return state
        _CAPTCHA_HTTP_DIAG_PAGE_IDS.add(pid)
    except Exception:
        return state

    logged: set[str] = state.setdefault("captcha_401_logged", set())  # type: ignore[assignment]

    def on_response(response) -> None:
        try:
            if response.status != 401:
                return
            u = response.url
            ul = u.lower()
            if not any(
                k in ul
                for k in (
                    "arkoselabs.com",
                    "octocaptcha.com",
                    "funcaptcha",
                    "fastly",
                    "akamai",
                )
            ):
                return
            state["captcha_401_total"] = int(state.get("captcha_401_total", 0)) + 1
            key = u[:280]
            if key not in logged:
                logged.add(key)
                log(
                    "验证码链路 HTTP 401（图片/资源未授权，常见：代理 IP、会话 Cookie 不一致、网络拦截）: "
                    f"{key}"
                )
            if CAPTCHA_401_ABORT_AFTER > 0:
                if int(state["captcha_401_total"]) >= CAPTCHA_401_ABORT_AFTER:
                    state["captcha_401_abort_requested"] = True
        except Exception:
            pass

    page.on("response", on_response)
    return state


def _check_captcha_401_abort(http_state: dict[str, Any], log: Callable[[str], None]) -> bool:
    """
    若已达到 401 中止策略，打一次摘要日志并返回 True（调用方应立即 return False 结束人机验证）。
    """
    if CAPTCHA_401_ABORT_AFTER <= 0:
        return False
    if not http_state.get("captcha_401_abort_requested"):
        return False
    if not http_state.get("_captcha_401_abort_summary_logged"):
        http_state["_captcha_401_abort_summary_logged"] = True
        total = int(http_state.get("captcha_401_total", 0))
        log(
            f"验证码链路已被拦截（HTTP 401 累计 {total} 次，阈值={CAPTCHA_401_ABORT_AFTER}），"
            "结束本账号人机验证，请换下一个账号或代理"
        )
    return True


async def _captcha_interruptible_sleep(
    http_state: Optional[dict[str, Any]],
    seconds: float,
) -> None:
    """在验证码等待阶段 sleep；若启用 401 中止策略，则短切片轮询以便尽快结束等待。"""
    if seconds <= 0:
        return
    if http_state is None or CAPTCHA_401_ABORT_AFTER <= 0:
        await asyncio.sleep(seconds)
        return
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if http_state.get("captcha_401_abort_requested"):
            return
        chunk = min(CAPTCHA_401_SLEEP_CHUNK, end - time.monotonic())
        if chunk > 0:
            await asyncio.sleep(chunk)


# 检测验证码 iframe 是否**已触发且可见**（区分预埋的隐藏 iframe 和真正弹出的验证码）
JS_DETECT_CAPTCHA_IFRAME = """() => {
    const iframes = document.querySelectorAll('iframe');
    for (const f of iframes) {
        const src = (f.src || '').toLowerCase();
        if (src.includes('octocaptcha') || src.includes('arkoselabs') ||
            src.includes('funcaptcha') || src.includes('arkose')) {
            // 必须有实际 src（不是空的预埋 iframe）且可见
            const rect = f.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0;
            const hasRealSrc = f.src && f.src.length > 20 && !f.src.endsWith('about:blank');
            if (visible && hasRealSrc) {
                return {found: true, src: src, visible: true};
            }
            // iframe 存在但不可见/无 src → 可能是预埋的，不算触发
            if (hasRealSrc) {
                return {found: true, src: src, visible: visible, preloaded: !visible};
            }
        }
    }
    // 检查容器元素是否可见（不仅仅是存在）
    const containers = document.querySelectorAll(
        '#captcha-container, [data-captcha], .captcha-wrapper, #octocaptcha, #arkose'
    );
    for (const c of containers) {
        const rect = c.getBoundingClientRect();
        const style = window.getComputedStyle(c);
        if (rect.width > 0 && rect.height > 0 &&
            style.display !== 'none' && style.visibility !== 'hidden') {
            // 容器可见且有内容（非空容器）
            if (c.innerHTML.trim().length > 50) {
                return {found: true, src: 'container-visible', visible: true};
            }
        }
    }
    return {found: false, src: null, visible: false};
}"""

# 检测表单是否还存在校验错误（仍在填写阶段，不应进入验证码流程）
JS_DETECT_FORM_VALIDATION_ERRORS = """() => {
    const text = (document.body.innerText || '').toLowerCase();
    // 优先结构化错误提示（更稳），找不到再回退全文本
    let emailText = '';
    try {
        const email = document.querySelector('input[id="email"], input[name="user[email]"], input[type="email"]');
        if (email) {
            const desc = (email.getAttribute('aria-describedby') || '').trim();
            if (desc) {
                for (const id of desc.split(/\\s+/)) {
                    const node = document.getElementById(id);
                    const t = ((node && (node.innerText || node.textContent)) || '').trim();
                    if (t) emailText += (emailText ? ' | ' : '') + t;
                }
            }
        }
        const alerts = document.querySelectorAll('[role="alert"], .flash-error, .error, .error-message');
        for (const a of alerts) {
            const t = ((a.innerText || a.textContent) || '').trim();
            if (t && /email|邮箱/i.test(t)) emailText += (emailText ? ' | ' : '') + t;
        }
    } catch (e) {}

    const hasEmailError = /email.*already.*associated|邮箱.*已.*关联/.test(emailText.toLowerCase()) ||
                          /email.*already.*associated|邮箱.*已.*关联/.test(text);
    const hasUsernameError = /username.*not.*available|用户名.*不可用/.test(text);
    const hasPasswordError = document.querySelector('input[type="password"]:invalid') !== null;
    const hasFieldError = document.querySelector('input:invalid, [aria-invalid="true"]') !== null;
    const hasCreateBtn = !!([...document.querySelectorAll('button')]
        .find(b => /create account|创建/i.test(b.textContent)));
    return {
        hasErrors: hasEmailError || hasUsernameError,
        hasCreateBtn: hasCreateBtn,
        emailTaken: hasEmailError,
        usernameTaken: hasUsernameError,
        passwordInvalid: hasPasswordError,
        fieldInvalid: hasFieldError
    };
}"""

# 页面已离开注册页/验证码页的标志（用 URL 精确匹配，避免误判）
CAPTCHA_PASSED_URL_PATTERNS = [
    "/sessions/verified-device",
    "/account_verifications",
    "/dashboard",
    "/settings",
    "/repositories",
]

# GitHub 注册页 URL 特征（仍在注册流程中）
SIGNUP_URL_PATTERNS = ["github.com/signup", "github.com/join"]

# 页面错误/空白的指示词
PAGE_ERROR_INDICATORS = [
    "something went wrong", "reload", "try again", "error occurred",
    "page not found", "couldn't load", "failed to load",
    "我们无法创建", "出错了", "重新加载", "重试",
]

# 检测页面是否空白或异常的 JS
JS_DETECT_PAGE_HEALTH = """() => {
    const body = document.body;
    if (!body) return {healthy: false, reason: 'no-body'};
    const text = (body.innerText || '').trim();
    const html = (body.innerHTML || '').trim();
    if (html.length < 50) return {healthy: false, reason: 'empty-html', len: html.length};
    if (text.length < 10 && !document.querySelector('iframe'))
        return {healthy: false, reason: 'empty-text', len: text.length};
    return {healthy: true, textLen: text.length, htmlLen: html.length};
}"""


async def _detect_captcha_state(page) -> str:
    """
    检测页面验证码状态，返回:
      "captcha"      — 验证码已触发且可见
      "passed"       — 已跳过验证码（URL 明确在后续页面）
      "form_error"   — 表单有校验错误（邮箱已注册/用户名占用），不应等验证码
      "signup_page"  — 仍在注册页但验证码未触发（可能还在加载）
      "error"        — 页面空白/崩溃/加载失败
      "unknown"      — 无法判断
    """
    try:
        url = page.url.lower()

        # 1. 页面是 about:blank / 崩溃页 → 错误
        if url == "about:blank" or url == "" or url.startswith("chrome-error"):
            return "error"

        # 2. 检查页面是否空白/异常
        try:
            health = await page.evaluate(JS_DETECT_PAGE_HEALTH)
            if health and not health.get("healthy"):
                return "error"
        except Exception:
            pass

        # 3. 检查页面是否包含加载失败的错误提示
        try:
            if any(p in url for p in SIGNUP_URL_PATTERNS):
                visible_text = (await page.inner_text("body")).lower()
                if any(ind in visible_text for ind in PAGE_ERROR_INDICATORS):
                    return "error"
        except Exception:
            pass

        # 4. URL 已明确离开注册流程 → passed
        if not any(p in url for p in SIGNUP_URL_PATTERNS):
            if any(p in url for p in CAPTCHA_PASSED_URL_PATTERNS):
                return "passed"

        # 5. 还在注册页上 → 先检查表单是否有校验错误（比验证码检测优先级高）
        if any(p in url for p in SIGNUP_URL_PATTERNS):
            try:
                form_status = await page.evaluate(JS_DETECT_FORM_VALIDATION_ERRORS)
                if form_status and form_status.get("hasErrors") and form_status.get("hasCreateBtn"):
                    return "form_error"
            except Exception:
                pass

        # 6. 检查验证码 iframe 是否已触发且**可见**
        iframe_info = await page.evaluate(JS_DETECT_CAPTCHA_IFRAME)
        if iframe_info and iframe_info.get("found") and iframe_info.get("visible"):
            return "captcha"

        # 7. iframe 存在但不可见（预加载状态），或页面文本含验证码关键词
        # 在注册页上时只算 signup_page（可能还没真正触发验证码）
        if any(p in url for p in SIGNUP_URL_PATTERNS):
            return "signup_page"

    except Exception:
        return "error"
    return "unknown"


async def _page_signup_unavailable(page) -> bool:
    """页面是否出现 GitHub「无法创建账号」服务端拒绝提示。"""
    try:
        text = (await page.inner_text("body")).lower()
    except Exception:
        return False
    if "couldn't create your account" in text or "could not create your account" in text:
        return True
    if "unable to complete your signup at this time" in text:
        return True
    return False


async def _raise_if_signup_unavailable(page, log: Callable[[str], None]) -> None:
    if await _page_signup_unavailable(page):
        log("GitHub 提示无法创建账号（Unable to complete signup），本账号注册终止")
        raise SignupFormError(["signup_unavailable"], "GitHub 暂时无法完成注册")


MAX_ERROR_RECOVERIES = 2


async def _recover_from_error(page, log: Callable[[str], None]) -> str:
    """
    页面空白/错误后仅尝试刷新当前页，不跳转到注册首页。

    人机验证/提交后的会话挂在当前 URL 上，goto /signup 会丢掉进度且易被误判为
    「验证结束」；对注册流程没有实质帮助。
    """
    log("页面异常，尝试刷新当前页（不跳转注册首页，以免中断验证会话）...")
    try:
        await page.reload(wait_until=NAV_WAIT_UNTIL, timeout=30000)
        await page.wait_for_load_state(LOAD_STATE_THEN, timeout=30000)
        await asyncio.sleep(3)
        state = await _detect_captcha_state(page)
        if state != "error":
            log(f"刷新后页面恢复，状态: {state}")
        else:
            log("刷新后页面仍异常")
        return state
    except Exception as e:
        log(f"刷新失败: {e}")
        return "error"


async def _captcha_iframe_visible_now(page) -> bool:
    """当前是否仍存在可见的 OctoCaptcha/Arkose iframe（说明挑战未结束或仍占屏）。"""
    try:
        info = await page.evaluate(JS_DETECT_CAPTCHA_IFRAME)
        return bool(info and info.get("found") and info.get("visible"))
    except Exception:
        return False


async def _click_visible_create_account_cta(page, log: Callable[[str], None]) -> bool:
    """点击可见且可用的 Create account / 创建账号 主按钮。"""
    selectors = (
        'button:has-text("Create account")',
        'a:has-text("Create account")',
        'button:has-text("创建账号")',
        'a:has-text("创建账号")',
        'button:has-text("创建帐户")',
        'a:has-text("创建帐户")',
    )
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() == 0:
                continue
            if not await loc.is_visible():
                continue
            if await loc.is_disabled():
                continue
            await loc.scroll_into_view_if_needed()
            await asyncio.sleep(0.35)
            await loc.click(timeout=15000)
            try:
                await page.wait_for_load_state(LOAD_STATE_THEN, timeout=45000)
            except Exception:
                pass
            await asyncio.sleep(2)
            return True
        except Exception:
            continue
    return False


async def try_finalize_verify_create_account(
    page,
    log: Callable[[str], None],
    *,
    seen_captcha_iframe: bool = False,
) -> bool:
    """
    人机验证通过后 GitHub 常出现「Verify your account」+ Create account，必须点击才能进入邮箱验证等后续页。

    - 严格模式：页面文案同时命中「验证账户」类标题 + 创建账号提示后再点，避免误点注册表单首屏的 Create account。
    - 若曾出现过验证码 iframe、且当前 iframe 已不可见：允许宽松点击（应对文案略有差异的改版）。
    """
    try:
        txt = (await page.inner_text("body")).lower()
    except Exception:
        return False

    verify_markers = (
        "verify your account",
        "验证你的帐户",
        "验证你的账户",
        "verify your email",
        "验证你的电子邮件",
        "account verification",
    )
    on_verify_copy = any(m in txt for m in verify_markers)

    create_markers = (
        "create account",
        "创建账号",
        "创建帐户",
    )
    has_create_copy = any(m in txt for m in create_markers)

    # 严格：有验证页语义 + 有创建账号文案
    if on_verify_copy and has_create_copy:
        if await _click_visible_create_account_cta(page, log):
            log("验证已通过，已自动点击 Create account 继续")
            return True
        return False

    # 宽松：仅当页面已有「验证账户」类文案时再点。注册首屏也有 Create account，
    # 绝不能仅凭 has_create_copy 点击，否则 goto 回 /signup 后会误触表单主按钮。
    if seen_captcha_iframe and not await _captcha_iframe_visible_now(page):
        if on_verify_copy:
            if await _click_visible_create_account_cta(page, log):
                log("人机验证已结束，已自动点击 Create account 继续")
                return True

    return False


async def _poll_silent_verify_then_continue(
    page,
    log: Callable[[str], None],
    max_sec: float = 36.0,
    interval: float = 2.0,
    http_state: Optional[dict[str, Any]] = None,
    seen_captcha_iframe: bool = False,
) -> bool:
    """短轮询：检测验证完成并尽量点击「创建账号」；URL 已 passed 时也会先 try_finalize。"""
    seen = bool(seen_captcha_iframe)
    elapsed = 0.0
    while elapsed < max_sec:
        if http_state is not None and _check_captcha_401_abort(http_state, log):
            return False
        if await _captcha_iframe_visible_now(page):
            seen = True
        if await try_finalize_verify_create_account(
            page, log, seen_captcha_iframe=seen
        ):
            return True
        st = await _detect_captcha_state(page)
        if st == "passed":
            if await try_finalize_verify_create_account(
                page, log, seen_captcha_iframe=seen
            ):
                return True
            log("人机验证已完成（页面已进入后续步骤）")
            return True
        await _captcha_interruptible_sleep(http_state, interval)
        elapsed += interval
    return False


async def wait_for_captcha_done(
    cdp_ws_url: str,
    poll_interval: float = 3.0,
    max_wait: float = 120.0,
    log_callback: Optional[Callable[[str], None]] = None,
    manual_fallback: Optional[bool] = None,
) -> bool:
    """
    处理人机验证（Arkose/octocaptcha）：
    1. 等待验证码加载（检测到 error 时自动恢复）
    2. 设置 CAPTCHA_MANUAL_WAIT=1 或传入 manual_fallback=True 时提示手动完成验证；
       无论是否开启，均以页面状态（验证码 iframe、验证页文案、「创建账号」、URL）轮询推进，
       max_wait 仅作安全超时，不以「等满时长」作为成功条件。
    页面异常时仅尝试刷新当前页，不会重新打开注册首页（避免丢失验证会话与误判）。

    验证码资源被代理/CDN 拦截（HTTP 401）时：CAPTCHA_401_ABORT_AFTER（默认 1）表示累计 401
    达到该次数即结束人机验证；响应回调会立置中止标志，等待循环用短切片 sleep，约 0.15s 内退出，不再长时间空等。
    设为 0 则只打 401 日志，不提前结束。
    """
    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    from playwright.async_api import async_playwright

    allow_manual = (
        CAPTCHA_MANUAL_WAIT if manual_fallback is None else manual_fallback
    )

    async with async_playwright() as p:
        try:
            browser, page = await _connect_and_get_page(p, cdp_ws_url)
        except Exception:
            return False
        if not page:
            return False

        http_state: dict[str, Any] = {}
        _attach_captcha_resource_http_diag(page, log, http_state)

        error_recovery_count = 0
        seen_captcha_iframe = False

        # ---- 阶段 1：等待验证码加载 ----
        log("等待人机验证加载...")
        await _captcha_interruptible_sleep(http_state, float(CAPTCHA_WAIT_INITIAL))
        if _check_captcha_401_abort(http_state, log):
            return False

        waited = 0.0
        state = "unknown"
        while waited < CAPTCHA_WAIT_APPEAR_MAX:
            await _raise_if_signup_unavailable(page, log)
            if _check_captcha_401_abort(http_state, log):
                return False

            if await _captcha_iframe_visible_now(page):
                seen_captcha_iframe = True

            state = await _detect_captcha_state(page)

            if state == "captcha":
                log("检测到人机验证（验证码已触发且可见）")
                seen_captcha_iframe = True
                break

            if state == "passed":
                if await try_finalize_verify_create_account(
                    page, log, seen_captcha_iframe=seen_captcha_iframe
                ):
                    return True
                log("页面已跳过人机验证阶段（URL），继续流程")
                return True

            if state == "form_error":
                log("检测到表单校验错误（邮箱已注册/用户名占用），表单未提交成功，验证码不会出现")
                log("此账号将被标记为失败并跳过")
                return False

            if state == "error":
                if error_recovery_count < MAX_ERROR_RECOVERIES:
                    error_recovery_count += 1
                    log(f"页面异常（空白/错误），尝试恢复... (第 {error_recovery_count} 次)")
                    state = await _recover_from_error(page, log)
                    if state == "captcha":
                        log("恢复后检测到验证码")
                        seen_captcha_iframe = True
                        break
                    if state == "passed":
                        if await try_finalize_verify_create_account(
                            page, log, seen_captcha_iframe=seen_captcha_iframe
                        ):
                            return True
                        log("恢复后已跳过验证码阶段")
                        return True
                    if state == "form_error":
                        log("恢复后发现表单校验错误，跳过此账号")
                        return False
                    if state == "error":
                        log("恢复失败，页面仍然异常")
                    waited = 0.0
                    continue
                else:
                    log(f"已达到最大恢复次数 ({MAX_ERROR_RECOVERIES})，无法恢复")
                    break

            if state == "signup_page":
                if waited > 0 and int(waited) % 10 == 0:
                    log(f"仍在注册页但验证码未触发，继续等待... ({int(waited)}s)")
            else:
                log(f"页面状态: {state}，继续等待... ({int(waited)}s)")

            waited += CAPTCHA_APPEAR_CHECK_INTERVAL
            if waited < CAPTCHA_WAIT_APPEAR_MAX:
                await _captcha_interruptible_sleep(
                    http_state, float(CAPTCHA_APPEAR_CHECK_INTERVAL)
                )

        if _check_captcha_401_abort(http_state, log):
            return False

        if state not in ("captcha", "passed"):
            log(f"等待 {CAPTCHA_WAIT_APPEAR_MAX}s 后验证码状态: {state}")
            if state == "signup_page":
                log("仍在注册页但验证码未触发。可能原因：")
                log("  1. 表单提交未成功（浏览器中可能有校验错误）")
                log("  2. 验证码 iframe 加载缓慢（检查代理能否访问 octocaptcha.com）")
            if state == "error":
                log("页面持续异常，请检查网络/代理状态")
                return False
            if state == "form_error":
                log("表单校验错误持续存在，跳过此账号")
                return False
            log("假定验证码存在，继续处理流程...")

        if await _captcha_iframe_visible_now(page):
            seen_captcha_iframe = True

        await _raise_if_signup_unavailable(page, log)

        if await try_finalize_verify_create_account(
            page, log, seen_captcha_iframe=seen_captcha_iframe
        ):
            return True

        if _check_captcha_401_abort(http_state, log):
            return False

        # ---- 阶段 2：以页面检测为主（完成验证 / 出现并点击「创建账号」/ URL 进入下一步），max_wait 仅作安全超时
        deadline = time.monotonic() + float(max_wait)
        if not allow_manual:
            log(
                "人机验证：未开启 CAPTCHA_MANUAL_WAIT，仍将轮询检测完成与「创建账号」按钮；"
                "若需自己在浏览器里点，请在 .env 设置 CAPTCHA_MANUAL_WAIT=1"
            )
        else:
            log(
                "请在浏览器中完成人机验证；完成后将检测页面并尽量自动点击「创建账号」以进入邮箱验证等后续步骤…"
            )

        next_progress_log = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if _check_captcha_401_abort(http_state, log):
                return False
            try:
                await _raise_if_signup_unavailable(page, log)
            except SignupFormError:
                return False

            if await _captcha_iframe_visible_now(page):
                seen_captcha_iframe = True

            if await try_finalize_verify_create_account(
                page, log, seen_captcha_iframe=seen_captcha_iframe
            ):
                return True

            st = await _detect_captcha_state(page)
            if st == "passed":
                if await try_finalize_verify_create_account(
                    page, log, seen_captcha_iframe=seen_captcha_iframe
                ):
                    return True
                log("已进入注册后续页面（URL）")
                return True
            if st == "form_error":
                log("检测到表单校验错误，跳过此账号")
                return False
            if st == "error":
                if error_recovery_count < MAX_ERROR_RECOVERIES:
                    error_recovery_count += 1
                    log(f"等待中页面异常，尝试恢复... (第 {error_recovery_count} 次)")
                    st = await _recover_from_error(page, log)
                    if st == "passed":
                        if await try_finalize_verify_create_account(
                            page, log, seen_captcha_iframe=seen_captcha_iframe
                        ):
                            return True
                        log("恢复后已进入后续步骤")
                        return True
                    if st == "form_error":
                        log("恢复后发现表单校验错误")
                        return False
                    if st == "captcha":
                        seen_captcha_iframe = True
                    continue
                log("页面持续异常，无法恢复")
                return False

            await _captcha_interruptible_sleep(http_state, float(poll_interval))
            now = time.monotonic()
            if now >= next_progress_log:
                remaining = int(deadline - now)
                log(f"仍待人机验证或「创建账号」…（剩余约 {max(0, remaining)}s 超时）")
                next_progress_log = now + 15.0

        log(
            "人机验证阶段超时：在限定时间内未检测到验证完成，或未能点击「创建账号」进入下一步"
        )
        return False


async def fill_verification_code(
    cdp_ws_url: str,
    code: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """在 GitHub 验证码输入页面自动填入验证码并提交。"""
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
            return False

        try:
            code_input = await page.query_selector(SEL_CODE_INPUT)
            if not code_input:
                log("未找到验证码输入框，尝试直接在当前焦点位置输入")
                await page.keyboard.type(code, delay=random.randint(80, 200))
                await _human_delay((500, 1200))
                await page.keyboard.press("Enter")
                return True

            await code_input.click()
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await page.keyboard.type(code, delay=random.randint(80, 200))
            await _human_delay((800, 1500))

            verify_btn = await page.query_selector(SEL_VERIFY_BUTTON)
            if verify_btn:
                await verify_btn.click()
            else:
                await page.keyboard.press("Enter")
            await asyncio.sleep(2)
            log("验证码已自动填入并提交")
            return True
        except Exception as e:
            log(f"自动填入验证码异常: {e}")
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
                await asyncio.sleep(1.5)
            else:
                # 新 UI 下按钮文案可能变化，或用户已在 2FA 页面上；
                # 此时不再强行跳 URL，由用户在浏览器中自行导航到 2FA 设置页。
                log("未找到 \"Enable two-factor\" 按钮，请在浏览器中手动进入 2FA 设置页后再次点击 UI 中的「开启 2FA 并获取密钥」。")

            # 不再强制跳转 /setup 或 /two_factor_authentication，直接在当前页面解析，
            # 以避免 GitHub 将 /setup/intro 等路径返回 404。
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
