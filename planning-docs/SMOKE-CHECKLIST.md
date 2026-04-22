# MONI Smoke Checklist

Muc tieu: chot ship confidence truoc khi merge/release local dev.

## 1) Preflight

- Backend dang chay o `http://127.0.0.1:8010`
- Frontend dang chay o `http://127.0.0.1:5173`
- Celery worker + beat dang chay neu can test scheduler/incident flow
- Co tai khoan da verify email de login UI

## 2) Scripted smoke (toi thieu)

Chay script:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1`

Neu co token:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1 -AccessToken "<jwt>"`

Neu muon check 1 monitor cu the:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-check.ps1 -AccessToken "<jwt>" -MonitorId "<uuid>"`

Expected:

- Tất cả step `[PASS]`
- Cuoi script: `Smoke summary: N/N steps passed.`

## 3) Manual UI smoke

- Login thanh cong, vao `Dashboard` duoc
- Dashboard load du cards + recent lists, khong error banner
- Monitors page:
  - create monitor thanh cong
  - run-check hien state queued/checking/completed hoac timeout ro rang
  - list co pagination + risk field (`consecutive_failures`, `last_failure_at`)
- Monitor detail:
  - uptime range hoat dong (`To` mac dinh now)
  - checks/incidents/alerts render table + sort/filter
  - response-time chart 24h/7d render khi du data
  - export CSV checks theo range tai duoc file

## 4) Manual incident/alert smoke (neu SMTP + beat da bat)

- Trigger monitor down -> tao incident open + alert event
- Recover monitor -> dong incident + alert recovered
- Kiem tra alerts history trong detail map dung event/send status

## 5) Done criteria

- Script smoke pass
- Manual UI smoke pass
- (Neu ap dung) incident/alert smoke pass
- Khong co error regression moi trong backend tests/frontend build
