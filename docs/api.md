# API guide

All routes use `/api`. JSON money is integer cents; dates are `YYYY-MM-DD`; identifiers are UUIDs. Errors return `{code,message}`. Mutations require the current session's CSRF token: fetch `GET /auth/csrf`, then send the returned `headerName`/`token` with the session cookie. Logout clears the session. Never cache private responses.

FastAPI generates development documentation at `/docs` and `/openapi.json`. Both are disabled publicly in production. Pydantic rejects malformed or fractional monetary input with HTTP 400. Authentication uses a PostgreSQL-backed HttpOnly `JSESSIONID` cookie; there are no bearer tokens in localStorage. Cookie/session state survives API restarts, and account changes revoke prior sessions.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health`, `/auth/csrf` | Health and CSRF bootstrap |
| POST | `/auth/register`, `/auth/login` | `{email,password,name}`; name required for registration |
| POST | `/auth/logout` | Invalidate session |
| GET | `/auth/me` | Safe profile projection |
| PATCH | `/profile` | `{name,diet,timezone,notifications}` |
| GET | `/auth/capabilities` | Email availability and verification policy |
| POST | `/auth/forgot-password` | `{email}`; generic response, optional email delivery |
| POST | `/auth/reset-password` | `{token,password}`; single-use link, revokes prior sessions |
| POST | `/auth/verify-email` | `{token}`; single-use verification link |
| POST | `/account/resend-verification` | Signed-in account requests another email |
| POST | `/account/password` | `{currentPassword,password}`; changes password and signs out |
| POST | `/account/deactivate` | `{password}`; preserves financial history and signs out |
| GET / POST | `/households` | List current households / create `{name}` |
| PATCH | `/households/{id}` | Owner renames `{name}` |
| GET | `/households/{id}/members` | Dated membership history, names and diets; no emails |
| DELETE | `/households/{id}/members/{membership}` | Owner ends non-owner membership today |
| POST | `/households/{id}/invitations` | Owner creates single-use token |
| POST | `/households/{id}/invitations/email` | Owner emails an invitation using `{email}` |
| POST | `/invitations/accept` | Authenticated user joins using JSON `{token}` |
| POST | `/invitations/{token}/accept` | Deprecated compatibility route; keep codes out of URLs |
| GET | `/households/{id}/activity` | Latest 50 shared events |
| GET / POST | `/expenses` | Paginated list / create expense |
| GET / PATCH / DELETE | `/expenses/{id}` | Authorized read, creator edit/soft-delete |
| GET / POST | `/recurring` | List templates / create template |
| PATCH | `/recurring/{id}` | Creator updates template |
| POST | `/recurring/{id}/record` | Creator materializes next due occurrence |
| GET | `/households/{id}/balances` | Derived net positions |
| GET / POST | `/households/{id}/settlements` | Latest 100 repayments / record payment sent by caller |
| GET | `/analytics/personal?month=2026-09` | Caller responsibility and trends |
| GET | `/households/{id}/analytics?month=2026-09` | Shared totals only |
| GET | `/receipts/capabilities` | Whether an extraction adapter is configured |
| GET / POST | `/receipts` | Latest 50 private receipts / create manual draft |
| POST | `/receipts/extract` | Multipart `file` upload |
| GET / PUT | `/receipts/{id}` | Owner reads/replaces draft |
| POST | `/receipts/{id}/confirm` | Atomically finalize all items |
| GET | `/export/expenses?householdId=&from=&to=` | Private by default, authorized shared export when household specified |
| GET | `/export/settlements?householdId=` | Authorized household CSV |

Financial creation requests (`POST /expenses` and `POST /households/{id}/settlements`)
use `Idempotency-Key`, required in production and supplied by the first-party forms.
Retain the same key for an uncertain request: matching details replay the original
result, changed details return 409, and expired keys cannot be reused. See the
[retry/retention contract](production-hardening.md#financial-request-retries-h2).
Keys are not authorization and do not replace the session or CSRF checks.

Expense input:

```json
{
  "title": "Electricity", "merchant": "", "amount": 16000,
  "category": "Utilities", "scope": "HOUSEHOLD",
  "householdId": "household-uuid", "payerId": "payer-uuid",
  "date": "2026-09-01", "splitMethod": "EQUAL",
  "participants": [], "values": {}, "notes": ""
}
```

For `HOUSEHOLD`, the server resolves everyone applicable on `date`. For `SELECTED_MEMBERS`, supply explicit participant UUIDs. For `PERSONAL`, householdId must be null; caller is owner/payer/sole participant. `FIXED` values map each participant UUID to cents; `PERCENTAGE` values map each participant UUID to basis points totaling 10,000. Edits require the current numeric `version`; scope and household are immutable. Personal scope always uses an equal single-person split.

List query: optional `householdId` (otherwise private expenses only), `scope`, `search` (title/merchant), `category`, `from`, `to`, `payer`, `participant`, `min`, `max`, `page`. Page size is fixed at 25; response contains `items,total,page,pageSize`. Receipt/recurrence/settlement-state filtering is a future extension.

Recurring input: `{expense: <expense input>, nextDue, frequency: "MONTHLY"|"WEEKLY"|"YEARLY", active}`. Settlement input: `{fromUser,toUser,amount,method,date}`; `fromUser` must equal the caller. Receipt PUT uses the [provider draft schema](receipt-provider.md), including explicit per-item scopes/participants chosen by the user.
