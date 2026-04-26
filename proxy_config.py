"""
通用代理配置：支持通过环境变量 / .env 文件配置任意 HTTP/SOCKS5 代理。
不再绑定特定代理服务商。
"""
from __future__ import annotations

import os
import sys
import json
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# 获取可执行文件所在目录（兼容打包后与开发环境）
# ---------------------------------------------------------------------------
def _get_base_path():
    if getattr(sys, 'frozen', False):
        # 打包后的可执行文件所在目录
        return os.path.dirname(sys.executable)
    # 开发环境代码所在目录
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = _get_base_path()
IPINFO_URL = "https://ipinfo.io/"
REQUEST_TIMEOUT = 15
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")


def load_config() -> dict[str, str]:
    """从 config.json 加载代理配置。"""
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_config(config: dict[str, str]) -> None:
    """将配置保存到 config.json。"""
    try:
        current = load_config()
        # 更新代理和 BitBrowser 字段
        current.update({
            "proxyHost": config.get("proxyHost", ""),
            "proxyPort": config.get("proxyPort", ""),
            "proxyUser": config.get("proxyUser", ""),
            "proxyPass": config.get("proxyPass", ""),
            "proxyType": config.get("proxyType", "http"),
            "bitbrowserUrl": config.get("bitbrowserUrl", "http://127.0.0.1:54345"),
            "bitbrowserKey": config.get("bitbrowserKey", ""),
        })
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_bitbrowser_config() -> tuple[str, str]:
    """获取 BitBrowser API 配置：(url, key)"""
    file_cfg = load_config()
    url = file_cfg.get("bitbrowserUrl") or os.environ.get("BITBROWSER_BASE_URL", "http://127.0.0.1:54345")
    key = file_cfg.get("bitbrowserKey") or os.environ.get("BITBROWSER_API_KEY", "")
    return url, key


def get_proxy_config(
    host: Optional[str] = None,
    port: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    proxy_type: Optional[str] = None,
) -> dict[str, str]:
    """
    获取代理配置，优先级：传入参数 > config.json > 环境变量。
    返回统一格式的 dict:
      {"proxyHost", "proxyPort", "proxyUser", "proxyPass", "proxyType"}
    """
    file_cfg = load_config()
    return {
        "proxyHost": host or file_cfg.get("proxyHost") or os.environ.get("PROXY_HOST", ""),
        "proxyPort": port or file_cfg.get("proxyPort") or os.environ.get("PROXY_PORT", ""),
        "proxyUser": user or file_cfg.get("proxyUser") or os.environ.get("PROXY_USER", ""),
        "proxyPass": password or file_cfg.get("proxyPass") or os.environ.get("PROXY_PASS", ""),
        "proxyType": proxy_type or file_cfg.get("proxyType") or os.environ.get("PROXY_TYPE", "http"),
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


def test_proxy_connectivity(
    config: Optional[dict[str, str]] = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    """
    通过代理获取出口 IP，验证代理是否真正生效。
    :return: (ok, message)
    """
    try:
        info = check_proxy_ip(config)
        ip = info.get("ip", "未知")
        country = info.get("country", "")
        city = info.get("city", "")
        loc_str = f" ({city}, {country})" if country else ""
        return True, f"测试成功！出口 IP: {ip}{loc_str}"
    except requests.exceptions.ProxyError as e:
        return False, f"代理连接失败: {e}"
    except requests.exceptions.ConnectTimeout:
        return False, f"代理连接超时（{timeout}s）"
    except Exception as e:
        if "Missing dependencies for SOCKS support" in str(e):
            return False, "缺少 SOCKS 依赖：请安装 PySocks（pip install pysocks）"
        return False, f"代理检测异常: {e}"
