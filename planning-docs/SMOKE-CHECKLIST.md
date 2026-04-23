# MONI Smoke Checklist

## Purpose

Use this checklist to decide whether release confidence is sufficient after meaningful changes.
It combines:

- scripted smoke (fast and repeatable)
- manual UI smoke (real user flow validation)
- incident/alert smoke (when SMTP + scheduler are enabled)

## How to use

1. Run scripted smoke first to catch hard failures early
2. Run manual UI smoke on core product paths
3. If alerting is in scope, run incident/alert smoke
4. Mark release as ready only when done criteria pass

## Coverage

- service health and reachability
- authentication and dashboard/list reads
- monitor lifecycle (create -> run check -> detail)
- alert lifecycle (down -> recovered), when applicable

## 1) Preflight

- Backend running at `http://127.0.0.1:8010`
- Frontend running at `http://127.0.0.1:5173`
- Celery worker + beat running if scheduler/incident flow is being tested
- At least one verified account available for login

## 2) Scripted smoke (minimum)

Run:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1`

With token:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1 -AccessToken "<jwt>"`

With monitor scope:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1 -AccessToken "<jwt>" -MonitorId "<uuid>"`

Expected:

- every step returns `[PASS]`
- final line: `Smoke summary: N/N steps passed.`

## 3) Manual UI smoke

- Login succeeds and dashboard is reachable
- Dashboard loads cards and recent lists without error banners
- Monitors page:
  - create monitor succeeds
  - run-check shows clear state transitions (queued/checking/completed/timeout)
  - list shows pagination and risk fields (`consecutive_failures`, `last_failure_at`)
- Monitor detail:
  - uptime range works (`To` defaults to current time)
  - checks/incidents/alerts tables render with sort/filter
  - response-time chart 24h/7d renders when enough data exists
  - CSV export downloads correctly for selected range

## 4) Manual incident/alert smoke (if SMTP + beat enabled)

- Trigger monitor down -> incident opens + alert event logged/sent
- Recover monitor -> incident closes + recovered alert logged/sent
- Verify alert history in detail matches expected event and send status

## 5) Done criteria

- scripted smoke passes
- manual UI smoke passes
- incident/alert smoke passes when in release scope
- no new regression errors in backend tests or frontend build
