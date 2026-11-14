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
