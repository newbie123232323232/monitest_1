# Monitor-Region Resource-Saving Plan

## 1) Context and objective

This document defines the operational model for monitor-region execution with a strict resource-saving priority.

Current target behavior:
- One monitor can be associated with multiple regions.
- Exactly one region is active for execution at any point in time.
- Check execution uses only `active_region`.
- Other mapped regions are retained as configuration options, not executed concurrently.

Primary objective:
- Prevent queue overload and broker pressure caused by N-way fanout checks per monitor cycle.
- Keep user control explicit and deterministic (active region is visible and changeable).

Non-objective:
- No silent backward-compatibility fallback to legacy CSV behavior.
- No hidden consensus engine running in background.

## 2) Design constraints

- Keep Celery decoupled from API runtime.
- Preserve existing monitor business flow (create, run check, incidents, alerts).
- Make failure modes visible (invalid active region -> HTTP 400, missing runtime -> degraded warning).
- Avoid “smart” orchestration layers that hide queue state.

## 3) Data contract

### 3.1 Core entities

- `probe_regions`:
  - authoritative region catalog (`code`, `name`, `is_active`, `sort_order`).
- `monitor_regions`:
  - mapping table monitor <-> region.
- `monitors.active_region`:
  - single selected region used for check execution.

### 3.2 Invariants

- `active_region` MUST belong to monitor’s mapped `probe_regions`.
- A monitor must always have at least one mapped region.
- `check_runs.probe_region` stores the actual execution region (equal to `active_region` at run time).

## 4) Runtime execution policy

For each due check cycle:
1. Scheduler enqueues one check task for the monitor.
2. Worker loads monitor + `active_region`.
3. Worker executes one probe only.
4. Worker writes one `check_run` and updates monitor snapshot.
5. Incident/alert transitions follow that single execution outcome.

Result:
- Task volume scales with monitor count, not monitor_count * region_count.

## 5) UX policy

- Create monitor:
  - user selects mapped regions (`probe_regions` list),
  - user selects active region (single select from mapped list).
- Edit monitor/list/detail:
  - active region can be changed quickly via dropdown,
  - server validates selection strictly against mapped list.

Invalid selection behavior:
- backend returns HTTP 400 with explicit reason (`active_region must be one of probe_regions`).

## 6) Operational hardening policy

### 6.1 Restart and process discipline (local)

- Use guarded restart scripts:
  - `scripts/restart_full_stack.ps1`
  - `scripts/restart_celery_runtime.ps1`
- Enforce port guards on `8011` (API local) and `5173` (Frontend).
- Deploy runtime remains on `8010` (compose/nginx path).
- Avoid duplicate Celery worker/beat processes by idempotent stop/start.

### 6.2 Celery/Redis pressure controls

- Keep `broker_pool_limit` low and explicit.
- Keep `worker_prefetch_multiplier=1`.
- Enable broker heartbeat and health-check intervals.
- Use worker flags `--without-gossip --without-mingle` for lean runtime control traffic.

### 6.3 Runtime observability

- Use runtime endpoints:
  - `/api/v1/runtime/health`
  - `/api/v1/runtime/queue-profile`
- Treat degraded runtime as operational incident, not UI-only issue.

## 7) Rollout and verification checklist

Before merge/deploy:
- API tests for monitor create/update with `probe_regions` + `active_region`.
- Regression test: invalid `active_region` must return 400.
- Smoke test:
  - manual run-check enqueues once and executes once per click,
  - scheduled checks continue without queue pile-up,
  - check history shows expected `probe_region`.

After deploy:
- Verify `runtime/health` is `ok`.
- Verify queue profile recommendations do not indicate sustained lag.
- Verify no duplicate worker/beat instances in runtime environment.

## 8) Known risks and guardrails

- Risk: user selects overly aggressive interval/timeout/retry -> queue backlog.
  - Guardrail: queue profile endpoint + runtime warnings.
- Risk: stale local process holds port and causes false restart success.
  - Guardrail: strict port guard + explicit failure unless force-kill is requested.
- Risk: hidden fallback paths reintroduce legacy behavior.
  - Guardrail: keep contract strict; reject old shape explicitly.

## 9) Future extension (explicitly deferred)

If multi-region simultaneous execution is needed later, it must be a separate mode with:
- explicit capacity controls,
- explicit billing/plan constraints,
- explicit queue budget.

Do not reintroduce fanout as implicit default.

## 10) Implementation status (current)

- Completed:
  - Contract migration from CSV region to mapping tables (`probe_regions`, `monitor_regions`).
  - Active region execution model (`monitors.active_region`) with strict validation.
  - UI create/edit/list/detail flows for region assignment and active-region switching.
  - Runtime hardening for queue/celery stability and dashboard runtime UX optimization.
- Deprecated by design:
  - Old multi-region fanout/check-consensus behavior from early C1 slices is retired for resource-saving mode.
