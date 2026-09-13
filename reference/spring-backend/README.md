# Retired Spring behavioral reference

This directory preserves the Java/Spring implementation and tests used to verify the controlled Python migration. It is **not part of the active application, Docker Compose stack or CI pipeline**. Normal development and deployment require no Java or Maven.

Before migration, this reference passed 59 tests on PostgreSQL and H2 plus the five browser acceptance tests. The Python replacement passed 114 pytest tests on PostgreSQL and the same five browser contracts before archival. See `../../docs/python-migration.md` and `../../docs/verification.md`.

The historical Flyway SQL remains here for review. The active Alembic baseline retains identical SQL under `../../backend/alembic/baseline`; future schema changes belong in Alembic. Do not run the retired service against a database after Python migration or enable both backends as concurrent writers.
