# Deployment

For the verified private staging setup, use [the Vercel/Render/Neon runbook](staging.md).
It includes the environment audit, strict $0/no-card boundary, Mailtrap Sandbox setup,
protected backend ingress and exact provider setup/acceptance steps.

The active backend is Python/FastAPI. Use PostgreSQL 17, Python 3.13 and Node.js 24. Containers and the GitHub Actions pipeline no longer require Java.

The latest hardening is locally verified and merged into staging, but its hosted
backend redeploy/smoke is pending. See the [project summary](project-summary.md).

## Local or hosted startup

Backend build: `uv sync --frozen --no-dev`.
Local development migration: `uv run alembic upgrade head`.
Production uses the explicit [sanitized release command](production-hardening.md#controlled-release-and-restricted-runtime-b7) with separate release credentials; do not use the raw CLI in shared production logs.
Runtime: `uv run python -m app.serve`. `HOST` defaults to `0.0.0.0`, `PORT` to `8080`. The launcher disables implicit forwarded-header trust and raw access logs, and allows 150 seconds for graceful shutdown. Configure at least that shutdown grace period on the host.

The backend Dockerfile installs locked dependencies on Python slim and runs as an unprivileged user. Its `app.start` entrypoint migrates in development, delegates to the guarded staging launcher in staging, and starts production without runtime migrations. It has a readiness healthcheck. Compose waits for PostgreSQL health before starting the API, then API health before the frontend.

Build the frontend with `API_INTERNAL_URL` pointing to the reachable API origin, with protected ingress. The normal Next.js rewrite reads this at build time; the protected staging proxy also reads it server-side. Rebuild after changing the target. Use `npm ci`, `npm run build`, `npm run start`, or its Dockerfile. Keep browser traffic on one HTTPS origin.

For staging/production, set `APP_ENV`, exact public HTTPS `FRONTEND_URL`, `COOKIE_SECURE=true`, `EMAIL_VERIFICATION_REQUIRED=true`, SMTP settings and `SMTP_STARTTLS=true`. Configuration fails closed without them. Set database TLS options in `DATABASE_URL` as required by the managed provider, and protect database/API ingress. Staging uses a public Render hostname guarded by the server-only deployment proxy key; this is not a network-private API. Store secrets in the host's secret manager. Never deploy the test mailbox or demo seeding command.

## Database rollout

Back up first and verify restoration into a separate database. Stop Java writers for cutover. Run Alembic on the restored copy and compare rows, allocations and balances before adopting the original database. The migration preserves cent units, constraints/indexes and Flyway history. Existing Java in-memory sessions cannot transfer; users sign in again. Python sessions persist in PostgreSQL afterward.

The migration user needs DDL and temporary schema-creation permission. A separate restricted runtime user is recommended after a release migration. Development and guarded staging combine startup and migration for their current topology. Production requires a controlled release migration and restricted runtime role; no production job or role is provisioned by this repository. Do not edit already-applied migrations.

Avoid destructive downgrade or volume removal. `docker compose down` retains data. The Docker smoke script creates and cleans up only its own uniquely named project/volume; its ports must be free. Run `node frontend/scripts/docker-smoke.mjs` on a Docker-capable machine to verify fresh setup, API behavior and persistence after restart.

## Ingress and health

Preserve cookies, Content-Type, X-CSRF-TOKEN, Idempotency-Key and request bodies. Allow 9 MB bodies and a timeout above the 45-second extraction deadline. Configure per-client auth/upload limits and private API ingress. Anonymous application limits use the connection address, which may be the Next.js proxy; do not blindly trust arbitrary forwarded-IP headers. Configure trusted proxy handling only for known ingress addresses.

Use `/actuator/health/liveness` for process health and `/actuator/health/readiness` for PostgreSQL/Alembic readiness. `/api/health` remains a compatibility endpoint. Development has generated `/docs` and `/openapi.json`; production disables these public documentation routes. Application errors return safe references, not tracebacks. Forward application logs to your hosting monitor and alert on readiness failures, 5xx rates, failed email delivery and saturation. The frontend error boundary exposes a monitoring integration event without sending receipt data to an external service.

## Acceptance and external setup

Run full Playwright only on isolated staging with `E2E_BASE_URL` and its test inbox; it creates fictional records. For production use the guarded [hosted smoke procedure](release-operations.md), which defaults to health-only. Live AI additionally requires explicit opt-in and `LIVE_RECEIPT_FILE`; no simulated extraction success is substituted.

Set a verified SMTP sender and the provider-required DNS records. Set an OpenAI key and explicit vision model, or an HTTPS adapter endpoint/key, only if automated extraction is desired. Verify actual receipt photos through review before advertising scanning quality.

GitHub publication and CI are verified. The owner verified private staging on 2026-09-11 with backend commit `d8f6a5f74b1438f9d268c3b680346b6c5a2eb001`: Vercel Preview, Render, Neon, sandbox SMTP and the listed account/expense flows work. See the [staging checklist](staging.md#verified-staging-checklist) for the exact scope. Public production, real recipient email delivery and live AI remain future work in the [production readiness plan](production-runbook.md).

## Known limits

USD only; no money transmission, refunds, ownership transfer, settlement correction/recipient approval, automatic recurring scheduler or persistent receipt-image storage. Deactivation preserves shared obligations. The activity trail records actions rather than full before/after snapshots. Sessions and rate limits are shared through PostgreSQL; size the pool/worker count and ingress controls for the actual host.
