# Production readiness plan and runbook

An earlier private staging backend was verified on 2026-09-11. The latest
hardening still needs a hosted staging redeploy/smoke; production is not deployed.
This document extends the existing production runbook with the work still needed
before real users depend on the app. The unchecked items below are release gates,
not completed work or permission to provision services.

Staging can continue on Vercel protected Preview, Render Free, Neon Free,
Mailtrap Sandbox and manual receipt entry. Keep staging at $0/month. Stop at a
credit-card requirement; do not enable trials or automatically upgrade any service.
This plan does not select or provision paid infrastructure.

## Audit status

The [production audit updated 2026-09-12](production-audit.md) separates completed,
partially completed and remaining production work. It records source evidence,
remaining launch gates and a fixed production startup logging defect. Treat the
checklists below as production work still to do, not evidence that launch is approved.

The [repository hardening contract](production-hardening.md) documents required
production idempotency keys, membership cutoff, budgets and the controlled release
command. H2/H5 are resolved; provider-dependent launch gates remain open.

## Before production: separate resources and access

- [ ] Create a separate production frontend/Vercel environment and backend.
- [ ] Use a separate production PostgreSQL database and role. Never reuse staging
  data, resources, SMTP credentials or keys for production.
- [ ] Configure `APP_ENV=production`, a real production domain and HTTPS.
- [ ] Set the production `FRONTEND_URL` and `API_INTERNAL_URL`; rebuild the frontend.
- [ ] Generate a new production `DEPLOYMENT_PROXY_KEY` in secret storage and retain
  protected API ingress. Never expose it through `NEXT_PUBLIC_*`, logs or URLs.
- [ ] Review the frontend's Preview-only guard before implementing production:
  `frontend/src/proxy.ts` currently rejects non-Preview Vercel deployments when
  `DEPLOYMENT_PROXY_REQUIRED=true`. A separate, tested production access design is
  required. Do not disable the flag to get around it or promote staging to public production.
- [ ] Use the production migration/runtime commands below. `app.staging_start`
  intentionally accepts only the staging database, Neon hostname and sandbox configuration.
- [ ] Validate the production database configuration separately: general `Settings`
  does not enforce the staging launcher's database identity/TLS restrictions.
- [ ] Verify database `sslmode=verify-full`, matching hostname and readable CA,
  Secure/HttpOnly cookies, CSRF and required email verification.
- [ ] Review proxy/network trust and production `RATE_*` limits. Never trust broad
  shared ranges, `0.0.0.0/0`, `::/0` or client-supplied forwarding headers.

## Before production: real email

- [ ] Configure a real SMTP delivery provider with STARTTLS and a verified sender/domain.
  Mailtrap Email Sandbox must not be used for production delivery.
- [ ] Configure and verify SPF, DKIM and DMARC for that domain.
- [ ] Test production registration/email verification, password-reset email and
  invitation email, including link origins and delivery to real inboxes.
- [ ] Set up email failure monitoring and a support path for undelivered messages.

## Before production: recovery and operations

- [ ] Define backup frequency, encrypted storage, access, retention and recovery objectives.
- [ ] Perform an actual restore into an isolated database; check records, balances,
  Alembic revision and readiness without touching the source database.
- [ ] Monitor readiness and 5xx errors with alerts that reach an operator.
- [ ] Monitor database connections/pool pressure and email failures.
- [ ] Document and rehearse secret rotation for the database, SMTP and deployment
  proxy key. Update dependent services, verify access, then revoke old credentials.
- [ ] Apply production migrations with an appropriate role and a verified backup.
- [ ] Run the production smoke test: account emails, permissions, privacy, expense
  splits, balances, sessions and persistence. Use explicitly authorized test accounts.
- [ ] Publish a privacy policy and, for public users, terms/contact information.
  Describe stored financial data, retention and account deactivation accurately.

Use [release operations](release-operations.md) for backup/restore commands,
rotation procedures, pool sizing and the guarded smoke test. Do not run test-database
reset scripts against staging or production. No production restore or smoke result
is claimed by the staging verification.

## Additional audit follow-up

- [ ] Explain that selected-member splits remain visible to current household members.
- [ ] Define idempotent retry and settlement correction behavior before broad usage.
- [ ] Review enumeration, unbounded anonymous session creation and membership/write races.
- [ ] Review current dependency advisories, digest pinning and required CI/PR protections.
- [ ] Verify release/ingress logs and test artifacts cannot expose tokens or credentials.
- [ ] Load-test connection pools, query/lock budgets and synchronous email requests.

See audit IDs H1–H9 for evidence and acceptance work. A successful startup alone
is not a production smoke test.

## Later improvements

- A monitoring dashboard and automated backup verification.
- Better account/admin support and production email templates.
- Custom-domain setup as part of the separate production launch.
- More mobile UX testing, an accessibility review and performance/load tests.
- Error reporting that excludes financial data, receipt contents, cookies and secrets.
- Optional receipt AI only after a cost/privacy review and explicit approval;
  manual entry remains available.

## Operational reference

## Required hosting settings

- Python 3.13, locked `uv.lock` dependencies; PostgreSQL 17 with private connectivity.
- `DATABASE_URL=postgresql+psycopg://host:port/database`, `DATABASE_USER`, `DATABASE_PASSWORD`. Add the managed provider's verified TLS options.
- `APP_ENV=production`, `FRONTEND_URL=https://your-domain.example`, `COOKIE_SECURE=true`, `EMAIL_VERIFICATION_REQUIRED=true`.
- SMTP host/port, username/password when required, verified `EMAIL_FROM`, `SMTP_STARTTLS=true`.
- Frontend build variables `APP_ENV`, `FRONTEND_URL`, `API_INTERNAL_URL`.
- `SESSION_TIMEOUT_SECONDS` defaults to 1800 (idle expiry); `COOKIE_SAME_SITE=lax`. Cross-site None requires Secure and deliberate browser compatibility verification.
- Leave `CORS_ALLOWED_ORIGINS` empty for the same-origin proxy. Additional production origins must be exact HTTPS origins without wildcards or paths.

Keep secrets in provider secret storage. Production config rejects missing HTTPS, insecure cookies, missing SMTP/STARTTLS or disabled verification.

## Email and account behavior

Configure the SMTP provider's domain verification and SPF/DKIM/DMARC records through your domain account. Test real delivery and spam-folder behavior. The loopback SMTP sink used in acceptance tests proves the application flow, not external delivery.

Reset links expire in 30 minutes, verification links in 24 hours. Tokens are random, hashed in storage and single-use; resending invalidates prior links. The URL fragment is removed when the frontend reads it. Reset and password changes revoke all prior sessions. A password change requires the current password.

Deactivation ends memberships, pauses owned templates and expires owned-household invitations. Owners cannot abandon active roommates. Financial history remains; this is not data erasure or debt forgiveness. CSV exports are available before deactivation.

## Receipt providers

Default manual mode needs no credentials. For OpenAI, set `RECEIPT_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_RECEIPT_MODEL` to an explicitly chosen vision model supporting structured outputs. The server calls Responses with a strict schema and `store=false`. Review the provider's retention and pricing terms through its official account documentation before production use.

Alternatively set `RECEIPT_PROVIDER=adapter`, HTTPS `RECEIPT_PROVIDER_URL`, and `RECEIPT_PROVIDER_API_KEY`. See [provider contract](receipt-provider.md).

Application timeouts cover connection and the complete response body; the body is bounded to 256 KiB. Invalid or unreadable money fails safely. AI never assigns participants or confirms records. Only Decimal service code allocates reviewed amounts. Live extraction remains unverified until configured with real credentials and receipt photos.

## Abuse controls and monitoring

PostgreSQL counters preserve limits across requests, workers and restarts. Configure `RATE_WINDOW_SECONDS` and `RATE_LOGIN`, `RATE_REGISTRATION`, `RATE_PASSWORD_RESET`, `RATE_RESET_CONFIRM`, `RATE_VERIFICATION`, `RATE_INVITATIONS`, `RATE_EXTRACTION`, `RATE_ACCOUNT`, `RATE_SESSION_CREATION`, `RATE_WRITES` and `ANONYMOUS_SESSION_LIMIT`. See the [budgets and shared-proxy limits](production-hardening.md#session-and-write-budgets-h4b6). Failed attempts count. Place per-client limits at ingress because the Next.js proxy may appear as the peer address.

Disable raw access logging or redact invitation paths and sensitive query strings at ingress. Application errors expose only a reference and generic message. Alert on readiness failure, application 5xx, SMTP delivery failure, pool saturation, disk/memory pressure and backup failure. Connect the frontend `roommateledger:error` event to your chosen monitor without recording receipt data or credentials. An external collector is not configured by default.

## Backup and release checklist

1. Back up PostgreSQL and restore into an isolated copy.
2. Apply Alembic to the copy and verify all historical values and allocation sums.
3. Pause old writers, take a final backup, run the release migration and start FastAPI.
4. Verify readiness, secure cookie attributes, CSRF, account email, household privacy, all splits, receipts and settlement signs.
5. Restart FastAPI and verify persisted data and sessions.
6. Run hosted browser acceptance and inspect logs.
7. Retain the pre-migration backup under encrypted access controls with a defined retention policy.

The tested migration retained 12 existing tables and 249 rows in a restored Flyway V3 copy, with zero allocation mismatches. Fresh and V1/V2/V3 adoption tests run on real PostgreSQL. See [verification](verification.md) for current results.
