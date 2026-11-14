# Dautu – Current System Architecture

Last reviewed: 2026-11-14

This document describes the production-oriented architecture after moving operational data and scheduled price collection to Render + MongoDB Atlas. It is an operational map, not a claim that every external dashboard setting has been independently verified.

## 1. System at a glance

```text
                    GitHub repository (main)
                   source code + CI + frontend
                     |                 |
             Render auto-deploy     GitHub Actions
                     |             (tests / Pages /
                     v              manual DB tools)
             Render: dautu-api
             FastAPI + Uvicorn
             Free web service
             - authenticated read API
             - in-process price Scheduler
             - bounded background batches
                     |
                     | MongoDB connection (MONGODB_URI)
                     v
              MongoDB Atlas / dautu
              operational source of truth
              stocks, price_history, financial_reports,
              screener_results, ai_analyses, simulations,
              pipeline_runs, dataset_versions, app_metadata
                     ^
                     |
        Browser frontend (GitHub Pages static site)
        index.html + login.html + chart library
        Firebase Authentication / Firestore membership

External availability monitor (UptimeRobot, configured outside this repo)
        └── probes the public Render /healthz endpoint
```

**Source of truth:** MongoDB Atlas is the durable operational data store. Render's filesystem and GitHub are not used as the live stock-data database. GitHub stores application source, frontend assets, migration snapshots and CI definitions.

## 2. Runtime and deployment

- **API service:** Render web service `dautu-api`, FastAPI/Uvicorn, production origin `https://dautu-api.onrender.com`.
- **Deployment source:** the `main` branch of this repository. Render Auto-Deploy is expected to deploy merged commits; confirm each deployment reaches **Live** in the Render dashboard.
- **Health probe:** `GET /healthz` (also supports HEAD) pings MongoDB and returns HTTP 200 with `{"status":"ok"}` only when Atlas is reachable; otherwise it returns HTTP 503.
- **Frontend:** static website deployed by `.github/workflows/pages.yml` to GitHub Pages. The workflow builds an allowlisted site from `index.html`, `login.html`, `lightweight-charts.js`, `CNAME` and a generated `api-config.js`. The API origin is supplied by the Actions variable `DAUTU_API_BASE_URL` (defaults to the production API origin).
- **Authentication:** Firebase Authentication provides browser sign-in; the API verifies Firebase ID tokens with Firebase Admin and checks membership in Firestore. Stock and metadata endpoints are authenticated. The health probe is intentionally public and reveals no infrastructure detail.

## 3. Price Scheduler on Render Free

The price Scheduler is an **in-process asyncio task inside the FastAPI web service**, not a Render Cron Job or a separate worker.

- Startup in `app/api/main.py` creates the task when `PRICE_SCHEDULER_ENABLED` is true (default: true). It is cancelled during graceful shutdown.
- `app/pipeline/scheduler.py` polls every 60 seconds by default (`PRICE_SCHEDULER_POLL_SECONDS`) and schedules the latest due **Monday–Friday** run at `PRICE_SYNC_TIME`, default **20:30 Asia/Ho_Chi_Minh**.
- The crawler is called with `asyncio.to_thread`, so blocking VNstock/pandas work does not run on the ASGI event loop and API requests can continue to be served.
- `app/pipeline/price_job.py` processes symbols in bounded batches: default 5, configurable through `PRICE_BATCH_SIZE`, clamped to 1–10. It releases Python memory between batches with garbage collection.
- Each scheduled run is recorded in Atlas `pipeline_runs` using a date-based run ID. A 30-minute lease prevents duplicate workers from claiming an active run. Successful dates are not repeated; after a process restart, the Scheduler checks Atlas and can recover the latest due weekday that has not succeeded.
- The job writes per-symbol data and its final outcome directly to Atlas. The latest price result is written to `app_metadata` under `_id: "price_sync"`.

### Free-instance limitation

The Scheduler exists only while the Render web process is running. A Free instance can sleep or restart; an in-process timer cannot execute while the process is stopped. On restart, the Atlas run ledger supports recovery of the latest due weekday, but this is not the same as an always-on, independently hosted scheduler. Do not treat an HTTP health probe as proof that a scheduled price job completed.

Relevant environment settings (values belong in Render's Environment page, never in Git):
- `MONGODB_URI` – Atlas connection string (secret).
- `MONGODB_DATABASE` – database name; defaults to `dautu`.
- `FIREBASE_SERVICE_ACCOUNT_JSON` – Firebase Admin service-account JSON (secret).
- `PRICE_SCHEDULER_ENABLED` – defaults to `true`.
- `PRICE_SYNC_TIME` – defaults to `20:30` Vietnam time.
- `PRICE_SCHEDULER_POLL_SECONDS` – defaults to 60 seconds, minimum 15.
- `PRICE_BATCH_SIZE` – defaults to 5, clamped to 1–10.
- `PRICE_SESSIONS` – crawler lookback, defaults to 30.

## 4. MongoDB Atlas data model

Database: `dautu` (selected by `MONGODB_DATABASE`).

| Collection | Purpose |
| --- | --- |
| `stocks` | Current per-symbol fundamentals and latest price fields |
| `price_history` | D1/W1/MN history, keyed by symbol + interval + date |
| `financial_reports` | Balance sheet, income statement and cash-flow reports |
| `screener_results` | Current quantitative screener output |
| `ai_analyses` | AI analysis by symbol |
| `simulations` | Historical-return / quarterly-mean simulation results |
| `pipeline_runs` | Durable job status, progress, checkpoints and leases |
| `dataset_versions` | Dataset publication/version metadata |
| `app_metadata` | UI timestamps and other small metadata values |

The website reads the API; it does not read these collections directly.

### Price update timestamp

1. The price job completes (or records a failed/partial outcome).
2. It writes `last_updated`, `status`, symbol counts and run ID to `app_metadata` document `_id: "price_sync"`.
3. The authenticated `GET /api/metadata` route reads that document and sends no-cache response headers.
4. The frontend's `loadPriceMetadata()` displays `last_updated` in `Asia/Ho_Chi_Minh` time.

A missing or unreadable metadata document returns safe fallback values; it does not block the stock list API.

## 5. UptimeRobot / external availability monitoring

UptimeRobot is an external monitor and is configured outside this Git repository. The intended probe target is the public Render health endpoint:

`https://dautu-api.onrender.com/healthz`

The endpoint checks Atlas connectivity, so an alert can reveal an API/database availability problem. A periodic monitor request may wake a sleeping Render Free instance, but it does **not** execute the price crawler, does not prove the Scheduler is enabled, and is not a guarantee that the process stays awake at 20:30. The exact monitor URL, interval, alert contacts and current status must be verified in the UptimeRobot dashboard; they are not represented as code configuration here.

## 6. GitHub Actions responsibilities

GitHub Actions is for code quality, frontend publishing, controlled migration/verification and explicitly manual maintenance—not the recurring production price schedule.

| Workflow | Trigger / responsibility |
| --- | --- |
| `Python tests` | Pull requests and pushes to `main`; Python tests, compile check, authentication tests, Quant Screener JSON smoke test and Firestore Rules Emulator tests |
| `Render production smoke check` | After successful main-branch Python tests, or manual dispatch; checks `/healthz` only |
| `Deploy secure Dautu frontend` | Frontend asset changes on `main`, or manual dispatch; publishes the allowlisted GitHub Pages site |
| `Import legacy JSON to MongoDB` | Manual dry-run/apply workflow; apply requires the explicit `IMPORT_TO_ATLAS` confirmation |
| `MongoDB Atlas verification` | Manual read-only connectivity and collection-count check |
| `Backfill price metadata (2026-11-13)` | Manual one-time metadata backfill for the successful 13 November pipeline run; not part of daily scheduling |

Normal weekday price collection is performed by the Render in-process Scheduler, not by GitHub Actions.

## 7. Legacy JSON and repository cleanup policy

The application runtime and API use Atlas for operational reads/writes. However, the repository still contains migration and CI input snapshots that are **not yet safe to delete**:

- `data.json` is read by the Quant Screener's `--smoke-test-json` CI mode and by `scripts/migrate_json_to_mongo.py`.
- `screener_results.json`, `symbol_sim_rates.json`, `quarterly_mean_details.json` and `last_update.json` are read by the JSON-to-Atlas migration script.
- `bctc_data/*.json` and `history/*.json` are also migration inputs.
- `mongodb-import.yml` remains an explicit manual migration workflow. Keep its source snapshots until the migration/fallback path is formally retired and the retained data has been independently validated in Atlas.

Generated Python bytecode and cache directories are excluded by `.gitignore` (`__pycache__/`, `*.py[cod]`, `.pytest_cache/`). No root `__pycache__` directory is present on the reviewed `main` tree; the previously tracked simulator bytecode was removed in the metadata-backfill cleanup. Do not delete migration JSON merely to reduce repository size while the import workflow still depends on it.

## 8. Operational checks

For a suspected missed update, verify in this order:

1. Render service is **Live** and the latest deploy is healthy.
2. Render application logs show Scheduler startup and a scheduled price-sync start/finish for the expected date.
3. Atlas `pipeline_runs` has `price_sync:YYYY-MM-DD` with `status: succeeded`, expected symbol totals and `completed_at`.
4. Atlas `app_metadata` document `_id: "price_sync"` has a matching/newer `last_updated` and successful counts.
5. Authenticated `GET /api/metadata`, `GET /api/stocks` and `GET /api/screener` return expected data; the frontend timestamp is displayed in Vietnam time.
6. Check UptimeRobot separately for availability history; do not use an uptime ping as evidence of a successful data pipeline.

Operational runbook: [docs/production-operations.md](docs/production-operations.md).
