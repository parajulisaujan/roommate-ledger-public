# Verification

Commit references use the privacy-rewritten equivalents of the original tested
versions. Their source trees are identical; rewriting metadata did not deploy or
re-verify hosted staging.

## Portfolio documentation/demo check — 2026-09-12

The isolated local recorder built both app images and passed the demo UI flow,
including login, expenses, exact-cent splitting, reports and receipt confirmation.
It generated a 125.92-second WebM; eight sampled frames were reviewed. Optional
MP4 conversion was unavailable. Syntax, frontend lint/typecheck, Markdown
links/anchors and whitespace checks passed. No application code changed and the
full backend suite was not rerun for this documentation/demo cleanup. See the
[demo evidence](demo.md).

## Latest local hardening — 2026-09-12

Commit `6b314fe08daca21af6a8c2da57f61f8d8ce4ccaf` recorded **243 backend tests**
on isolated PostgreSQL 17, **14 frontend unit tests** and **5 browser E2E tests**
passing. Ruff, frontend lint/typecheck/build, both Docker builds and the isolated
TLS/startup/migration/restart smoke passed. Two existing test-client dependency
deprecation warnings remain. See the [hardening evidence](production-hardening.md#completion-evidence).

The code was merged into staging by `54848781fbe999a1394d46ff3fc3198885a0a888`,
but its hosted backend redeploy and smoke are still pending. These are local
results, not a new hosted verification or a new assertion about remote CI runs.
The [project summary](project-summary.md) records the exact resume checklist.

## Earlier verified hosted staging — 2026-09-11

The owner verified private staging on backend commit
`d8f6a5f74b1438f9d268c3b680346b6c5a2eb001`. GitHub CI, Vercel protected Preview,
the API proxy/key, Render build/startup/readiness, Neon PostgreSQL 17, expected
database identity, `verify-full` and client-side TLS, migrations and Mailtrap
STARTTLS passed. Registration, verification, login/session, households,
invitations, private/shared expenses, equal splits, balances and persistence
after refresh passed. AI is disabled with manual entry available. Staging remains
$0/month. See the [complete checklist](staging.md#verified-staging-checklist).

This is owner-reported hosted evidence, not a fresh provider inspection by the
documentation cleanup. It does not claim production delivery, live AI, live
password-reset/settlement testing, full hosted Playwright coverage or a production
backup/restore test.

Local checks for that backend commit: **198 pytest tests passed**, Ruff lint and
format checks passed, Docker build passed, and the isolated Docker TLS smoke
passed migrations, readiness and restart. Two existing test-client dependency
deprecation warnings remain. The later hardening results are recorded separately above and do not extend
that earlier hosted verification.

## Historical Python migration and local release checks — 2026-09-06/07

Tests use fictional data. The active backend is FastAPI/Python with PostgreSQL. This report supersedes the earlier Spring/H2 audit. The final regression checks passed after response-schema, persistent rate-limit, packaging and deployment updates. Java is archived under `reference/spring-backend` and is not required by the active application.

| Observed command/check | Result |
| --- | --- |
| `uv sync --project backend --frozen --extra dev` | Python 3.13.15 and 39 locked packages verified |
| `python -m pytest -q --tb=short` | Production-readiness final rerun: 132 passed in 79.85 seconds on PostgreSQL 17.11; two upstream test-client deprecation warnings |
| `uv build --project backend` | Source distribution and Python wheel built successfully |
| Isolated wheel installation/import | Passed in a separate virtual environment outside the source directory; installed package exposes 41 OpenAPI paths, including `/health` |
| `ruff check app tests alembic scripts` / `ruff format --check ...` | Passed |
| Fresh `alembic upgrade head` | Passed; repeated upgrade is idempotent |
| Flyway V1, V2 and V3 adoption tests | Passed, retaining identity/password hashes and exact amounts |
| Unknown/drifted schema tests | Passed; migration refuses unsafe adoption |
| Real `pg_dump` / `pg_restore` copy + `scripts/verify_adoption.py` | 12 existing tables, 249 rows unchanged; zero allocation mismatches |
| FastAPI runtime/readiness | Passed on migrated copy; final active API on port 8080 |
| `python scripts/runtime_smoke.py` | Real process restart retained session, expense and exact allocation; logout revoked access |
| Preserved Java account login | Original `$2a$` BCrypt account authenticated through FastAPI with unchanged identity/hash |
| Read-only ledger audit after production smoke | 115 expenses checked; 0 allocation mismatches; 0 expenses linked to unconfirmed receipts; additional regression records are fictional |
| `npm ci` / explicit `npm audit --json` | 435 packages installed; separate registry audit reports 0 vulnerabilities |
| `npm run lint` / `npm run typecheck` | Both passed |
| `npm run test` | 4 tests passed in one file |
| `npm run build` against FastAPI | Passed, Next.js 16.3.4 production build |
| `npm run test:e2e` against FastAPI | Production-readiness final rerun: 5 passed in 38.4 seconds, verification required and local SMTP enabled |
| `scripts/hosted_smoke.py` against local native services | Passed health/readiness, disposable registration/verification/login, exact split, private isolation, settlement, logout and account deactivation; no live AI flag enabled |
| Docker | VERIFIED: owner reported `node frontend/scripts/docker-smoke.mjs` passed on 2026-09-07; fresh migrations, healthy PostgreSQL/FastAPI/Next.js containers, two-user workflow, exact split, privacy, restart persistence, logout revocation and cleanup |
| GitHub Actions | Initially statically checked; later verified by the owner on 2026-09-11 as recorded above |
| Hosted services | See current staging evidence above; real recipient SMTP delivery, live AI and public production remain future work |

## Behavioral coverage

Money: $100/four, $100/three, selected $90/three, personal $40, fixed and 50/30/20 percentage splits, invalid totals, signed UUID tie ordering, and conservation across 1,000 amounts plus the maximum.

Privacy: household owner and roommate denied private expenses, outsider denied every household projection/export, own-allocation analytics, shared-only household totals, former-member loss of access with preserved obligations.

History: dated membership, immutable allocations, creator-only optimistic edits/deletion, independent recurring templates, duplicate due-date conflicts, sender-only settlements and zero-sum balances.

Receipts: decoded JPEG/PNG/WebP, corrupt/truncated/oversized/spoofed uploads, missing provider fallback, duplicate fingerprint privacy, processing guards, mixed item responsibility, reconciliation, proportional adjustments, immutable confirmed items, failed-second-item rollback and concurrent confirmation exactly once.

Accounts: registration/login/logout, CSRF, cookie security, session rotation/expiry, password compatibility, single-use/hashed/expired/superseded reset tokens, multi-session revocation, verification gate, password change, deactivation preservation, owner safeguards, shared-worker rate windows and exact-origin CORS.

Providers: strict required monetary types, unknown/duplicate/trailing fields, missing credentials, error statuses, refusal/incomplete/ambiguous OpenAI responses, bounded bodies and deadline covering stalled bodies. Transport is mocked; no live extraction success is fabricated.

The unchanged browser suite covers SMTP verification/reset, invitations, expense scopes/splits, history, recurring bills, analytics, receipts, settlement updates and privacy. Responsive checks retain 375, 430, 768, 1024 and 1440px. All five tests ran; the account test was not skipped.

## Migration evidence

The actual restored copy initially differed from fresh DDL only in PostgreSQL's equivalent representation of varchar-array-to-text casts after pg_dump restoration. The comparer now normalizes that narrow representation while retaining each enum value/operator, and still rejects missing indexes or other schema drift. Existing Flyway history is retained. Monetary units stay cents throughout BIGINT-to-NUMERIC conversion.

Original databases were not erased. The local migration test used a migrated copy, preserving the original Java database and a native backup for review. Hosted staging uses its separate Neon database. Existing Java sessions require reauthentication; Python sessions persist in PostgreSQL.

## Diagnostics and limits

Ignored logs: `.tools/final-pytest.log`, `.tools/final-python-install.log`, `.tools/final-python-package.log`, `.tools/final-wheel-install.log`, `.tools/python-adoption.log`, `.tools/python-restart.log`, `.tools/python-conservation.log`, `.tools/python-legacy-login.log`, `.tools/python-frontend-build.log`, `.tools/python-e2e-final.log`, plus frontend install/lint/typecheck/unit logs. Playwright reports/screenshots remain in ignored frontend output directories.

An oversized-upload test initially exceeded Windows' environment-variable limit because pytest generated an 8 MB parameter name. Short explicit case IDs fixed the test harness without weakening its upload assertion. The full rerun passed. Two deprecation warnings originate in the installed Starlette test-client compatibility layer, not application failures.

The 2026-09-07 Docker runtime result came from the owner's smoke-run report. The separate 2026-09-11 Docker TLS smoke was run locally as recorded above. Later CI and private staging evidence is above. Live AI accuracy, real recipient email deliverability and public production remain future work.

## Repository and release evidence

The initial publication review covered 177 candidate files and found no known
credential patterns, generated artifacts or files over 5 MiB in that snapshot.
Generated reports, caches, environment files, local tools, dumps and build outputs
are ignored. That historical pattern review is not a guarantee about every secret
format. The repository is now published and GitHub CI is verified.

Production-readiness work adds a validated environment name, bounded SMTP/receipt timeouts, positive configurable rate controls, explicit trusted-proxy CIDRs, a configurable Python launcher, server-generated request IDs, production Uvicorn error redaction, `/health`, CI package building/install, Docker logout coverage and guarded hosted smoke. Existing migrations and Decimal allocation logic are unchanged. The final full backend suite covers these changes, including production HTTPS subdomain cookies/CORS/CSRF, forwarded-IP spoofing rejection, SMTP timeout/failure token revocation and error redaction. Frontend install/lint/typecheck/unit/build and full browser regression were rerun.

Production-readiness evidence is retained in ignored `.tools/production-*` logs: `production-pytest-final.log`, `production-python-install.log`, `production-python-package.log`, `production-wheel-install.log`, `production-frontend-{install,lint,typecheck,unit,build}.log`, `production-npm-audit.json`, `production-e2e-final.log`, `production-hosted-smoke.log` and `production-conservation-final.log`. Packaging used cached build dependencies after network access was restricted. A browser run passed assertions but stalled during Windows teardown; running against an explicitly owned frontend with normal process permissions yielded a clean exit. Repeated local runs hit the configured registration limit as expected; only loopback test-client counters on the adoption copy were reset before rerunning, with production limits and assertions unchanged.

The successful local release checks observed `/health` and `/api/health` returning `{"status":"ok"}`; `/actuator/health/readiness` returns `{"status":"UP"}`. Staging/production topology, TLS/proxy requirements, database backup/restore/rotation, provider settings and exact external actions are in [release operations](release-operations.md). Current private staging evidence is recorded above; public production is a separate release gate.


## Documentation cleanup — 2026-09-11

Reviewed all 186 tracked paths for deployment status, secret patterns and generated
artifacts. Relative Markdown links and anchors resolve, documented commands were
checked against scripts/configuration, and `git diff --check` passed. Credential
patterns matched intentional fictional test fixtures and local smoke settings;
no suspected real provider credential or private key was found. This is a pattern
and source review, not a guarantee about every possible secret format.

No `.env`, local secret files, screenshots, generated logs or test reports are
tracked. `.env.example` is the intentional template; the two tracked `pixel.png`
files are test fixtures. Ignore checks cover local environment files, `.tools/`
secrets, Playwright output and Python caches. No application tests, startup
diagnostics or useful deployment scripts were removed. This cleanup changes only
Markdown documentation and performs no provider or database operations.

## Production audit — 2026-09-11

See [production-audit.md](production-audit.md) for the 15-area source review,
which recorded remaining production work and a startup logging defect. Provider controls,
production delivery, dependency advisories and load behavior were not independently
verified by this audit. The owner-reported staging results above remain valid.

One production entrypoint logging defect was reproduced in a subprocess using
fictional settings: an invalid SMTP field produced a traceback containing its
input. The fix adds a safe production startup boundary/server formatter. After
the fix, 80 relevant backend tests passed (4 database-dependent tests deliberately
deselected), including all staging startup tests and the new redaction tests.
Ruff passed; Markdown links/anchors and `git diff --check` passed. Two existing
test-client deprecation warnings remain. No frontend code changed, and no database
or provider operations were performed. The earlier full suite was not rerun.
