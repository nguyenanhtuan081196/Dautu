# Gmail verification resend limits

The `POST /api/auth/send-verification` endpoint applies a per-account 60-second resend cooldown in the Dautu API process. The cooldown is checked before Firebase link generation and Gmail API delivery, so failed provider attempts also consume the cooldown.

The current Render deployment uses one API instance. The in-memory limiter is intentionally simple and does not provide a shared quota across multiple instances or survive a process restart. Before scaling the API horizontally, move this limiter to MongoDB Atlas or another shared atomic counter store.

The endpoint accepts no recipient address from the browser. It derives the recipient only from the verified Firebase ID token, and returns HTTP 429 with a `Retry-After` header when the cooldown is active.
