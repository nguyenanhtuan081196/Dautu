# Dautu – Current System Architecture

Last reviewed: 2026-11-14

This document describes the production-oriented architecture after moving operational data and scheduled price collection to Render + MongoDB Atlas. It is an operational map, not a claim that every external dashboard setting has been independently verified.

## 1. System at a glance

```text
GitHub repository (source + CI + frontend)
        |                         |
        | Render auto-deploy      | GitHub Actions
        v                         | (CI / Pages / manual recovery)
Render: dautu-api                 |
FastAPI + Uvicorn                 |
- authenticated read API         |
- in-process price Scheduler     |
- bounded background batches     |
        |                         |
        v                         |
MongoDB Atlas / dautu <-----------+
operational source of truth
stocks, price_history, financial_reports,
screener_results, ai_analyses, simulations,
pipeline_runs, dataset_versions, app_metadata

Browser frontend (GitHub Pages static site)
        |
        +--> authenticated Render API --> MongoDB Atlas

UptimeRobot (external monitor) --> public Render /healthz
```

**Source of truth:** MongoDB Atlas is the durable operational data store. Render's filesystem and GitHub are not used as the live stock-data database.

## 2. Render API and deployment

- Render web service: `dautu-api`, FastAPI/Uvicorn, production origin `https://dautu-api.onrender.com`.
- Merged commits on `main` are deployed by Render Auto-Deploy; confirm each deployment reaches **Live** in Render.
- `GET /healthz` checks Atlas connectivity and returns HTTP 200 only when the database is reachable.
- The static frontend is deployed by `.github/workflows/pages.yml`; its API origin is configured by the `DAUTU_API_BASE_URL` Actions variable.
- Firebase Authentication provides browser sign-in. The API verifies Firebase ID tokens and checks membership in Firestore.

## 3. Render Free Scheduler and automatic Metadata

The price Scheduler is an **in-process asyncio task inside the FastAPI web service**, not a paid Render Cron Job or a separate worker.

- FastAPI startup creates the scheduler task when `PRICE_SCHEDULER_ENABLED` is true (default true); shutdown cancels it.
- It polls every 60 seconds by default (`PRICE_SCHEDULER_POLL_SECONDS`) and schedules Monday–Friday at `PRICE_SYNC_TIME`, default **20:30 Asia/Ho_Chi_Minh**.
- The crawler runs via `asyncio.to_thread`; it processes 5 symbols per batch by default and is capped at 10 (`PRICE_BATCH_SIZE`).
- Atlas `pipeline_runs` stores durable checkpoints and a 30-minute lease. Partial/failed runs are retried from confirmed saved symbols.
- **Metadata is Scheduler-owned.** After a complete successful crawl, the Scheduler calls `ensure_price_metadata` to publish `app_metadata/_id=price_sync` from the durable successful pipeline run.
- If the process stops after the crawl commits success but before Metadata is written, the next poll/restart detects the successful `pipeline_runs` record and repairs Metadata without rerunning the crawler.
- If a crawl is partial or fails, Metadata is not published for that attempt; the date remains eligible for recovery. Once recovery completes successfully, Metadata is published automatically.
- Metadata writes are idempotent: the same run is not rewritten; a newer timestamp is never replaced by an older recovery; an older Metadata record advances to the newer successful run.
- `.github/workflows/backfill-price-metadata.yml` remains available as a manual emergency fallback. It is not part of the normal daily data path.

### Render Free limitations

- The Scheduler runs only while the Render web process is alive. Free services may sleep or restart, so exact wall-clock execution is not guaranteed.
- On startup/wake, the scheduler recovers the latest due weekday from Atlas. UptimeRobot health pings can provide monitoring/wake-up traffic, but do not guarantee continuous process uptime or exact schedule execution.
- Keep the service at one instance unless a distributed scheduler/lock strategy is introduced; Atlas leases prevent duplicate claims for the same run.
- Memory use is constrained by the 512 MB Free instance: bounded batches, background threads and garbage collection are intentional.

## 4. MongoDB Atlas

Atlas database: `dautu`. Operational collections include:

- `stocks`, `price_history`, `financial_reports`
- `screener_results`, `ai_analyses`, `simulations`
- `pipeline_runs`, `dataset_versions`, `app_metadata`

The API reads live data from Atlas; Render's local filesystem is not the operational database.

## 5. UptimeRobot

UptimeRobot is configured outside this repository. Its intended role is to monitor the public `/healthz` endpoint. Dashboard URL, probe interval and current monitor status must be verified in the UptimeRobot account; this repository cannot prove those external settings. A health ping is not a guarantee that the in-process Scheduler remains awake at the scheduled minute.

## 6. GitHub Actions responsibilities

- `python-tests.yml`: Python tests, compile checks, Quant Screener smoke test and Firestore Rules Emulator.
- `render-production-smoke.yml`: post-CI production `/healthz` check.
- `pages.yml`: build and publish the static frontend.
- `mongodb-import.yml`: manual legacy JSON-to-Atlas migration (dry-run/apply with confirmation).
- `mongodb-verify.yml`: manual Atlas connectivity/collection verification.
- `backfill-price-metadata.yml`: manual emergency Metadata recovery only; normal daily publication is handled by Render Scheduler.

GitHub Actions does **not** run the regular daily price crawler.

## 7. Configuration names (never store secret values here)

- `MONGODB_URI`, `MONGODB_DATABASE` (normally `dautu`)
- `PRICE_SCHEDULER_ENABLED`, `PRICE_SCHEDULER_POLL_SECONDS`
- `PRICE_SYNC_TIME`, `PRICE_BATCH_SIZE`, `PRICE_SESSIONS`
- Firebase Admin service-account configuration (secret JSON or supported file configuration)

Never commit database URIs, Firebase private keys or other credentials.


## 8. Optional SSI realtime market-data collector

The realtime feature is opt-in and disabled unless `ENABLE_REALTIME_CRAWLER=true`.
When enabled, a separate in-process background task uses the official SSI FastConnect
Python SDK (`ssi-sdk`) to connect to SSI's market-data WebSocket. API request
handlers never call SSI; the authenticated `/api/realtime` and
`/api/realtime/{symbol}` endpoints read only from MongoDB Atlas.

- SSI market-data stream is event-driven (push), not a REST polling loop. The
  collector subscribes to the configured Atlas stock universe in groups of
  `SSI_STREAM_BATCH_SIZE` (default 25, capped at 50); it processes at most
  `REALTIME_MAX_SYMBOLS` symbols (default 100).
- Incoming trade events are coalesced by symbol in a bounded in-memory queue
  (default 2,000 entries) and flushed to `realtime_prices` in bulk every
  `REALTIME_FLUSH_SECONDS` (default 2 seconds). Each symbol has one latest
  document, upserted by symbol.
- The collector runs on weekdays during Vietnam cash-equity sessions:
  09:00–11:30 and 13:00–15:00. It does not intentionally stream during the
  lunch break or weekends. After 15:00 it snapshots the latest day's prices
  into D1 documents in `price_history`.
- A disconnect/error is retried with exponential backoff (5 seconds to a
  maximum of 120 seconds). A full queue drops the oldest queued tick to
  prioritize the latest price. This is a latest-price cache, not a complete
  exchange tick archive.
- Required Render secrets: `SSI_CLIENT_ID`, `SSI_API_KEY`,
  `SSI_API_SECRET`. Never commit these values. The SSI account must be
  approved for FastConnect market-data streaming. Market-data streaming is
  configured without trading callbacks or order permissions.
- Other safe controls: `ENABLE_REALTIME_CRAWLER=false` (default/off),
  `SSI_STREAM_BATCH_SIZE=25`, `REALTIME_MAX_SYMBOLS=100`,
  `REALTIME_QUEUE_MAXSIZE=2000`, and `REALTIME_FLUSH_SECONDS=2`.
- Keep one Render instance. Multiple instances would require a distributed
  collector lease/leader-election mechanism before enabling this feature.
- Render Free may sleep/restart, so the in-process collector is best-effort and
  cannot guarantee continuous realtime delivery while the process is stopped.
  The daily D1 snapshot is based on the latest received SSI trade event; if no
  event was received for a symbol that day, that symbol is not finalized from
  the realtime collection.
