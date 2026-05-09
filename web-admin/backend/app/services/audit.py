from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    operator_type: str,
    operator_id: int,
    action: str,
    target_type: str,
    target_id: int | None,
    details: dict | None = None,
) -> None:
    log = AuditLog(
        operator_type=operator_type,
        operator_id=operator_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )
    db.add(log)
