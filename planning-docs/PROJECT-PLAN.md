# MONI — Plan triển khai chi tiết (cập nhật sau khi hoàn thành Auth cơ bản)

## 1) Mục tiêu MVP

Xây MONI theo luồng "thêm website -> hệ thống check định kỳ -> user thấy trạng thái ngay -> cảnh báo khi fail".
Ưu tiên tính đúng, ổn định, dễ vận hành hơn thêm nhiều tính năng trình diễn.

## 2) Trạng thái hiện tại (đã làm xong)

### Backend/Auth
- FastAPI + SQLAlchemy async + Alembic + PostgreSQL đã chạy ổn.
- Auth local: register, verify email (GET/POST), login, refresh, logout.
- Google OAuth: start + callback backend + trả token về SPA callback route.
- `JWT` access/refresh đang dùng được.
- Bổ sung xử lý lỗi dev để debug rõ traceback.
- Sửa luồng register để account chưa verify có thể đăng ký lại cùng email (không bị "kẹt" do data rác).

### Frontend/Auth
- Vue Router đã có `/login`, `/register`, `/verify-email`, `/auth/callback`.
- API client auth xử lý lỗi rõ hơn (parse `detail.message`, code, traceback dev).
- Vite proxy dev hoạt động (`/api` -> backend) để tránh lỗi CORS khi dev.

### Hạ tầng local
- Backend dev chuẩn: `127.0.0.1:8010`.
- Frontend dev chuẩn: `127.0.0.1:5173`.
- `.env` callback Google đã chỉnh về `http://localhost:8010/api/v1/auth/google/callback`.

## 3) Scope còn lại cho MVP Monitoring

### Có trong MVP
- Dashboard tổng quan.
- CRUD monitor HTTP(S) đầy đủ.
- Chạy check định kỳ qua Celery Beat + worker.
- Trigger check thủ công (Run Check Now).
- Website detail: summary + history + response-time chart + lỗi gần nhất.
- Trạng thái: `UP`, `DOWN`, `PENDING`, `CHECKING`, `PAUSED`, `SLOW`.
- Incident cơ bản + gửi email cảnh báo Gmail SMTP.
- Location-based monitoring (chon vi tri probe cho moi monitor).

### Không đưa vào MVP vòng này
- Status page public.
- Realtime websocket (dùng polling).
- SSO nhiều provider ngoài Google.
- Rule cảnh báo đa kênh (Slack/Telegram/SMS).
- Multi-location consensus check (3-5 locations, >50% fail moi mark DOWN).

## 4) Mapping user flow UI -> backend feature

### 4.1 Dashboard
Hiển thị:
- total monitors
- up/down/pending/checking
- average response time (N lần check gần nhất)
- recent monitors
- recent failures

API tối thiểu:
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/recent-monitors`
- `GET /api/v1/dashboard/recent-failures`

### 4.2 Add Website
Form:
- name, url, interval_seconds, timeout_seconds, detect_content_change (bool), slow_threshold_ms

Hành vi:
- tạo monitor thành công -> enqueue first check ngay.
- UI thấy trạng thái `PENDING` hoặc `CHECKING`.

API:
- `POST /api/v1/monitors`
- nội bộ: enqueue task `check_http_monitor(monitor_id)`.

### 4.3 Websites List
Cột:
- name, url, current_status, latest_response_time_ms, last_checked_at, interval

Filter/search:
- filter: all/up/down/slow/paused
- search: name/url

API:
- `GET /api/v1/monitors?status=&q=&page=&page_size=`

### 4.4 Website Detail
Summary:
- name, url, current status, last checked, current response, uptime%

Actions:
- run check now
- pause/resume
- edit config
- delete

Nội dung:
- status history table
- response time line chart
- latest metadata (title, final_url, content_type, status_code)
- latest logs/errors

API:
- `GET /api/v1/monitors/{id}`
- `GET /api/v1/monitors/{id}/checks`
- `POST /api/v1/monitors/{id}/run-check`
- `PATCH /api/v1/monitors/{id}`
- `DELETE /api/v1/monitors/{id}`

### 4.5 Trigger check thủ công
- UI đổi trạng thái `QUEUED/CHECKING`, polling 5s đến khi job xong.
- Không dùng websocket ở bản đầu.

### 4.6 DOWN và SLOW UX
- DOWN: block cảnh báo rõ failed_at, error_type, retries, last_success.
- SLOW: hiển thị cảnh báo mềm theo threshold.
- Tránh gộp SLOW vào DOWN để user phân biệt degradation vs outage.

## 5) Thiết kế dữ liệu (MVP - HTTP first)

## `monitors`
- id (uuid), user_id, name, url
- monitor_type (`http`)
- probe_region (vd: `ap-southeast-1`, `eu-central-1`) de ho tro location-based monitoring
- interval_seconds, timeout_seconds, max_retries
- slow_threshold_ms
- detect_content_change (bool)
- is_paused (bool)
- current_status (`pending|checking|up|down|slow|paused`)
- last_checked_at, last_response_time_ms, last_status_code
- last_error_message, last_success_at
- created_at, updated_at, deleted_at (nullable cho soft delete)

## `check_runs`
- id, monitor_id
- status (`up|down|slow|timeout|dns_error|tls_error|http_error`)
- started_at, finished_at, response_time_ms
- status_code, error_type, error_message
- final_url, title, content_type, content_hash
- dns_resolve_ms, tcp_connect_ms, tls_handshake_ms, ttfb_ms
- retry_count

## `incidents`
- id, monitor_id
- opened_at, closed_at, status (`open|closed`)
- open_reason, close_reason
- first_failed_check_id, last_failed_check_id

## `alert_events`
- id, incident_id, monitor_id, channel (`email`)
- event_type (`incident_opened|incident_recovered|still_down`)
- sent_to, sent_at, provider_message_id, send_status, error_message

Ghi chú:
- TCP/ICMP thêm sau, không ép abstraction sớm khi HTTP chưa ổn.

## 6) Worker + scheduler flow

### Beat
- mỗi N giây/phút enqueue monitor active.
- skip monitor `is_paused=true` hoặc `deleted_at != null`.

### Worker check HTTP
1. set `current_status=checking`
2. thực hiện HTTP request theo timeout/retries
3. do metrics ky thuat: DNS resolve time, TCP connect time, TLS handshake, TTFB
4. ghi `check_runs`
5. tính trạng thái `up/down/slow`
6. update snapshot ở `monitors`
7. mở/đóng incident nếu đổi trạng thái
8. enqueue email task khi mở/đóng incident

### Chính sách retry (MVP)
- retry nhanh trong cùng task: ví dụ `max_retries=2`.
- nếu fail toàn bộ -> `DOWN`.
- nếu thành công nhưng response_time vượt threshold -> `SLOW`.

## 7) API contract chi tiết cho monitor (MVP)

### Create monitor
- `POST /api/v1/monitors`
- body:
  - `name`, `url`, `interval_seconds`, `timeout_seconds`, `max_retries`, `slow_threshold_ms`, `detect_content_change`
- validate:
  - interval >= 30s (MVP anti abuse)
  - timeout <= interval
  - url phải là http/https

### Update monitor
- `PATCH /api/v1/monitors/{id}`
- cho phép sửa: name/url/interval/timeout/max_retries/threshold/detect_content_change/is_paused
- đổi config có hiệu lực cho lần check kế tiếp.

### Run check now
- `POST /api/v1/monitors/{id}/run-check`
- trả `202 Accepted` + `job_id` + trạng thái `queued`.

### Delete monitor
- `DELETE /api/v1/monitors/{id}`
- MVP: soft delete để không mất lịch sử audit.

## 8) Frontend plan theo page

### Page 1: Dashboard
- Stats cards, recent monitors, recent failures.
- Polling nhẹ mỗi 30s.

### Page 2: Websites List
- table + filter + search + pagination.
- row actions: `View Detail`, `Run Check Now`.

### Page 3: Website Detail
- summary + actions + chart + history + logs.
- khi run check now: polling 5s đến khi trạng thái ổn định.

### Modal
- Add Website
- Edit Website

## 9) Ưu tiên triển khai (milestone thực thi)

## M1 - HTTP vertical slice end-to-end
- model + migration cho `monitors`, `check_runs`, `incidents`.
- monitor CRUD + list/filter/search.
- celery task check HTTP + beat schedule.
- run-check-now endpoint.
- dashboard summary API cơ bản.

## M2 - UX hoàn thiện cho monitoring
- dashboard cards + recent failures.
- list/status badges + detail page.
- chart response time.
- block cảnh báo DOWN/SLOW rõ ràng.
- hien thi metrics DNS/TCP/TLS/TTFB tren detail.

## M3 - Alerting ổn định
- email incident opened/recovered.
- dedupe gửi mail (không spam mỗi lần beat chạy).
- logs alert events.
- SMTP-only (giu scope alert channel gon cho MVP).

## M4 - hardening trước mở rộng TCP/ICMP
- rate limit, concurrency guard.
- retention check_runs.
- test integration cho worker flow.

## 10) Checklist kỹ thuật bắt buộc

- Test:
  - unit: status calculation / incident transition.
  - integration: create monitor -> run check -> open incident -> recover.
- Observability:
  - structured logs cho API + worker.
  - endpoint health: db, redis, worker heartbeat.
- Security:
  - validate URL đầu vào tránh SSRF cơ bản (deny private ranges ở MVP nếu có thể).
  - giới hạn interval tối thiểu để tránh abuse.

## 11) Runbook dev hiện tại

1. Backend:
   - `cd backend`
   - `py -3 -m pip install -e ".[dev]"`
   - `py -3 -m alembic upgrade head`
   - `py -3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010`

2. Frontend:
   - `cd frontend`
   - `npm install`
   - `npx vite --host 127.0.0.1 --port 5173 --strictPort`

3. Worker/Beat (khi vào phase monitoring):
   - `cd backend`
   - `py -3 -m celery -A app.workers.celery_app worker -P solo -l info` (Windows)
   - `py -3 -m celery -A app.workers.celery_app beat -l info`

## 12) Quyết định kiến trúc chốt

- Monorepo, không tách microservice sớm.
- HTTP monitor làm chuẩn trước rồi mới mở TCP/ICMP.
- Polling thay websocket cho bản đầu.
- Dùng trạng thái `SLOW` riêng, không trộn với `DOWN`.
- Tập trung hoàn thiện core monitoring trước khi làm profile/change-password.
- Ho tro location-based monitoring; chua lam consensus da-vung o M1.
- Advanced metrics scope: DNS resolve, TCP connect, TLS handshake, TTFB (khong lam full page load trong M1).

## 13) M1 progress update (latest)

- Day 1 done: da co schema monitoring core (`monitors`, `check_runs`, `incidents`, `alert_events`) + migration.
- Day 2 done: monitor CRUD, filter/search, ownership check, soft delete, `run-check-now` endpoint.
- Create monitor da enqueue first check ngay sau khi save.
- Co integration test bao phu ownership + filter/search + run-check.
- Day 3 in progress: task HTTP da co retry theo `max_retries`, mapping timeout/dns/tls/http errors, va unit tests logic check.
- Da them `probe_region` cho location-based monitoring co ban.
- Da them metrics ky thuat vao check run: `dns_resolve_ms`, `tcp_connect_ms`, `tls_handshake_ms`, `ttfb_ms`.
- Da expose endpoint `GET /api/v1/monitors/{id}/checks` de UI/doc co du lieu metrics chi tiet.
- Day 4 da implement backend core:
  - incident transition `DOWN -> open`, `UP/SLOW -> close`.
  - alert email task SMTP (`incident_opened`, `incident_recovered`) + log `alert_events`.
  - beat schedule enqueue monitor den han (30s).
- Day 5 backend API da them:
  - `GET /api/v1/dashboard/summary`, `/recent-monitors`, `/recent-failures`.
  - `GET /api/v1/monitors/{id}/checks`, `/incidents`, `/alerts`.
- Uptime percentage, range query (`from/to`) va UI wiring cho dashboard/detail da implement (summary + monitor uptime/checks, detail co From/To).
- Day 6 UI toi thieu da khoi dong:
  - Da them route/page `dashboard` va `monitors` voi typed API client rieng.
  - Dashboard da render stats cards + recent monitors + recent failures.
  - Monitors page da co create monitor co ban, monitor table, `Run Check` action, va xem nhanh checks gan nhat.
  - Van con pending cho Day 6: filter/search, polling den khi check xong, va detail page day du.

## 14) Decision after manual testing

- Manual test da pass cho luong auth + monitor create/run-check + dashboard failure listing.
- Chot huong tiep theo: lam UI co ban ngay (khong cho backend "xong het"), theo vertical slice.
- Nguyen tac de tranh viet lai nhieu khi vao Vue:
  - API contract first: tao typed API client/stores truoc, UI consume qua layer nay.
  - UI thin layer: page/component khong embed business logic network.
  - Reuse payload hien co (`dashboard`, `checks`, `incidents`, `alerts`) thay vi tao endpoint moi khong can thiet.
  - Keep route skeleton som (`/dashboard`, `/monitors`, `/monitors/:id`) de on dinh navigation va state shape.
  - Build UI MVP first (read + basic actions), postpone styling polish.

## 15) Gap check vs plan + next priorities (updated)

- Chua xong o UI:
  - [x] Edit monitor tren UI (backend `PATCH` da duoc consume tren `Monitors` page).
  - [x] List filter/search co ban.
  - [x] Detail page route `/monitors/:id` consume checks/incidents/alerts.
  - [x] Pagination UI cho monitors list.
  - [x] Run-check polling deterministic (queued/checking/completed/timeout/failed) tren list + detail.
- ~~Chua xong o backend monitoring:~~ (done)
  - [x] Uptime percentage (dashboard aggregate + per-monitor endpoint).
  - [x] Range query `from/to` cho checks history va uptime (query params; checks default 30d neu bo trong).
- Alert hardening chua day du:
  - debounce/cooldown.
  - still-down reminder theo chu ky.
- Security hardening can uu tien:
  - SSRF guard host/IP.
  - rate limit cho `run-check-now`.
  - validation FE/BE dong bo va ro loi.

## 16) Execution order chot (product-first)

1. Hardening toi thieu bat buoc (security/correctness):
   - SSRF guard + run-check rate limit + validation chot.
2. Hoan thien UI core flow:
   - edit monitor, filter/search, monitor detail page.
3. Alert quality:
   - debounce/cooldown/still-down.
4. Test + release confidence:
   - integration/security tests va smoke checklist.

## 17) Hardening package status (current)

- [x] Bat dau SSRF guard:
  - API create/update monitor block host noi bo (`localhost`, `.local`, private/internal IP literal).
  - Worker check block target resolve vao private/internal IP (`blocked_target` error).
- [x] Rate limit `run-check-now`:
  - Block khi monitor dang `checking` (409).
  - Block khi monitor vua check trong cua so toi thieu (`run_check_min_interval_seconds`, mac dinh 15s) (429).
- [x] Tests cho SSRF/rate-limit path:
  - API test SSRF deny localhost/private IP.
  - API test run-check 429/409.
  - Worker-level SSRF deny when DNS resolve private/internal IP.
- [x] Auth/edge hardening bo sung:
  - Auth rate limit cho `register/login/refresh` theo IP + subject.
  - Production hardening middleware: trusted host, optional HTTPS redirect.
  - Security headers (`CSP`, `X-Frame-Options`, `HSTS` o production).
  - Production docs toggle (`expose_docs_in_production=false` mac dinh).
  - Fail-fast: chan dev mode tren public host neu khong explicit allow.

## 18) Next batch agreed (post-M1 polish)

- [~] Detail presentation upgrade:
  - [x] checks/incidents/alerts dang table + sort/filter nhe.
  - [x] response-time chart 24h/7d.
  - [x] export CSV checks theo range tu detail page.
- [x] Monitoring risk-prioritization data:
  - them `last_failure_at` + `consecutive_failures` vao list/dashboard.
- [x] Error contract standardization FE/BE:
  - thong nhat payload loi `code + message`, khong chi chuoi detail.
- [x] Smoke confidence package:
  - manual checklist + script hoa toi thieu de chot ship confidence (`planning-docs/SMOKE-CHECKLIST.md`, `scripts/smoke-check.ps1`).
  - [ ] Them npm/powershell shortcut command de chay smoke nhanh (defer sau).
