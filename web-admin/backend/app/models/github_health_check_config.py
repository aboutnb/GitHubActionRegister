from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class GitHubHealthCheckConfig(TimestampMixin, Base):
    __tablename__ = "github_health_check_configs"
    __table_args__ = {"schema": "asset_center"}

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cron_expression: Mapped[str] = mapped_column(String(64), nullable=False, default="0 0 1,15 * *")
    proxy_pool: Mapped[str | None] = mapped_column(Text, nullable=True)
    accounts_per_proxy: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_batch_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.web_users.id"), nullable=True
    )
