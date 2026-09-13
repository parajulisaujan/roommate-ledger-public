# Local demo video

The recorder runs RoommateLedger in disposable local Docker containers and records
only the browser. It uses fictional data and no production/provider credentials.
It does not connect to hosted staging or verify a production deployment.

## Regenerate the walkthrough

Prerequisites: Docker with Linux containers, Node.js 24, the locked frontend
dependencies and the matching Playwright Chromium build. Initial builds need
package/registry access. Optional MP4 conversion uses an existing `ffmpeg` with
`libx264`; no converter is downloaded automatically.

From the repository root:

```sh
cd frontend
npm ci
npx playwright install chromium
cd ..
node frontend/scripts/record-demo.mjs --check
node frontend/scripts/record-demo.mjs
```

The script selects a free loopback browser port. Build/startup time is followed by
about 90?120 seconds of recording. Existing local app/database instances can stay
running.

## Fictional data and mail

[The demo fixture](../frontend/scripts/demo-seed.py) creates Irving Apartment with
four fictional roommates: Saujan Parajuli, Sejal Khadka, Bikash Gurung and Binod
Tiwari. Display addresses use the reserved `example.test` domain; they cannot be
mistaken for a real inbox. Three months of modest grocery, utility, household-supply
and dining expenses provide useful reports. The UI adds a private coffee and a
shared grocery expense, including an exact-cent remainder.

The fixture requires development mode, an explicitly named disposable demo
database and empty account tables. It calls the ordinary financial services;
it changes no application security or financial rules. Login and UI writes use
normal session, authorization and CSRF paths.

The existing [local SMTP sink](../frontend/scripts/test-mailbox.mjs) runs on the
API container's loopback network, accepts only fictional recipients and stores
messages in memory. A preflight sends a fictional message and verifies capture.
No email is relayed. No external SMTP credentials or provider integrations are
configured. The generated local login password stays masked and is never printed.

## What viewers see

A short title, login, dashboard, household members, private expense, shared expense,
equal split, balances and personal/household reports. The recording ends on the
normal dashboard after a short hold. It is a silent product walkthrough with
simple captions, no narration and no music. No operational status cards, terminal
windows, provider dashboards, invitation codes or environment contents appear.

## Isolation and output

Each run creates uniquely named API, PostgreSQL, frontend and SMTP-sink containers.
The API/database use an internal network without published ports or external
routing. Only the frontend also joins a bridge so its browser port can be published
on `127.0.0.1`. Frontend outbound routing exists, but no provider integration is
configured and telemetry is disabled. Browser requests are restricted to its
local origin. The recorder never loads the root `.env` or forwards parent secrets.

Output is ignored by Git:

```text
artifacts/demo/<timestamp>-<run-id>/
  roommateledger-demo.webm
  roommateledger-demo-poster.png
  recording.json
  roommateledger-demo.mp4    # only if optional conversion succeeds
```

The video is 1280?720. Actual duration must be 90?120 seconds for a successful run.
Metadata records duration, bytes, chapters and fictional/local status without
credentials or session data. The poster is a clean dashboard capture.

The script attempts to remove only its uniquely named containers, database volume,
networks and image tags after success or handled failure. A hard process kill or
Docker shutdown may prevent cleanup. Inspect abandoned resources by their unique
`ledger-demo-` prefix; never broadly prune volumes or reset another ledger.

Keep `artifacts/` ignored in this repository. Review at least eight frames and the
final screen before publishing a new recording elsewhere. A separately reviewed,
reasonably sized copy may be hosted by the portfolio website.

## Validation

From `frontend/`, run `node --check scripts/record-demo.mjs`, `npm run lint` and
`npm run typecheck`, then run the full recorder. Check the fixture with Ruff.
Failures report fixed stages and suppress raw command/provider output. Correct
script/UI mismatches without weakening application checks.

The [verification history](verification.md) separates earlier recordings and local
tests from hosted staging checks. The [project summary](project-summary.md) records
what remains before public production.


## Reviewed recording ? 2026-09-12

The current walkthrough passed all UI assertions and the local SMTP capture check.
It is **98.16 seconds**, **1280?720**, and **5,086,495 bytes** (about 5.09 MB).
Ten sampled frames, including the final frame, were reviewed. The intended four
names appear, and the final screen is the dashboard. No previous placeholder
names, operational status cards, numeric ratings or secret values appeared in the
reviewed frames. The video is silent. MP4 was not created because `ffmpeg` was not
available; WebM and a PNG poster are ready for the portfolio.
