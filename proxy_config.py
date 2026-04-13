"""
通用代理配置：支持通过环境变量 / .env 文件配置任意 HTTP/SOCKS5 代理。
不再绑定特定代理服务商。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# 从环境变量读取代理配置（可在 .env / .env.local 中设置）
# ---------------------------------------------------------------------------

PROXY_HOST = os.environ.get("PROXY_HOST", "")
PROXY_PORT = os.environ.get("PROXY_PORT", "")
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
PROXY_TYPE = os.environ.get("PROXY_TYPE", "http")  # http / socks5

IPINFO_URL = "https://ipinfo.io/"
REQUEST_TIMEOUT = 15


def get_proxy_config(
    host: Optional[str] = None,
    port: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    proxy_type: Optional[str] = None,
) -> dict[str, str]:
    """
    获取代理配置，优先使用传入参数，其次使用环境变量。
    返回统一格式的 dict:
      {"proxyHost", "proxyPort", "proxyUser", "proxyPass", "proxyType"}
    """
    return {
        "proxyHost": host or PROXY_HOST,
        "proxyPort": port or PROXY_PORT,
        "proxyUser": user or PROXY_USER,
        "proxyPass": password or PROXY_PASS,
        "proxyType": proxy_type or PROXY_TYPE,
    }


def is_proxy_configured(config: Optional[dict[str, str]] = None) -> bool:
    """检查代理是否已配置（至少有 host 和 port）。"""
    cfg = config or get_proxy_config()
    return bool(cfg.get("proxyHost") and cfg.get("proxyPort"))


def build_proxy_url(config: Optional[dict[str, str]] = None) -> str:
    """
    构建代理 URL，格式如:
      http://user:pass@host:port
      socks5://host:port
    """
    cfg = config or get_proxy_config()
    scheme = cfg.get("proxyType", "http")
    host = cfg["proxyHost"]
    port = cfg["proxyPort"]
    user = cfg.get("proxyUser", "")
    pwd = cfg.get("proxyPass", "")
    if user and pwd:
        return f"{scheme}://{user}:{pwd}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def to_bitbrowser_proxy(config: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """将通用代理配置转为 Bitbrowser API 所需的字段。"""
    cfg = config or get_proxy_config()
    if not is_proxy_configured(cfg):
        return {"proxyMethod": 2, "proxyType": "noproxy"}
    return {
        "proxyMethod": 2,
        "proxyType": cfg.get("proxyType", "http"),
        "host": cfg["proxyHost"],
        "port": int(cfg["proxyPort"]),
        "proxyUserName": cfg.get("proxyUser", ""),
        "proxyPassword": cfg.get("proxyPass", ""),
    }


def check_proxy_ip(config: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """通过代理请求 ipinfo.io，返回出口 IP 信息。无代理时直接请求。"""
    cfg = config or get_proxy_config()
    if is_proxy_configured(cfg):
        url = build_proxy_url(cfg)
        proxies = {"http": url, "https": url}
        resp = requests.get(IPINFO_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
    else:
        resp = requests.get(IPINFO_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()
