# API security controls

The FastAPI service is designed to sit behind Render's public web-service load balancer. This document records the application-level controls and their current boundaries.

## Authentication and authorization

- Every `/api/*` route depends on `require_user`.
- Firebase ID tokens are verified with revocation checking.
- The token must contain a verified email address.
- The lower-cased email must have an `allowed_users/{email}` Firestore record.
- Ordinary users require role `user` and a future `expiresAt` timestamp.
- The `admin` role is accepted only for the fixed administrator email in `app/api/main.py`.
- Firestore Admin SDK access is separately authorized in the API; client-side Firestore Rules do not protect Admin SDK reads.

## Host and CORS policy

- `TrustedHostMiddleware` validates the HTTP Host header.
- On Render, `RENDER_EXTERNAL_HOSTNAME` is automatically included.
- Add any API custom domain to `API_ALLOWED_HOSTS` as a comma-separated list of hostnames only (no scheme or path), for example `api.example.com`.
- `CORS_ALLOWED_ORIGINS` is a comma-separated list of exact frontend origins, including scheme, for example `https://owner.github.io`. If it is empty, CORS remains disabled.
- CORS permits only GET/OPTIONS and Authorization/Content-Type headers; credentialed CORS is disabled.

## Rate limiting

- Email-verified Firebase identities are limited to 120 API requests per 60-second fixed window. The quota is applied after token verification but before the Firestore membership lookup, reducing repeated authorization-store reads.
- Exceeded requests receive HTTP 429 and a `Retry-After` header.
- The counter is in-process and keyed by verified Firebase UID, so it does not trust client-supplied `X-Forwarded-For` headers.
- **Scaling boundary:** this is a single-process/single-instance guard, not a distributed quota. Before running multiple API instances or workers, replace the in-memory counter with shared storage such as Render Key Value/Redis. Do not claim cross-instance enforcement until that migration is tested.

## Response data minimization

MongoDB API reads use explicit field allowlists for stock, screener, and AI documents. Internal identifiers and unreviewed fields such as run IDs or raw provider payloads are not returned by those endpoints. History and financial report routes retain their purpose-specific projections.

## Reverse proxy

Render terminates inbound TLS and forwards requests to the web service over HTTP. The application does not independently trust arbitrary forwarding headers for authorization or rate-limit identity. Do not add `--forwarded-allow-ips=*` or derive identity from `X-Forwarded-For` without validating the Render proxy trust boundary. Revisit this before custom proxying or non-Render deployment.

## Verification checklist

- Run `python -m unittest discover -s tests -p 'test_api_auth.py' -v`.
- Run the complete Python tests and Quant Screener smoke test.
- Run the Firestore Rules Emulator suite.
- Confirm the deployed API hostname is accepted and an unrelated Host is rejected.
- Confirm the frontend's exact origin is configured in `CORS_ALLOWED_ORIGINS`.
- Verify 429 behavior and confirm that shared storage is in place before scaling beyond one API process.
- Do not deploy Firebase Rules, mutate Atlas data, or create Render resources as part of this code-only review.
