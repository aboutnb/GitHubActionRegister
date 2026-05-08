from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SyncBatch(TimestampMixin, Base):
    __tablename__ = "sync_batches"
    __table_args__ = {"schema": "asset_center"}

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    batch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.desktop_clients.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("asset_center.web_users.id"), nullable=True
    )
