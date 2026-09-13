# Release operations

Current rollout: [private staging verified on 2026-09-11](staging.md), based on
the owner's live checks. GitHub CI, Vercel Preview, Render Free, Neon PostgreSQL 17
and Mailtrap Sandbox passed. Public production and real recipient email delivery
remain future work; see the [production readiness plan](production-runbook.md).
The latest hardening code still needs a hosted backend redeploy/smoke; this
earlier result does not verify that newer code. See the [resume checklist](project-summary.md#exact-next-steps-when-development-resumes).
No paid provisioning, trials or credit-card entry is authorized.

## Environments and browser topology

Use separate projects, PostgreSQL databases/roles, SMTP credentials and AI keys for development, staging and production. `APP_ENV=staging` enforces the same HTTPS, Secure-cookie and email verification requirements as production. Misspelled environments fail startup. Release flow: feature branch → CI → staging migration → staging smoke/E2E → production backup/migration → production smoke. Never deploy the fictional test inbox publicly.

The shipped frontend calls relative `/api` URLs. For `https://app.example.com` and `https://api.example.com`, set `FRONTEND_URL=https://app.example.com` and build-time `API_INTERNAL_URL=https://api.example.com`. Next.js proxies browser calls to the API, keeping the browser session same-origin on app.example.com. Prefer private API networking when supported. Rebuild when changing the API target. `BACKEND_URL` is not an application setting; its name here is `API_INTERNAL_URL`.

Cookies are HttpOnly, Secure in staging/production, Path=/, host-only (no Domain attribute), SameSite=Lax. Do not widen Domain. A separate client calling the API directly must use credentials, obtain CSRF from that API origin, configure exact `CORS_ALLOWED_ORIGINS=https://app.example.com`, and permit the API in its CSP. HTTPS sibling subdomains are same-site; unrelated domains introduce third-party-cookie limitations and are not the default frontend topology. The existing frontend continues using its same-origin proxy.

Leave CORS empty for the shipped proxy. Production rejects HTTP CORS origins and wildcards. Opaque random session tokens are hashed in PostgreSQL: no JWT/session signing secret is applicable. `SESSION_TIMEOUT_SECONDS` controls idle expiry; logout deletes the session and cookie.

## Proxy, environment and providers

Use `python -m app.serve`, which disables implicit Uvicorn forwarded-header trust. `TRUSTED_PROXY_CIDRS` defaults empty, so limits use the socket peer. Configure only known proxy IPs/CIDRs and restrict backend ingress to those proxies. Every trusted proxy must overwrite untrusted incoming X-Forwarded-For or append the actual socket peer. The application walks right-to-left to the first untrusted address. Never trust all addresses or a shared network with uncontrolled peers. On a Next.js/ingress chain, configure every controlled proxy hop. Otherwise retain empty trust and enforce per-client edge limits; anonymous application limits will aggregate users behind the proxy.

TLS terminates at ingress. Secure cookies are explicit and do not depend on forwarded scheme. Preserve cookies/X-CSRF-TOKEN, allow 9 MiB bodies and an upstream timeout longer than extraction plus database overhead. Redact tokens/query strings from ingress logs. PostgreSQL rate counters persist across workers/restarts and count failures; they expire automatically. Existing rate variables are listed in `.env.example` and Compose. The newer
`RATE_SESSION_CREATION`, `RATE_WRITES` and `ANONYMOUS_SESSION_LIMIT` settings
use application defaults unless explicitly injected; see the [budget contract](production-hardening.md#session-and-write-budgets-h4b6).

`.env.example` contains local defaults/placeholders. Python does not automatically load it: inject environment variables through secret storage. Compose loads the root `.env` for interpolation. Required production settings:

| Variables | Purpose |
| --- | --- |
| `DATABASE_URL` | Managed PostgreSQL URL with verified TLS; example `postgresql+psycopg://db.example.com:5432/ledger?sslmode=verify-full&sslrootcert=/run/secrets/db-ca.pem` |
| `DATABASE_USER`, `DATABASE_PASSWORD` | Dedicated role and secret; embedded URL credentials take precedence. `DB_USERNAME`/`DB_PASSWORD` aliases are not used |
| `APP_ENV`, `FRONTEND_URL` | `production` or `staging`; exact public HTTPS frontend origin |
| `API_INTERNAL_URL` | Reachable API origin, required at frontend build time |
| `DEPLOYMENT_PROXY_REQUIRED`, `DEPLOYMENT_PROXY_KEY` | Protected API ingress and a new production-only key; review the Preview-only frontend guard in the production plan before launch |
| `COOKIE_SECURE`, `COOKIE_SAME_SITE` | `true`, `lax` |
| `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_CIDRS` | Deliberate origin/proxy policy above |
| `HOST`, `PORT` | Backend bind address/port, default 0.0.0.0:8080; Compose keeps internal 8080 |
| `SMTP_HOST`, `SMTP_PORT` | Provider STARTTLS submission host/port, typically 587 |
| `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | Provider credential and verified sender |
| `SMTP_STARTTLS`, `EMAIL_VERIFICATION_REQUIRED` | Both `true` |
| `SMTP_TIMEOUT_SECONDS` | Per socket-operation timeout, 1–30 seconds; default 5 |
| `RECEIPT_PROVIDER` | `adapter` or `openai`; missing credentials retain manual entry |
| `RECEIPT_PROVIDER_URL`, `RECEIPT_PROVIDER_API_KEY` | HTTPS adapter URL and backend-only key |
| `OPENAI_API_KEY`, `OPENAI_RECEIPT_MODEL` | Backend-only key and explicit supported vision/structured-output model |
| `RECEIPT_TIMEOUT_SECONDS` | Total extraction deadline, 1–120 seconds; default 45 |

SMTP verifies TLS certificates and supports configurable sender, verification/reset and household invitations. Submission uses STARTTLS, not implicit TLS port 465. Failures invalidate undelivered account tokens and log redacted warnings; user resend is supported. Tokens expire, are single-use and are superseded by resend. Invitation failure offers code sharing. No automatic SMTP retry is added. Real provider sender/SPF/DKIM/DMARC setup and deliverability are external checks.

AI accepts decoded JPEG/PNG/WebP at most 8 MiB/24 megapixels. Responses are limited to 256 KiB and parsed strictly. There are no automatic paid retries. Output stays NEEDS_REVIEW with manual recovery; AI neither assigns participants nor confirms transactions. Only Decimal service logic computes allocations. Original images are not persisted. Live transport success is separate from human verification of transcription accuracy.

## Production audit follow-up

The [production audit](production-audit.md) records the remaining launch blockers.
The normal `python -m app.serve` entrypoint now suppresses raw startup inputs and
server error text when `APP_ENV=production`; failed startup exits nonzero.
Use application request references and health/alert signals for operations.
Direct `uvicorn` invocation and separate `alembic` commands do not inherit that
entrypoint's safe error boundary. Review the release runner and provider log
redaction before collecting production migration logs. Never dump environment
variables to troubleshoot a failed launch.

Keep production release migrations separate from restricted runtime access where
supported. Require an approved artifact, backup, database identity/verified TLS
check, migration result, readiness and production smoke before opening traffic.
The staging launcher is deliberately not a production runner. General Settings
does not itself enforce the staging database TLS/identity restrictions.

First-party invitation codes now travel in a JSON body; browser capture and raw CI
failure-artifact uploads are off. Review deprecated invitation URL-path redaction
and provider/CI log access; use only
fictional test records in CI. Verify branch protections and manual release approval
with the owner instead of assuming they follow from a passing workflow.

## Observability

`/health` and `/api/health` check the process. `/actuator/health/readiness` checks PostgreSQL and the expected Alembic revision, returning only UP/DOWN. Responses include a server-generated X-Request-ID; uncaught errors log the same reference and exception class without payloads or credentials. Production JSON logs can feed any host collector. No monitoring DSN/vendor SDK is implemented; a collector and frontend `roommateledger:error` event provide integration boundaries without requiring a vendor. Alert on readiness, 5xx, email failures, rate-limit spikes, pool pressure and backup failures. Never capture cookies, passwords, financial form payloads or receipt contents.

## Database operations

Each process allows 5 steady ledger connections plus 5 overflow and 2 independent rate connections: maximum 12, plus migration/maintenance capacity. Size PostgreSQL before increasing replicas/workers. Pool wait is 5 seconds. Runtime libpq connect timeout defaults to 5 seconds, statement timeout to 15 seconds and lock timeout to 5 seconds; migration defaults are 5/300/10 seconds respectively. Explicit connection options take precedence; review the [timeout strategy](production-hardening.md#database-timeout-strategy-h9). Use private networking and `sslmode=verify-full` with the managed CA and matching DNS hostname. Never disable certificate verification to work around a configuration error.

From `backend`, with environment secrets injected:

```sh
uv sync --frozen --no-dev
# Migration job: approved image and separately injected DDL credentials.
uv run python -m app.release --expected-database ledger_production_example
uv run python -m app.release --expected-database ledger_production_example --apply
# Runtime deployment: separately injected restricted runtime credentials.
uv run python -m app.start
```

Production Docker startup does not migrate. The explicit release command uses an advisory migration lock and a safe output boundary; see the [release/role contract](production-hardening.md#controlled-release-and-restricted-runtime-b7). Development and guarded staging retain startup migration. New revision `0003_request_idempotency` adds request receipts and an expiry index; old revisions are unchanged. Never run reset/clean/TRUNCATE/downgrade against production. Review schema compatibility before code rollback; use a forward fix or separately tested isolated restore/cutover.

Use PostgreSQL 17 tools. Set `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE=verify-full`, `PGSSLROOTCERT` and a private `PGPASSFILE` outside the repo (0600 on Unix, restrictive ACL on Windows). Avoid password URLs in commands/history. Backups must have encrypted storage, restricted access, scheduled retention and monitored restore tests; evaluate recovery options against those objectives in a separate production plan; this cleanup does not authorize upgrades.

```sh
pg_dump --format=custom --no-owner --no-acl --file=/secure-backups/ledger-release.dump
pg_restore --list /secure-backups/ledger-release.dump
# Set PGDATABASE to a newly provisioned EMPTY ISOLATED restore database first.
pg_restore --exit-on-error --no-owner --no-acl --dbname="$PGDATABASE" /secure-backups/ledger-release.dump
```

Do not use `--clean` or overwrite a live database. Test the restore with a separate application instance: inspect Alembic current/head, readiness and `uv run python scripts/audit_ledger.py`, and compare original/restored table counts through authorized read-only access. Keep the source untouched. The adoption verifier deliberately accepts only `ledger_adoption_*` copies. Repeat adoption if migration code changes, not for unrelated release configuration.

Rotate database credentials by provisioning a replacement role with equivalent least-privilege grants, updating staging then production secrets, restarting pools and checking readiness/smoke before revoking the old role. Rotate SMTP/AI credentials the same way. Never commit secrets as part of rotation.

## Safe hosted smoke

Set `SMOKE_FRONTEND_URL` and `SMOKE_BACKEND_URL` to exact origins reachable by the operator. HTTPS is required except loopback. From `backend`, the default is read-only:

```sh
uv run python scripts/hosted_smoke.py
```

For full disposable-account checks, explicitly set `SMOKE_ALLOW_MUTATIONS=true` and `SMOKE_EMAIL_DOMAIN` to a dedicated catch-all email domain you control. Random account addresses/passwords are generated; existing users cannot be selected. Enter each emailed token privately when prompted (the value after `#verify=`). The script verifies login, a new household, exact $50/$50 allocation, private isolation, a $50 settlement, zero balances and logout. Cleanup deactivates only newly created accounts, member before owner, including on failures. Fictional financial history remains by design. Cleanup failures identify disposable account addresses for operator follow-up; avoid interrupting cleanup.

For loopback acceptance only, `SMOKE_LOCAL_MAILBOX_URL=http://127.0.0.1:8025` and `SMOKE_EMAIL_DOMAIN=example.test` read actual locally delivered tokens. That mode rejects hosted frontend targets. No hosted verification bypass exists.

Live AI also requires `SMOKE_LIVE_AI=true`, `LIVE_RECEIPT_FILE` pointing to an authorized image, and credentials/model already configured on the backend. The script checks provider availability and NEEDS_REVIEW, never confirms the receipt. Without the flag no image is sent. Human review must assess accuracy afterward. Do not copy backend keys into the smoke runner.

Run full browser E2E only on isolated staging with its test inbox. For Docker, ports 5432/3000 must be free: `node frontend/scripts/docker-smoke.mjs` creates a uniquely named project, builds from fresh storage, waits for health, checks split/privacy/login/restart/logout, and runs `down -v` only on its own project. Never run an unqualified `docker compose down -v` on an existing ledger. The owner reported the complete Docker smoke passed on 2026-09-07; runtime verification is complete for that tested configuration.

## Future production setup (owner actions only)

Use separate production resources after the readiness plan is complete. This is
not authorization to provision services or pay for infrastructure.

| Service | Create/click and settings | Non-secret values to share | What happens next |
| --- | --- | --- | --- |
| GitHub | Existing repository and CI are verified; keep release checks green | Approved commit SHA | Review before any production release |
| Hosting/PostgreSQL | Next.js host, backend Docker service, separate staging/production PostgreSQL 17 with private networking and verified TLS | Project/service IDs and non-secret hostnames; inject database secrets/CA privately | Create a separate production deployment only after its readiness gates pass; never promote staging resources |
| DNS/HTTPS | App/API subdomains, certificates, ingress restrictions and trusted proxies | Domains, DNS authorization and actual proxy CIDRs | Configure origins/build target and verify TLS/cookies/CSRF |
| SMTP | STARTTLS provider credential, verified sender, SPF/DKIM/DMARC and disposable smoke inbox | Host/port/sender; inject username/password privately | Verify real verification/reset/invitation delivery and hosted smoke |
| Optional AI | Provider project/key and explicit vision model, or HTTPS adapter | Provider/model/endpoint; inject key privately | Run opt-in real receipt smoke and inspect draft accuracy |

Never paste secrets into chat, issues, PRs, committed files, frontend environment variables or screenshots. Use the host secret manager or a local ignored environment file loaded privately into the process. Share variable names and confirmation that they are installed. Account access, payment, visibility and DNS require account-owner authorization. No public deployment is complete until the actual hosted app is smoke-tested.

The repository is published at `parajulisaujan/roommate-ledger` and CI is verified. Push normally to `origin/main` after checks pass. Choose a license deliberately; repository publication alone does not grant reuse rights.
