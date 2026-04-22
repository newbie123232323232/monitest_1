# MONI M1 Breakdown - Day by Day Checklist

Muc tieu M1: hoan thanh HTTP vertical slice end-to-end (create monitor -> check -> status -> incident -> email) va UI toi thieu de dung duoc.

## Current progress
- [x] Day 1 foundation da hoan thanh: model + migration + index cho `monitors`, `check_runs`, `incidents`, `alert_events`.
- [x] Day 2 hoan thanh:
  - [x] Monitor CRUD API co ownership check.
  - [x] Filter/search/pagination cho list monitors.
  - [x] `POST /api/v1/monitors/{id}/run-check` tra `202` + `task_id`.
  - [x] Create monitor tu dong enqueue first check.
  - [x] Integration test cho ownership + filter/search + run-check.
- [~] Day 3 da khoi dong:
  - [x] Tao Celery task `check_http_monitor` va luong cap nhat `check_runs` + snapshot monitor.
  - [x] Bo sung retries theo `max_retries`.
  - [x] Tach ham tinh status + map HTTP error de test don vi.
  - [x] Unit tests cho status/error mapping.
  - [ ] Them incident transition (Day 4 scope).
  - [ ] UI verify run-check-now cap nhat status sau polling.
- [ ] Scope refinement da chot:
  - [x] Them location-based monitoring vao data model + API (`probe_region`).
  - [x] Them advanced metrics ky thuat (DNS/TCP/TLS/TTFB) vao check_runs + worker.
  - [ ] Khong lam multi-location consensus trong M1.
  - [x] Alert channel giu SMTP-only.
- [x] Manual test pass:
  - [x] Create monitor + run-check + status update (UP/DOWN) hoat dong.
  - [x] Dashboard `recent-failures` lay dung monitor `down`.
  - [x] Incident/alert endpoints tra du lieu dung voi monitor flow.
- [~] Hardening package da bat dau:
  - [x] SSRF guard API level (block localhost/.local/private IP literal khi create/update monitor).
  - [x] SSRF guard worker level (block target resolve vao private/internal IP, ghi `blocked_target`).
  - [x] Rate limit `run-check-now` (409 neu dang checking, 429 neu goi qua nhanh).
  - [x] Security tests cho SSRF/rate-limit.
    - [x] API test: create monitor reject localhost/private IP.
    - [x] API test: run-check rate-limit tra 429/409.
    - [x] Worker-level SSRF test cho path resolve private/internal IP.
  - [x] Auth rate-limit co ban cho register/login/refresh.
  - [x] Security middleware/headers cho production mode (trusted host, CSP, HSTS, docs toggle).

## Day 1 - Data model + migration (foundation)
- [ ] Tao model `monitors` voi cac truong MVP:
  - [ ] `id`, `user_id`, `name`, `url`, `monitor_type`
  - [ ] `interval_seconds`, `timeout_seconds`, `max_retries`, `slow_threshold_ms`
  - [ ] `detect_content_change`, `is_paused`, `current_status`
  - [ ] `last_checked_at`, `last_response_time_ms`, `last_status_code`
  - [ ] `last_error_message`, `last_success_at`, `created_at`, `updated_at`, `deleted_at`
- [ ] Tao model `check_runs`:
  - [ ] `monitor_id`, `status`, `started_at`, `finished_at`, `response_time_ms`
  - [ ] `status_code`, `error_type`, `error_message`
  - [ ] `final_url`, `title`, `content_type`, `content_hash`, `retry_count`
- [ ] Tao model `incidents`:
  - [ ] `monitor_id`, `opened_at`, `closed_at`, `status`
  - [ ] `open_reason`, `close_reason`, `first_failed_check_id`, `last_failed_check_id`
- [ ] Tao model `alert_events`:
  - [ ] `incident_id`, `monitor_id`, `channel`, `event_type`
  - [ ] `sent_to`, `sent_at`, `provider_message_id`, `send_status`, `error_message`
- [ ] Viet migration Alembic + chay `upgrade head`.
- [ ] Them index can thiet:
  - [ ] `monitors(user_id, current_status, is_paused)`
  - [ ] `check_runs(monitor_id, started_at desc)`
  - [ ] `incidents(monitor_id, status)`

Definition of done Day 1:
- [ ] DB schema tao xong, migrate clean tren local.
- [ ] Co seed data test nhanh 2-3 monitor.

## Day 2 - Monitor CRUD + list/filter/search API
- [ ] Tao schema request/response cho monitor.
- [ ] Implement API:
  - [ ] `POST /api/v1/monitors`
  - [ ] `GET /api/v1/monitors`
  - [ ] `GET /api/v1/monitors/{id}`
  - [ ] `PATCH /api/v1/monitors/{id}`
  - [ ] `DELETE /api/v1/monitors/{id}` (soft delete)
- [ ] Validate dau vao:
  - [ ] URL chi cho `http/https`
  - [ ] `interval_seconds >= 30`
  - [ ] `timeout_seconds <= interval_seconds`
  - [ ] `max_retries` trong nguong hop ly (vd 0-5)
- [ ] List API support:
  - [ ] `status`
  - [ ] `q` (name/url)
  - [ ] `page`, `page_size`
- [ ] User ownership check cho moi monitor.

Definition of done Day 2:
- [ ] Swagger test pass tat ca endpoint CRUD.
- [ ] Khong doc/sua monitor cua user khac.

## Day 3 - Celery app + HTTP check task
- [ ] Tao `celery_app.py` va config broker/result backend tu `.env`.
- [ ] Tao task `check_http_monitor(monitor_id)`:
  - [ ] set monitor `current_status=checking`
  - [ ] thuc hien HTTP request voi timeout/retry
  - [ ] ghi 1 dong `check_runs`
  - [ ] tinh status (`up/down/slow`)
  - [ ] update snapshot o `monitors`
- [ ] Tach ham tinh status de test don vi.
- [ ] Xu ly loi ky thuat ro rang:
  - [ ] dns_error
  - [ ] timeout
  - [ ] tls_error
  - [ ] http_error
- [ ] Tao endpoint `POST /api/v1/monitors/{id}/run-check`:
  - [ ] enqueue task
  - [ ] tra `202` + `job_id`

Definition of done Day 3:
- [ ] Tao monitor -> run-check-now -> co `check_runs`.
- [ ] UI/documents nhan duoc status moi.

## Day 4 - Scheduler + incident open/close + alert email
- [ ] Tao Beat scheduler enqueue monitor active theo `interval_seconds`.
- [ ] Skip monitor `is_paused=true` hoac `deleted_at != null`.
- [ ] Implement transition incident:
  - [ ] `UP -> DOWN`: open incident
  - [ ] `DOWN -> UP`: close incident
  - [ ] `SLOW` khong mo incident hard-down (MVP)
- [ ] Tao task email alert:
  - [ ] incident opened
  - [ ] incident recovered
- [ ] Dedupe alert:
  - [ ] khong gui email lien tuc moi lan beat check khi incident van open.
- [ ] Ghi `alert_events`.
- [x] Da implement:
  - [x] Incident transition trong checker (`UP/SLOW -> close`, `DOWN -> open neu chua co`).
  - [x] Email alert task SMTP cho `incident_opened` va `incident_recovered`.
  - [x] Ghi `alert_events` sau moi lan gui mail (sent/failed).
  - [x] Beat task `enqueue_due_monitor_checks` chay moi 30s.
  - [x] Worker task list da co `checks`, `notify`, `scheduler`.

Definition of done Day 4:
- [ ] Mo phong 1 URL loi va 1 URL phuc hoi, incident va email dung hanh vi.

## Day 5 - Dashboard + detail API (backend-ready cho UI)
- [ ] Tao API dashboard:
  - [x] `GET /api/v1/dashboard/summary`
  - [x] `GET /api/v1/dashboard/recent-monitors`
  - [x] `GET /api/v1/dashboard/recent-failures`
- [ ] Tao API detail data:
  - [x] `GET /api/v1/monitors/{id}/checks`
  - [x] `GET /api/v1/monitors/{id}/incidents`
  - [x] `GET /api/v1/monitors/{id}/alerts`
  - [x] support `limit`, `from`, `to` (checks + uptime; default window 30d khi khong truyen)
- [x] Tinh uptime percentage (dashboard `average_uptime_percent` + `GET .../uptime`; window clamp max 366d).
- [ ] Tra metadata moi nhat tu check run.
- [ ] Tra them advanced metrics: `dns_resolve_ms`, `tcp_connect_ms`, `tls_handshake_ms`, `ttfb_ms`.

Definition of done Day 5:
- [ ] Co du payload cho Dashboard/List/Detail page theo plan UI.

## Day 6 - Frontend M1 pages
- [~] Tao API client cho monitors + dashboard.
- [~] Dashboard page:
  - [x] stats cards (gom `average_uptime_percent` + tong check trong window mac dinh 30d)
  - [x] recent monitors
  - [x] recent failures
- [~] Websites list page:
  - [x] table
  - [x] filter (all/up/down/slow/paused)
  - [x] search (name/url)
- [~] Add Website modal:
  - [x] form validate basic (inline form ban dau)
  - [x] save -> refresh list
- [~] Run Check Now action:
  - [x] set queued/checking state co ban (show task queued)
  - [x] polling deterministic den khi xong (state ro rang: queued/checking/completed/timeout/failed)
- [~] Kien truc UI de giam rewrite:
  - [x] typed API layer (auth/monitors/dashboard) tach khoi views.
  - [x] page state toi thieu (loading/error/data) nhat quan.
  - [x] monitor detail consume `/uptime`, `/checks` (range), `/incidents`, `/alerts` khong tao flow rieng.

Definition of done Day 6:
- [x] Happy path UI co ban: add monitor -> run-check -> thay du lieu list/checks.

## Day 7 - Detail page + hardening + tests
- [ ] Website detail page:
  - [ ] summary block
  - [ ] actions (run check, pause/resume, edit, delete)
  - [x] history table (checks/incidents/alerts + sort/filter nhe)
  - [x] response time chart line co ban (24h/7d)
  - [ ] latest logs/errors block
  - [ ] block metrics ky thuat DNS/TCP/TLS/TTFB
- [ ] DOWN UX block:
  - [ ] failed_at, error_type, retry_attempts, last_success
- [ ] Viet tests toi thieu:
  - [ ] status calculator unit test
  - [ ] incident transition integration test
  - [ ] run-check-now API test
  - [ ] SSRF deny-list test (API + worker path)
  - [ ] run-check rate-limit test
- [ ] Smoke test full luong:
  - [ ] add monitor
  - [ ] beat check
  - [ ] down -> open incident + email
  - [ ] recover -> close incident + email

## Next batch (da agree de lam tiep)
- [x] Detail data presentation:
  - [x] checks/incidents/alerts table + sort/filter nhe.
  - [x] response-time chart 24h/7d.
  - [x] export CSV checks theo range.
- [x] Dashboard/List prioritization:
  - [x] them `last_failure_at` + `consecutive_failures`.
- [x] Error contract:
  - [x] thong nhat loi FE/BE theo `code + message`.
- [x] Ship confidence:
  - [x] smoke checklist manual + script hoa toi thieu (`planning-docs/SMOKE-CHECKLIST.md`, `scripts/smoke-check.ps1`).

Definition of done Day 7:
- [ ] M1 ship duoc o local Docker/VPS dev.
- [ ] Co checklist bug ton dong de vao M2.

## Non-negotiable technical guardrails (ap dung moi ngay)
- [ ] Khong silent-fail; loi phai co `code + message` ro rang.
- [ ] Khong over-abstract khi HTTP flow chua xong.
- [ ] Moi endpoint monitor phai ownership-check.
- [ ] Moi thay doi schema phai co migration va rollback note.
- [ ] Truoc khi chot ngay: test manually + update `PROJECT-PLAN.md` progress.
