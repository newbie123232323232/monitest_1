# MONI

**Live deployment:** [https://monitest.top](https://monitest.top)  
**API health check:** [https://monitest.top/api/v1/health](https://monitest.top/api/v1/health)

MONI is an uptime-style monitoring system focused on reliable website checks, clear incident state transitions, and practical operational workflows.

## Upgrade session highlights (current)

This upgrade cycle completed a large backend+frontend hardening and feature block. The key additions are:

- **Monitor contract migration:** from CSV probe regions to mapping table (`monitor_regions`) with explicit `active_region` execution model (resource-saving, one active region per cycle).
- **Region catalog:** dedicated `probe_regions` API/model flow for controlled region selection.
- **Status pages:** managed private/public status pages with monitor mapping and maintenance notes.
- **SSL/domain expiry monitoring:** expiry status storage, check tasks, summary APIs, and alert threshold tracking.
- **Runtime observability:** runtime health and queue profile APIs with dashboard integration.
- **Operational hardening:** safer local restart scripts, strict Celery topology checks, and packaged smoke gate script.
- **Deploy safety:** CI deploy pipeline now runs Alembic migration through the live `api` service container, then restarts `api/worker/beat` to keep code and schema synchronized.

## What this project does

MONI lets a user:
- create monitors (HTTP first, with TCP/ICMP planned)
- run checks on schedule and manually
- track status history, incidents, and alerts
- receive email alerts for outage/recovery

The project is optimized for correctness and operability over feature sprawl.

## Tech stack

- **Frontend:** Vue 3, Vue Router, Vite, TypeScript
- **Backend API:** FastAPI, SQLAlchemy (async), Alembic
- **Database:** PostgreSQL
- **Async processing:** Celery + Celery Beat + Redis
- **Auth:** JWT access/refresh, email verification (SMTP), Google OAuth
- **Deployment:** Docker Compose on VPS, Nginx reverse proxy, Let's Encrypt TLS
- **CI/CD:** GitHub Actions + GHCR images + SSH deploy

## Repository structure

- `backend/` - API, models, migrations, worker tasks
- `frontend/` - SPA application
- `planning-docs/` - roadmap, checklists, environment/deploy runbooks
- `scripts/` - smoke checks and utility scripts
- `starting-doc.txt` - high-level BA/data-design brief
- `docker-compose.prod.yml` - production compose stack
- `.env.prod.example` - production env template

## Architecture overview

High-level runtime components:
- **API service** receives user actions and exposes REST endpoints.
- **Beat scheduler** enqueues due monitor checks.
- **Worker** executes checks, writes check results, updates monitor snapshot, and handles incident transitions.
- **Alert flow** sends SMTP notifications and logs alert events.
- **PostgreSQL** stores source-of-truth data.
- **Redis** is broker/result backend for Celery tasks.

## Core data model (conceptual)

- `users` - account identity
- `refresh_tokens` - session continuity/revocation
- `monitors` - target config + latest snapshot
- `check_runs` - immutable check execution history
- `incidents` - outage lifecycle records
- `alert_events` - notification audit trail

Relationship summary:
- one user -> many monitors
- one monitor -> many check runs
- one monitor -> many incidents
- one incident -> many alert events

## Data flow

1. User creates/updates a monitor via API.
2. Beat enqueues check task when monitor is due.
3. Worker executes check and records `check_runs`.
4. Worker computes resulting monitor status (`up/down/slow/...`) and updates snapshot fields.
5. Incident transition logic opens/closes incidents based on status transitions.
6. Alert task sends email and writes `alert_events`.
7. Frontend reads dashboard/list/detail endpoints and renders operational state.

## User flow

1. Register or sign in (email/password or Google OAuth).
2. Create a monitor (name, URL, interval, timeout, thresholds).
3. Observe status in Dashboard and Monitors list.
4. Trigger manual run-check when needed.
5. Investigate detail history (checks/incidents/alerts/chart).
6. Receive down/recovered notifications by email.

## Local development quickstart

### Backend

```bash
cd backend
py -3 -m pip install -e ".[dev]"
py -3 -m alembic upgrade head
py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

### Frontend

```bash
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5173 --strictPort
```

### Worker and scheduler

```bash
cd backend
py -3 -m celery -A app.workers.celery_app worker -P solo -l info
py -3 -m celery -A app.workers.celery_app beat -l info
```

For safer local restarts (avoid duplicate worker/beat):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_celery_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_celery_runtime.ps1
```

For full local restart with port guards (API + Celery + Frontend):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_full_stack.ps1
```

Optional flags:
- `-NoFrontend` restart only backend + celery
- `-NoCelery` restart only backend + frontend
- `-NoBackend` restart only frontend + celery
- `-ForceKillPortOwners` terminate unknown processes holding guarded ports

Recommended strict restart flow (manual, no extra wrapper script):
1. Preflight:
   - ensure repo root has `.env`
   - ensure no stale process is holding API/Frontend ports unexpectedly
2. Run guarded restart:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\restart_full_stack.ps1 -ForceKillPortOwners`
3. Health verification:
   - open `http://127.0.0.1:8011/api/v1/health` and confirm HTTP 200
4. Runtime topology verification:
   - run `powershell -ExecutionPolicy Bypass -File .\scripts\check_celery_runtime.ps1 -Strict -Retries 4 -RetryDelaySeconds 2`
   - expected: worker and beat are both present, no strict failure
5. Final readiness:
   - API docs reachable: `http://127.0.0.1:8011/docs`
   - frontend reachable (if started): `http://127.0.0.1:5173`

Why this flow is mandatory:
- `restart_full_stack.ps1` guarantees idempotent stop/start + port guard.
- `/api/v1/health` confirms API process is actually serving, not just spawned.
- strict celery check catches false-green starts (e.g., beat crash after spawn).
- local Windows scripts intentionally avoid Unix pidfile paths for celery beat.

Onboarding copy-paste flows:

Flow A - restart full local stack (API + Celery + Frontend):

```powershell
# 1) guarded restart (kill unknown port owners if needed)
powershell -ExecutionPolicy Bypass -File .\scripts\restart_full_stack.ps1 -ForceKillPortOwners

# 2) backend health must be 200
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/api/v1/health

# 3) celery topology must be healthy
powershell -ExecutionPolicy Bypass -File .\scripts\check_celery_runtime.ps1 -Strict -Retries 4 -RetryDelaySeconds 2
```

Expected result:
- backend responds `200` at `/api/v1/health`
- celery check prints worker and beat present, no strict failure
- frontend reachable at `http://127.0.0.1:5173`

One-command local pre-deploy smoke gate:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_local_gate.ps1
```

Notes:
- This script runs guarded restart and then runs `scripts/smoke-check.ps1`.
- For full authenticated smoke (dashboard/monitors/runtime), pass `-AccessToken "<token>"`.
- Optional monitor-detail/checks/uptime checks remain available in `scripts/smoke-check.ps1` via `-MonitorId`.
- To skip restart and only run checks: `-SkipRestart`

Flow B - restart backend + celery only (no frontend):

```powershell
# 1) restart without frontend
powershell -ExecutionPolicy Bypass -File .\scripts\restart_full_stack.ps1 -NoFrontend -ForceKillPortOwners

# 2) backend health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/api/v1/health

# 3) celery strict check
powershell -ExecutionPolicy Bypass -File .\scripts\check_celery_runtime.ps1 -Strict -Retries 4 -RetryDelaySeconds 2
```

Expected result:
- backend and celery ready
- Swagger reachable at `http://127.0.0.1:8011/docs`
- frontend is intentionally not started in this flow

Port note (important):
- Local guarded runtime defaults API to `8011` for stability on Windows dev.
- Production deploy stack continues using API port `8010` behind Nginx/compose.
- If you must run local API on another port, pass `-BackendPort` to `restart_full_stack.ps1`.

## Production deployment quickstart

1. Prepare VPS folders (`/opt/moni`, `/opt/moni/backups`).
2. Configure `.env` from `.env.prod.example`.
3. Configure Nginx site and issue TLS certificate.
4. Start compose stack and run migrations.
5. Verify health endpoint and login flows.
6. Configure GitHub Actions secrets for CI deploy.

See detailed runbook in `planning-docs/DEPLOY-RUNBOOK-X3MPHIM.md` (adapt domain values if needed).

Production deploy safety note:
- Deploy workflow now performs migration with:
  - `docker compose ... up -d api`
  - `docker compose ... exec -T api alembic upgrade head`
  - `docker compose ... restart api worker beat`
- This order prevents "new code / old schema" mismatch after image rollout.

## Common issues when cloning / modifying / self-deploying

### 1) API fails on startup in production
- Often caused by weak `JWT_SECRET` policy in production.
- Use a high-entropy secret (32+ chars, no weak keywords like `secret`, `password`, `changeme`).

### 2) Google OAuth save/login errors
- Ensure callback URL exactly matches env and Google Console.
- Use correct production domain and HTTPS.
- Domain reputation (Safe Browsing) can block OAuth config for problematic domains.

### 3) CORS confusion in dev
- Recommended dev setup uses Vite proxy (`/api`) so `VITE_API_BASE_URL` can stay empty.
- If calling backend directly from another origin, ensure backend CORS allows that origin.

### 4) "Site is down" for some URLs even though URL is reachable in browser
- Some targets return `403` to bot-like probes/WAF-blocked traffic.
- This is often expected target behavior, not necessarily a bug in MONI.

### 5) Redis/Celery mismatches
- Keep `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` aligned.
- For internal Docker Redis, use `redis://redis:6379/0`.
- Celery is intentionally decoupled from API runtime:
  - `run-check` endpoint only enqueues task (`queued`)
  - actual execution requires `worker` (and `beat` for scheduled checks)
  - in local/dev, start `uvicorn + worker + beat` together for full behavior
- To avoid recurring `queued/pending` caused by duplicated local processes:
  - always restart Celery via `scripts/restart_celery_runtime.ps1`
  - verify process count via `scripts/check_celery_runtime.ps1`
  - keep local Redis/Celery separate from production broker

### 8) Dashboard appears slow even when API is up
- Root cause seen in local hardening phase: dashboard core endpoints were fast, but runtime health path could be slow/intermittent and block page rendering.
- Current mitigation:
  - runtime panel is not in dashboard critical render path
  - runtime calls use `allSettled` and short TTL cache (health 10s, queue profile 15s)
  - backend runtime health uses heartbeat-based worker/beat checks with timeout guards
- Expected behavior now:
  - dashboard core cards load first
  - runtime card may refresh slightly later without freezing whole page

### 6) Swagger docs appear blank or unavailable
- In production, docs are disabled by default with `EXPOSE_DOCS_IN_PRODUCTION=false`.
- If enabled for temporary testing, ensure API is restarted and `/docs` route is reachable.
- Docs route uses a dedicated CSP path policy; API routes keep strict CSP hardening.

### 7) Backup script fails with unbound env vars
- Ensure backup script loads `.env` and references `POSTGRES_USER`/`POSTGRES_DB` from env.
- Verify compressed backup integrity (`gzip -t`).

## Planning docs guide

Use these docs as your onboarding map:

- `starting-doc.txt`  
  BA-style product and database-design brief. Start here for product context and system intent.

- `planning-docs/PROJECT-PLAN.md`  
  Master roadmap: architecture decisions, milestones, progress tracking, and execution order.

- `planning-docs/M1-DAY-BY-DAY-CHECKLIST.md`  
  Detailed implementation checklist by day for M1 vertical slice.

- `planning-docs/ENV-CONVENTIONS.md`  
  Environment and URL conventions (dev/prod), OAuth URLs, DB/Redis/Celery config patterns.

- `planning-docs/SMOKE-CHECKLIST.md`  
  Release confidence checklist: scripted + manual smoke validation.

- `planning-docs/DEPLOY-RUNBOOK-X3MPHIM.md`  
  Production deploy and rollback workflow on VPS with Nginx + Docker Compose + GH Actions.

- `planning-docs/MONITOR-REGION-RESOURCE-SAVING-PLAN.md`  
  Region execution strategy, active-region rationale, and runtime/port discipline notes.

- `upgrade_planning_docs_1`  
  Full execution log for this upgrade cycle (what was done, test checkpoints, and remaining/closed items).

## Quick access map for new files

If you are onboarding and need the fastest path:

- Start with feature scope/progress:
  - `upgrade_planning_docs_1`
  - `planning-docs/MONITOR-REGION-RESOURCE-SAVING-PLAN.md`
- Then read deploy/runtime operations:
  - `planning-docs/DEPLOY-RUNBOOK-X3MPHIM.md`
  - `.github/workflows/deploy.yml`
- Then use scripts directly:
  - `scripts/restart_full_stack.ps1` (guarded local full restart)
  - `scripts/restart_celery_runtime.ps1` (idempotent local celery restart)
  - `scripts/check_celery_runtime.ps1` (strict topology check)
  - `scripts/smoke-check.ps1` (API/frontend smoke checks)
  - `scripts/smoke_local_gate.ps1` (one-command local pre-deploy gate)
  - `scripts/smoke_alert_timeline_e2e.py` (incident alert timeline smoke)

## Project status

Core monitoring flow, auth, and deployment baseline are operational.  
Current priorities are operational robustness (CI discipline, backup/restore confidence, incremental hardening) and controlled feature expansion.
