from __future__ import annotations

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class GitHubCredential(TimestampMixin, Base):
    __tablename__ = "github_credentials"
    __table_args__ = {"schema": "asset_center"}

    github_account_id: Mapped[int] = mapped_column(
        ForeignKey("asset_center.github_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    github_password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_codes_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    github_account = relationship("GitHubAccount", back_populates="credential")
