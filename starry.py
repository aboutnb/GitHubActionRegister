"""Starry 代理请求：通过代理访问 ipinfo.io 校验出口 IP。"""
from __future__ import annotations

import random
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

AREA_OPTIONS = ["us", "gb", "de", "ca", "jp", "fr", "nl"]
IPINFO_URL = "https://ipinfo.io/"
REQUEST_TIMEOUT = 15

# 代理账号基础信息（area 由 get_default_proxy_config 随机填充；敏感信息建议用环境变量覆盖）
_PROXY_BASE = {
    "proxyUser": "accountId-6530-tunnelId-15166-area-{area}",
    "proxyPass": "CkgZ4q",
    "proxyHost": "proxyus.starryproxy.com",
    "proxyPort": "10000",
}


def get_default_proxy_config() -> dict[str, str]:
    """返回默认代理配置，area 从 AREA_OPTIONS 中随机选一个国家。"""
    area = random.choice(AREA_OPTIONS)
    return {
        "proxyUser": _PROXY_BASE["proxyUser"].format(area=area),
        "proxyPass": _PROXY_BASE["proxyPass"],
        "proxyHost": _PROXY_BASE["proxyHost"],
        "proxyPort": _PROXY_BASE["proxyPort"],
    }


def get_proxy_ip_info(
    proxy_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    通过指定代理请求 ipinfo.io，返回当前代理出口 IP 信息。
    :param proxy_config: 需含 proxyUser, proxyPass, proxyHost, proxyPort；None 时使用默认（随机国家）
    :return: 包含 ip, country, region, city, timezone, loc 等字段
    """
    config = proxy_config or get_default_proxy_config()
    proxy_url = "http://{proxyUser}:{proxyPass}@{proxyHost}:{proxyPort}".format(**config)
    proxies = {"http": proxy_url, "https": proxy_url}
    resp = requests.get(IPINFO_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    data = get_proxy_ip_info()
    print(data)
    print("\n--- 解析后 ---")
    print(f"IP: {data.get('ip')}, Country: {data.get('country')}, Region: {data.get('region')}")
    print(f"City: {data.get('city')}, Timezone: {data.get('timezone')}")
