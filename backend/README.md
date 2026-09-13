# RoommateLedger API

Python 3.13 / FastAPI / SQLAlchemy 2 / Pydantic / PostgreSQL / Alembic.

From this directory, with database credentials exported:

```sh
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run python -m app.serve
```

Run `uv run pytest -q` against an isolated `TEST_DATABASE_URL` whose database name begins `ledger_pytest_`. Tests clear that database and create temporary migration databases. Never point tests at a development or production ledger. Run `uv run ruff check app tests alembic scripts` and `uv run ruff format --check app tests alembic scripts` for quality checks.

Money is Decimal cents in Python, NUMERIC cents in PostgreSQL and integer cents in JSON. Existing Flyway schema/data is adopted safely; no Java service is required. The source distribution includes Alembic and tests; the wheel contains application code, while deployment uses the repository/Docker image with migrations.

See the root README and `docs/` for account, provider, migration and deployment details. OpenAPI documentation is available at `/docs` in development.
