# Receipt extraction adapter contract

The Python `ReceiptProvider` protocol separates the ledger from OCR/vision vendors. `HttpReceiptProvider` posts raw JPEG, PNG or WebP bytes to the configured HTTPS `RECEIPT_PROVIDER_URL` with a server-side Bearer credential when `RECEIPT_PROVIDER=adapter`. Both URL and key are required. It defaults to a 10-second connect limit and 45-second overall deadline (configurable with RECEIPT_TIMEOUT_SECONDS), rejects redirects/non-200 responses, reads at most 256 KiB and validates strict Pydantic data. Images and credentials must not be logged by the adapter.

The repository also implements the OpenAI Responses adapter. Set `RECEIPT_PROVIDER=openai`, `OPENAI_API_KEY`, and an explicit supported vision `OPENAI_RECEIPT_MODEL`. It sends an image data URL with `store=false` and a strict JSON schema. Refusals, incomplete responses, unreadable required fields and ambiguous output fail safely. No live provider call has been verified without credentials. Manual entry remains fully supported.

Example **contract fixture, not live extraction**:

```json
{
  "merchant": "Fictional Grocery",
  "date": "2026-09-01",
  "currency": "USD",
  "householdId": null,
  "payerId": null,
  "items": [{
    "description": "Rice",
    "rawDescription": "LONG GRAIN RICE",
    "quantity": 1,
    "unitPrice": 1299,
    "amount": 1299,
    "category": "Groceries",
    "confidence": 0.91,
    "scope": "PERSONAL",
    "participants": []
  }],
  "subtotal": 1299,
  "discounts": 0,
  "tax": 104,
  "fees": 0,
  "total": 1403
}
```

All monetary fields are integer cents; quantity/confidence are decimal metadata. Item `amount` and all five receipt totals are required. Fractional/string/null money, unknown fields, missing required money and trailing JSON are rejected rather than coerced. Maximum 100 items. Currency must be USD. The app validates field limits, positive amounts/quantity and confidence range; a draft can be unreconciled so the user can correct extraction errors. Confirmation requires exact item subtotal and `subtotal - discounts + tax + fees = total`.

The adapter must not invent unreadable amounts. Return a non-200 response if extraction cannot meet the contract. It must never decide financial participants: the server discards provider scope, payer and membership suggestions and initializes each item as unassigned/private for review. The user explicitly chooses responsibility. Private defaults do not create ledger records before confirmation.

Receipt images are not persisted. After failure users can enter data manually or upload the photo again to retry. An exact fingerprint match warns only the uploading user, avoiding a cross-user receipt-existence disclosure. Improved merchant/date/total duplicate matching and persistent private images remain roadmap items.

The upload boundary checks both the 8 MiB byte limit and actual Pillow decoding. It rejects mismatched declared MIME types, unsupported/corrupt images, dimensions over 12,000 per side, and more than 24 million pixels before full decoding. An absent MIME type or `application/octet-stream` is accepted only when actual content is supported. Filenames are ignored; database IDs are generated UUIDs. Starlette may spool multipart data into private temporary files, which are closed after use. Protect the host temporary directory and set container memory/concurrency limits. No uploaded image is served, executed, or retained by the app; the external provider's retention policy is a separate deployment responsibility.

Upload state advances `UPLOADED → PROCESSING → NEEDS_REVIEW` or `FAILED`. Processing drafts cannot be edited or confirmed, and delayed extraction updates only a still-processing row. A failed draft can be saved as `NEEDS_REVIEW`; only a reviewed draft can transition to `CONFIRMED`. Confirmation locks the row and writes every expense/allocation in one transaction. Mocked HTTP transport tests cover successful parsing, missing credentials, malformed output, failures, cancellation on timeout, and response size limits. These are boundary tests, not evidence of a live vision-provider call.
