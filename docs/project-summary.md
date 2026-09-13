# RoommateLedger Project Summary

Commit references use the privacy-rewritten equivalents of the original tested
versions. Their source trees are identical; rewriting metadata did not deploy or
re-verify hosted staging.

Pause point: **2026-09-12**. This is a portfolio/demo milestone, not a production release.

## Project goal

Build a full-stack application that keeps personal spending separate from shared
household costs and makes each roommate's responsibility easy to understand.

## Problem being solved

A purchase can contain shared groceries, items for two roommates and personal
items on the same receipt. One equal split can be unfair. RoommateLedger lets
users choose each expense or item's scope and split, then derives balances from
the recorded shares and payments.

## Main features

- Accounts, email verification/recovery, profile preferences and session revocation.
- Households, owner/member permissions, invitation codes and optional invitation email.
- Private expenses; household or selected-member allocations; equal, fixed and
  percentage splits; history, filtering and CSV exports.
- Balances and records of repayments made outside the app.
- Personal/household reports, monthly comparisons and recurring templates.
- Private receipt drafts, manual review and atomic confirmation of allocations.
  Automated extraction is optional and disabled in private staging.

## Architecture

The browser uses a Next.js/React/TypeScript frontend and same-origin API proxy.
FastAPI validates requests with Pydantic, authorizes operations in Python services,
and uses SQLAlchemy transactions with PostgreSQL 17. Alembic owns migrations.
SMTP handles account/invitation emails; receipt extraction has an optional provider
boundary. The retired Spring backend remains under `reference/spring-backend` for
migration history, not as an active service.

In staging, those roles map to Vercel, Render, Neon and Mailtrap Sandbox.
See [architecture](architecture.md) and the
[ingress contract](production-hardening.md#production-ingress-design-to-implement-and-verify-b1b6).

## Important design decisions

- Store money in cents and calculate with `Decimal`. Splits must conserve the
  total, including remainder cents; percentages use 10,000 basis points.
- Keep personal expenses inaccessible to others. Shared expenses are visible
  to current household members, even when only selected members pay.
- Use revocable server-side sessions and synchronizer CSRF tokens.
- Commit an expense, allocations and audit event together. Confirm a receipt's
  items together; a failed item rolls back the entire confirmation.
- Scope idempotency keys to user/operation and bind them to the request. Replays
  return the original result; changed details conflict.
- Use a shared/exclusive transaction gate for financial writes versus membership
  changes, preserving historical eligibility and existing obligations.
- Keep production migrations out of runtime startup. A separate sanitized release
  command verifies the database/TLS before an explicitly requested migration.

The [hardening contract](production-hardening.md) documents retry retention,
timeout budgets, lock tradeoffs and the remaining limitations.

## Security and privacy approach

Backend permissions do not depend on visible buttons or client record IDs.
Passwords are hashed; login rotates the opaque session token. Verification,
recovery and invitation tokens expire and are single-use. Password changes and
deactivation revoke sessions. Cookies are HttpOnly and Secure in staging and
production; state-changing requests require CSRF checks.

The staging origin gate and Preview-only guard remain enabled. Staging startup
requires the expected database, `verify-full`, a readable CA bundle and client-side
TLS verification. Logs use safe labels/references rather than raw provider errors
or credentials. Rate counters and anonymous-session limits bound some abuse, but
do not replace public edge protection or lifetime storage quotas.

Receipt images are not retained. Drafts and ledger history are private data;
account deactivation is not data erasure. Retention/deletion policies still need
work before public use. See the [production audit](production-audit.md).

## Testing completed

The production-hardening phase recorded these local results:

| Check | Result |
| --- | --- |
| Backend suite on isolated PostgreSQL 17 | 243 passed; two existing dependency deprecation warnings |
| Frontend unit tests | 14 passed |
| Browser E2E with fictional data/local SMTP | 5 passed |
| Ruff lint/format and frontend lint/typecheck/build | Passed |
| Backend and frontend Docker builds | Passed |
| Isolated staging TLS/startup/migration/restart smoke | Passed |
| Markdown links/UTF-8 and whitespace | Passed |

Coverage includes allocations, authorization, rollback, concurrent retries,
membership cutoff, session caps, real timeouts, migration/adoption and a restricted
runtime role. These results do not verify the latest hosted backend. The
[verification history](verification.md) separates hosted checks from local evidence.

## Deployment setup

| Environment | Recorded state |
| --- | --- |
| Local | Docker or native development; explicit fictional demo seeding. |
| Private staging | Earlier backend verified on Vercel protected Preview / Render Free / Neon Free / Mailtrap Sandbox. Private, $0/month, manual receipts. |
| Latest hardening on GitHub | Present in both branches with local evidence; hosted backend redeploy/smoke pending. |
| Public production | Not launched; eight launch blockers remain. |

A branch push or Preview build does not prove Render runs the same backend commit.
The checked-in Render blueprint disables automatic deployment and uses the guarded
staging launcher. No provider settings, secrets, DNS or billing were changed during
this pause cleanup.

## Current pause point

These historical references identify the code being paused:

| Reference | Commit |
| --- | --- |
| Earlier owner-verified hosted staging backend | `d8f6a5f74b1438f9d268c3b680346b6c5a2eb001` |
| Production-hardening implementation on main | `6b314fe08daca21af6a8c2da57f61f8d8ce4ccaf` |
| Merge bringing that code into staging | `54848781fbe999a1394d46ff3fc3198885a0a888` |

The final documentation/demo commit follows these references. Annotated tag
`portfolio-pause-2026-09-12` identifies that main-branch pause point, not a
production release. Both branches receive the final documentation by normal merge.

Core features support a private demonstration, and the newer hardening has local
evidence. Work is paused before calling that newer backend hosted-verified. Start
the next session with the deployment check below, not a redesign of the financial
calculations.

## Known limitations

USD only. No money transmission, refunds, settlement correction/recipient approval,
ownership transfer or automatic recurring scheduler. Selected-member allocation
does not create participant-only visibility. Activity stores actions rather than
complete before/after snapshots. Historical shares remain after leaving.

Forms retain retry keys during their lifetime; after closing/reloading an uncertain
submission, reconcile the ledger before creating another request. Expired response
snapshots need maintenance, while key tombstones remain. Shared proxy budgets and
the coarse membership gate need load testing. The deprecated invitation URL route
remains compatible; first-party clients use the body-based route.

Live receipt AI, production email, accessibility review and realistic production
capacity are not verified. No license has been added without an owner decision.

## Production readiness

**Public production is not complete yet.** Financial idempotency (H2) and
membership concurrency (H5) are completed with regression tests. Abuse safeguards,
build controls, log privacy, database timeouts and controlled releases have partial
improvements. The audit records the remaining work by finding and evidence.

Remaining work includes ingress, separate infrastructure, real email, backup/restore,
monitoring, load testing, dependency/security scans, release approval and
privacy/retention/support policies. Use the [audit](production-audit.md),
[runbook](production-runbook.md) and [release operations](release-operations.md).
Do not enable paid services or bypass the staging guard to make production start.

## Exact next steps when development resumes

Use existing private staging resources and authorized test accounts. Never paste
secrets, tokens or private financial records into verification notes.

1. Deploy the latest backend hardening code to **Render staging**, selecting the
   intended commit explicitly. Confirm it includes `6b314fe`; a branch merge is
   not a deployment. Do not deploy production.
2. Confirm migration **`0003_request_idempotency`** through guarded staging startup.
   Do not rerun old revisions or use a destructive downgrade.
3. Confirm readiness, verified client TLS and the expected
   `roommateledger_staging` database identity using sanitized checks.
4. Test the latest protected **Vercel staging Preview against that backend**.
5. Test login and access to existing authorized test data without resetting it.
6. Create/read a fictional private expense; verify another member cannot read it.
7. Create a fictional shared expense and check its exact allocations.
8. Check balances and their signs; confirm allocations conserve cents.
9. Test invitations through the current UI/body-based flow. Do not record or
   publish the invitation code.
10. Refresh and confirm persistence and session continuity.
11. Verify financial retries: repeat an expense and a settlement with the same
    retained key/payload, confirm one record each, and confirm changed details
    with that key return 409. Use fictional payments; no money is moved.
12. Update [staging verification](staging.md#verified-staging-checklist) and
    [verification history](verification.md) with the actual deployed commit, date,
    passed checks and failures. Keep the earlier evidence dated.
13. Only then continue the remaining production-readiness work.

For presentation, use the [README](../README.md) and [local demo guide](demo.md).

## Suggested GitHub presentation

Description: **Full-stack roommate expense tracker with private spending, shared
splits, balances and PostgreSQL-backed account security.**

Topics: `fastapi`, `python`, `nextjs`, `typescript`, `postgresql`, `docker`,
`expense-tracker`, `roommates`, `playwright`.

These are recommendations for the About panel. No unverified badges, public demo
URL, production release or license decision is implied.
