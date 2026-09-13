"""Verify a restored database copy before and after Alembic adoption; never log row data."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.config import Settings
from app.db import engine_for


def fingerprint(connection, tables):
    result = {}
    for table in tables:
        # Table names originate from PostgreSQL's schema inspector, quoted by its dialect.
        quoted = connection.dialect.identifier_preparer.quote(table)
        rows = connection.execute(text("SELECT * FROM " + quoted)).mappings()
        encoded = sorted(
            json.dumps(
                dict(row),
                sort_keys=True,
                default=lambda value: (
                    int(value)
                    if isinstance(value, Decimal) and value == value.to_integral_value()
                    else str(value)
                ),
            )
            for row in rows
        )
        result[table] = (len(encoded), hashlib.sha256("\n".join(encoded).encode()).hexdigest())
    return result


def main():
    settings = Settings()
    if not settings.sqlalchemy_url.database.startswith("ledger_adoption_"):
        raise RuntimeError(
            "This verification command requires an isolated ledger_adoption_* database copy."
        )
    engine = engine_for(settings)
    tables = inspect(engine).get_table_names()
    with engine.connect() as connection:
        before = fingerprint(connection, tables)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        after = fingerprint(connection, tables)
        if before != after:
            raise RuntimeError("Existing row contents changed during adoption.")
        mismatches = connection.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT e.id FROM expense e LEFT JOIN allocation a ON a.expense_id=e.id GROUP BY e.id,e.amount HAVING e.amount<>COALESCE(SUM(a.amount),0)) bad"
            )
        ).scalar_one()
        if mismatches:
            raise RuntimeError("Financial allocation mismatch.")
    print(
        json.dumps(
            {
                "existing_tables_unchanged": len(tables),
                "existing_rows_unchanged": sum(v[0] for v in before.values()),
                "allocation_mismatches": mismatches,
                "alembic": "head",
            }
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
