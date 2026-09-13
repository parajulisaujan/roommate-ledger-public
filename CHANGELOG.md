# Changelog

## 2026-09-12 ? public portfolio presentation

Preserved source trees while rewriting owner commit/tag metadata to the public
repository identity. Replaced numeric assessments with factual production-work
status and refreshed commit references to their rewritten equivalents. Rebuilt
the isolated walkthrough with four fictional roommates, local-only mail capture
and a dashboard ending. The reviewed WebM is 98.16 seconds and about 5.09 MB;
generated media remains ignored here. No hosted backend deployment or application
logic change is included.

## 2026-09-12 — portfolio pause point

Refreshed the README, added a project summary with an ordered resume checklist,
and added an isolated local demo-recording workflow. Documentation now separates
core functionality, earlier hosted staging verification and later local hardening.
The latest hardening still needs a Render staging redeploy and hosted smoke.
Public production is not launched; operational and provider-dependent work remains.
No provider settings, credentials, billing or deployment configuration changed.
See the [project summary](docs/project-summary.md) and [demo guide](docs/demo.md).

## 2026-09-12 — production hardening, locally verified

Commit `6b314fe08daca21af6a8c2da57f61f8d8ce4ccaf` added financial retry receipts,
membership/write concurrency controls, anonymous-session/write budgets, database
timeouts and controlled release tooling. First-party invitations now use request
bodies; build references are pinned and raw CI failure-artifact uploads removed.
Migration `0003_request_idempotency` adds request receipts and an expiry index.

Local results: 243 backend tests, 14 frontend unit tests and five browser tests
passed, plus lint/typecheck/build, Docker builds and isolated TLS/startup smoke.
H2/H5 are resolved; other launch gates remain open. The code entered staging via
merge `54848781fbe999a1394d46ff3fc3198885a0a888`; this is not hosted verification.
See [hardening evidence](docs/production-hardening.md#completion-evidence).

## 2026-09-11 — private staging verified

The owner verified private staging on backend commit
`d8f6a5f74b1438f9d268c3b680346b6c5a2eb001`: GitHub CI, protected Vercel Preview,
Render Free, Neon PostgreSQL 17, verified client-side TLS, Alembic and Mailtrap
Email Sandbox. Registration, verification, login, households, invitations,
private/shared expenses, equal splits, balances and refresh persistence passed.
AI stays disabled with manual entry available. See the [staging checklist](docs/staging.md#verified-staging-checklist).

The repository documentation now reflects that result, shortens the startup
debugging history and adds a practical [production readiness plan](docs/production-runbook.md).
Staging remains private and $0/month. Production and real email delivery are
future work; no provider resources or application behavior changed in this cleanup.

## 2.0.0 — release candidate

FastAPI/Python is the active backend with SQLAlchemy/Pydantic, PostgreSQL/Alembic and the existing Next.js/React/TypeScript frontend. Spring is archived under `reference/spring-backend`.

The verified migration preserves 249 rows across 12 existing tables and exact cent allocations. Account verification/recovery, private expenses, shared splits, recurring bills, analytics, settlements, secure CSV exports and user-confirmed receipt drafts are retained.

Production readiness adds explicit trusted proxies, configurable provider deadlines, request IDs, a configurable Python server entrypoint, package-build CI and guarded hosted smoke/operations documentation. Docker runtime smoke passed per the owner's report on 2026-09-07. See [verification](docs/verification.md) for evidence and provenance. The later staging and CI verification is recorded above. Real recipient email delivery, live AI and public production are still future work.
