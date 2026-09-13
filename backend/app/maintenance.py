"""Bounded expiry compaction. Retain key tombstones to prevent delayed duplicates."""

import logging
import sys

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Store, engine_for


def compact(db: Store):
    db.execute("""WITH expired AS (
        SELECT user_id,operation,key_hash FROM request_idempotency
        WHERE expires_at<CURRENT_TIMESTAMP AND response IS NOT NULL
        LIMIT 500 FOR UPDATE SKIP LOCKED)
        UPDATE request_idempotency r SET response=NULL FROM expired e
        WHERE r.user_id=e.user_id AND r.operation=e.operation AND r.key_hash=e.key_hash""")


def main():
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        engine = engine_for(Settings(), pool_size=1, max_overflow=0)
        try:
            with Session(engine) as session, session.begin():
                compact(Store(session))
        finally:
            engine.dispose()
    except Exception:
        print("MAINTENANCE FAIL compaction", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        logging.disable(previous)
    print("MAINTENANCE PASS compaction")


if __name__ == "__main__":
    main()
