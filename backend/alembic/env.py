from alembic import context
from app.config import Settings
from app.db import engine_for
from app.models import Base

if context.is_offline_mode():
    raise RuntimeError(
        "Migration requires a PostgreSQL connection to validate the existing schema."
    )


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, transactional_ddl=True)
    with context.begin_transaction():
        # Serialize simultaneous deployment migration runners, without affecting application queries.
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(724195382)")
        context.run_migrations()


provided = context.config.attributes.get("connection")
if provided is not None:
    migrate(provided)
else:
    engine = engine_for(Settings(), migration=True)
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()
