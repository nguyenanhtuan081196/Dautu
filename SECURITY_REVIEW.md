# Authentication and Firestore security review

## Scope and verified frontend behavior

The current frontend uses Firebase Authentication email/password sign-in and Firestore collection `allowed_users`, with document IDs derived from lower-cased email addresses.

The current browser code:
- Creates a Firebase Auth account in `handleRegister`, then writes `allowed_users/{email}` with `role: "user"` and a seven-day `expiresAt` value.
- During `onAuthStateChanged`, reads the same document and creates a seven-day user document when it is missing.
- Treats the Firestore document's `role` field as the source for showing the Admin button.
- Lets the Admin UI list all `allowed_users` documents, extend expiry, and delete user documents.
- Fails closed in the browser when the Firestore verification read fails.

No `firestore.rules`, `firebase.json`, or rules deployment configuration was found in the repository during this review. The deployed Firebase rules and current admin account configuration were not accessible, so this review cannot establish whether the live database is currently exploitable.

## Security risk

The browser is an untrusted client. Hiding the Admin button or checking `role === "admin"` in JavaScript is not authorization. Firestore Security Rules must independently protect:
- Listing all `allowed_users` documents.
- Updating expiry dates.
- Deleting users.
- Preventing a normal user from changing their own `role` to `admin`.
- Preventing one user from reading another user's account record.

The registration and auto-provision code legitimately creates a `role: "user"` record from the client. This is safe only if deployed rules restrict self-creation to the authenticated user's own email document, validate the allowed fields and role, and deny client-side role changes. If the deployed rules permit broad writes, privilege escalation may be possible. This is a conditional risk until the live rules are inspected.

## Supplied Firestore Rules review

The owner supplied the deployed rules text for review. Confirmed findings:
- `allow read: if isSignedIn()` permits any signed-in account to list/read every `allowed_users` document.
- Self-registration constrains `role` but does not constrain `expiresAt`; a client can request an arbitrary expiry value.
- Owner updates deny changes only to `role` and `expiresAt`, leaving every other field writable.
- The email allow-list is a server-enforced admin check, which is stronger than trusting the client-side role field. However, the rule should also require `email_verified == true` for the admin identity.

A tightened candidate ruleset is now in `firestore.rules` on this review branch. The frontend now writes expiry as a Firestore Timestamp (including the seven-day initial trial and admin extension), which allows rules to compare expiry against server `request.time`.

Candidate policy changes:
- Users can get only their own account document; only Admin can list the collection.
- Self-registration is limited to the exact three account fields, role `user`, and an expiry no later than seven days after server request time.
- Users cannot update account documents; only Admin can change role/expiry or delete accounts.
- Admin access requires the allow-listed email and a verified Firebase Auth email.
- Watchlists remain restricted by UID.

**Important:** The candidate rules have not been deployed and have not yet been validated in the Firebase Emulator. The current administrator must have a verified email before deployment, or Admin list/update/delete operations will be denied. Existing account expiry strings must be migrated to Firestore Timestamps before applying these rules. Test existing account, trial signup, Admin list, extension, and deletion flows first.

## Recommended target policy

Use Firebase Authentication identity for user ownership and a trusted authorization source for administrator privileges.

Preferred long-term design:
1. Key account documents by Firebase UID (`users/{uid}`), not email address.
2. Allow a signed-in user to read only their own account document.
3. Allow public trial registration to create only a constrained `user` record for their own UID; never allow clients to set or modify admin privileges.
4. Grant administrator access through Firebase Auth custom claims assigned only by a trusted Admin SDK process or a carefully controlled Firebase Console migration.
5. Require the admin claim in Firestore Rules for listing, updating, extending, and deleting account records.
6. Validate expiry using a consistent timestamp representation and enforce expiry in trusted authorization rules or backend code, not only in client-side date comparisons.
7. Add Firestore Rules emulator tests for unauthenticated access, own-account access, cross-account reads, self-promotion attempts, user-list queries, admin extension, and admin deletion.

## Migration constraints — do not deploy blindly

The current app uses `allowed_users/{lowercase-email}` and stores expiry as an ISO string. Switching to UID documents or custom claims changes the data model and may remove Admin access until the existing administrator receives the custom claim.

Before deploying any new rules:
- Export and inspect the currently deployed Firestore Rules.
- Identify the current administrator UID(s) through a trusted Firebase console or Admin SDK process.
- Back up the `allowed_users` collection.
- Decide whether the existing email-keyed documents will be migrated to UID-keyed documents or temporarily supported by a narrow compatibility rule.
- Run the complete rules test suite in the Firebase Emulator.
- Deploy rules separately from the frontend and verify existing admin and trial-user flows.

Do not add a permissive fallback rule such as `allow read, write: if request.auth != null`; it would defeat the protections above.

## Data publication note

The generated JSON and static website files committed to a public GitHub Pages repository are public assets. Firebase login can gate the user interface, but it cannot make publicly hosted JSON private. If screener data is intended to be paid/private, move it behind an authenticated backend or private storage with server-side authorization rather than relying on the login overlay.

## Review status

This is a code-level review and migration plan, not a claim that deployed Firebase configuration has been changed. No production Firestore Rules were replaced because the live rules and admin identity were not available for a safe migration.
