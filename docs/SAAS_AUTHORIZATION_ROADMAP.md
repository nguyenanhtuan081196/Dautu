# SaaS Authentication & Authorization Roadmap

## Current code audit

- Firebase Authentication already verifies ID tokens on the API and the browser obtains Firebase ID tokens for API requests.
- FastAPI currently has a single `require_user` dependency protecting all data endpoints. It distinguishes only the bootstrap Admin and ordinary User; there is no Guest tier and no MongoDB account-state check.
- The current authorization source is Firestore `allowed_users`. Ordinary accounts are created by the browser with a seven-day `expiresAt` value when no membership document exists.
- The existing browser Admin modal reads and writes Firestore directly. It is a transitional legacy workflow, not yet a MongoDB-backed Admin Dashboard.
- MongoDB Atlas is already used for market data; the `users` collection does not yet exist in the main branch.

## PR 1 — MongoDB user registry and three-role middleware (this PR)

- Add the `users` collection and indexes for unique email, unique sparse Firebase UID, and role/status lookup.
- Verify Firebase ID tokens exactly as before, then resolve account status and permissions from MongoDB on every protected API request.
- On first access only, migrate an existing Firestore `allowed_users` record into MongoDB. MongoDB becomes authoritative after that initial migration; Firestore is not re-read to overwrite the MongoDB role on every request.
- Firebase identities without a legacy membership are provisioned as `guest` with active status and no subscription expiry.
- Preserve the existing fixed bootstrap Admin only when its legacy Firestore record explicitly has `role=admin`.
- `guest`: only basic status and stock-list/stock-detail endpoints.
- `user`: authenticated, verified, active, non-expired account; access to the full user data API.
- `admin`: full API access, subject to active status; bootstrap Admin retains the existing email-verification exception.
- Locked accounts receive HTTP 403. Expired accounts receive HTTP 401. A MongoDB authorization-store failure fails closed with HTTP 503.
- No crawler, scheduler, realtime collector, price schema, Render configuration, secret, or production data is changed.

### MongoDB user document

| Field | Type | Meaning |
| --- | --- | --- |
| `email` | string | Normalized Firebase email; unique |
| `firebase_uid` | string | Firebase UID; unique sparse index |
| `created_at` | datetime | Membership creation time or first-seen time |
| `expired_at` | datetime/null | Subscription expiry; null for guest/bootstrap Admin |
| `role` | string | `guest`, `user`, or `admin` |
| `status` | string | `active` or `locked` |
| `created_source` | string | `firestore_migration` or `firebase_guest` |
| `updated_at` | datetime | Last account registry update |

### Role matrix

| API capability | Guest | User | Admin |
| --- |:---:|:---:|:---:|
| `GET /api/status` | Yes | Yes | Yes |
| `GET /api/stocks` and `GET /api/stocks/{symbol}` | Yes | Yes | Yes |
| Screener, simulations, history, financials, AI analysis, realtime and metadata | No | Yes | Yes |
| Account administration | No | No | Future PR 2 |

## PR 2 — Admin API and Dashboard

- Add Admin-only endpoints for listing users, locking/unlocking, changing expiry and granting/revoking Admin.
- Protect the last active Admin and write audit events for every administrative change.
- Add a separate `admin.html`, authenticated through the existing Firebase session and backed exclusively by Admin APIs.
- Replace direct browser writes to Firestore `allowed_users`.
- Update the current browser login flow: it currently creates a seven-day Firestore `user` record for every new account. It must be changed to support Guest accounts and use the backend role response, otherwise the new Guest role is not reachable through the existing UI.
- Keep all service-account and MongoDB credentials server-side.

## PR 3 — Expiry automation

- Add a bounded background task to the existing Scheduler lifecycle (not a new continuously running service).
- Periodically query only users with `role=user`, `status=active`, and `expired_at <= now`; mark them expired/locked with an idempotent update.
- Authorization remains request-time enforced; the background sweep is for account state, reporting and UI visibility, not the only security control.
- Run in small batches and short timeouts so the 512 MB Render Free service and market-data jobs are not starved.
- Do not let the expiry sweep touch crawler state or price collections.

## Rollout and safety

1. Review CI and the PR diff. Merge only after explicit approval.
2. Deploy only after the account migration and compatibility path have been reviewed; do not change Render secrets for this work.
3. Verify existing Admin/User accounts, new Guest accounts, locked accounts, expired accounts and MongoDB outage behavior.
4. Only then proceed to the Admin UI and expiry automation PRs.
5. Back up Firestore `allowed_users` and MongoDB before production rollout. No destructive migration is part of PR 1.

## Transitional compatibility note

The existing browser Admin modal still edits Firestore directly. Because PR 1 makes MongoDB authoritative after first migration, those legacy edits will not update already-migrated MongoDB records. Do not use the legacy modal to change roles or expiry after PR 1 is deployed; PR 2 replaces it with Admin APIs and the dedicated dashboard. This is explicitly called out to avoid a false impression that the old and new account stores remain bidirectionally synchronized.


## Emergency registration hardening (security follow-up)

- Firestore Rules deny all client writes to `allowed_users` except the fixed Admin identity. User-owned read access remains unchanged; listing remains Admin-only.
- New Firebase registrations are provisioned as Guest by the API. They do not need, and must not create, a Firestore membership document.
- A legacy Firestore `role=user` record is eligible for migration only when it contains `created_by: "nguyenanhtuan081196@gmail.com"` and a valid timestamp `expiresAt`. Records without this explicit provenance (including old records whose creator cannot be proven) are migrated as Guest with no expiry.
- The fixed bootstrap Admin remains recognized only for the configured Admin email and an explicit legacy `role=admin` record.
- Firebase ID-token `email_verified` is checked at request time. An unverified identity cannot access User APIs even if MongoDB contains an active User record.
- Existing MongoDB accounts previously tagged `created_source=firestore_migration` are also rechecked against Firestore once; unverifiable records are immediately downgraded to Guest. Explicit Admin role grants or subscription extensions are tagged `created_source=admin_api` and are not mistaken for legacy self-registration.
- This migration is intentionally fail-closed: historical Firestore User records without provenance may need the Admin to re-grant User access through the MongoDB-backed Admin Dashboard after rollout.
