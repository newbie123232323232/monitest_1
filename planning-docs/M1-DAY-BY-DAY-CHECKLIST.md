# MONI M1 Breakdown - Day-by-Day Checklist

## How to use this checklist

This is the M1 execution ledger. It helps any contributor see:

1. what M1 must deliver at the product-behavior level
2. what is done, in progress, or deferred
3. where hardening/security decisions are currently tracked

Checklist notation:
- `[x]` completed and verified
- `[~]` in progress or partially completed
- `[ ]` not done yet

## M1 at a glance

- Primary scope: HTTP vertical slice end-to-end
  - create monitor -> check -> status -> incident -> email
  - minimum usable UI (`Dashboard` / `List` / `Detail`)
- Non-goals in M1:
  - multi-location consensus
  - multi-channel alerts
  - websocket realtime

## Current delivery status (high-level)

- Foundation schema: done
- CRUD + run-check API: done
- Worker + beat core: done
- Incident/alert flow: done (SMTP-only scope)
- Core UI path: usable
- Hardening package: SSRF + rate-limit + production security middleware

## Traceability to `PROJECT-PLAN.md`

This document tracks implementation-level execution for M1.
Architecture decisions and roadmap rationale are maintained in `PROJECT-PLAN.md`.

## Current progress
- [x] Day 1 foundation completed: models + migration + indexes for `monitors`, `check_runs`, `incidents`, `alert_events`.
- [x] Day 2 completed:
  - [x] Monitor CRUD API with ownership checks.
  - [x] Filter/search/pagination for monitor list.
  - [x] `POST /api/v1/monitors/{id}/run-check` returns `202` + `task_id`.
  - [x] Create monitor auto-enqueues first check.
  - [x] Integration tests for ownership + filter/search + run-check.
- [~] Day 3 started:
  - [x] Implemented Celery task `check_http_monitor` and check/snapshot update flow.
  - [x] Added retries via `max_retries`.
  - [x] Isolated status calculation + HTTP error mapping for unit testing.
  - [x] Unit tests for status/error mapping.
  - [ ] Incident transitions (Day 4 scope).
  - [ ] UI verification for post-polling run-check status updates.
- [ ] Scope refinements (agreed):
  - [x] Added location-based monitoring fields/API (`probe_region`).
  - [x] Added technical metrics (DNS/TCP/TLS/TTFB) to check_runs + worker.
  - [ ] Multi-location consensus is excluded from M1.
  - [x] Alert channel remains SMTP-only.
- [x] Manual tests passed:
  - [x] Create monitor + run-check + status update (UP/DOWN).
  - [x] Dashboard `recent-failures` lists down monitors correctly.
  - [x] Incident/alert endpoints return expected monitor-linked data.
- [~] Hardening package started:
  - [x] API-level SSRF guard (block localhost/.local/private IP literals on create/update).
  - [x] Worker-level SSRF guard (block resolved private/internal targets; write `blocked_target`).
  - [x] `run-check-now` rate-limit (409 if checking, 429 if triggered too soon).
  - [x] Security tests for SSRF/rate-limit:
    - [x] API test: reject localhost/private IP monitor creation.
    - [x] API test: run-check returns 429/409 as expected.
    - [x] Worker-level SSRF test for private/internal DNS resolution path.
  - [x] Basic auth rate-limit for register/login/refresh.
  - [x] Production security middleware/headers (trusted host, CSP, HSTS, docs toggle).

## Day 1 - Data model + migration (foundation)
- [ ] Create `monitors` model with MVP fields:
  - [ ] `id`, `user_id`, `name`, `url`, `monitor_type`
  - [ ] `interval_seconds`, `timeout_seconds`, `max_retries`, `slow_threshold_ms`
  - [ ] `detect_content_change`, `is_paused`, `current_status`
  - [ ] `last_checked_at`, `last_response_time_ms`, `last_status_code`
  - [ ] `last_error_message`, `last_success_at`, `created_at`, `updated_at`, `deleted_at`
- [ ] Create `check_runs` model:
  - [ ] `monitor_id`, `status`, `started_at`, `finished_at`, `response_time_ms`
  - [ ] `status_code`, `error_type`, `error_message`
  - [ ] `final_url`, `title`, `content_type`, `content_hash`, `retry_count`
- [ ] Create `incidents` model:
  - [ ] `monitor_id`, `opened_at`, `closed_at`, `status`
  - [ ] `open_reason`, `close_reason`, `first_failed_check_id`, `last_failed_check_id`
- [ ] Create `alert_events` model:
  - [ ] `incident_id`, `monitor_id`, `channel`, `event_type`
  - [ ] `sent_to`, `sent_at`, `provider_message_id`, `send_status`, `error_message`
- [ ] Write Alembic migration and run `upgrade head`.
- [ ] Add required indexes:
  - [ ] `monitors(user_id, current_status, is_paused)`
  - [ ] `check_runs(monitor_id, started_at desc)`
  - [ ] `incidents(monitor_id, status)`

Definition of done (Day 1):
- [ ] schema created and migration runs cleanly on local
- [ ] seed data available for quick validation (2-3 monitors)

## Day 2 - Monitor CRUD + list/filter/search API
- [ ] Define monitor request/response schemas.
- [ ] Implement APIs:
  - [ ] `POST /api/v1/monitors`
  - [ ] `GET /api/v1/monitors`
  - [ ] `GET /api/v1/monitors/{id}`
  - [ ] `PATCH /api/v1/monitors/{id}`
  - [ ] `DELETE /api/v1/monitors/{id}` (soft delete)
- [ ] Input validation:
  - [ ] only `http/https` URLs
  - [ ] `interval_seconds >= 30`
  - [ ] `timeout_seconds <= interval_seconds`
  - [ ] `max_retries` in safe range (e.g. 0-5)
- [ ] List API supports:
  - [ ] `status`
  - [ ] `q` (name/url)
  - [ ] `page`, `page_size`
- [ ] Ownership checks on every monitor endpoint.

Definition of done (Day 2):
- [ ] all CRUD endpoints validated via Swagger
- [ ] cross-user monitor read/update is blocked

## Day 3 - Celery app + HTTP check task
- [ ] Create `celery_app.py`; load broker/result backend from `.env`.
- [ ] Implement `check_http_monitor(monitor_id)`:
  - [ ] set monitor `current_status=checking`
  - [ ] execute HTTP request with timeout/retry
  - [ ] write `check_runs` row
  - [ ] compute status (`up/down/slow`)
  - [ ] update monitor snapshot
- [ ] Isolate status calculation for unit tests.
- [ ] Explicit technical error handling:
  - [ ] dns_error
  - [ ] timeout
  - [ ] tls_error
  - [ ] http_error
- [ ] Add `POST /api/v1/monitors/{id}/run-check`:
  - [ ] enqueue task
  - [ ] return `202` + `job_id`

Definition of done (Day 3):
- [ ] create monitor -> run-check-now -> check rows exist
- [ ] UI/docs reflect updated status correctly

## Day 4 - Scheduler + incident open/close + alert email
- [ ] Beat scheduler enqueues active monitors by `interval_seconds`.
- [ ] Skip `is_paused=true` or `deleted_at != null`.
- [ ] Implement incident transitions:
  - [ ] `UP -> DOWN`: open incident
  - [ ] `DOWN -> UP`: close incident
  - [ ] `SLOW` does not open hard-down incident in MVP
- [ ] Implement email alert tasks:
  - [ ] incident opened
  - [ ] incident recovered
- [ ] Alert dedupe:
  - [ ] avoid repeated email spam while incident remains open
- [ ] Write `alert_events`.
- [x] Implemented so far:
  - [x] incident transition logic (`UP/SLOW -> close`, `DOWN -> open if none`)
  - [x] SMTP email tasks for `incident_opened` and `incident_recovered`
  - [x] `alert_events` persisted per send result (sent/failed)
  - [x] beat task `enqueue_due_monitor_checks` every 30s
  - [x] worker task list includes `checks`, `notify`, `scheduler`

Definition of done (Day 4):
- [ ] simulate one failing URL and one recovery URL; incident and email behavior is correct

## Day 5 - Dashboard + detail API (backend-ready for UI)
- [ ] Dashboard APIs:
  - [x] `GET /api/v1/dashboard/summary`
  - [x] `GET /api/v1/dashboard/recent-monitors`
  - [x] `GET /api/v1/dashboard/recent-failures`
- [ ] Detail APIs:
  - [x] `GET /api/v1/monitors/{id}/checks`
  - [x] `GET /api/v1/monitors/{id}/incidents`
  - [x] `GET /api/v1/monitors/{id}/alerts`
  - [x] support `limit`, `from`, `to` (checks + uptime; 30d default window)
- [x] Uptime percentage support (`average_uptime_percent` + `GET .../uptime`; max 366d window).
- [ ] Return latest check metadata.
- [ ] Return advanced metrics: `dns_resolve_ms`, `tcp_connect_ms`, `tls_handshake_ms`, `ttfb_ms`.

Definition of done (Day 5):
- [ ] payloads are complete for Dashboard/List/Detail UI plan

## Day 6 - Frontend M1 pages
- [~] Create API clients for monitors + dashboard.
- [~] Dashboard page:
  - [x] stats cards (including `average_uptime_percent` and window check totals)
  - [x] recent monitors
  - [x] recent failures
- [~] Websites list page:
  - [x] table
  - [x] filter (all/up/down/slow/paused)
  - [x] search (name/url)
- [~] Add Website modal/form:
  - [x] basic validation
  - [x] save -> refresh list
- [~] Run Check Now action:
  - [x] queued/checking state display
  - [x] deterministic polling to terminal state (queued/checking/completed/timeout/failed)
- [~] UI architecture to reduce rewrite cost:
  - [x] typed API layer (`auth/monitors/dashboard`) separated from views
  - [x] consistent page state model (loading/error/data)
  - [x] detail consumes `/uptime`, `/checks` (range), `/incidents`, `/alerts` directly

Definition of done (Day 6):
- [x] happy-path UI works: add monitor -> run-check -> list/checks data updates

## Day 7 - Detail page + hardening + tests
- [ ] Website detail page:
  - [ ] summary block
  - [ ] actions (run check, pause/resume, edit, delete)
  - [x] history tables (checks/incidents/alerts with light sort/filter)
  - [x] basic response-time line chart (24h/7d)
  - [ ] latest logs/errors block
  - [ ] DNS/TCP/TLS/TTFB metric block
- [ ] DOWN UX block:
  - [ ] failed_at, error_type, retry_attempts, last_success
- [ ] Minimum test set:
  - [ ] status calculator unit test
  - [ ] incident transition integration test
  - [ ] run-check-now API test
  - [ ] SSRF deny-list test (API + worker)
  - [ ] run-check rate-limit test
- [ ] End-to-end smoke:
  - [ ] add monitor
  - [ ] beat check
  - [ ] down -> open incident + email
  - [ ] recover -> close incident + email

## Next batch (already agreed)
- [x] Detail data presentation:
  - [x] checks/incidents/alerts tables + light sort/filter
  - [x] response-time chart 24h/7d
  - [x] checks CSV export by range
- [x] Dashboard/List prioritization:
  - [x] add `last_failure_at` + `consecutive_failures`
- [x] Error contract:
  - [x] FE/BE standardized on `code + message`
- [x] Ship confidence:
  - [x] manual smoke checklist + minimum scripted smoke (`planning-docs/SMOKE-CHECKLIST.md`, `scripts/smoke-check.ps1`)

Definition of done (Day 7):
- [ ] M1 is shippable on local Docker/VPS dev
- [ ] backlog checklist for M2 is prepared

## Non-negotiable technical guardrails (daily)
- [ ] no silent-fail paths; errors must return explicit `code + message`
- [ ] no over-abstraction before HTTP flow is stable
- [ ] all monitor endpoints enforce ownership
- [ ] every schema change includes migration + rollback note
- [ ] before day close: manual verification + update `PROJECT-PLAN.md` progress
