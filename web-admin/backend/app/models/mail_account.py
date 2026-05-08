from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class MailAccount(TimestampMixin, Base):
    __tablename__ = "mail_accounts"
    __table_args__ = {"schema": "asset_center"}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    lease_client_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.desktop_clients.id"), nullable=True
    )
    lease_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    credential = relationship(
        "MailCredential",
        back_populates="mail_account",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )
