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
- `FIREBASE_SERVICE_ACCOUNT_JSON`: complete Firebase service-account JSON, stored as a secret. This is a server credential, not the public Firebase web config.\n- `FIREBASE_ADMIN_EMAILS`: optional comma-separated server-side administrator email allow-list. Defaults to the existing administrator email `nguyenanhtuan081196@gmail.com`; set this explicitly in Render when changing administrators.
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

All `/api/*` routes require `Authorization: Bearer <Firebase ID token>`. The API verifies the token (including revocation status), then independently reads `allowed_users/{lowercase-email}` through the Firebase Admin SDK. Missing records, mismatched emails, unknown roles, expired/malformed expiry values, and non-allow-listed admin identities are denied. Admin access requires both `role: "admin"` in Firestore and membership in `FIREBASE_ADMIN_EMAILS`; normal users require `role: "user"` and a future `expiresAt`. Legacy ISO-8601 expiry strings and Firestore Timestamps are supported. If Firestore cannot be reached, the API fails closed with HTTP 503. The API never exposes the MongoDB URI or accepts arbitrary collection names from clients.

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
