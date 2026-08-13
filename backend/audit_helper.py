"""Helper module for audit trail logging - direct DB insert."""

import uuid
from datetime import datetime
from db.database import get_session
from db.models import AuditLog


def log_audit_action(
    user_id: str,
    action: str,
    table_name: str,
    record_id: str,
    detail: str = None,
) -> None:
    """
    Insert an audit log entry directly into the database.

    This is a synchronous fire-and-forget operation that uses its own DB session
    so it never interferes with the calling tool's transaction.
    """
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    db = get_session()
    try:
        log_entry = AuditLog(
            audit_id=audit_id,
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            timestamp=datetime.now(),
        )
        db.add(log_entry)
        db.commit()
    except Exception:
        # Fail silently - audit logging should never break the main operation
        db.rollback()
    finally:
        db.close()