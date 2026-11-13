# Dautu: MongoDB Atlas + Render migration

## Target responsibilities

- GitHub: source code, reviews, CI, and deployment configuration.
- MongoDB Atlas: operational datasets. The database name defaults to `dautu`.
- Render: authenticated API and, in a later migration phase, the scheduled Python pipeline.
- Firebase Authentication: user identity. The browser sends a Firebase ID token to the API; the API verifies it with the Firebase Admin SDK.

## Collections

| Collection | Key | Purpose |
|---|---|---|
| `stocks` | `_id = SYMBOL` | Current stock metrics; preserves legacy `data.json` fields |
| `price_history` | `_id = SYMBOL:INTERVAL:DATE` | One document per symbol, interval (D1/W1/MN), and date |
| `financial_reports` | `_id = SYMBOL:REPORT_TYPE` | Balance sheet, income statement, cash flow |
| `screener_results` | `_id = SYMBOL` | Latest quant screener result |
| `ai_analyses` | `_id = SYMBOL` | Latest AI analysis (collection is ready for pipeline writes) |
| `simulations` | `_id = SYMBOL` | Latest simulation metrics |
| `pipeline_runs` | `run_id` | Job execution audit trail |
| `dataset_versions` | `version_id` | Dataset publication/version metadata |
| `app_metadata` | `key` | Active dataset version and last update metadata |

Unique indexes are created idempotently by `app.database.mongo.ensure_indexes()`.

## Environment variables

Set these as Render secrets/environment variables. Never commit their values.

- `MONGODB_URI`: Atlas connection string.
- `MONGODB_DATABASE`: optional; defaults to `dautu`.
- `FIREBASE_SERVICE_ACCOUNT_JSON`: complete Firebase service-account JSON, stored as a secret. This is a server credential, not the public Firebase web config.
- `CORS_ALLOWED_ORIGINS`: comma-separated exact website origins, e.g. `https://your-domain.example`.
- `MONGODB_SERVER_SELECTION_TIMEOUT_MS`: optional; defaults to 10000.
- `MONGODB_CONNECT_TIMEOUT_MS`: optional; defaults to 10000.

The existing browser Firebase config (`FIREBASE_CONFIG`) is public client configuration and is not a substitute for the Firebase Admin service account.

## MongoDB-backed data jobs

The following jobs now use Atlas as their operational read/write store and no longer
perform interactive prompts or Git operations:

| Job | MongoDB input | MongoDB output |
|---|---|---|
| `fetch_data_local.py` | Existing `stocks`, D1 history, and BCTC reports | `stocks`, `price_history`, `app_metadata` |
| `crawl_bctc.py` | None (provider crawl) | `financial_reports`, `app_metadata` |
| `advanced_screener.py` | `stocks` | `screener_results` |
| `analyze_ai.py` | `stocks`, `screener_results` | `ai_analyses` and AI fields on `stocks` |
| `simulator.py` | D1 bars from `price_history` | `simulations` |

Run from the repository root with `MONGODB_URI` and `MONGODB_DATABASE` configured:

```bash
# Quarterly financial reports
python crawl_bctc.py --all-vn100

# Price data (default: VN100, 30 latest sessions)
python fetch_data_local.py --sessions 30
python fetch_data_local.py --symbols FPT,MWG --sessions 2500

# Sequential analysis stages
python advanced_screener.py
python analyze_ai.py --mode all --force
python simulator.py
```

The price and BCTC crawlers accept CLI arguments/environment defaults and are suitable
for non-interactive Render jobs. Set `ALIBABA_API_KEY` for AI analysis.
Legacy JSON files are no longer written by these jobs. Existing JSON snapshots remain
available for rollback and for the one-time migration importer; do not remove them until
Atlas counts and representative symbols have been checked.

## API

- `GET /healthz`: database connectivity health check; no user data.
- `GET /api/status`
- `GET /api/stocks`
- `GET /api/stocks/{symbol}`
- `GET /api/screener`
- `GET /api/history/{symbol}`
- `GET /api/financials/{symbol}`
- `GET /api/analysis/{symbol}`

All `/api/*` routes require `Authorization: Bearer <Firebase ID token>`. The API never exposes the MongoDB URI or accepts arbitrary collection names from clients.

## Initial JSON import

Run from the repository root after setting `MONGODB_URI` and optionally `MONGODB_DATABASE`:

```bash
python -m pip install -r requirements.txt
python scripts/migrate_json_to_mongo.py
python scripts/migrate_json_to_mongo.py --apply
```

The first command is a dry run and only counts local records. The second performs idempotent upserts. It does not delete MongoDB documents that are absent from the legacy JSON files. Verify counts and sample symbols in Atlas before switching production reads.

## Migration safety

This foundation deliberately does not change the existing GitHub Actions writers, current website JSON reads, or production schedules. Do not deploy the API or disable the old workflows until:
1. Atlas import has been checked against the legacy JSON files.
2. Existing Python jobs have been migrated to read/write the repositories (without interactive `input()` or Git pushes).
3. The website has been switched to the authenticated API and tested with Firebase sign-in.
4. A single Render pipeline has passed a full end-to-end test.

Keep the current JSON files as a rollback snapshot until the new pipeline has run successfully more than once.


## Render price-crawler Cron Job

The first Render pipeline stage is deployed as a dedicated **Cron Job**, not as work
inside the FastAPI web process. It runs independently from the API instance and
therefore does not consume the API process's event loop or request workers.

The root `render.yaml` defines:
- Service: `dautu-price-sync` (Python, Singapore, Starter plan).
- Schedule: `30 15 * * 1-5` UTC = 22:30 Vietnam time, Monday through Friday.
- Command: `python -m app.pipeline.price_job --sessions 30`.
- Required secrets: `MONGODB_URI` and `FHSC_API_KEY` (manual secrets; never committed).
- Database: `dautu`.

The crawler uses the current vnstock v6 `Market("fhsc").equity(symbol).ohlcv(...)` interface. FHSC is the default source and requires the `FHSC_API_KEY` secret; an optional second source can be configured with `VNSTOCK_MARKET_FALLBACK_SOURCE` when its credentials are available. The wrapper invokes the existing `fetch_data_local.py` crawler, applies randomized
20% jitter to its existing provider backoff delays, and writes a `pipeline_runs`
record before and after each run. Each record includes status, start/end timestamps,
duration, requested/successful/failed symbol counts, and failed symbol names. A
partial or failed run exits non-zero so Render marks that invocation as failed.

The Cron service must be created/synced in Render after this code is reviewed and
merged. The Blueprint is declarative configuration only; adding `render.yaml` to
GitHub does not create or start the service by itself.
