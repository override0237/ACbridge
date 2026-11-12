"""Append-only audit trail for money events. Stores a SHA-256 of the canonical payload, never the payload itself
(so no phone numbers, references or amounts are copied into the log, yet an event can still be proven later)."""
import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog


def payload_hash(payload: dict | None) -> str:
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record(db: Session, actor_type: str, actor_id: uuid.UUID | str | None, action: str, target: str,
           payload: dict | None = None) -> AuditLog:
    entry = AuditLog(actor_type=actor_type, actor_id=str(actor_id) if actor_id else None, action=action,
                     target=str(target), payload_hash=payload_hash(payload))
    db.add(entry)
    return entry
