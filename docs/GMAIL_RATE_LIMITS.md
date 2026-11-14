# Gmail verification rate limiting (MongoDB Atlas)

The verification endpoint stores rate-limit counters in the shared MongoDB
collection `email_rate_limits`; it no longer keeps verification-send state in
Python process memory.

## Limits

- Per account: 1 send attempt per 60-second UTC fixed window.
- Per account: 3 send attempts per 3,600-second UTC fixed window.
- Per source IP: 10 attempts per minute and 30 per hour. The wider IP quota
  avoids blocking several legitimate household/mobile users behind one NAT.
- Attempts are counted before Firebase link generation/SMTP delivery. Failed
  provider attempts also consume quota, preventing retries from bypassing limits.
- A rejected request returns HTTP 429 with a `Retry-After` header.

Counters are incremented with MongoDB `$inc` using deterministic document IDs,
so concurrent requests and separate Render instances update the same counter.
Only SHA-256 digests of account email and IP address are stored. A TTL index
removes counters after the window closes plus a one-hour retention period.

## Deployment

No new Render secret is required. The API uses the existing `MONGODB_URI` and
`MONGODB_DATABASE` settings. Application startup creates the TTL index
idempotently through `ensure_indexes()`.

The counters persist across API process restarts because MongoDB Atlas is the
source of truth. This PR does not change Firebase account authorization,
Firestore rules, or the security logic merged in PR #48.
