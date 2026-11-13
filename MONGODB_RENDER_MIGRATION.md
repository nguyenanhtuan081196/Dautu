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
| Render Web Service | FastAPI, Firebase token verification, authenticated API | None on local disk |
| Render Cron/Worker services | Price crawler and subsequent pipeline stages | MongoDB Atlas only |
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
- FHSC_API_KEY: API key for VNstock's FHSC market source, required by the price Cron Job.
- ALIBABA_API_KEY: required later by the AI-analysis job.
- MONGODB_SERVER_SELECTION_TIMEOUT_MS and MONGODB_CONNECT_TIMEOUT_MS: optional connection timeouts.

The browser Firebase configuration is public client configuration; it is not the Firebase Admin service account.

## Current Render price job

The first automated pipeline stage is a dedicated Render Cron Job, isolated from the FastAPI web process.

- Service name: dautu-price-sync.
- Region: Singapore.
- Compute plan: Standard (1 CPU, 2 GB RAM) to give pandas/VNstock enough headroom.
- Schedule: 30 12 * * 1-5 UTC = 19:30 Vietnam time, Monday-Friday. This leaves a 90-minute buffer before FHSC's 21:00 Vietnam service cutoff.
- Command: python -m app.pipeline.price_job --sessions 30.
- Provider: VNstock v6 Market("fhsc").equity(symbol).ohlcv(...).
- Secret: FHSC_API_KEY.
- Database: MongoDB Atlas database dautu.

The job refreshes the configured VN100 universe, merges the latest daily candles with existing Atlas history, derives weekly/monthly candles in memory, and upserts candles and stock metrics directly into Atlas. It does not write local JSON/CSV files or commit data to GitHub.

Provider retry and inter-request waits use randomized +/-20% jitter. The job records a pipeline_runs document before and after execution, including requested/successful/failed symbol counts, symbol lists, duration, and error details. A partial or failed run exits non-zero.

The Cron service is defined declaratively in render.yaml. Merging the code does not create the Render service automatically. Before enabling the schedule, create/sync the service in Render, add MONGODB_URI and FHSC_API_KEY as secrets, and verify the service configuration. Render bills Cron compute by active minute; the current minimum charge is $1/month per Cron service. The Standard compute rate is usage-based, not a flat monthly Starter fee. Confirm the current estimate in the Render dashboard before provisioning.

## Pipeline rollout order

The production pipeline will be migrated incrementally, with each stage isolated and tested:

1. Price history and current stock metrics — Render Cron, implemented in this change.
2. Quarterly financial reports — dedicated Render job, direct upserts to financial_reports.
3. Quant screener — reads Atlas and writes screener_results.
4. Historical simulation — reads price_history and writes simulations.
5. AI analysis — reads Atlas and writes ai_analyses and the required compatibility fields.

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
