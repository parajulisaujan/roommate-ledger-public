"""Adopt verified Flyway history or initialize a clean database."""

from pathlib import Path

from sqlalchemy import inspect, text

from alembic import op
from app.migration_validation import apply_scripts, verify_baseline

revision = "0001_baseline"
down_revision = None


def upgrade():
    connection = op.get_bind()
    tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
    scripts = sorted((Path(__file__).parents[1] / "baseline").glob("V*.sql"))
    completed = 0
    if tables:
        if "flyway_schema_history" not in tables:
            raise RuntimeError(
                "Refusing to adopt a nonempty database without verified Flyway history."
            )
        history = connection.execute(
            text(
                "SELECT version,success FROM flyway_schema_history WHERE version IS NOT NULL ORDER BY installed_rank"
            )
        ).all()
        if not history or any(not row.success for row in history):
            raise RuntimeError("Flyway history is missing or contains failed migrations.")
        versions = [row.version for row in history]
        if versions not in [["1"], ["1", "2"], ["1", "2", "3"]]:
            raise RuntimeError(
                "Unsupported Flyway version sequence; review schema before adoption."
            )
        completed = len(versions)
        required = {
            "app_user",
            "household",
            "membership",
            "invitation",
            "receipt",
            "recurring_template",
            "expense",
            "allocation",
            "settlement",
            "audit_event",
        }
        if completed == 3:
            required.add("account_token")
        if tables != required | {"flyway_schema_history"}:
            raise RuntimeError("Existing tables differ from the expected Flyway schema.")
        verify_baseline(connection, scripts[:completed], required)
    apply_scripts(connection, scripts[completed:])


def downgrade():
    raise RuntimeError("Baseline downgrade is destructive. Restore a verified backup instead.")
