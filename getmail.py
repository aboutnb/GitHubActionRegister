"""
邮箱取件模块 — 基于小水滴微软邮箱 API。

实际取件逻辑全部委托给 xiaoshuidi_mail 模块。
"""

from xiaoshuidi_mail import (
    get_mail,
    get_verification_info,
)

__all__ = [
    "get_mail",
    "get_verification_info",
]
