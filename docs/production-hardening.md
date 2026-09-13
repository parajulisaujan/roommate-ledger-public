# Repository production hardening — 2026-09-12

This phase changes repository code and local tests only. No production resource,
DNS record, provider setting, credential, subscription or trial was changed.
Private staging remains Vercel protected Preview / Render Free / Neon Free /
Mailtrap Sandbox. The production launch blockers remain in the
[audit](production-audit.md). The hardening code is merged into staging, but its
latest hosted backend redeploy/smoke remains pending. See the
[resume checklist](project-summary.md#exact-next-steps-when-development-resumes).

## Financial request retries (H2)

`POST /api/expenses` and `POST /api/households/{id}/settlements` accept
`Idempotency-Key`: 16–128 ASCII letters, digits, underscores or hyphens. Generate a
random UUID for each intentional creation. The header is **required when
`APP_ENV=production`**; missing keys return 400. Development and staging retain
unkeyed compatibility, which is explicitly not retry-safe. Both first-party
creation forms now send keys. Existing response shapes remain unchanged,
including the settlement endpoint's JSON `null` result.

Keys are scoped to the authenticated user and operation. Settlement fingerprints
include the household ID. The fingerprint is SHA-256 of sorted JSON after schema
parsing/defaults; array order remains significant. Keys are hashed before storage.
Client record IDs never authorize access. Authentication, active-account and
current household membership checks run before replay. Loss of membership or
account access denies replay, including a formerly successful request.

A PostgreSQL transaction advisory lock serializes a key's concurrent submissions.
The response snapshot and expense/allocations/settlement/audit event commit in the
same request transaction. Rollback removes both. The same key and fingerprint
return the original snapshot, even after later edits. Different details return
409; failed validation does not reserve a key. Exact-cent calculations and the
existing financial transaction remain intact. These are ledger records, not
money transfers or proof that a recipient received payment.

Snapshots can be replayed for **30 days** from the original transaction. Expired
keys return 409 and are never reusable. A bounded maintenance command clears up
to 500 expired response snapshots per invocation while retaining compact
user/operation/key/request hashes and expiration timestamps as tombstones:

```sh
python -m app.maintenance
```

Run it with runtime credentials injected privately. Schedule enough invocations
to keep up with expiry; scheduling and storage monitoring remain operator work
(M4/H4). Snapshot deletion occurs when maintenance runs, not automatically at the
30-day instant. Do not delete tombstones during ordinary cleanup: a delayed retry
could otherwise recreate a financial record. Account erasure needs a separate
retention design and must never reassign a former account UUID.

The browser retains a key through errors for the form's lifetime and rotates it
after success. It does not persist financial form content or keys to browser
storage. After a lost response, retry the original details in that form. If
details were changed, a 409 requires reconciliation rather than a fresh key.
After closing/reloading the page, inspect the ledger before submitting again.
Clients outside the UI must retain their key until the outcome is reconciled.
Settlement correction remains a product limitation (M5); no silent reversal or
new balance semantics were introduced. Recurring recording is a separate
operation and has not gained generic request idempotency.

## Membership transaction cutoff (H5)

Financial writes take a shared transaction advisory lock before authorization.
Household creation, joining, removal and account deactivation take the same lock
exclusively before their membership checks/changes. Recurring operations acquire
the gate before their template lock, and expense edits before their expense lock.
The gate is held to commit or rollback, not merely until validation returns.

If a financial writer acquires the gate first, its transaction may finish using
the membership state before the change. If removal/deactivation commits first,
the later writer fails authorization; if joining commits first, the new member
can write. Date-based historical eligibility remains inclusive and unchanged.
This is a transaction cutoff, not a promise that removal invalidates an already
committed expense or that historical participants disappear from balances.

One gate across households is deliberately conservative for this small app:
writers run concurrently, but a membership change waits for all current financial
writers. It avoids complicated multi-household deactivation lock ordering. Long
transactions can delay membership changes or hit the lock timeout. Load-test
before replacing it with per-household locks; keep the same cutoff and consistent
lock order across receipts, recurring templates and account deactivation.

Tests observe an actual ungranted PostgreSQL advisory lock and exercise both
orderings for removal, deactivation and joining versus expenses and settlements.
The original audit described an untested boundary; no historical privacy bypass
or corrupted balance is claimed from that observation alone.

## Session and write budgets (H4/B6)

New anonymous sessions consume `RATE_SESSION_CREATION` (default 120 per
`RATE_WINDOW_SECONDS`, default 900) for the verified peer identity. Reusing a
valid session's CSRF token does not consume that allocation budget. The existing
trusted-hop parser remains unchanged; empty trust uses the actual socket peer.
The protected staging proxy therefore shares this budget among visitors.
Changing `X-Forwarded-For` cannot evade it when the peer is not trusted.

`ANONYMOUS_SESSION_LIMIT` (default 10,000, range 1–100,000) bounds anonymous rows
after expired-session cleanup. PostgreSQL serializes capacity checks and inserts
across workers. Capacity or rate exhaustion returns 429; existing sessions still
work. An attacker can exhaust a shared budget and deny new sessions: these are
database safety limits, not adequate public edge protection.

Authenticated POSTs also consume `RATE_WRITES` (default 300 per rate window),
including household creation, manual drafts and financial creation. Specific
login/account/invitation/extraction budgets still apply. Failed attempts count
through independently committed counters. Tune limits for legitimate shared-peer
traffic. Per-account lifetime storage quotas, edge connection/request limits,
retention scheduling and load evidence remain open; no broad proxy CIDRs were
added and no forwarding claim became trusted.

## Database timeout strategy (H9)

`engine_for` supplies actual libpq connection parameters, not unused environment
settings. Defaults are `connect_timeout=5` seconds and PostgreSQL connection
`options` setting `statement_timeout=15000` and `lock_timeout=5000` milliseconds.
Runtime and rate-counter pools use these defaults. Migration engines instead
default to a 300,000 ms statement limit and 10,000 ms lock limit. Pool checkout
still has a separate five-second timeout.

These bound connection attempts, individual database statements and lock waits.
They do not impose a whole HTTP request deadline, SMTP deadline, total transaction
lifetime or universal five-second DNS/network deadline. No idle-transaction
timeout was added: receipt/SMTP operations may hold an otherwise idle transaction.
The existing external-call limits still apply; outbox/transaction restructuring
needs a separate design and tests.

Operators can explicitly supply `connect_timeout` and `options` in the injected
database connection configuration. Explicit URL values take precedence. Providing
`options` replaces the entire default options string, so include both timeout
settings when overriding and verify with `SHOW statement_timeout` and
`SHOW lock_timeout`. Never paste the credential-bearing URL into a command or log.
Role/database defaults can be superseded by startup options; review them together.
Test migration duration on an isolated restored copy and tune the release
connection separately. Do not set `sslmode=require` or remove CA/hostname checks.

The APIs are documented by [Psycopg 3](https://www.psycopg.org/psycopg3/docs/api/connections.html),
[libpq connection parameters](https://www.postgresql.org/docs/17/libpq-connect.html),
and [PostgreSQL timeout settings](https://www.postgresql.org/docs/17/runtime-config-client.html).
Integration tests check live parameter values, interruption of a sleeping query
and a blocked lock, and transaction recovery after rollback. Capacity remains
unproven: each runtime process can use 10 ledger plus 2 rate connections; reserve
additional migration/maintenance capacity before sizing workers or replicas.

## Invitations, build artifacts and release logs (H8/H6)

First-party UI, smoke scripts and browser tests accept invitations through
`POST /api/invitations/accept` with a JSON `token` field. The legacy URL endpoint
is deprecated for compatibility, so ingress must still redact it and callers
must migrate. Never capture request bodies, cookies, idempotency keys, account
links or invitation responses in access logs.

Automatic Playwright failure traces/screenshots are off. Existing browser tests
can still explicitly write fictional local screenshots to ignored test-results. CI no longer uploads raw backend
logs, browser reports or test-results directories on failure. Test runners can
still report assertion values; use only fictional local data and restrict CI log
access. Hosted diagnostics and provider access logging remain a separate review.
The release wrapper prints fixed success/failure labels and suppresses rejected
settings, provider exceptions and third-party migration output. Do not bypass it
with raw Alembic CLI commands in shared production logs.

Docker base images and CI Actions are pinned to resolved immutable digests/SHAs
on their existing version lines. Python/npm lockfiles and package versions were
not upgraded. Apt packages, build-isolation dependencies and downloaded runtimes
are not fully hermetic. Weekly Dependabot configuration covers Actions, uv, npm
and Docker; review PRs and rerun full checks, never auto-merge dependency changes.
[GitHub documents uv ecosystem support](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories).
Owner activation/operation of update automation, current advisory/secret scanning
and provenance review remain open. Pinning is not evidence of vulnerability-free
dependencies, and this phase did not perform a comprehensive CVE review.

## Controlled release and restricted runtime (B7)

The Docker default is now `python -m app.start`. With `APP_ENV=production` it
starts the sanitized server **without migrating**. Development retains automatic
migrations; staging delegates to its existing restrictive staging launcher.
Render's explicit staging command still works. Readiness expects
`0003_request_idempotency`. The new migration adds the request-receipt table and
expiry index; it does not rewrite financial rows or edit old revisions.

Use the same reviewed image for an explicitly approved release job. Inject a
separate migration role privately, mount the readable CA bundle at the documented
path, and supply the expected database name independently of its connection URL:

```sh
# Fictional database name only; credentials are already injected privately.
python -m app.release --expected-database ledger_production_example
python -m app.release --expected-database ledger_production_example --apply
```

The first command only verifies production settings, the expected non-staging
database, `sslmode=verify-full`, the expected CA path/readability, connection,
database identity and client-side libpq TLS state. It does not certify backups,
pending schema compatibility or DDL privileges. Only `--apply` runs Alembic under
its existing transaction advisory migration lock. Failure exits nonzero with a
fixed label. An inspection-unavailable TLS state fails closed.

Before approval: record the exact image/commit, inspect the migration, rehearse on
an isolated restored copy, verify a recoverable backup, and pause old writers.
After migration: deploy the same artifact with runtime credentials, verify
readiness, then run authorized disposable-account smoke tests before traffic.
Do not run destructive downgrades; use a reviewed forward fix or isolated
restore/cutover. Retaining the old image alone is not a database rollback plan.

The runtime role must not own the database/schema/tables, inherit the migration
role, create roles/databases, or be superuser. Grant schema USAGE and required
SELECT/INSERT/UPDATE/DELETE on application tables (including request receipts and
abuse counters), plus **SELECT only** on `alembic_version`. Remove public schema
CREATE privileges, review PUBLIC grants, and grant new-table privileges explicitly
after each migration. UUID records require no sequence grant. Keep DDL ownership
with the release role. Restrict network access and credentials separately.

A local PostgreSQL test runs financial creation/idempotency with a temporary
restricted role and verifies schema creation and revision mutation are denied.
No production roles were created. Job scheduling, approval, least-privilege grants,
backup/restore and hosted smoke are still B7 launch gates.

## Production ingress design to implement and verify (B1/B6)

Keep the staging Preview guard unchanged. It deliberately returns 404 for a
protected non-Preview Vercel deployment. Production remains blocked until a
separate explicit access mode has reviewed tests; do not solve promotion failure
by disabling `DEPLOYMENT_PROXY_REQUIRED`.

The target is a public HTTPS frontend with a same-origin `/api` server proxy and a
backend reachable only through controlled ingress. The proxy must replace the
origin credential, remove client authorization/forwarding claims, preserve CSRF
and idempotency headers, and send the credential upstream only. Direct backend
requests must fail the origin gate except deliberately minimal health probes.
Keep cookies host-only/Secure/HttpOnly, use SameSite=Lax and empty CORS for this
topology. Backend origin credentials are additional to user authentication.

| Boundary | Required evidence before implementation/deployment |
| --- | --- |
| Frontend deployment mode | An explicit production mode distinct from staging, with public HTML and protected API proxy tests; staging non-Preview denial must still pass. |
| Backend origin | Exact HTTPS target, verified certificate/hostname, private ingress or proven origin gate, no key in HTML, client bundles, responses or logs. |
| Visitor abuse controls | Edge connection/body/rate limits based on an actual trusted identity; keep backend aggregate limits until a controlled-hop identity mechanism is proven. |
| Proxy trust | No broad/shared CIDRs. Never trust an arbitrary visitor forwarding header or assume a provider supplies a documented identity header. |
| Failure cases | Missing/wrong key, direct-origin bypass, spoofed forwarding, duplicate financial submission, cookie/CSRF continuity, uploads and streaming/timeout limits. |

This is an implementation contract, not a claim that any free provider exposes all
required features. No new unused ingress configuration flags or provider resources
were added. Resolve hosting capability and cost constraints with the owner before
choosing an implementation.

## Completion evidence

- Backend: **243 passed**, no failures/skips, against isolated PostgreSQL 17.
  Two existing dependency deprecation warnings remain.
- Frontend: lint, TypeScript, **14 unit tests**, production build and **5 browser
  E2E tests passed** using only fictional users and a loopback SMTP sink.
- Browser prerequisites: installed the Chromium build required by the existing
  lockfile. Earlier missing-browser failures were environmental; repeated attempts
  exhausted the local registration budget, so only isolated test counters were
  reset before the successful complete run. Production limits were not changed.
- Both pinned Docker images built. The frontend build's automatic npm audit
  reported zero vulnerabilities; this is not a backend/container advisory audit.
- Isolated staging TLS Docker smoke: CA presence, six sanitized failure cases,
  successful TLS/migration/readiness and restart passed. No provider was contacted.
- Ruff lint/format, Markdown links/UTF-8 and `git diff --check` passed.
- Completed: H2/H5. Operational and provider-dependent findings remain before public production; partial safeguards are documented separately.
  H4/H6/H8/H9 and B7 are partially improved. B1/B6 have an explicit design contract
  and preserved staging-guard tests, but remain blocked on production ingress.
- Added migration: **0003_request_idempotency**. No old revision or package lockfile
  was edited. No production resources, settings, secrets or paid services changed.

## Changed files

- [.github/dependabot.yml](../.github/dependabot.yml)
- [.github/workflows/ci.yml](../.github/workflows/ci.yml)
- [backend/Dockerfile](../backend/Dockerfile)
- [backend/alembic/env.py](../backend/alembic/env.py)
- [backend/alembic/versions/0003_request_idempotency.py](../backend/alembic/versions/0003_request_idempotency.py)
- [backend/app/api/ledger.py](../backend/app/api/ledger.py)
- [backend/app/config.py](../backend/app/config.py)
- [backend/app/db.py](../backend/app/db.py)
- [backend/app/main.py](../backend/app/main.py)
- [backend/app/maintenance.py](../backend/app/maintenance.py)
- [backend/app/release.py](../backend/app/release.py)
- [backend/app/security/session.py](../backend/app/security/session.py)
- [backend/app/services/accounts.py](../backend/app/services/accounts.py)
- [backend/app/services/expenses.py](../backend/app/services/expenses.py)
- [backend/app/services/finance.py](../backend/app/services/finance.py)
- [backend/app/services/households.py](../backend/app/services/households.py)
- [backend/app/services/idempotency.py](../backend/app/services/idempotency.py)
- [backend/app/services/recurring.py](../backend/app/services/recurring.py)
- [backend/app/services/write_guard.py](../backend/app/services/write_guard.py)
- [backend/app/staging_start.py](../backend/app/staging_start.py)
- [backend/app/start.py](../backend/app/start.py)
- [backend/scripts/hosted_smoke.py](../backend/scripts/hosted_smoke.py)
- [backend/tests/conftest.py](../backend/tests/conftest.py)
- [backend/tests/test_ledger.py](../backend/tests/test_ledger.py)
- [backend/tests/test_production_hardening.py](../backend/tests/test_production_hardening.py)
- [backend/tests/test_release.py](../backend/tests/test_release.py)
- [backend/tests/test_runtime_role.py](../backend/tests/test_runtime_role.py)
- [docs/production-audit.md](../docs/production-audit.md)
- [docs/production-hardening.md](../docs/production-hardening.md)
- [docs/production-runbook.md](../docs/production-runbook.md)
- [docs/release-operations.md](../docs/release-operations.md)
- [frontend/Dockerfile](../frontend/Dockerfile)
- [frontend/e2e/completion.spec.ts](../frontend/e2e/completion.spec.ts)
- [frontend/e2e/deployment-smoke.spec.ts](../frontend/e2e/deployment-smoke.spec.ts)
- [frontend/e2e/privacy.spec.ts](../frontend/e2e/privacy.spec.ts)
- [frontend/playwright.config.ts](../frontend/playwright.config.ts)
- [frontend/scripts/docker-smoke.mjs](../frontend/scripts/docker-smoke.mjs)
- [frontend/src/components/BalancesView.tsx](../frontend/src/components/BalancesView.tsx)
- [frontend/src/components/ExpenseForm.tsx](../frontend/src/components/ExpenseForm.tsx)
- [frontend/src/components/HouseholdView.tsx](../frontend/src/components/HouseholdView.tsx)
- [frontend/src/lib/submission.test.ts](../frontend/src/lib/submission.test.ts)
- [frontend/src/lib/submission.ts](../frontend/src/lib/submission.ts)
- [frontend/src/proxy.test.ts](../frontend/src/proxy.test.ts)
