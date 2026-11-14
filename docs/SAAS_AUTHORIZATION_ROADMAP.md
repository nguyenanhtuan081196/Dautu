# SaaS Authentication & Authorization Roadmap

## Current baseline

- Firebase Authentication verifies identity and supplies the bearer token.
- Firestore `allowed_users` is the existing membership compatibility store and is still used by the current web client and Firestore Rules.
- MongoDB Atlas is the operational data store. This phase adds a MongoDB `users` registry without changing crawler collections, scheduler jobs, or price-data pipelines.
- The existing Admin modal in `index.html` is legacy UI. A dedicated, non-linked `admin.html` is planned for Phase 2.

## Phase 1 — Backend account registry and Admin API (this PR)

- Provision existing Firestore allow-list accounts into MongoDB lazily on authenticated API use; the Admin list endpoint also performs a one-time-per-request compatibility sync so existing members are discoverable.
- Store `email`, `firebase_uid`, `created_at`, `expired_at`, `role` and `status` in MongoDB.
- Enforce locked status and subscription expiry centrally in `require_user`. Expired subscriptions return HTTP 401; locked accounts return HTTP 403.
- Add `require_admin` and `GET /api/admin/users`, `PATCH /api/admin/users/{email}`. Only Admin tokens can call these endpoints.
- Keep Firestore role and expiry fields synchronized for compatibility with the current browser application and Firestore Rules.
- Protect the bootstrap Admin from self-lockout/self-demotion and prevent demoting the last active Admin.
- No crawler, scheduler, price collection, Render setting, secret, or production data migration is changed by this PR.

### Account fields

| Field | Meaning |
| --- | --- |
| `email` | Normalized Firebase account email; unique |
| `firebase_uid` | Firebase UID when first seen |
| `created_at` | Membership document creation time, falling back to first API sighting |
| `expired_at` | UTC subscription expiry timestamp |
| `role` | `user` or `admin` |
| `status` | `active` or `locked` |

### Admin API

- `GET /api/admin/users?limit=500` — returns account list, role, status, joined date and expiry.
- `PATCH /api/admin/users/{email}` — accepts one or more of `status`, `role`, `expired_at`.
- Every route requires Firebase authentication and server-side Admin authorization. Hiding a page or button is never treated as a security boundary.

## Phase 2 — Dedicated Admin Dashboard

- Add a separate `admin.html` that is not linked from the public navigation.
- Authenticate with the existing Firebase client session, obtain an ID token, and call only the Admin API.
- Show email, join date, expiry, status and role; add Lock/Unlock, Grant/Revoke Admin and expiry-edit actions.
- Redirect non-Admin users away from the page, while relying on backend 403 checks as the actual protection.
- Add safe loading, empty, error, confirmation and pagination states. Never place service-account credentials or database credentials in frontend code.

## Phase 3 — Complete authorization coverage and auditability

- Maintain an explicit permission matrix for read APIs, account administration and any future operational controls.
- The current price scheduler is an internal background task; there is no public scheduler-trigger endpoint today. If a manual trigger API is added later, it must be Admin-only and protected against duplicate/concurrent runs.
- Add immutable audit records for role, lock and expiry changes (actor, target, before/after, timestamp).
- Add pagination/search, admin action rate limits, last-admin invariants and tests for every protected route.
- Consider token revocation/session invalidation on lock and role changes; API authorization remains checked on every request.

## Phase 4 — Controlled rollout

1. Review CI and the PR diff; merge only after explicit approval.
2. Back up the current Firestore allow-list and MongoDB database before production rollout.
3. Deploy with no crawler-related environment changes; verify the bootstrap Admin and a test User.
4. Confirm 401 for expired users, 403 for locked/non-Admin administrative access, and successful access for active Users.
5. Only after verification, replace the legacy Admin modal with `admin.html` and document the operational recovery procedure.

## Rollback

- Revert the application PR if API authorization behaves unexpectedly.
- Existing Firestore membership documents are retained; this phase does not delete or rewrite price data.
- The `users` collection is additive and can be retained for investigation. Do not bulk-delete it during rollback.
