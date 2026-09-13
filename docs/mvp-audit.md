# Migration and MVP audit — 2026-09-06

The Python backend preserves the implemented ledger and account features. The original Spring implementation is retained as a retired behavioral reference only. The active stack is Next.js/TypeScript → FastAPI/Python → PostgreSQL/Alembic.

Production readiness includes configurable provider timeouts, explicit proxy trust, request IDs, package-build CI and a guarded hosted smoke script. Docker runtime is verified per the owner's report on 2026-09-07. Update on 2026-09-11: the owner verified GitHub CI and private staging, including Mailtrap Sandbox. Public production, real recipient email delivery and live AI remain future work. See the [staging checklist](staging.md#verified-staging-checklist). See [release operations](release-operations.md).

| Area | Implementation and verification |
| --- | --- |
| Accounts and profile | BCrypt compatibility; registration/login/logout, profile persistence, CSRF, session rotation/expiry/revocation |
| Recovery and email | Hashed one-use reset/verification tokens, SMTP abstraction, verification gate, password change and deactivation |
| Households | Owner/member roles, single-use invitations, optional invite email, dated memberships, private-data boundaries |
| Expense engine | PERSONAL/HOUSEHOLD/SELECTED_MEMBERS; equal/fixed/percentage; payer/date/participant validation; exact Decimal cents |
| History | Search/filter/pagination, optimistic edits, creator-only soft deletion, CSV privacy and formula protection |
| Balances and settlements | SQL-derived obligations; tested signs and zero sum; payments recorded by sender only |
| Recurring | Independent templates, locked recording, unique due date and immutable historical expense |
| Analytics | Own allocations, household shared-only totals, six months, categories, previous month and null percentage baseline |
| Receipts | JPEG/PNG/WebP decoding, byte/dimension/MIME bounds, private drafts, recovery, review, reconciliation, atomic and concurrent confirmation |
| AI | OpenAI Responses adapter and generic HTTPS adapter; strict data, bounded body/deadline, safe failure; manual mode without credentials |
| Database | PostgreSQL integration; Alembic fresh setup and Flyway V1/V2/V3 adoption; real restored-copy row preservation |
| Frontend | Preserved React screens; production build and existing five-test browser suite against FastAPI |
| Responsive UI | Existing browser overflow/interaction checks at 375, 430, 768, 1024 and 1440px |
| Python quality | Locked dependencies, Pydantic contracts, SQLAlchemy sessions, centralized financial rules, Ruff and pytest |
| Docker and CI | Python configuration prepared; complete Docker runtime smoke passed per owner report; GitHub CI verified per the owner on 2026-09-11 |
| Documentation | Python setup, architecture, API, migration, deployment, provider and actual verification evidence |

No unsupported banking, card storage, automatic transfers, investing, cryptocurrency or microservices were introduced.

See [verification](verification.md) for observed counts/results and [deployment](deployment.md) for exact external actions. Local test success is not evidence of a deployed service or live provider accuracy.
