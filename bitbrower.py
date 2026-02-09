"""
Bitbrowser 本地 API 封装：创建/打开/关闭浏览器窗口，代理使用 Starry 配置。
为 GitHub 等严格风控场景提供高仿真指纹配置，避免时区/语言/WebRTC 等破绽。
"""
from __future__ import annotations

import os
import warnings
from typing import Any, Optional

import requests

from starry import get_default_proxy_config, get_proxy_ip_info

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

BITBROWSER_BASE_URL = os.environ.get("BITBROWSER_BASE_URL", "http://127.0.0.1:54345")
BITBROWSER_API_KEY = os.environ.get("BITBROWSER_API_KEY", "ce09d101554e4383818d2da198c8f8fd")

API_TIMEOUT = 30


def _starry_to_bitbrowser_proxy(
    proxy_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """将 Starry 代理配置转为 Bitbrowser API 所需字段。"""
    config = proxy_config or get_default_proxy_config()
    return {
        "proxyMethod": 2,
        "proxyType": "http",
        "host": config["proxyHost"],
        "port": int(config["proxyPort"]),
        "proxyUserName": config["proxyUser"],
        "proxyPassword": config["proxyPass"],
    }


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


def _github_ready_fingerprint(os_type: str = "win") -> dict[str, Any]:
    """
    生成适合 GitHub 等严格风控的高仿真指纹，与代理 IP 一致、无自动化痕迹。
    时区/语言/地理位置按代理 IP 自动生成；WebRTC 替换为代理 IP；canvas/webGL 等为随机噪音。
    """
    if os_type.lower() in ("win", "windows"):
        os_platform, os_version = "Win32", "11,10"
        resolution = "1920 x 1080"
        device_pixel_ratio, hardware_concurrency, device_memory = "1", "8", "8"
    else:
        os_platform, os_version = "MacIntel", ""
        resolution = "1920 x 1080"
        device_pixel_ratio, hardware_concurrency, device_memory = "2", "10", "8"
    return {
        "coreProduct": "chrome",
        "coreVersion": "126",
        "ostype": "PC",
        "os": os_platform,
        "osVersion": os_version,
        "version": "",
        "userAgent": "",
        "isIpCreateTimeZone": True,
        "timeZone": "",
        "timeZoneOffset": 0,
        "webRTC": "0",
        "ignoreHttpsErrors": True,
        "position": "1",
        "isIpCreatePosition": True,
        "isIpCreateLanguage": True,
        "resolutionType": "1",
        "resolution": resolution,
        "devicePixelRatio": device_pixel_ratio,
        "colorDepth": 24,
        "hardwareConcurrency": hardware_concurrency,
        "deviceMemory": device_memory,
        "fontType": "0",
        "canvas": "0",
        "webGL": "0",
        "webGLMeta": "0",
        "audioContext": "0",
        "mediaDevice": "0",
        "clientRects": "0",
        "deviceNameType": "1",
        "deviceName": "",
        # Bitbrowser API：0=开启 DNT，1=关闭 DNT。必须为 "1" 关闭 DNT，否则 Arkose 验证码易报错
        "doNotTrack": "1",
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
    url: str = "https://github.com/signup",
    platform: str = "https://github.com",
    os_type: str = "win",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    创建面向 GitHub 注册的高仿真浏览器档案（使用 Starry 代理）。
    指纹与代理 IP 一致，避免风控检测到 IP 与浏览器环境不符。
    指纹中 doNotTrack=1（关闭 DNT）、abortImage/abortMedia=False，以利于 Arkose 验证码加载。
    若出现「We couldn't create your account」或验证码报错，请见项目内 TROUBLESHOOTING.md；
    官方排查：https://docs.github.com/zh/get-started/using-github/troubleshooting-connectivity-problems
    要点：代理/网络须允许 https://octocaptcha.com/ 与 https://arkoselabs.com/ ，可用同一档案访问 octocaptcha.com/test 自测。
    :return: API 返回的 data（含 id, seq 等）
    """
    platform_icon = _platform_icon_from_url(platform)
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
        "browserFingerPrint": _github_ready_fingerprint(os_type=os_type),
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
        **kwargs,
    }
    body.update(_starry_to_bitbrowser_proxy(proxy_config))
    return _api_post("/browser/update", body)


def create_browser(
    name: str,
    proxy_config: Optional[dict[str, Any]] = None,
    url: str = "",
    platform: str = "https://www.google.com",
    fingerprint: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    创建浏览器档案（使用 Starry 代理）。
    :param fingerprint: None 或 {} 表示随机生成
    :return: API 返回的 data（含 id, seq 等）
    """
    platform_icon = _platform_icon_from_url(platform) if platform else ""
    body: dict[str, Any] = {
        "name": name,
        "url": url or platform,
        "platform": platform,
        "platformIcon": platform_icon,
        "remark": kwargs.pop("remark", ""),
        "userName": kwargs.pop("userName", ""),
        "password": kwargs.pop("password", ""),
        "proxyMethod": 2,
        "proxyType": "noproxy",
        "browserFingerPrint": fingerprint if fingerprint is not None else {},
        **kwargs,
    }
    body.update(_starry_to_bitbrowser_proxy(proxy_config))
    return _api_post("/browser/update", body)


def open_browser(
    profile_id: str,
    args: Optional[list[str]] = None,
    queue: bool = False,
    load_extensions: bool = False,
) -> dict[str, Any]:
    """
    根据档案 id 打开浏览器，返回 CDP 地址与驱动路径。
    风控场景请勿传 args（尤其不要 --headless）。默认不加载扩展，避免拦截验证码。
    """
    body: dict[str, Any] = {"id": profile_id, "loadExtensions": load_extensions}
    if args is not None:
        body["args"] = args
    if queue:
        body["queue"] = True
    return _api_post("/browser/open", body)


def close_browser(profile_id: str) -> dict[str, Any]:
    """关闭指定档案的浏览器窗口。"""
    return _api_post("/browser/close", {"id": profile_id})


def get_browser_detail(profile_id: str) -> dict[str, Any]:
    """获取档案详情。"""
    return _api_post("/browser/detail", {"id": profile_id})


def list_browsers(
    page: int = 0,
    page_size: int = 20,
    **filters: Any,
) -> dict[str, Any]:
    """分页获取档案列表。filters 可为 name, remark, groupId 等。"""
    body = {"page": page, "pageSize": page_size, **filters}
    return _api_post("/browser/list", body)


def check_proxy_ip(
    proxy_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """使用 Starry 代理请求 ipinfo.io，返回当前出口 IP 信息。"""
    return get_proxy_ip_info(proxy_config)
