from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.migration_validation import apply_scripts
from app.services.accounts import password_hash

ROOT = Path(__file__).parents[1]


@pytest.fixture
def migration_engine(settings):
    name = "ledger_migration_test_" + uuid4().hex
    admin = create_engine(
        settings.sqlalchemy_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
    )
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(settings.sqlalchemy_url.set(database=name), hide_parameters=True)
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE "{name}"')
    admin.dispose()


def upgrade(engine):
    with engine.connect() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def baseline(engine, version):
    with engine.begin() as connection:
        apply_scripts(connection, sorted((ROOT / "alembic/baseline").glob("V*.sql"))[:version])
        connection.exec_driver_sql(
            "CREATE TABLE flyway_schema_history(installed_rank INTEGER PRIMARY KEY,version VARCHAR(50),success BOOLEAN NOT NULL)"
        )
        for i in range(1, version + 1):
            connection.execute(
                text("INSERT INTO flyway_schema_history VALUES(:i,:version,true)"),
                {"i": i, "version": str(i)},
            )


def test_fresh_upgrade_and_repeat(migration_engine):
    upgrade(migration_engine)
    upgrade(migration_engine)
    assert "web_session" in inspect(migration_engine).get_table_names()
    for table in ("expense", "allocation", "settlement"):
        amount = next(
            c for c in inspect(migration_engine).get_columns(table) if c["name"] == "amount"
        )
        assert str(amount["type"]) == "NUMERIC(14, 0)"


@pytest.mark.parametrize("version", [1, 2, 3])
def test_adopt_flyway_preserves_money_identity_and_history(migration_engine, version):
    baseline(migration_engine, version)
    user, expense = uuid4(), uuid4()
    encoded = password_hash("existing user password")
    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO app_user(id,name,email,password_hash) VALUES(:id,'Existing','existing@example.test',:password)"
            ),
            {"id": user, "password": encoded},
        )
        connection.execute(
            text(
                "INSERT INTO expense(id,owner_id,payer_id,title,amount,category,scope,split_method,expense_date) VALUES(:id,:u,:u,'Existing expense',10001,'Groceries','PERSONAL','EQUAL',CURRENT_DATE)"
            ),
            {"id": expense, "u": user},
        )
        connection.execute(
            text("INSERT INTO allocation VALUES(:id,:u,10001)"), {"id": expense, "u": user}
        )
    upgrade(migration_engine)
    with migration_engine.connect() as connection:
        assert connection.execute(text("SELECT amount FROM expense")).scalar_one() == 10001
        assert connection.execute(text("SELECT amount FROM allocation")).scalar_one() == 10001
        assert (
            connection.execute(text("SELECT password_hash FROM app_user")).scalar_one() == encoded
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM flyway_schema_history")).scalar_one()
            == version
        )


def test_schema_drift_rejected_without_changes(migration_engine):
    baseline(migration_engine, 3)
    with migration_engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX expense_household_date")
    with pytest.raises(RuntimeError, match="drift"):
        upgrade(migration_engine)
    assert "web_session" not in inspect(migration_engine).get_table_names()
    assert (
        str(
            next(
                c for c in inspect(migration_engine).get_columns("expense") if c["name"] == "amount"
            )["type"]
        )
        == "BIGINT"
    )


def test_unknown_schema_fails_closed(migration_engine):
    with migration_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE valuable_data(id INTEGER)")
    with pytest.raises(RuntimeError, match="nonempty"):
        upgrade(migration_engine)
    assert "valuable_data" in inspect(migration_engine).get_table_names()
