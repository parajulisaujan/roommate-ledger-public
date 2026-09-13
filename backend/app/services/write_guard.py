"""Membership changes take precedence at a transaction, not calendar, boundary."""

from uuid import UUID

from app.db import Store
from app.errors import forbidden


def write_guard(db: Store, user: UUID, *, membership_change: bool = False):
    # One shared/exclusive gate avoids cross-household deactivation lock inversions.
    # Writers run concurrently; rare membership changes wait for existing writers.
    function = "pg_advisory_xact_lock" if membership_change else "pg_advisory_xact_lock_shared"
    db.execute(f"SELECT {function}(731924, 1)")
    if not db.exists("SELECT id FROM app_user WHERE id=:u AND deactivated=false", u=user):
        raise forbidden()
