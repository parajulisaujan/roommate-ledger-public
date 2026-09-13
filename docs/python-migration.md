# Controlled backend migration

Status: Python is the authoritative backend. PostgreSQL/financial/privacy/account tests and all five existing browser contracts passed before the Spring source was archived under `reference/spring-backend`. No active Java service, Docker stage or CI job remains.

| Reference | Python replacement | Contract to preserve |
| --- | --- | --- |
| AuthController, SecurityConfig, AccountSecurityFilter | api/auth.py, security/session.py | BCrypt compatibility, HttpOnly JSESSIONID, session rotation/revocation, synchronizer CSRF, exact CORS origins |
| AccountService, EmailProvider | services/accounts.py | hashed single-use reset/verification links, password changes, deactivation, SMTP abstraction |
| HouseholdService | services/households.py | current-member authorization, inclusive historical membership, owner-only invitations |
| ExpenseService, Money | services/expenses.py, services/money.py | integer-cent JSON, Decimal calculations, stable Java UUID remainder ordering, immutable confirmed receipt items |
| FinanceService | services/finance.py | SQL-derived balances, settlement signs, private allocation analytics, shared-only household analytics |
| RecurringService | services/recurring.py | locked template recording, unique due date, immutable historical expense |
| ReceiptService, ReceiptImage | services/receipts.py | private draft, decoded bounded images, reconciliation, atomic locked confirmation |
| ReceiptExtractionProvider implementations | ai/receipts.py | bounded HTTP, strict structured data, unavailable/manual fallback, no AI-selected responsibility |
| ExportController | api/exports.py | authenticated scope, CSV formula protection and bounded export |
| Flyway V1–V3 | Alembic baseline and forward revisions | existing constraints/indexes/data and Flyway history retained |
| JDBC Store | SQLAlchemy 2 session and mapped schema | parameterized queries and request transactions |
| Spring tests | pytest on PostgreSQL plus existing Playwright contracts | authorization, money, concurrency, rollback, migration and browser behavior |

## Money and database adoption

The existing schema and API store amounts in cents. The migration preserves those units: `BIGINT` amount columns become `NUMERIC(14,0)` using an exact cast. Python uses `Decimal` for authoritative money and allocation arithmetic; only validated, integral results become JSON integer cents. Changing units to dollars would unnecessarily rewrite all reporting queries and stored draft contracts. No binary floating point enters financial arithmetic.

Java UUID natural order compares each signed 64-bit half, unlike Python UUID ordering. The Python split service explicitly preserves Java's ordering for cent ties.

Alembic recognizes only a verified Flyway V1–V3 schema (including upgrades from V1/V2), retains its history, and applies forward-only migrations. Unknown/partial schemas fail closed. Fresh databases execute the preserved baseline SQL before forward revisions. The actual restored V3 database copy retained all 249 existing rows in 12 tables; a financial conservation query found zero mismatches. Original databases and the backup remain intact. Existing in-memory Java sessions cannot transfer; users sign in again after cutover. Python sessions persist across process restarts, verified with the native runtime smoke test.

## Historical cutover gates

Before archiving Java and switching Docker/CI to Python, the project required
PostgreSQL migration, financial, privacy, account, upload and provider tests,
plus the existing frontend browser suite against FastAPI. Live services and
hosting were tracked separately from local results.

Those local gates passed: 114 pytest tests on PostgreSQL, fresh/repeated Alembic setup, V1/V2/V3 adoption, real-copy preservation, production frontend build and five browser tests. At the migration audit, Python Docker/Compose and CI were statically validated. Subsequent Docker runs passed, and the owner verified GitHub CI and private staging on 2026-09-11; see [verification](verification.md). The preserved Java reference last passed 59 tests on PostgreSQL and H2, plus the same five browser contracts.

## Operational adoption

1. Back up and restore into a separate database using native PostgreSQL tools.
2. Set the copy's connection environment, install locked Python dependencies, and run `uv run alembic upgrade head`.
3. For a copy named `ledger_adoption_*`, `uv run python scripts/verify_adoption.py` compares existing rows before/after migration and checks allocation conservation without logging record contents.
4. Verify login with existing credentials, private/shared history, balances and draft recovery. Stop Java writers and take a final backup before switching the original database connection.
5. Start FastAPI and rebuild the frontend for its API origin. Users sign in again; retain the backup under appropriate access controls.

The API preserves routes and integer-cent response semantics. Standard FastAPI validation is normalized to the existing HTTP 400 `{code,message}` model. Unsupported input fields are rejected; exact-origin CORS preflight denial uses the framework's HTTP 400. No frontend feature rewrite was needed; only shared fixture paths changed in browser tests.
