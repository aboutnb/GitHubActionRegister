from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class MailCredential(TimestampMixin, Base):
    __tablename__ = "mail_credentials"
    __table_args__ = {"schema": "asset_center"}

    mail_account_id: Mapped[int] = mapped_column(
        ForeignKey("asset_center.mail_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    receive_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    smtp_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    mail_account = relationship("MailAccount", back_populates="credential")
