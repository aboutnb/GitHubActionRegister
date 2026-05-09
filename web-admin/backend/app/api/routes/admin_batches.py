from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.desktop_client import DesktopClient
from app.models.sync_batch import SyncBatch
from app.models.web_user import WebUser
from app.schemas.admin import SyncBatchListItem
from app.utils.datetime import format_datetime

router = APIRouter(prefix="/admin/batches", tags=["admin-batches"])


@router.get("")
def list_batches(
    batch_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(SyncBatch)
    if batch_type:
        query = query.filter(SyncBatch.batch_type == batch_type)
    if source:
        query = query.filter(SyncBatch.source == source)

    total = query.count()
    batches = (
        query.order_by(SyncBatch.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    client_map = {client.id: client.name for client in db.query(DesktopClient).all()}
    items = [
        SyncBatchListItem(
            id=batch.id,
            batch_no=batch.batch_no,
            batch_type=batch.batch_type,
            source=batch.source,
            client_name=client_map.get(batch.client_id),
            total_count=batch.total_count,
            success_count=batch.success_count,
            duplicate_count=batch.duplicate_count,
            created_at=format_datetime(batch.created_at),
        ).model_dump()
        for batch in batches
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
