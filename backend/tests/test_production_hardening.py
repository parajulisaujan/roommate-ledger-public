from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from time import monotonic
from uuid import UUID, uuid4

import pytest
from conftest import csrf, mutate, register
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_ledger import expense

from app.db import Store, engine_for
from app.errors import ApiError
from app.schemas import ExpenseInput, SettlementInput
from app.services.accounts import Accounts
from app.services.expenses import Expenses
from app.services.finance import Finance
from app.services.households import Households
from app.services.idempotency import replayable
from app.services.write_guard import write_guard


def payment(users):
    return dict(
        fromUser=users[1]["id"],
        toUser=users[0]["id"],
        amount=101,
        method="Cash",
        date=date.today().isoformat(),
    )


def keyed(client, path, payload, key):
    return client.post(path, json=payload, headers=csrf(client) | {"Idempotency-Key": key})


@pytest.mark.parametrize("kind", ["expense", "settlement"])
def test_retry_replays_and_conflicting_payload_rejected(household, engine, kind):
    clients, users, house = household
    client = clients[1]
    path = "/api/expenses" if kind == "expense" else f"/api/households/{house}/settlements"
    payload = expense(users[1], house, 101) if kind == "expense" else payment(users)
    key = str(uuid4())
    first = keyed(client, path, payload, key)
    assert first.status_code == 200
    assert keyed(client, path, payload, key).json() == first.json()
    assert keyed(client, path, payload | {"amount": 102}, key).status_code == 409
    with engine.begin() as conn:
        assert conn.execute(text(f"SELECT COUNT(*) FROM {kind}")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM request_idempotency")).scalar_one() == 1
        conn.execute(
            text("UPDATE request_idempotency SET expires_at=CURRENT_TIMESTAMP-INTERVAL '1 day'")
        )
    assert keyed(client, path, payload, key).status_code == 409


def test_legacy_unkeyed_retry_demonstrates_risk(client):
    user = register(client)
    data = expense(user)
    first = mutate(client, "POST", "/api/expenses", data).json()
    second = mutate(client, "POST", "/api/expenses", data).json()
    assert first["id"] != second["id"]


def test_retry_authorization_and_snapshot(household, engine):
    clients, users, house = household
    key, payload = str(uuid4()), expense(users[1], house)
    first = keyed(clients[1], "/api/expenses", payload, key).json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE expense SET title='Later correction'"))
    assert keyed(clients[1], "/api/expenses", payload, key).json() == first
    members = clients[0].get(f"/api/households/{house}/members").json()
    member = next(m["id"] for m in members if m["user_id"] == users[1]["id"])
    assert (
        mutate(clients[0], "DELETE", f"/api/households/{house}/members/{member}").status_code == 200
    )
    assert keyed(clients[1], "/api/expenses", payload, key).status_code == 403


@pytest.mark.parametrize("kind", ["expense", "settlement"])
def test_concurrent_duplicate_transactions(household, engine, kind):
    _, users, house = household
    actor, house = UUID(users[1]["id"]), UUID(house)
    data = (
        ExpenseInput(**expense(users[1], str(house), 101))
        if kind == "expense"
        else SettlementInput(**payment(users))
    )
    key = str(uuid4())
    barrier = Barrier(2)

    def submit():
        with Session(engine) as session, session.begin():
            db = Store(session)
            write_guard(db, actor)
            barrier.wait(timeout=5)
            create = (
                (lambda: Expenses(db).create(actor, data))
                if kind == "expense"
                else (lambda: Finance(db).settle(actor, house, data))
            )
            return replayable(db, actor, kind, key, data.model_dump(mode="json"), create)

    with ThreadPoolExecutor(2) as pool:
        one, two = pool.submit(submit), pool.submit(submit)
        assert one.result(timeout=10) == two.result(timeout=10)
    with engine.connect() as conn:
        assert conn.execute(text(f"SELECT COUNT(*) FROM {kind}")).scalar_one() == 1
        assert (
            conn.execute(
                text("SELECT COUNT(*) FROM audit_event WHERE action=:action"),
                {"action": "EXPENSE_CREATED" if kind == "expense" else "SETTLEMENT_RECORDED"},
            ).scalar_one()
            == 1
        )
        if kind == "expense":
            assert conn.execute(text("SELECT SUM(amount) FROM allocation")).scalar_one() == 101


def test_failed_write_rolls_back_key_and_user_operation_scope(client, engine):
    user = register(client)
    actor, key = UUID(user["id"]), str(uuid4())
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():

        def fail():
            raise RuntimeError("fictional failure")

        replayable(Store(session), actor, "expense.create", key, {}, fail)
    with Session(engine) as session, session.begin():
        db = Store(session)
        assert replayable(db, actor, "expense.create", key, {}, lambda: {"ok": 1}) == {"ok": 1}
        assert replayable(db, actor, "settlement.create", key, {}, lambda: None) is None
    assert (
        keyed(client, "/api/expenses", expense(user), "fictional-secret://invalid").status_code
        == 400
    )
    assert (
        "fictional-secret"
        not in keyed(client, "/api/expenses", expense(user), "fictional-secret://invalid").text
    )


@pytest.mark.parametrize("change", ["remove", "deactivate", "join"])
@pytest.mark.parametrize("write_first", [True, False])
@pytest.mark.parametrize("kind", ["expense", "settlement"])
def test_membership_transaction_cutoff(
    household, engine, settings, mailbox, change, write_first, kind
):
    clients, users, house = household
    owner, actor, house_id = UUID(users[0]["id"]), UUID(users[1]["id"]), UUID(house)
    member = next(
        m["id"]
        for m in clients[0].get(f"/api/households/{house}/members").json()
        if m["user_id"] == str(actor)
    )
    invitation = None
    if change == "join":
        assert (
            mutate(clients[0], "DELETE", f"/api/households/{house}/members/{member}").status_code
            == 200
        )
        invitation = mutate(clients[0], "POST", f"/api/households/{house}/invitations").json()[
            "token"
        ]
    acquired, release = Event(), Event()

    def run(is_write, first):
        try:
            with Session(engine) as session, session.begin():
                db = Store(session)
                if first:
                    write_guard(db, owner, membership_change=not is_write)
                    acquired.set()
                    assert release.wait(4)
                if is_write:
                    if kind == "expense":
                        Expenses(db).create(actor, ExpenseInput(**expense(users[1], house, 101)))
                    else:
                        Finance(db).settle(actor, house_id, SettlementInput(**payment(users)))
                elif change == "remove":
                    Households(db).leave(owner, house_id, UUID(member))
                elif change == "deactivate":
                    Accounts(db, settings, mailbox).deactivate(actor, users[1]["password"])
                else:
                    Households(db).accept(actor, invitation)
            return 200
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(run, write_first, True)
        assert acquired.wait(3)
        second = pool.submit(run, not write_first, False)
        try:
            # Observe the real PostgreSQL waiter, rather than assuming a sleep proves a race.
            deadline = monotonic() + 3
            blocked = False
            while monotonic() < deadline:
                with engine.connect() as conn:
                    blocked = conn.execute(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND classid=731924 AND objid=1 AND NOT granted)"
                        )
                    ).scalar_one()
                if blocked:
                    break
                Event().wait(0.02)
            assert blocked
        finally:
            release.set()
        outcomes = {write_first: first.result(timeout=5), not write_first: second.result(timeout=5)}
    allowed = (not write_first) if change == "join" else write_first
    assert outcomes[True] == (200 if allowed else 403)
    assert outcomes[False] == 200
    with engine.connect() as conn:
        assert conn.execute(text(f"SELECT COUNT(*) FROM {kind}")).scalar_one() == int(allowed)


def test_anonymous_cap_reuse_and_spoofed_forwarding(app, engine):
    app.state.settings = app.state.settings.model_copy(
        update={"rate_session_creation": 2, "anonymous_session_limit": 2}
    )
    with TestClient(app) as first, TestClient(app) as second, TestClient(app) as third:
        assert first.get("/api/auth/csrf").status_code == 200
        for _ in range(4):
            assert first.get("/api/auth/csrf").status_code == 200
        assert second.get("/api/auth/csrf").status_code == 200
        assert (
            third.get("/api/auth/csrf", headers={"X-Forwarded-For": "203.0.113.7"}).status_code
            == 429
        )
        assert (
            third.get("/api/auth/csrf", headers={"X-Forwarded-For": "203.0.113.8"}).status_code
            == 429
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM web_session")).scalar_one() == 2


def test_concurrent_anonymous_global_cap(app, engine):
    app.state.settings = app.state.settings.model_copy(update={"anonymous_session_limit": 1})
    barrier = Barrier(2)

    def create():
        with TestClient(app) as client:
            barrier.wait(timeout=5)
            return client.get("/api/auth/csrf").status_code

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(create) for _ in range(2)]
        assert sorted(f.result(timeout=10) for f in futures) == [200, 429]


def test_general_write_budget(app, client):
    register(client)
    app.state.settings = app.state.settings.model_copy(update={"rate_writes": 1})
    assert mutate(client, "POST", "/api/households", {"name": "Fictional one"}).status_code == 200
    assert mutate(client, "POST", "/api/households", {"name": "Fictional two"}).status_code == 429


def test_production_requires_financial_request_key(app, household):
    clients, users, house = household
    app.state.settings = app.state.settings.model_copy(update={"app_env": "production"})
    assert mutate(clients[1], "POST", "/api/expenses", expense(users[1], house)).status_code == 400
    assert (
        mutate(
            clients[1], "POST", f"/api/households/{house}/settlements", payment(users)
        ).status_code
        == 400
    )
    assert (
        keyed(clients[1], "/api/expenses", expense(users[1], house), str(uuid4())).status_code
        == 200
    )


def test_keys_are_scoped_to_user_and_compaction_retains_tombstones(household, engine):
    from app.maintenance import compact

    clients, users, _ = household
    key = str(uuid4())
    for index in (0, 1):
        assert keyed(clients[index], "/api/expenses", expense(users[index]), key).status_code == 200
    with Session(engine) as session, session.begin():
        db = Store(session)
        assert db.one("SELECT COUNT(*) AS n FROM request_idempotency")["n"] == 2
        db.execute("UPDATE request_idempotency SET expires_at=CURRENT_TIMESTAMP-INTERVAL '1 day'")
        compact(db)
        assert (
            db.one("SELECT COUNT(*) AS n FROM request_idempotency WHERE response IS NULL")["n"] == 2
        )
    assert keyed(clients[0], "/api/expenses", expense(users[0]), key).status_code == 409


@pytest.mark.parametrize("migration,statement,lock", [(False, "15s", "5s"), (True, "5min", "10s")])
def test_real_postgres_timeout_defaults(settings, migration, statement, lock):
    engine = engine_for(settings, migration=migration)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SHOW statement_timeout").scalar_one() == statement
            assert conn.exec_driver_sql("SHOW lock_timeout").scalar_one() == lock
            assert conn.connection.driver_connection.info.get_parameters()["connect_timeout"] == "5"
    finally:
        engine.dispose()


def test_explicit_libpq_options_preserved(settings):
    url = settings.sqlalchemy_url.update_query_dict(
        {"options": "-c statement_timeout=1234 -c lock_timeout=123", "connect_timeout": "7"}
    )
    configured = settings.model_copy(
        update={"database_url": url.render_as_string(hide_password=False)}
    )
    engine = engine_for(configured)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SHOW statement_timeout").scalar_one() == "1234ms"
            assert conn.exec_driver_sql("SHOW lock_timeout").scalar_one() == "123ms"
    finally:
        engine.dispose()


def test_statement_and_lock_timeouts_interrupt_queries(engine):
    with engine.connect() as connection:
        connection.exec_driver_sql("SET LOCAL statement_timeout='50ms'")
        with pytest.raises(OperationalError) as error:
            connection.exec_driver_sql("SELECT pg_sleep(0.2)")
        assert error.value.orig.sqlstate == "57014"
        connection.rollback()
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    with engine.begin() as holder, engine.connect() as waiter:
        holder.exec_driver_sql("SELECT pg_advisory_xact_lock(731924, 9)")
        waiter.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
        with pytest.raises(OperationalError) as error:
            waiter.exec_driver_sql("SELECT pg_advisory_xact_lock(731924, 9)")
        assert error.value.orig.sqlstate == "55P03"
        waiter.rollback()


def test_write_and_idempotency_receipt_rollback_together(client, engine):
    user = register(client)
    actor, key = UUID(user["id"]), str(uuid4())
    data = ExpenseInput(**expense(user, amount=101))
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        db = Store(session)
        replayable(
            db,
            actor,
            "expense.create",
            key,
            data.model_dump(mode="json"),
            lambda: Expenses(db).create(actor, data),
        )
        raise RuntimeError("Fictional commit-path failure")
    with engine.connect() as conn:
        for table in ["expense", "allocation", "request_idempotency"]:
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
    assert keyed(client, "/api/expenses", expense(user, amount=101), key).status_code == 200
