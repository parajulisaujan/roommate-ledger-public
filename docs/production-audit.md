# Production readiness audit — updated 2026-09-12

Commit references use the privacy-rewritten equivalents of the original tested
versions. Their source trees are identical; rewriting metadata did not deploy or
re-verify hosted staging.

**Public production is not complete yet.** There are **8 open
blockers**, **7 open high-priority items**, 5 medium-priority items and 3 optional items.
H2 and H5 are resolved by repository changes and PostgreSQL regression tests.
The earlier startup logging fix remains resolved. Partial improvements do not
close the remaining operational or provider-dependent findings.

Scope: repository `parajulisaujan/roommate-ledger`, including the 2026-09-12
[repository hardening phase](production-hardening.md) following `252c901`.
The original audit and startup-log reproduction remain historical evidence.
The owner's earlier verified staging code corresponds to rewritten commit
`d8f6a5f74b1438f9d268c3b680346b6c5a2eb001`. Its successful flows remain recorded in
the [staging checklist](staging.md#verified-staging-checklist). This audit does not
retest provider settings, DNS, email delivery, branch protection or billing.

Status is described by evidence:

- **Completed:** financial retry protection, membership transaction cutoff and sanitized startup logging, with regression tests.
- **Partially completed:** abuse safeguards, dependency/build controls, log privacy, database timeouts and controlled migration tooling.
- **Remaining before public production:** production ingress/infrastructure, real email, monitoring, backup/restore evidence, load testing, release controls and public-user policies.
- **Optional future work:** receipt automation and further product/support improvements.

Strong local tests and verified private staging do not replace production recovery
and access checks. The findings below retain their IDs, evidence and required work.

Staging stays private and $0/month on Vercel protected Preview, Render Free,
Neon Free and Mailtrap Sandbox, with AI disabled and manual receipt entry.
No provider resources, DNS, real secrets, billing, trials or plans were changed.
Do not require a credit card, upgrade automatically or turn staging into production.

Before resuming production work, follow the [pause-point checklist](project-summary.md#exact-next-steps-when-development-resumes):
the latest hardening has local evidence but still needs its hosted staging check.

## Findings

Evidence links point to repository code or procedures. Missing provider controls
mean **not evidenced by this repository**, not that an inspected provider setting
was found disabled. Each ID is one finding even when its action has several steps.

| Priority | Area | Finding | Evidence | Required action |
| --- | --- | --- | --- | --- |
| BLOCKER B1 | Frontend/network | The protected proxy returns 404 on non-Preview Vercel deployments. The staging access design cannot be promoted unchanged to public production. | [proxy.ts](../frontend/src/proxy.ts), `proxy`; [Next config](../frontend/next.config.ts) | Design and test a separate production frontend/backend access path. Preserve the origin gate or verified private ingress; do not disable the guard to get a public page. |
| BLOCKER B2 | Production configuration | Separate production resources/domain and an audited environment are still a plan. General Settings validates HTTPS/cookies/email but does not require database verified TLS, a production-specific database, or proxy protection; those strict database checks live in the staging launcher. | [Settings](../backend/app/config.py), [staging preflight](../backend/app/staging_start.py), [.env.example](../.env.example), [Render staging YAML](../deploy/render-api.yaml) | Prepare separate frontend/backend/PostgreSQL database and role, production domain/HTTPS, origins and new key. Verify actual database TLS and identity in the production release procedure. Never reuse staging defaults/resources. |
| BLOCKER B3 | Email | Only Mailtrap Sandbox delivery is verified. SMTP acceptance is not proof of recipient delivery; there is no bounce processing. | [SmtpEmailProvider and Accounts.issue](../backend/app/services/accounts.py), [email_invite](../backend/app/api/ledger.py), [staging](staging.md) | Configure real STARTTLS SMTP, verify sender/domain and SPF/DKIM/DMARC, then test verification/reset/invitation delivery and failure handling with real inboxes. Keep verification required. |
| BLOCKER B4 | Recovery | Backup/restore commands and historical local migration-copy results exist, but no production schedule, storage/retention policy, recovery objectives or production restore evidence is implemented. | [release operations](release-operations.md#database-operations), [adoption verifier](../backend/scripts/verify_adoption.py), [verification](verification.md) | Define RPO/RTO, encrypted restricted backups and retention; schedule and monitor them. Restore into an isolated database and validate rows, balances, revision and readiness. |
| BLOCKER B5 | Operations | Health/readiness and safe error references exist; an alerting system and operator response are not configured in code. | [create_app/readiness/unexpected](../backend/app/main.py), [frontend error event](../frontend/src/app/error.tsx) | Monitor uptime/readiness, 5xx, database failures, SMTP failures, backups and abuse spikes; deliver and rehearse alerts without capturing private payloads. No paid vendor is selected here. |
| BLOCKER B6 | Abuse/ingress | The protected proxy removes forwarding headers. With empty trusted ranges, anonymous rate limits group users by the proxy peer. Application counters are not per-client edge protection. | [rate_limit](../backend/app/security/session.py), [client_address](../backend/app/security/proxy.py), [proxy.ts](../frontend/src/proxy.ts) | Review public traffic limits and a trustworthy client identity path; test legitimate concurrency and abuse. Use documented ingress capabilities only. Never trust broad/shared CIDRs or arbitrary forwarded headers. |
| BLOCKER B7 | Release/migration — partially improved | Production Docker runtime no longer runs migrations. A sanitized explicit release command checks database identity and verified client TLS; local tests prove restricted-role financial writes and denied DDL. | [release command](../backend/app/release.py), [runtime role test](../backend/tests/test_runtime_role.py), [release design](production-hardening.md#controlled-release-and-restricted-runtime-b7) | Still requires an approved production job/artifact, separate actual roles and grants, backup/restore rehearsal, compatibility review and hosted smoke. Forward-fix/isolated restore guidance remains mandatory. |
| BLOCKER B8 | Public-user readiness | No published privacy policy, terms/contact or implemented data-deletion process is present. Deactivation retains the account and shared financial history. | [Accounts.deactivate](../backend/app/services/accounts.py), [frontend routes](../frontend/src/app/page.tsx), [runbook](production-runbook.md) | Define retention/deletion and support procedures; publish accurate privacy information and terms/contact for public users. Explain deactivation versus deletion. These are launch items, not legal advice. |
| HIGH PRIORITY H1 | Shared-data visibility | SELECTED_MEMBERS restricts allocations, not readership: all current household members can view non-personal expenses and exports. New members can view household history; former members lose household access but retain their own allocation analytics. | [Expenses.validate/get/list](../backend/app/services/expenses.py), [exports](../backend/app/api/exports.py), [Finance.analytics](../backend/app/services/finance.py) | Make this rule explicit before collecting real data. Test an unselected current member and a newly joined member. If participant-only privacy is desired, design/test that as a separate change across reads, reports and activity; this audit does not redefine it. |
| RESOLVED H2 | Financial request retry safety | Expense and settlement receipts commit atomically with writes; user/operation-scoped keys replay the original response or reject changed details. Keys are required in production and supplied by both UI forms. | [idempotency](../backend/app/services/idempotency.py), [regression tests](../backend/tests/test_production_hardening.py), [retention/recovery contract](production-hardening.md#financial-request-retries-h2) | Thirty-day replay, permanent compact tombstones, bounded snapshot maintenance. Unkeyed legacy staging clients remain explicitly unsafe to retry; closing/reloading a form requires reconciliation. Settlement correction remains M5 rather than changing financial semantics here. |
| HIGH PRIORITY H3 | Enumeration | Login uses a generic response and dummy BCrypt work. Registration's unique email conflict differs from success. Password reset returns generic JSON but only known accounts perform synchronous SMTP, potentially creating a timing distinction (not measured here). | [auth.register/login/forgot](../backend/app/api/auth.py), [Accounts.request_reset/issue](../backend/app/services/accounts.py), [integrity_error](../backend/app/main.py) | Review acceptable enumeration exposure; test timing and consistent recovery behavior with production SMTP. Combine changes with abuse controls, without weakening verification. |
| HIGH PRIORITY H4 | Resource abuse — partially improved | New anonymous sessions have a peer budget and transactional global row cap; existing sessions reuse CSRF. Authenticated POSTs have a general write budget. Concurrent cap and spoofed-header tests pass. | [session controls](../backend/app/security/session.py), [budgets](production-hardening.md#session-and-write-budgets-h4b6), [tests](../backend/tests/test_production_hardening.py) | Public edge protection, lifetime account/storage quotas, cleanup scheduling and load evidence remain open. Shared-budget exhaustion can still deny new legitimate sessions. |
| RESOLVED H5 | Membership transaction cutoff | Shared financial-write and exclusive membership-change transaction locks define before/after behavior. Active membership is rechecked after the gate. | [write guard](../backend/app/services/write_guard.py), [PostgreSQL race tests](../backend/tests/test_production_hardening.py), [cutoff contract](production-hardening.md#membership-transaction-cutoff-h5) | Both orderings of removal/deactivation/join versus expense and settlement creation are tested with actual blocked database locks. Historical date semantics remain unchanged. No past privacy bypass or corrupt balance is claimed. Coarse-lock load tuning remains H9. |
| HIGH PRIORITY H6 | Dependencies/builds — partially improved | Docker bases and CI Actions are pinned to immutable references on existing version lines; weekly update configuration covers Actions, uv, npm and Docker. Package lockfiles were not upgraded. | [Dependabot](../.github/dependabot.yml), [CI](../.github/workflows/ci.yml), [build limits](production-hardening.md#invitations-build-artifacts-and-release-logs-h8h6) | Verify update automation operates, assign review ownership, audit current advisories/secrets and review provenance. Apt/build bootstrap inputs are not fully hermetic; no current CVE scan was performed. |
| HIGH PRIORITY H7 | Release governance | CI tests/builds on push and PR with read-only permissions. Branch protection, required reviews/checks and a production approval environment are not evidenced. | [CI workflow](../.github/workflows/ci.yml), [release sequence](staging.md#subsequent-releaserollback) | Require reviewed PRs, both CI jobs, staging-first evidence, manual production approval and a documented rollback decision. Owner must verify actual repository settings; none were changed here. |
| HIGH PRIORITY H8 | Log/artifact privacy — partially improved | First-party invitation acceptance uses a JSON body. Browser traces/screenshots and CI raw failure-artifact uploads are off. The production release wrapper suppresses raw settings/migration output with redaction tests. | [invitation API](../backend/app/api/ledger.py), [release tests](../backend/tests/test_release.py), [privacy limits](production-hardening.md#invitations-build-artifacts-and-release-logs-h8h6) | The deprecated URL route remains compatible. Review provider access logs, request-body collection, CI assertion output/access and third-party callers before closing. Use only fictional CI data. |
| HIGH PRIORITY H9 | Capacity/timeouts — partially improved | Runtime defaults now bound libpq connection, statement and lock waits; migration engines have separate budgets. Real PostgreSQL tests verify effective values and cancellation. | [engine_for](../backend/app/db.py), [timeout strategy](production-hardening.md#database-timeout-strategy-h9), [tests](../backend/tests/test_production_hardening.py) | Tune operator overrides, pools/workers and migration budgets on realistic data. Synchronous provider calls can still hold transactions; total request/transaction duration and hosted load behavior remain unproven. |
| MEDIUM PRIORITY M1 | Browser security | Production CSP removes unsafe-eval but retains unsafe-inline scripts/styles. HSTS, frame denial and nosniff exist. | [Next headers](../frontend/next.config.ts) | Evaluate nonce/hash CSP compatible with Next.js and regression-test it; do not claim the current CSP prevents all script injection. |
| MEDIUM PRIORITY M2 | Frontend quality | Dialog labels, field labels, alerts, loading states and busy controls exist; no accessibility audit or production mobile/load evidence is recorded. Proxy upload sizes need hosted testing. | [ui.tsx](../frontend/src/components/ui.tsx), [ExpenseForm](../frontend/src/components/ExpenseForm.tsx), [Playwright config](../frontend/playwright.config.ts), [acceptance checks](staging.md#additional-acceptance-checks-for-future-releases) | Test keyboard/screen-reader flows, contrast, mobile layouts and real proxy receipt sizes/timeouts. Preserve error recovery. |
| MEDIUM PRIORITY M3 | Session policy | Sessions rotate at login and have sliding idle expiration; no separate absolute lifetime or session/device list exists. CSRF is preserved across login rotation. | [new_session/security](../backend/app/security/session.py) | Decide whether absolute lifetime/device revocation is needed; test multiple tabs and stale CSRF recovery before changing the policy. No fixation exploit was established. |
| MEDIUM PRIORITY M4 | Maintenance | Expired session/token/rate records are cleaned during request paths; there is no scheduled cleanup/retention worker. | [session cleanup](../backend/app/security/session.py), [account-token cleanup](../backend/app/services/accounts.py) | Review retention and cleanup cost on realistic data; schedule bounded maintenance if needed without resetting financial records. |
| MEDIUM PRIORITY M5 | Audit/product limits | Activity stores actor/action/entity only, not immutable before/after financial snapshots. Settlements are sender-entered records, not recipient-confirmed payments. Refunds and ownership transfer are unsupported. | [Store.audit](../backend/app/db.py), [Finance.settle](../backend/app/services/finance.py), [Households.leave](../backend/app/services/households.py) | Explain these limits; plan dispute/correction support and audit history if the intended public use needs them. Do not silently change financial rules. |
| OPTIONAL / FUTURE O1 | Receipt AI | Provider adapters exist, but live extraction is intentionally disabled/unverified. | [receipt adapters](../backend/app/ai/receipts.py), [receipt provider notes](receipt-provider.md) | Keep manual entry; enable AI only after explicit cost/privacy review and real-photo accuracy testing. |
| OPTIONAL / FUTURE O2 | Operational UX | Alert destinations and backup checks are launch work; a unified dashboard and automated restore verification are not implemented. | [operations](release-operations.md) | Improve the dashboard and recovery automation after basic alerts/restores are proven. |
| OPTIONAL / FUTURE O3 | Product/support tools | No full admin support console, advanced reporting or automatic recurring scheduler exists. | [recurring service](../backend/app/services/recurring.py), [frontend components](../frontend/src/components/LedgerApp.tsx) | Prioritize from user needs; retain permission checks and keep account support separate from private-data access. |

## Reproduced defect fixed during the audit

**R1 — production startup could print rejected settings inputs.** The ordinary
`python -m app.serve` entrypoint imported the application before a safe startup
exception boundary existed. A subprocess with fictional production settings and
an invalid SMTP field returned a Pydantic traceback containing the rejected
sentinel. Only boolean reproduction results were reported; no real secrets were used.

[serve.py](../backend/app/serve.py) now catches startup failures when
`APP_ENV=production`, exits unsuccessfully with a fixed message, and uses a
production server formatter that emits only severity and a fixed label. It also
rejects a server that never started. The existing staging formatter and normal
development behavior remain. Application request IDs and safe domain events are
unchanged. Tests cover the real import-time failure and messages with embedded
exception/credential sentinels. The fix does not sanitize a separately invoked
Alembic CLI or provider access logs; H8 and B7 still apply. Direct `uvicorn`
commands bypass this entrypoint and are not the documented production launch path.

## Controls confirmed by code review

### Authentication and authorization

- `secrets.token_urlsafe(32)` generates session, account and invitation tokens;
  SHA-256 hashes are stored for those bearer tokens. The separate CSRF token is
  stored directly in the server session. BCrypt uses cost 12 and enforces its
  72-byte input boundary.
- Login deletes the prior session token and issues a new one. Logout deletes the
  session; password change/reset/deactivation increments the account session
  version, invalidating older sessions on their next request. Idle expiry is
  checked before use. Reset/verification tokens expire and are consumed under a
  row lock; resends supersede prior tokens.
- Mutations require a session-bound constant-time CSRF check, including login,
  registration and invitation acceptance. Cookies are HttpOnly, host-only and
  Secure in validated staging/production; SameSite supports lax/strict/none,
  with Secure required for none. Use lax for the same-origin proxy plan.
- Personal expense reads require the owner. Household ownership gives no bypass.
  Receipt reads and drafts require the uploader. Exports gate household membership
  and exclude personal rows; CSV cells escape formula-leading input.
- Invitations are hashed, expiring, single-use and locked for acceptance; current
  household membership is checked, and household locking serializes acceptance.
  Historical allocations are retained when membership ends. Selected-member
  visibility follows H1, not participant-only privacy.

Evidence: [security tests](../backend/tests/test_security.py),
[ledger tests](../backend/tests/test_ledger.py), [receipt tests](../backend/tests/test_receipts.py).
The full PostgreSQL suite was rerun in the repository hardening phase below.

### Financial calculations and transactions

[Money services](../backend/app/services/money.py) require integer cents and use
Decimal arithmetic. Equal splits use deterministic UUID ordering and largest
remainders. Fixed amounts must sum to the expense, percentages must sum to 10,000
basis points, and allocations conserve cents. Negative/zero expenses and refunds
are rejected rather than silently converted. Frontend amount parsing uses BigInt
before conversion to bounded integer cents; display formatting is not authoritative.

Balances derive from paid amounts minus responsibilities plus outgoing minus
incoming settlements. Settlement entry is restricted to the sender and a
recipient in household history. It does not move money or verify an external payment.
Receipt confirmation locks the receipt, validates/reconciles totals, and creates
all expenses in one request transaction before marking confirmed. A second
confirmation fails. Edits use locks and optimistic versions. Recurring recording
locks its template and has a unique template/date constraint; repeating a request
can record the next overdue occurrence, so it is not a generic idempotency mechanism.
No demonstrated cent-conservation or balance-sign defect justified financial code changes.

[Database dependency](../backend/app/db.py) commits/rolls back at function scope.
[Migration env](../backend/alembic/env.py) uses a transaction-scoped advisory lock.
Baseline adoption refuses unknown/drifted schemas; applied migrations are
forward-only. Readiness now expects revision `0003_request_idempotency`. Production runtime
does not migrate; development and guarded staging retain startup migration.
An approved production release job is still required (B7).

### Logging, network and frontend boundaries

Application error responses are generic with generated request references;
SQLAlchemy hides bound parameters. Account SMTP failure logs only a fixed purpose,
not recipient or provider errors. Invitation SMTP failures return a safe 503 but
have no dedicated delivery-failure event. Receipt provider failures become safe
manual-recovery messages. No runtime log call reviewed intentionally records
financial payloads, receipt images, passwords, cookies or bearer tokens.

The deployment gate compares the server-only key in constant time and strips it
before endpoint handling. Only read-only health probes bypass it. Those probes
reveal status only. Next.js replaces client-supplied origin credentials and
removes authorization/forwarded-IP claims. CORS is not an ingress security boundary.

The API client uses same-origin credentials, no-store requests and a CSRF cache;
401/403 clears that cache for the next mutation, without automatically replaying
financial writes. Account link fragments are removed by the frontend after reading.
React renders content as text; dialogs, error boundaries and loading states exist.
CSP/accessibility/hosted upload limits still need the reviews listed above.

## Production configuration review

Only existing application settings are listed here; no provider feature is assumed.

| Setting/group | Production decision required |
| --- | --- |
| `APP_ENV` | Explicit `production` on backend and frontend build. Never copy development defaults. |
| `FRONTEND_URL` | Exact real production HTTPS origin, used for account links; separate from Preview. |
| `API_INTERNAL_URL` | Reachable production API target; validate HTTPS/ingress and rebuild frontend when changing it. |
| `DEPLOYMENT_PROXY_REQUIRED`, `DEPLOYMENT_PROXY_KEY` | Deliberate protected ingress with a new production-only key. Resolve B1 before using protected Vercel Production; never simply turn protection off. |
| `DATABASE_URL`, optional `DATABASE_USER`/`DATABASE_PASSWORD` | Separate production database/role and verified TLS/CA. Embedded URL credentials take precedence; never log or put them in commands. |
| `COOKIE_SECURE`, `COOKIE_SAME_SITE` | `true`, normally `lax`; test Secure/HttpOnly/host-only flags through the real proxy. |
| SMTP fields, `EMAIL_FROM`, `EMAIL_VERIFICATION_REQUIRED` | Real provider with STARTTLS, verified sender and verification enabled. Mailtrap Sandbox is staging only. |
| `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_CIDRS` | Empty CORS for same-origin proxy; trust only proven controlled hops. No broad proxy ranges. |
| `RATE_*`, timeout fields, `HOST`, `PORT` | Review documented ranges and capacity; database connect/statement limits need driver/database configuration rather than invented app variables. |
| Receipt provider keys/model | Keep absent until cost/privacy and extraction review; manual mode is valid production functionality. |

## Production launch checklist

Unchecked items are still open for **production**, even when their staging equivalent passed.

- [ ] Separate production frontend and reviewed public access design (B1).
- [ ] Separate production backend with controlled/private ingress where available (B1/B2).
- [ ] Separate production PostgreSQL database/role and new production secrets (B2).
- [ ] Production domain, HTTPS, exact origins and verified database TLS (B2).
- [ ] Real SMTP provider, verified sender and SPF/DKIM/DMARC (B3).
- [ ] Production verification, reset and invitation email delivery tests (B3).
- [ ] Backup schedule, encryption/access/retention policy and RPO/RTO (B4).
- [ ] Isolated restore test and ledger/revision/readiness validation (B4).
- [ ] Monitoring and actionable readiness/5xx/database/SMTP/backup/abuse alerts (B5).
- [ ] Secret rotation plan and a tested sequence for both proxy-key consumers (B2/H8).
- [ ] Rate-limit, session-creation and storage-abuse review (B6/H4).
- [ ] Proxy/ingress and safe logging review (B1/B6/H8).
- [ ] Protected branch, required CI/review and manual production approval (H7).
- [ ] Controlled production migration, backup and rollback decision (B7).
- [ ] Production smoke test with authorized disposable users and real email (B7).
- [ ] Document selected-member visibility and settlement correction limits for public users (H1/M5).
- [x] Define and test expense/settlement retry behavior and membership cutoff (H2/H5).
- [ ] Current dependency/advisory review and update process (H6).
- [ ] Privacy policy, retention/deletion explanation and terms/contact (B8).

## Validation and limits

The original 2026-09-11 startup-log audit passed 80 selected tests with four
DB tests deselected. That is historical evidence, superseded for this branch by
the repository hardening run: **243 backend tests passed** against isolated
PostgreSQL 17, including migrations/adoption, concurrency, rollback, timeout and
restricted runtime-role checks. Two existing Starlette/httpx/AnyIO deprecation
warnings remain. No dependency was blindly upgraded to silence them.

Frontend lint, TypeScript, **14 unit tests**, **5 browser E2E tests** and production
build passed. Both pinned backend and frontend Docker images built; the isolated TLS staging smoke passed CA,
sanitized failure cases, migration, readiness and restart checks. Ruff lint/format, Markdown links/UTF-8 and `git diff --check` passed. See the
[completion evidence and file manifest](production-hardening.md#completion-evidence).

No provider operation, hosted load test, comprehensive CVE review or legal
assessment was performed. The frontend image build's automatic npm audit reported
zero vulnerabilities; backend/container advisory and secret scans remain open. The owner's earlier private staging evidence is not a deployment
claim for this change. The remaining work is tracked above and in the
[production runbook](production-runbook.md).
