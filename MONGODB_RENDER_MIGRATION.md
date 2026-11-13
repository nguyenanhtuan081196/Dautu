# Dautu: Render runtime + MongoDB Atlas data architecture

## Mandatory architecture

- Render is the only runtime for application Python jobs. The developer's personal computer is not required to run crawlers, screeners, simulations, or AI analysis.
- MongoDB Atlas is the only durable operational data store. All runtime datasets are read from and written to Atlas.
- Render is compute only. Jobs may hold response data and intermediate calculations in RAM, then upsert results to Atlas. They must not persist candles, raw provider responses, BCTC payloads, or generated datasets as JSON/CSV files on Render disks.
- The website and FastAPI API read operational data only from Atlas. GitHub Pages contains frontend assets, not stock datasets.
- GitHub stores source, tests, CI definitions, and deployment configuration. GitHub Actions must not run scheduled production data jobs or commit generated datasets.

The old JSON/CSV files in the repository are legacy migration/rollback snapshots only. They are not a live data source and must not be refreshed by runtime workflows.

## Runtime topology

| Component | Responsibility | Durable data |
|---|---|---|
| Render Free Web Service | FastAPI plus an async scheduler; crawler runs in a worker thread | MongoDB Atlas only |
| MongoDB Atlas (dautu) | Current stock data, candles, reports, screener, simulations, AI output, job audit | All operational datasets |
| GitHub | Source control, pull requests, tests, deployment config | Source/config only |
| GitHub Pages | Static frontend assets | No market/fundamental datasets |
| Firebase Authentication | User identity | Firebase-managed |

## MongoDB collections

| Collection | Key | Purpose |
|---|---|---|
| stocks | _id = SYMBOL | Current stock metrics and compatibility fields |
| price_history | _id = SYMBOL:INTERVAL:DATE | D1/W1/MN candles |
| financial_reports | _id = SYMBOL:REPORT_TYPE | Balance sheet, income statement, cash flow |
| screener_results | _id = SYMBOL | Latest quant screener result |
| ai_analyses | _id = SYMBOL | Latest AI analysis |
| simulations | _id = SYMBOL | Latest historical simulation metrics |
| pipeline_runs | run_id | Job status, counts, timing, and errors |
| dataset_versions | version_id | Dataset publication/version metadata |
| app_metadata | key | Last update and active dataset metadata |

Indexes are created idempotently by app.database.mongo.ensure_indexes().

## Render environment variables

Configure values in the Render service's environment settings. Never commit secrets.

- MONGODB_URI: MongoDB Atlas connection string.
- MONGODB_DATABASE: dautu.
- FIREBASE_SERVICE_ACCOUNT_JSON: Firebase Admin service-account JSON for the API service.
- CORS_ALLOWED_ORIGINS: exact website origins.
- FHSC_API_KEY: API key for VNstock's FHSC market source, required by the in-process price scheduler.
- ALIBABA_API_KEY: required later by the AI-analysis job.
- MONGODB_SERVER_SELECTION_TIMEOUT_MS and MONGODB_CONNECT_TIMEOUT_MS: optional connection timeouts.

The browser Firebase configuration is public client configuration; it is not the Firebase Admin service account.

## Current Render Free price scheduler

The existing Free Web Service runs FastAPI and starts a lightweight async scheduler from the application lifespan. The scheduler polls once per minute in the event loop, but it dispatches all VNstock/pandas work through asyncio.to_thread so API requests continue to be served. No Cron, Background Worker, paid compute, or extra Render service is created.

- Service: the existing dautu-api Free Web Service in Singapore.
- Schedule: 20:30 Asia/Ho_Chi_Minh, Monday-Friday (configurable with PRICE_SYNC_TIME).
- Provider: VNstock v6 Market("fhsc").equity(symbol).ohlcv(...).
- Secrets: existing MONGODB_URI and FHSC_API_KEY.
- Database: MongoDB Atlas database dautu.

The crawler processes at most five symbols per batch by default (configurable 1-10), reads one stock document at a time, upserts candles and stock metrics directly to Atlas, then runs garbage collection before the next batch. It keeps only the requested recent pandas rows and does not write runtime JSON/CSV files to Render disk.

The scheduler checks Atlas for a successful run for the latest due weekday. If Render sleeps or restarts after the scheduled time, it recovers that missed run on the next startup/poll. A deterministic scheduled run ID and atomic 30-minute Atlas lease prevent duplicate concurrent runs. Completed batches and successful symbols are checkpointed in pipeline_runs; after a restart and lease expiry, the crawler skips already-saved symbols and resumes the remainder. Successful scheduled dates are not repeated. Provider retry and inter-request waits use randomized +/-20% jitter. All job state and audit counts are stored in pipeline_runs.

Render Free can restart at any time and has a 512 MB memory limit. The scheduler is best-effort, not a guaranteed clock: the ping service may reduce idle spin-down but cannot prevent platform restarts. Atlas-backed recovery makes the job resume on the next service start. Keep PRICE_SCHEDULER_ENABLED=true (default); PRICE_SYNC_TIME defaults to 20:30; PRICE_BATCH_SIZE defaults to 5; PRICE_SESSIONS defaults to 30.

## Pipeline rollout order

The production pipeline will be migrated incrementally, with each stage isolated and tested. Keep all stages on the existing Free web service unless a separate paid-cost approval is explicitly given:

1. Price history and current stock metrics — Render Free in-process scheduler, implemented in this change.
2. Quarterly financial reports — a sequential in-process stage, direct upserts to financial_reports.
3. Quant screener — reads Atlas and writes screener_results in a bounded run.
4. Historical simulation — reads price_history and writes simulations in bounded batches.
5. AI analysis — reads Atlas and writes ai_analyses and the required compatibility fields in bounded batches.

Until a later stage has its Render job, its former GitHub Actions production workflow remains retired. It must not silently fall back to running on GitHub Actions or a personal computer.

## API and frontend

- GET /healthz: API/Atlas health check.
- GET /api/status
- GET /api/stocks
- GET /api/stocks/{symbol}
- GET /api/screener
- GET /api/history/{symbol}
- GET /api/financials/{symbol}
- GET /api/analysis/{symbol}

Authenticated /api/* routes require Authorization: Bearer <Firebase ID token>. The API never exposes the MongoDB URI or accepts arbitrary collection names from clients. The frontend calls the API; it does not read JSON datasets from the repository or GitHub Pages.

## One-time legacy import

The migration importer is an administrative, one-time path only. It is not a recurring data pipeline. It can be used to move existing repository snapshots into Atlas after an explicit dry-run and apply confirmation. Once verified, all production reads and writes use Atlas.

## Safety gates

- Do not run a production crawler or any Atlas-writing job as part of CI.
- Do not provision a paid Render service without explicit cost approval.
- Do not enable a schedule until its secrets, database connection, and service plan have been verified.
- Never store runtime datasets on Render disk or commit generated JSON/CSV files.
- Do not re-enable retired GitHub Actions data workflows; their replacements must run on Render and persist to Atlas.
