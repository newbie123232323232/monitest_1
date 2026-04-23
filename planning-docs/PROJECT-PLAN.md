# MONI — Detailed Project Plan

## Document purpose and reading order

This document is the source of truth for project scope, architecture, progress, and execution decisions.
It is designed so that new contributors can quickly understand:

1. what MONI is solving (MVP objective and product scope)
2. which architecture and stack are in use (API, worker, scheduler, frontend)
3. how work is phased (M1 -> M4)
4. what technical guardrails are mandatory
5. how to run and verify locally

Recommended reading order:
- `1) MVP Objective`
- `3) MVP Scope (in / out)`
- `4) UI flow -> backend feature mapping`
- `9) Delivery milestones`
- `12) Architecture decisions`
- `13+) Progress, gap checks, and next execution order`

## Project snapshot (executive summary)

- Product shape: uptime-style website monitoring app, optimized for correctness and operational stability.
- Current baseline:
  - Authentication (local + Google OAuth) is implemented.
  - HTTP monitoring vertical slice is implemented (CRUD -> check -> incident -> alert).
  - Dashboard / Monitors / Detail UI is usable with polling.
  - Security hardening has started (SSRF guard, rate limits, security middleware/headers).
- Delivery strategy:
  - vertical slices over broad abstraction
  - polling first, websocket later
  - HTTP first, TCP/ICMP later

## Architecture and operational context

- Monorepo layout:
  - `backend`: FastAPI + SQLAlchemy async + Alembic + Celery
  - `frontend`: Vue 3 + Vue Router + typed API client
  - `planning-docs`: specs, checklists, conventions, smoke/runbooks
- Core runtime flow:
  - API receives monitor config and user actions.
  - Celery Beat enqueues due checks.
  - Worker executes HTTP checks, updates monitor snapshot, opens/closes incidents.
  - Alert task sends SMTP email and writes `alert_events`.
- Core data model:
  - `monitors`, `check_runs`, `incidents`, `alert_events`

## Change management note

The detailed sections below intentionally keep status markers and historical decisions.
- Checklist markers `[x]/[ ]/[~]` are used for progress tracking.
- Gap and next-batch sections are used for execution prioritization.
- Historical context is preserved to avoid decision drift.

## 1) MVP objective

Build MONI around this flow:
add website -> run scheduled checks -> show status immediately -> alert on failures.

Priority is correctness, reliability, and operability over feature breadth.

## 2) Current status (completed baseline)

### Backend / Auth
- FastAPI + SQLAlchemy async + Alembic + PostgreSQL are stable.
- Local auth: register, verify email (GET/POST), login, refresh, logout.
- Google OAuth: start + backend callback + token handoff to SPA callback route.
- `JWT` access/refresh flow is working.
- Development error handling includes traceback for debugging.
- Register flow fixed so unverified accounts can re-register safely (no deadlock on stale data).

### Frontend / Auth
- Vue Router includes `/login`, `/register`, `/verify-email`, `/auth/callback`.
- Auth API client has clearer error parsing (`detail.message`, code, dev traceback).
- Vite proxy (`/api` -> backend) works in dev to avoid CORS friction.

### Local environment
- Backend dev default: `127.0.0.1:8010`
- Frontend dev default: `127.0.0.1:5173`
- `.env` Google callback aligned to `http://localhost:8010/api/v1/auth/google/callback`

## 3) MVP scope (remaining / fixed)

### In-scope for MVP
- Dashboard overview
- Full HTTP(S) monitor CRUD
- Scheduled checks via Celery Beat + worker
- Manual trigger (`Run Check Now`)
- Website detail: summary + history + response-time chart + latest errors
- Status model: `UP`, `DOWN`, `PENDING`, `CHECKING`, `PAUSED`, `SLOW`
- Basic incident flow + SMTP email alerts
- Location-aware probe field (`probe_region`)

### Out-of-scope in this MVP cycle
- Public status page
- Realtime websocket updates (polling only)
- Non-Google SSO providers
- Multi-channel alerts (Slack/Telegram/SMS)
- Multi-location consensus logic (3-5 probes, majority-fail downing)

## 4) UI flow -> backend feature mapping

### 4.1 Dashboard
Displays:
- total monitors
- up/down/pending/checking counts
- average response time
- recent monitors
- recent failures

Minimum APIs:
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/recent-monitors`
- `GET /api/v1/dashboard/recent-failures`

### 4.2 Add Website
Form:
- name, url, interval_seconds, timeout_seconds, detect_content_change (bool), slow_threshold_ms

Behavior:
- after create, enqueue first check immediately
- UI should show `PENDING` or `CHECKING`

API:
- `POST /api/v1/monitors`
- internal enqueue: `check_http_monitor(monitor_id)`

### 4.3 Websites list
Columns:
- name, url, current_status, latest_response_time_ms, last_checked_at, interval

Filter/search:
- status: all/up/down/slow/paused
- search: name/url

API:
- `GET /api/v1/monitors?status=&q=&page=&page_size=`

### 4.4 Website detail
Summary:
- name, url, current status, last checked, current response, uptime%

Actions:
- run check now
- pause/resume
- edit config
- delete

Content:
- status history table
- response-time line chart
- latest metadata (title, final_url, content_type, status_code)
- latest logs/errors

API:
- `GET /api/v1/monitors/{id}`
- `GET /api/v1/monitors/{id}/checks`
- `POST /api/v1/monitors/{id}/run-check`
- `PATCH /api/v1/monitors/{id}`
- `DELETE /api/v1/monitors/{id}`

### 4.5 Manual run-check UX
- UI transitions through `QUEUED/CHECKING` and polls every 5s until completion.
- No websocket in first release.

### 4.6 DOWN and SLOW UX policy
- DOWN: show failed_at, error_type, retry details, last_success.
- SLOW: soft degradation warning based on threshold.
- Keep SLOW distinct from DOWN (degradation vs outage).

## 5) Data model design (MVP, HTTP-first)

### `monitors`
- id (uuid), user_id, name, url
- monitor_type (`http`)
- probe_region (e.g., `ap-southeast-1`, `eu-central-1`) for location-aware probing
- interval_seconds, timeout_seconds, max_retries
- slow_threshold_ms
- detect_content_change (bool)
- is_paused (bool)
- current_status (`pending|checking|up|down|slow|paused`)
- last_checked_at, last_response_time_ms, last_status_code
- last_error_message, last_success_at
- created_at, updated_at, deleted_at (nullable for soft delete)

### `check_runs`
- id, monitor_id
- status (`up|down|slow|timeout|dns_error|tls_error|http_error`)
- started_at, finished_at, response_time_ms
- status_code, error_type, error_message
- final_url, title, content_type, content_hash
- dns_resolve_ms, tcp_connect_ms, tls_handshake_ms, ttfb_ms
- retry_count

### `incidents`
- id, monitor_id
- opened_at, closed_at, status (`open|closed`)
- open_reason, close_reason
- first_failed_check_id, last_failed_check_id

### `alert_events`
- id, incident_id, monitor_id, channel (`email`)
- event_type (`incident_opened|incident_recovered|still_down`)
- sent_to, sent_at, provider_message_id, send_status, error_message

Note:
- TCP/ICMP comes later; avoid premature abstraction before HTTP path is fully stable.

## 6) Worker and scheduler flow

### Beat
- enqueue active monitors every fixed interval
- skip monitors with `is_paused=true` or `deleted_at != null`

### Worker HTTP check flow
1. set `current_status=checking`
2. execute HTTP request with timeout/retry
3. collect technical metrics (DNS/TCP/TLS/TTFB)
4. write `check_runs`
5. compute `up/down/slow`
6. update monitor snapshot
7. open/close incidents on transition
8. enqueue email task for open/close transitions

### Retry policy (MVP)
- fast retries within a single task (e.g. `max_retries=2`)
- all retries fail -> `DOWN`
- request succeeds but exceeds threshold -> `SLOW`

## 7) Monitor API contract (MVP)

### Create monitor
- `POST /api/v1/monitors`
- body:
  - `name`, `url`, `interval_seconds`, `timeout_seconds`, `max_retries`, `slow_threshold_ms`, `detect_content_change`
- validation:
  - interval >= 30s
  - timeout <= interval
  - URL must be http/https

### Update monitor
- `PATCH /api/v1/monitors/{id}`
- editable fields: name/url/interval/timeout/max_retries/threshold/detect_content_change/is_paused
- changes apply on next check

### Run check now
- `POST /api/v1/monitors/{id}/run-check`
- returns `202 Accepted` + `job_id` + `queued`

### Delete monitor
- `DELETE /api/v1/monitors/{id}`
- MVP behavior: soft delete to preserve audit/history

## 8) Frontend page plan

### Page 1: Dashboard
- stats cards, recent monitors, recent failures
- light polling every 30s

### Page 2: Websites list
- table + filter + search + pagination
- row actions: `View Detail`, `Run Check Now`

### Page 3: Website detail
- summary + actions + chart + history + logs
- run-check-now polls every 5s until stable state

### Modals
- Add Website
- Edit Website

## 9) Delivery milestones

### M1 - HTTP vertical slice end-to-end
- models + migrations (`monitors`, `check_runs`, `incidents`)
- monitor CRUD + list/filter/search
- Celery HTTP check task + beat schedule
- run-check-now endpoint
- basic dashboard summary API

### M2 - Monitoring UX completion
- dashboard cards + recent failures
- list/status badges + detail page
- response-time chart
- clear DOWN/SLOW warning blocks
- show DNS/TCP/TLS/TTFB metrics in detail

### M3 - Alerting stability
- email incident opened/recovered
- dedupe to avoid mail spam on each beat cycle
- alert event logging
- SMTP-only to keep MVP scope lean

### M4 - Hardening before TCP/ICMP expansion
- rate limits, concurrency safeguards
- check_runs retention policy
- integration tests for worker flow

## 10) Mandatory technical checklist

- Testing:
  - unit: status calculation and incident transitions
  - integration: create -> check -> incident open -> recover
- Observability:
  - structured logs for API + worker
  - health checks: db, redis, worker heartbeat
- Security:
  - input URL validation for basic SSRF defense (deny private ranges when possible)
  - minimum interval enforcement against abuse

## 11) Current development runbook

1. Backend:
   - `cd backend`
   - `py -3 -m pip install -e ".[dev]"`
   - `py -3 -m alembic upgrade head`
   - `py -3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010`

2. Frontend:
   - `cd frontend`
   - `npm install`
   - `npx vite --host 127.0.0.1 --port 5173 --strictPort`

3. Worker/Beat (monitoring phase):
   - `cd backend`
   - `py -3 -m celery -A app.workers.celery_app worker -P solo -l info` (Windows)
   - `py -3 -m celery -A app.workers.celery_app beat -l info`

## 12) Final architecture decisions

- Monorepo, no early microservice split
- HTTP monitor first, TCP/ICMP later
- polling over websocket for first release
- keep `SLOW` separate from `DOWN`
- finish core monitoring before profile/change-password extras
- include `probe_region` field early; postpone multi-region consensus in M1
- advanced metrics scope in M1: DNS resolve, TCP connect, TLS handshake, TTFB (not full page load)

## 13) Latest M1 progress update

- Day 1 done: monitoring schema (`monitors`, `check_runs`, `incidents`, `alert_events`) + migration.
- Day 2 done: monitor CRUD, filter/search, ownership checks, soft delete, `run-check-now`.
- Create monitor now enqueues first check immediately.
- Integration tests cover ownership + filter/search + run-check.
- Day 3 in progress: HTTP task retries (`max_retries`), timeout/dns/tls/http mapping, unit tests.
- Added `probe_region` for basic location-aware monitoring.
- Added technical metrics in check run: `dns_resolve_ms`, `tcp_connect_ms`, `tls_handshake_ms`, `ttfb_ms`.
- Exposed `GET /api/v1/monitors/{id}/checks` for detailed metrics in UI/docs.
- Day 4 backend core implemented:
  - incident transitions (`DOWN -> open`, `UP/SLOW -> close`)
  - SMTP alert task (`incident_opened`, `incident_recovered`) + `alert_events` logging
  - beat schedule enqueues due monitors every 30s
- Day 5 backend APIs added:
  - `GET /api/v1/dashboard/summary`, `/recent-monitors`, `/recent-failures`
  - `GET /api/v1/monitors/{id}/checks`, `/incidents`, `/alerts`
- Uptime percentage and range query (`from/to`) are wired into dashboard/detail.
- Day 6 UI minimum has started:
  - routes/pages for `dashboard` and `monitors` with typed API clients
  - dashboard renders stats + recent monitors + recent failures
  - monitors page supports basic create, monitor table, run-check, recent checks preview
  - pending on Day 6: full filter/search polish, deterministic polling UX, complete detail page

## 14) Decision after manual testing

- Manual tests passed for auth + monitor create/run-check + dashboard failure listing.
- Decision: ship base UI now via vertical slice (do not wait for all backend polish).
- Principles to avoid rewrite cost in Vue:
  - API contract first: typed API layer before page logic
  - thin UI pages/components (no embedded network business logic)
  - reuse existing payloads (`dashboard`, `checks`, `incidents`, `alerts`) before adding endpoints
  - keep route skeleton early (`/dashboard`, `/monitors`, `/monitors/:id`) for stable navigation/state
  - ship MVP usability first, postpone visual polish

## 15) Gap check vs plan + next priorities (updated)

- Remaining UI items:
  - [x] Edit monitor in UI (`PATCH` consumed in Monitors page)
  - [x] Basic list filter/search
  - [x] Detail route `/monitors/:id` consumes checks/incidents/alerts
  - [x] Monitors pagination UI
  - [x] Deterministic run-check polling on list + detail (queued/checking/completed/timeout/failed)
- Backend monitoring core:
  - [x] Uptime percentage (dashboard aggregate + per-monitor endpoint)
  - [x] `from/to` range query for checks history and uptime (default 30d for checks)
- Alert hardening not complete:
  - debounce/cooldown
  - still-down reminder cadence
- Security hardening priorities:
  - SSRF host/IP guard
  - run-check-now rate limit
  - clear FE/BE validation contract

## 16) Final execution order (product-first)

1. Mandatory hardening (security/correctness):
   - SSRF guard + run-check rate limit + final validation contract
2. Complete core UI flow:
   - edit monitor, filter/search, monitor detail page
3. Alert quality:
   - debounce/cooldown/still-down behavior
4. Test + release confidence:
   - integration/security tests + smoke checklist

## 17) Hardening package status (current)

- [x] SSRF guard started:
  - API create/update blocks local/private/internal host targets
  - worker check blocks targets resolving to private/internal IP (`blocked_target`)
- [x] `run-check-now` rate limit:
  - block while monitor is `checking` (409)
  - block if triggered within minimum interval (`run_check_min_interval_seconds`, default 15s) (429)
- [x] Tests for SSRF/rate-limit:
  - API tests for localhost/private IP rejection
  - API tests for 429/409 run-check behavior
  - worker-level SSRF tests for private/internal DNS resolution
- [x] Additional auth/edge hardening:
  - auth rate limit for register/login/refresh by IP + subject
  - production middleware hardening (trusted host, optional HTTPS redirect)
  - security headers (`CSP`, `X-Frame-Options`, `HSTS` in production)
  - docs toggle (`expose_docs_in_production=false` by default)
  - fail-fast guard for unsafe dev mode on public host

## 18) Agreed next batch (post-M1 polish)

- [~] Detail presentation upgrade:
  - [x] checks/incidents/alerts as tables with lightweight sort/filter
  - [x] response-time chart 24h/7d
  - [x] checks CSV export by selected range
- [x] Risk-prioritization data:
  - add `last_failure_at` + `consecutive_failures` to list/dashboard
- [x] FE/BE error contract standardization:
  - consistent `code + message` payload
- [x] Ship confidence package:
  - manual checklist + minimum script automation (`planning-docs/SMOKE-CHECKLIST.md`, `scripts/smoke-check.ps1`)
  - [ ] Add npm/powershell shortcut command for quick smoke run (deferred)
