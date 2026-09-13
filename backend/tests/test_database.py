from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.demo import seed


def test_demo_opt_in_and_idempotent(db):
    assert not db.exists("SELECT id FROM app_user")
    seed(db, "fictional demo password")
    before = db.one("SELECT COUNT(*) n FROM expense")["n"]
    seed(db, "fictional demo password")
    assert before == db.one("SELECT COUNT(*) n FROM expense")["n"] == 54
    assert db.one("SELECT COUNT(*) n FROM app_user")["n"] == 4
    assert (
        db.one(
            "SELECT COUNT(*) n FROM (SELECT e.id FROM expense e JOIN allocation a ON a.expense_id=e.id GROUP BY e.id,e.amount HAVING SUM(a.amount)<>e.amount) bad"
        )["n"]
        == 0
    )


def test_allocation_foreign_keys(engine, clean):
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text("INSERT INTO allocation VALUES(:id,:u,100)"), {"id": uuid4(), "u": uuid4()}
        )


def test_membership_dates_constraint(db):
    seed(db, "fictional demo password")
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.execute("UPDATE membership SET left_at=joined_at-1")


def test_backup_enum_cast_representation():
    from app.migration_validation import normalize_check

    assert normalize_check(
        "role::text = ANY (ARRAY['OWNER'::character varying::text, 'MEMBER'::character varying::text])"
    ) == normalize_check(
        "role::text = ANY (ARRAY['OWNER'::character varying, 'MEMBER'::character varying]::text[])"
    )
    assert normalize_check(
        "role::text = ANY (ARRAY['OWNER'::character varying]::text[])"
    ) != normalize_check("role::text = ANY (ARRAY['MEMBER'::character varying]::text[])")
