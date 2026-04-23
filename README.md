# MONI

**Live deployment:** [https://monitest.top](https://monitest.top)  
**API health check:** [https://monitest.top/api/v1/health](https://monitest.top/api/v1/health)

MONI is an uptime-style monitoring system focused on reliable website checks, clear incident state transitions, and practical operational workflows.

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
py -3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
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

## Production deployment quickstart

1. Prepare VPS folders (`/opt/moni`, `/opt/moni/backups`).
2. Configure `.env` from `.env.prod.example`.
3. Configure Nginx site and issue TLS certificate.
4. Start compose stack and run migrations.
5. Verify health endpoint and login flows.
6. Configure GitHub Actions secrets for CI deploy.

See detailed runbook in `planning-docs/DEPLOY-RUNBOOK-X3MPHIM.md` (adapt domain values if needed).

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

### 6) Backup script fails with unbound env vars
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

## Project status

Core monitoring flow, auth, and deployment baseline are operational.  
Current priorities are operational robustness (CI discipline, backup/restore confidence, incremental hardening) and controlled feature expansion.
