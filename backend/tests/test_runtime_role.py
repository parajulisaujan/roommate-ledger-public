from uuid import UUID, uuid4

import pytest
from conftest import register
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_ledger import expense

from app.db import Store
from app.schemas import ExpenseInput
from app.services.expenses import Expenses
from app.services.idempotency import replayable


def test_restricted_runtime_can_write_ledger_but_not_schema(client, engine):
    user = register(client)
    role = "ledger_runtime_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.exec_driver_sql(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
        )
        conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        conn.exec_driver_sql(
            f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'
        )
        conn.exec_driver_sql(f'REVOKE INSERT,UPDATE,DELETE ON alembic_version FROM "{role}"')
    try:
        with Session(engine) as session, session.begin():
            db = Store(session)
            db.execute(f'SET LOCAL ROLE "{role}"')
            data, actor = ExpenseInput(**expense(user, amount=101)), UUID(user["id"])
            created = replayable(
                db,
                actor,
                "expense.create",
                str(uuid4()),
                data.model_dump(mode="json"),
                lambda: Expenses(db).create(actor, data),
            )
            assert sum(row["amount"] for row in created["allocations"]) == 101
            assert (
                db.one("SELECT version_num FROM alembic_version")["version_num"]
                == "0003_request_idempotency"
            )
        for sql in [
            "CREATE TABLE forbidden_ddl(id int)",
            "UPDATE alembic_version SET version_num='forbidden'",
        ]:
            with pytest.raises(ProgrammingError) as exc, engine.begin() as conn:
                conn.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                conn.exec_driver_sql(sql)
            assert exc.value.orig.sqlstate == "42501"
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "{role}"'
            )
            conn.exec_driver_sql(f'REVOKE ALL PRIVILEGES ON SCHEMA public FROM "{role}"')
            conn.exec_driver_sql(f'DROP ROLE "{role}"')
