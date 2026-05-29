from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class GitHubAccount(TimestampMixin, Base):
    __tablename__ = "github_accounts"
    __table_args__ = {"schema": "asset_center"}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bind_mail_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.mail_accounts.id"), nullable=True
    )
    source_client_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.desktop_clients.id"), nullable=True
    )
    source_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.sync_batches.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    credential = relationship(
        "GitHubCredential",
        back_populates="github_account",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )
