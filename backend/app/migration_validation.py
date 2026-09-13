"""Compare an adopted database with the preserved SQL, including integrity constraints."""

import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, text


def normalize_check(expression: str) -> str:
    # pg_dump/restore may distribute a text[] cast over varchar array literals.
    # Normalize only this equivalent representation, preserving every enum value/operator.
    def array_cast(match):
        return (
            match.group(0)
            .replace("::character varying::text", "::character varying")
            .replace("]::text[]", "]")
        )

    return re.sub(
        r"ANY \(ARRAY\[(?:'[^']*'::character varying(?:::text)?(?:, )?)+\](?:::text\[\])?\)",
        array_cast,
        expression,
    )


def apply_scripts(connection, scripts: list[Path]) -> None:
    for script in scripts:
        for statement in script.read_text(encoding="utf-8-sig").split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)


def schema_signature(connection, schema: str, tables: set[str]) -> dict:
    inspector = inspect(connection)
    result = {}
    for table in sorted(tables):
        result[table] = {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"], c["default"])
                for c in inspector.get_columns(table, schema=schema)
            ),
            "primary": inspector.get_pk_constraint(table, schema=schema)["constrained_columns"],
            "checks": sorted(
                normalize_check(c["sqltext"])
                for c in inspector.get_check_constraints(table, schema=schema)
            ),
            "unique": sorted(
                tuple(c["column_names"])
                for c in inspector.get_unique_constraints(table, schema=schema)
            ),
            "foreign": sorted(
                (tuple(c["constrained_columns"]), c["referred_table"], tuple(c["referred_columns"]))
                for c in inspector.get_foreign_keys(table, schema=schema)
            ),
            "indexes": sorted(
                (c["name"], tuple(c["column_names"]), c["unique"])
                for c in inspector.get_indexes(table, schema=schema)
            ),
        }
    return result


def verify_baseline(connection, scripts: list[Path], tables: set[str]) -> None:
    original_path = connection.execute(text("SHOW search_path")).scalar_one()
    original_schema = connection.execute(text("SELECT current_schema()")).scalar_one()
    actual = schema_signature(connection, original_schema, tables)
    # This schema is generated here, contains only reference DDL, and never contains user data.
    scratch = "ledger_reference_" + uuid4().hex
    connection.exec_driver_sql(f'CREATE SCHEMA "{scratch}"')
    connection.execute(text("SELECT set_config('search_path', :path, true)"), {"path": scratch})
    apply_scripts(connection, scripts)
    expected = schema_signature(connection, scratch, tables)
    connection.execute(
        text("SELECT set_config('search_path', :path, true)"), {"path": original_path}
    )
    connection.exec_driver_sql(f'DROP SCHEMA "{scratch}" CASCADE')
    if actual != expected:
        differing = sorted(table for table in tables if actual[table] != expected[table])
        raise RuntimeError("Flyway schema drift detected in: " + ", ".join(differing))
