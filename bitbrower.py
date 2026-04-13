"""
BitBrowser 本地 API：创建档案、打开/关闭窗口。

针对「GitHub 注册 + OctoCaptcha / Arkose」的约定（本文件即默认最优组合）：

- **指纹与出口 IP 一致**：isIpCreateTimeZone / isIpCreatePosition / isIpCreateLanguage + ip-api，
  避免时区、语言、地理位置与代理 IP 不符。
- **验证码资源**：abortImage / abortMedia 关闭、disableGpu 关闭，保证拼图/脚本正常拉取；
  doNotTrack=「1」关闭 DNT，减少 Arkose 侧异常。
- **WebRTC**：「0」走代理出口，降低真实 IP 泄露。
- **一账号一档案**：启动前不清 Cookie/缓存/历史，避免人机验证会话断裂。
- **窗口启动参数**：压制首启弹窗、禁用扩展；不启用过激进的网络/站点隔离类开关，以免干扰 iframe 与 CDN。
- **扩展**：默认 loadExtensions=false，减少 chrome-extension 注入痕迹。

代理仍由 proxy_config / .env 提供；官方连通性说明：
https://docs.github.com/zh/get-started/using-github/troubleshooting-connectivity-problems
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests

from proxy_config import to_bitbrowser_proxy

# ---------------------------------------------------------------------------
# 环境变量（仅保留确有必要的开关）
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    v = (os.environ.get(name, "") or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


# 为 true 时打开窗口会加载扩展；GitHub 注册场景建议保持 false
BITBROWSER_LOAD_EXTENSIONS = _env_bool("BITBROWSER_LOAD_EXTENSIONS", False)

BITBROWSER_BASE_URL = os.environ.get("BITBROWSER_BASE_URL", "http://127.0.0.1:54345")
BITBROWSER_API_KEY = os.environ.get("BITBROWSER_API_KEY", "ce09d101554e4383818d2da198c8f8fd")

API_TIMEOUT = 30

# ---------------------------------------------------------------------------
# GitHub 注册：打开窗口时的 Chromium 启动参数（POST /browser/open → args）
# ---------------------------------------------------------------------------

GITHUB_REGISTER_LAUNCH_ARGS: list[str] = [
    # 首启：减少「设为默认浏览器」等打断
    "--no-first-run",
    "--no-default-browser-check",
    # Linux/部分环境共享内存不足时的稳定性
    "--disable-dev-shm-usage",
    # 扩展会改请求头、注入脚本，易触发风控或拦验证码
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
    # 减少无关后台与账号体系弹窗（不碰 background-networking，以免影响 CDN/挑战资源）
    "--disable-default-apps",
    "--disable-sync",
]


def _to_bitbrowser_proxy(
    proxy_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """将通用代理配置转为 Bitbrowser API 所需字段。"""
    return to_bitbrowser_proxy(proxy_config)


def _api_post(path: str, body: Optional[dict[str, Any]] = None) -> Any:
    """向 Bitbrowser 本地 API 发送 POST，body 为 JSON，带 x-api-key 鉴权。"""
    url = f"{BITBROWSER_BASE_URL.rstrip('/')}{path}"
    headers = {"x-api-key": BITBROWSER_API_KEY}
    resp = requests.post(url, json=body or {}, headers=headers, timeout=API_TIMEOUT)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError(f"Bitbrowser API 返回非 JSON: {e}") from e
    if not data.get("success"):
        raise RuntimeError(data.get("msg", "Bitbrowser API 调用失败"))
    return data.get("data")


def _github_browser_fingerprint(os_type: str = "win") -> dict[str, Any]:
    """
    GitHub / Arkose 场景指纹：与代理 IP 对齐 + 噪声字段交给 BitBrowser 随机化。
    UA/version 留空由客户端按内核生成，避免手写与真实 Chromium 不一致。
    """
    if os_type.lower() in ("win", "windows"):
        os_platform, os_version = "Win64", "11,10"
        resolution = "1920 x 1080"
        dpr, cores, mem = "1", "8", "8"
    else:
        os_platform, os_version = "MacIntel", ""
        resolution = "1920 x 1080"
        dpr, cores, mem = "2", "10", "8"

    return {
        "coreProduct": "chrome",
        "coreVersion": "",
        "ostype": "PC",
        "os": os_platform,
        "osVersion": os_version,
        "version": "",
        "userAgent": "",
        "isIpCreateTimeZone": True,
        "timeZone": "",
        "timeZoneOffset": 0,
        "webRTC": "0",
        "ignoreHttpsErrors": False,
        "position": "1",
        "isIpCreatePosition": True,
        "isIpCreateLanguage": True,
        "resolutionType": "1",
        "resolution": resolution,
        "devicePixelRatio": dpr,
        "colorDepth": 24,
        "hardwareConcurrency": cores,
        "deviceMemory": mem,
        "fontType": "0",
        "canvas": "0",
        "webGL": "0",
        "webGLMeta": "0",
        "audioContext": "0",
        "mediaDevice": "0",
        "clientRects": "0",
        "deviceNameType": "1",
        "deviceName": "",
        # BitBrowser：0=开 DNT，1=关 DNT。关 DNT 更利于 Arkose/OctoCaptcha
        "doNotTrack": "1",
    }


def _github_profile_side_options(
    *,
    workbench: str,
    sync_tabs: bool,
) -> dict[str, Any]:
    """
    与「指纹」无关、但对自动化/少标签页友好的档案选项。
    """
    return {
        "randomFingerprint": False,
        "clearCacheFilesBeforeLaunch": False,
        "clearCookiesBeforeLaunch": False,
        "clearHistoriesBeforeLaunch": False,
        "disableTranslatePopup": True,
        "disableNotifications": True,
        "abortImage": False,
        "abortMedia": False,
        "disableGpu": False,
        "muteAudio": False,
        "credentialsEnableService": False,
        "ipCheckService": "ip-api",
        "allowedSignin": True,
        "workbench": workbench,
        "syncTabs": sync_tabs,
    }


def _platform_icon_from_url(platform: str) -> str:
    """从 platform URL 提取图标名，如 https://github.com -> github。"""
    if not platform or "//" not in platform:
        return "github"
    try:
        return platform.split("//")[-1].split("/")[0].split(".")[-2]
    except Exception:
        return "github"


def create_github_ready_browser(
    name: str,
    proxy_config: Optional[dict[str, Any]] = None,
    url: str = "",
    platform: str = "",
    os_type: str = "win",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    创建用于 GitHub 注册的档案（POST /browser/update）。

    :param url: BitBrowser「额外打开」的 URL，逗号分隔；建议留空，由平台首页 + 自动化导航，减少多标签。
    :param platform: 绑定平台 URL，影响图标与首启页。
    :param os_type: win | mac，决定指纹里的 OS 字段。
    """
    platform_icon = _platform_icon_from_url(platform)
    workbench = kwargs.pop("workbench", "disable")
    sync_tabs = kwargs.pop("syncTabs", False)

    body: dict[str, Any] = {
        "name": name,
        "url": url,
        "platform": platform or "https://github.com",
        "platformIcon": platform_icon,
        "remark": kwargs.pop("remark", ""),
        "userName": kwargs.pop("userName", ""),
        "password": kwargs.pop("password", ""),
        "proxyMethod": 2,
        "proxyType": "noproxy",
        "browserFingerPrint": _github_browser_fingerprint(os_type=os_type),
        **_github_profile_side_options(workbench=workbench, sync_tabs=sync_tabs),
        **kwargs,
    }
    body.update(_to_bitbrowser_proxy(proxy_config))
    return _api_post("/browser/update", body)


def close_extra_tabs_after_open(
    cdp_ws_url: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """
    打开窗口后通过 CDP 关闭除第一个标签外的所有页。
    BitBrowser 首启仍可能叠加「平台页 + 工作台」等，此处收敛为单标签便于自动化。
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            br = p.chromium.connect_over_cdp(cdp_ws_url)
            if not br.contexts:
                return
            ctx = br.contexts[0]
            pages = list(ctx.pages)
            if len(pages) <= 1:
                return
            for pg in pages[1:]:
                try:
                    pg.close()
                except Exception:
                    pass
            if callable(log):
                log(f"已关闭多余标签页，保留 1 个（原有 {len(pages)} 个）")
    except Exception as e:
        if callable(log):
            log(f"收敛标签页时跳过: {e}")


def open_browser(
    profile_id: str,
    args: Optional[list[str]] = None,
    queue: bool = False,
    load_extensions: bool = False,
) -> dict[str, Any]:
    """
    打开浏览器窗口（POST /browser/open）。

    默认使用 GITHUB_REGISTER_LAUNCH_ARGS；勿传 headless；需要完全自定义时传入 args。
    """
    body: dict[str, Any] = {
        "id": profile_id,
        "loadExtensions": BITBROWSER_LOAD_EXTENSIONS if not load_extensions else True,
    }
    if args is None:
        body["args"] = list(GITHUB_REGISTER_LAUNCH_ARGS)
    else:
        body["args"] = args
    if queue:
        body["queue"] = True
    return _api_post("/browser/open", body)


def close_browser(profile_id: str) -> dict[str, Any]:
    """关闭指定档案的浏览器窗口。"""
    return _api_post("/browser/close", {"id": profile_id})


def check_proxy_ip(
    proxy_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """通过代理请求 ipinfo.io，返回当前出口 IP 信息。"""
    from proxy_config import check_proxy_ip as _check

    return _check(proxy_config)