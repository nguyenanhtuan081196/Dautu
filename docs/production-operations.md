# Dautu API – production operations runbook

## Production service

- Render service: `dautu-api`
- Production URL: https://dautu-api.onrender.com
- Deployment branch: `main`
- Runtime: FastAPI / Uvicorn
- Database: MongoDB Atlas (database name configured separately in Render)

## Deployment flow

1. Make changes on a feature branch and open a pull request to `main`.
2. Require the Python tests and Firestore Rules Emulator checks to pass before merging.
3. Merge only after review. Render Auto-Deploy watches `main` and builds the new commit automatically.
4. In Render, confirm the new deployment reaches **Live** and check the application logs for:
   - `Application startup complete.`
   - `Uvicorn running on http://0.0.0.0:$PORT`
   - Render's `Your service is live` event.
5. Confirm the API health endpoint returns HTTP 200 and JSON `{"status":"ok"}`.

## Health endpoint

`GET /healthz` is a public infrastructure probe. It calls MongoDB's `ping` command and returns:

- HTTP 200 with `{"status":"ok"}` when MongoDB is reachable.
- HTTP 503 with a generic error body when the database cannot be reached.

After verifying the endpoint against production, set Render's **Health Check Path** to `/healthz` in the service settings. Do not configure this path while MongoDB connectivity is known to be failing; Render may mark the service unhealthy.

## Monitoring checklist

- Check Render service state and latest deploy status.
- Review application logs for startup errors, repeated restarts, MongoDB timeouts, and HTTP 5xx responses.
- Review HTTP request count/latency, CPU, and memory metrics.
- Treat repeated `/healthz` HTTP 503 responses as a database connectivity incident.
- Do not expose environment-variable values, Firebase service-account JSON, SMTP app passwords, or MongoDB credentials in logs or support reports.

## Rollback

If a new release causes a production incident:

1. Open the Render service's Events / Deploys page.
2. Select the last known-good deployment and use Render's rollback action.
3. Confirm the rollback reaches **Live**.
4. Recheck `/healthz`, application logs, and the key authenticated API flows.
5. Open a follow-up pull request to fix the regression before redeploying the newer code.

Rollback and production environment changes should be deliberate operator actions. Do not run database import/apply workflows as part of a web-service rollback.
