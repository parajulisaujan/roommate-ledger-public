"""Receipts commit atomically with the financial write; keys are never authorization."""

import hashlib
import json
import re
from collections.abc import Callable
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.db import Store
from app.errors import conflict, invalid


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def replayable(
    db: Store, user: UUID, operation: str, key: str | None, payload: dict, create: Callable
):
    # Compatibility for existing integrations. First-party clients always send a key.
    if key is None:
        return create()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
        raise invalid(
            "Use an Idempotency-Key of 16 to 128 letters, digits, underscores or hyphens."
        )
    key_hash = digest(key)
    request_hash = digest(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    # Hash collisions merely serialize unrelated requests; full identities match below.
    lock = int.from_bytes(
        hashlib.sha256(f"{user}:{operation}:{key_hash}".encode()).digest()[:8], "big", signed=True
    )
    db.execute("SELECT pg_advisory_xact_lock(:lock)", lock=lock)
    params = dict(u=user, operation=operation, key=key_hash)
    rows = db.all(
        """SELECT request_hash,response,expires_at>CURRENT_TIMESTAMP AS live
        FROM request_idempotency WHERE user_id=:u AND operation=:operation AND key_hash=:key""",
        **params,
    )
    if rows:
        row = rows[0]
        if row["request_hash"] != request_hash:
            raise conflict("This request key was already used with different details.")
        if not row["live"]:
            raise conflict(
                "This request key has expired. Reconcile the ledger before creating a new request."
            )
        return row["response"]
    result = jsonable_encoder(create())
    db.execute(
        """INSERT INTO request_idempotency(user_id,operation,key_hash,request_hash,response)
        VALUES(:u,:operation,:key,:request,CAST(:response AS jsonb))""",
        **params,
        request=request_hash,
        response=json.dumps(result),
    )
    return result
