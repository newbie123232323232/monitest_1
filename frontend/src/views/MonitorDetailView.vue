<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue"
import { RouterLink, useRoute } from "vue-router"
import AppLayout from "../components/AppLayout.vue"
import UiBadge from "../components/ui/UiBadge.vue"
import UiButton from "../components/ui/UiButton.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import UiTable from "../components/ui/UiTable.vue"
import {
  getMonitorAlerts,
  getMonitorChecks,
  getMonitorDetail,
  getMonitorExpiryStatus,
  getMonitorIncidents,
  getMonitorUptime,
  runExpiryCheckNow,
  runCheckNow,
  updateMonitor,
  type AlertItem,
  type ChecksItem,
  type IncidentItem,
  type MonitorDetail,
  type MonitorExpiryStatus,
  type MonitorUptime,
} from "../api/monitors"

const route = useRoute()
const monitorId = computed(() => String(route.params.id || ""))

const loading = ref(false)
const error = ref<string | null>(null)
const actionMsg = ref<string | null>(null)
const notFound = ref(false)
const monitor = ref<MonitorDetail | null>(null)
const uptime = ref<MonitorUptime | null>(null)
const checks = ref<ChecksItem[]>([])
const incidents = ref<IncidentItem[]>([])
const alerts = ref<AlertItem[]>([])
const expiry = ref<MonitorExpiryStatus | null>(null)
const checksStatusFilter = ref<"all" | "up" | "slow" | "down" | "pending">("all")
const checksSort = ref<"finished_desc" | "finished_asc" | "latency_desc" | "latency_asc">("finished_desc")
const incidentsStatusFilter = ref<"all" | "open" | "closed">("all")
const incidentsSort = ref<"opened_desc" | "opened_asc">("opened_desc")
const alertsEventFilter = ref<"all" | AlertItem["event_type"]>("all")
const alertsSort = ref<"created_desc" | "created_asc">("created_desc")
const chartWindow = ref<"24h" | "7d">("24h")

/** Empty = backend default window (last 30 days). */
const rangeFrom = ref("")
const rangeTo = ref("")
const partialErrors = ref<string[]>([])
const runCheckPhase = ref<"idle" | "queued" | "checking" | "completed" | "failed" | "timeout">("idle")
const runCheckStatusMsg = ref<string | null>(null)
const activeRegionDraft = ref("global")
let runCheckPollTimer: number | null = null
let runCheckTimeoutTimer: number | null = null

function toDateTimeLocalValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function clearRunCheckPolling() {
  if (runCheckPollTimer !== null) {
    window.clearInterval(runCheckPollTimer)
    runCheckPollTimer = null
  }
  if (runCheckTimeoutTimer !== null) {
    window.clearTimeout(runCheckTimeoutTimer)
    runCheckTimeoutTimer = null
  }
}

function startRunCheckPolling(baselineLastCheckedAt: string | null) {
  clearRunCheckPolling()
  runCheckPhase.value = "queued"
  runCheckPollTimer = window.setInterval(async () => {
    try {
      const id = monitorId.value
      const m = await getMonitorDetail(id)
      monitor.value = m
      const hasNewCheck = (m.last_checked_at ?? null) !== (baselineLastCheckedAt ?? null)
      if (m.current_status === "checking") {
        runCheckPhase.value = "checking"
        runCheckStatusMsg.value = "Run check is in progress..."
      } else if (hasNewCheck) {
        runCheckPhase.value = "completed"
        runCheckStatusMsg.value = `Run check completed (${m.current_status})`
        clearRunCheckPolling()
        await loadDetail()
      } else {
        runCheckPhase.value = "queued"
        runCheckStatusMsg.value = "Run check queued..."
      }
    } catch (e) {
      runCheckPhase.value = "failed"
      runCheckStatusMsg.value = e instanceof Error ? e.message : "Polling failed"
      clearRunCheckPolling()
    }
  }, 2000)
  runCheckTimeoutTimer = window.setTimeout(() => {
    runCheckPhase.value = "timeout"
    runCheckStatusMsg.value = "Run check polling timeout after 60s"
    clearRunCheckPolling()
  }, 60000)
}

function rangeQuery():
  | { from?: string; to?: string }
  | undefined {
  const f = rangeFrom.value.trim()
  const t = rangeTo.value.trim()
  if (!f && !t) return undefined
  const q: { from?: string; to?: string } = {}
  if (f) {
    const from = new Date(f)
    if (Number.isNaN(from.getTime())) {
      error.value = "Invalid From datetime."
      return undefined
    }
    q.from = from.toISOString()
  }
  if (t) {
    const to = new Date(t)
    if (Number.isNaN(to.getTime())) {
      error.value = "Invalid To datetime."
      return undefined
    }
    q.to = to.toISOString()
  }
  return q
}

async function loadDetail() {
  const id = monitorId.value.trim()
  if (!id) {
    error.value = "Invalid monitor id"
    notFound.value = true
    return
  }
  loading.value = true
  error.value = null
  notFound.value = false
  partialErrors.value = []
  const rq = rangeQuery()
  if (rangeFrom.value.trim() || rangeTo.value.trim()) {
    if (!rq) {
      loading.value = false
      return
    }
  }
  try {
    const m = await getMonitorDetail(id)
    monitor.value = m
    activeRegionDraft.value = m.active_region || (m.probe_regions[0] ?? "global")
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Failed to load monitor detail"
    error.value = msg
    if (msg.toLowerCase().includes("not found")) {
      notFound.value = true
    }
    monitor.value = null
    uptime.value = null
    checks.value = []
    incidents.value = []
    alerts.value = []
    loading.value = false
    return
  }

  const results = await Promise.allSettled([
    getMonitorUptime(id, rq),
    getMonitorChecks(id, { limit: 100, ...rq }),
    getMonitorIncidents(id, 20),
    getMonitorAlerts(id, 20),
    getMonitorExpiryStatus(id),
  ])

  const [uptimeRes, checksRes, incidentsRes, alertsRes, expiryRes] = results
  if (uptimeRes.status === "fulfilled") uptime.value = uptimeRes.value
  else {
    uptime.value = null
    const msg = uptimeRes.reason instanceof Error ? uptimeRes.reason.message : "Failed to load uptime"
    if (msg.toLowerCase() === "not found") {
      partialErrors.value.push("uptime: endpoint unavailable on backend runtime (restart backend)")
    } else {
      partialErrors.value.push(`uptime: ${msg}`)
    }
  }
  if (checksRes.status === "fulfilled") checks.value = checksRes.value
  else {
    checks.value = []
    partialErrors.value.push(
      `checks: ${checksRes.reason instanceof Error ? checksRes.reason.message : "Failed to load checks"}`,
    )
  }
  if (incidentsRes.status === "fulfilled") incidents.value = incidentsRes.value
  else {
    incidents.value = []
    partialErrors.value.push(
      `incidents: ${incidentsRes.reason instanceof Error ? incidentsRes.reason.message : "Failed to load incidents"}`,
    )
  }
  if (alertsRes.status === "fulfilled") alerts.value = alertsRes.value
  else {
    alerts.value = []
    partialErrors.value.push(
      `alerts: ${alertsRes.reason instanceof Error ? alertsRes.reason.message : "Failed to load alerts"}`,
    )
  }
  if (expiryRes.status === "fulfilled") expiry.value = expiryRes.value
  else {
    expiry.value = null
    const msg = expiryRes.reason instanceof Error ? expiryRes.reason.message : "Failed to load expiry"
    if (!msg.toLowerCase().includes("not available yet")) {
      partialErrors.value.push(`expiry: ${msg}`)
    }
  }

  if (partialErrors.value.length > 0) {
    error.value = `Some sections failed to load: ${partialErrors.value.join(" | ")}`
  }
  loading.value = false
}

function clearRange() {
  rangeFrom.value = ""
  rangeTo.value = ""
  error.value = null
  void loadDetail()
}

async function handleRunCheck() {
  actionMsg.value = null
  error.value = null
  try {
    const baselineLastCheckedAt = monitor.value?.last_checked_at ?? null
    const res = await runCheckNow(monitorId.value)
    actionMsg.value = `Queued check task ${res.task_id}`
    runCheckStatusMsg.value = `Task ${res.task_id}`
    startRunCheckPolling(baselineLastCheckedAt)
  } catch (e) {
    runCheckPhase.value = "failed"
    error.value = e instanceof Error ? e.message : "Run check failed"
  }
}

async function handleActiveRegionChange() {
  if (!monitor.value) return
  const allowed = monitor.value.probe_regions ?? []
  if (!allowed.includes(activeRegionDraft.value)) {
    error.value = "Active region must be one of monitor regions."
    activeRegionDraft.value = monitor.value.active_region || allowed[0] || "global"
    return
  }
  actionMsg.value = null
  error.value = null
  try {
    const updated = await updateMonitor(monitor.value.id, { active_region: activeRegionDraft.value })
    monitor.value = updated
    activeRegionDraft.value = updated.active_region || (updated.probe_regions[0] ?? "global")
    actionMsg.value = `Active region updated: ${activeRegionDraft.value}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to update active region"
  }
}

async function handleRunExpiryCheck() {
  actionMsg.value = null
  error.value = null
  try {
    const res = await runExpiryCheckNow(monitorId.value)
    actionMsg.value = `Queued expiry check task ${res.task_id}`
    window.setTimeout(() => {
      void loadDetail()
    }, 2000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Run expiry check failed"
  }
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "n/a"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function escapeCsv(value: string | number | null | undefined): string {
  const raw = value == null ? "" : String(value)
  if (/[",\n]/.test(raw)) return `"${raw.replace(/"/g, "\"\"")}"`
  return raw
}

function exportChecksCsv() {
  const rows = filteredChecks.value
  if (!rows.length) {
    actionMsg.value = "No checks to export for current filters/range."
    return
  }
  const header = [
    "id",
    "status",
    "started_at",
    "finished_at",
    "status_code",
    "response_time_ms",
    "dns_resolve_ms",
    "tcp_connect_ms",
    "tls_handshake_ms",
    "ttfb_ms",
    "retry_count",
    "error_type",
    "error_message",
  ]
  const body = rows.map((c) =>
    [
      c.id,
      c.status,
      c.started_at,
      c.finished_at,
      c.status_code,
      c.response_time_ms,
      c.dns_resolve_ms,
      c.tcp_connect_ms,
      c.tls_handshake_ms,
      c.ttfb_ms,
      c.retry_count,
      c.error_type,
      c.error_message,
    ]
      .map(escapeCsv)
      .join(","),
  )
  const csv = [header.join(","), ...body].join("\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  const ts = new Date().toISOString().replace(/[:.]/g, "-")
  a.href = url
  a.download = `checks-${monitorId.value}-${ts}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  actionMsg.value = `Exported ${rows.length} checks to CSV`
}

function checkStatusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const s = status.toLowerCase()
  if (s === "up") return "success"
  if (s === "slow" || s === "checking" || s === "pending") return "warning"
  return "danger"
}

function expiryTone(state: string): "success" | "warning" | "danger" | "neutral" {
  if (state === "ok") return "success"
  if (state.startsWith("warn_")) return "warning"
  if (state === "expired") return "danger"
  return "neutral"
}

const filteredChecks = computed(() => {
  let rows = checks.value.slice()
  if (checksStatusFilter.value !== "all") {
    rows = rows.filter((c) => c.status.toLowerCase() === checksStatusFilter.value)
  }
  if (checksSort.value === "finished_desc") {
    rows.sort((a, b) => +new Date(b.finished_at) - +new Date(a.finished_at))
  } else if (checksSort.value === "finished_asc") {
    rows.sort((a, b) => +new Date(a.finished_at) - +new Date(b.finished_at))
  } else if (checksSort.value === "latency_desc") {
    rows.sort((a, b) => (b.response_time_ms ?? -1) - (a.response_time_ms ?? -1))
  } else {
    rows.sort((a, b) => (a.response_time_ms ?? Number.MAX_SAFE_INTEGER) - (b.response_time_ms ?? Number.MAX_SAFE_INTEGER))
  }
  return rows
})

type RegionSummaryRow = {
  probe_region: string
  total_checks: number
  up_checks: number
  slow_checks: number
  down_checks: number
  avg_response_time_ms: number | null
  last_finished_at: string | null
}

const regionSummaryRows = computed<RegionSummaryRow[]>(() => {
  const grouped = new Map<string, {
    total: number
    up: number
    slow: number
    down: number
    latencySum: number
    latencyCount: number
    lastFinishedAt: string | null
  }>()
  for (const row of checks.value) {
    const region = (row.probe_region || "global").trim() || "global"
    const current = grouped.get(region) ?? {
      total: 0,
      up: 0,
      slow: 0,
      down: 0,
      latencySum: 0,
      latencyCount: 0,
      lastFinishedAt: null,
    }
    current.total += 1
    const st = row.status.toLowerCase()
    if (st === "up") current.up += 1
    else if (st === "slow") current.slow += 1
    else current.down += 1
    if (typeof row.response_time_ms === "number") {
      current.latencySum += row.response_time_ms
      current.latencyCount += 1
    }
    if (!current.lastFinishedAt || +new Date(row.finished_at) > +new Date(current.lastFinishedAt)) {
      current.lastFinishedAt = row.finished_at
    }
    grouped.set(region, current)
  }
  return Array.from(grouped.entries())
    .map(([probe_region, agg]) => ({
      probe_region,
      total_checks: agg.total,
      up_checks: agg.up,
      slow_checks: agg.slow,
      down_checks: agg.down,
      avg_response_time_ms: agg.latencyCount > 0 ? agg.latencySum / agg.latencyCount : null,
      last_finished_at: agg.lastFinishedAt,
    }))
    .sort((a, b) => {
      const bt = a.last_finished_at ? +new Date(a.last_finished_at) : 0
      const at = b.last_finished_at ? +new Date(b.last_finished_at) : 0
      return at - bt
    })
})

const filteredIncidents = computed(() => {
  let rows = incidents.value.slice()
  if (incidentsStatusFilter.value !== "all") {
    rows = rows.filter((i) => i.status === incidentsStatusFilter.value)
  }
  if (incidentsSort.value === "opened_desc") rows.sort((a, b) => +new Date(b.opened_at) - +new Date(a.opened_at))
  else rows.sort((a, b) => +new Date(a.opened_at) - +new Date(b.opened_at))
  return rows
})

const filteredAlerts = computed(() => {
  let rows = alerts.value.slice()
  if (alertsEventFilter.value !== "all") rows = rows.filter((a) => a.event_type === alertsEventFilter.value)
  if (alertsSort.value === "created_desc") rows.sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
  else rows.sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at))
  return rows
})

const chartData = computed(() => {
  const now = Date.now()
  const windowMs = chartWindow.value === "24h" ? 24 * 3600 * 1000 : 7 * 24 * 3600 * 1000
  return checks.value
    .filter((c) => c.response_time_ms != null && +new Date(c.finished_at) >= now - windowMs)
    .sort((a, b) => +new Date(a.finished_at) - +new Date(b.finished_at))
})

const chartPolyline = computed(() => {
  const rows = chartData.value
  if (rows.length < 2) return ""
  const w = 640
  const h = 140
  const minTs = +new Date(rows[0].finished_at)
  const maxTs = +new Date(rows[rows.length - 1].finished_at)
  const maxRt = Math.max(...rows.map((r) => r.response_time_ms ?? 0), 1)
  return rows
    .map((r) => {
      const ts = +new Date(r.finished_at)
      const x = maxTs === minTs ? 0 : ((ts - minTs) / (maxTs - minTs)) * w
      const y = h - ((r.response_time_ms ?? 0) / maxRt) * h
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(" ")
})

watch(
  () => route.params.id,
  () => {
    clearRunCheckPolling()
    runCheckPhase.value = "idle"
    runCheckStatusMsg.value = null
    // Default "To" to current local time for faster uptime filtering.
    rangeTo.value = toDateTimeLocalValue(new Date())
    void loadDetail()
  },
  { immediate: true },
)

onUnmounted(() => {
  clearRunCheckPolling()
})
</script>

<template>
  <AppLayout>
  <div class="page">
    <p class="back muted"><RouterLink to="/monitors">← Monitors</RouterLink></p>
    <h1>{{ monitor?.name ?? "Monitor" }}</h1>
    <p v-if="loading">Loading…</p>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="actionMsg" class="ok">{{ actionMsg }}</p>
    <p v-if="runCheckStatusMsg" class="muted">Run-check: {{ runCheckPhase }}{{ runCheckStatusMsg ? ` · ${runCheckStatusMsg}` : "" }}</p>

    <UiCard v-if="notFound">
      <UiPanelHeader title="Monitor not found" />
      <p class="muted">Monitor này không còn tồn tại, hoặc không thuộc tài khoản hiện tại.</p>
      <div class="actions">
        <RouterLink :to="`/monitors?q=${encodeURIComponent(monitorId)}&focusSearch=1`">Try another monitor</RouterLink>
        <RouterLink to="/monitors">Back to Monitors</RouterLink>
        <RouterLink to="/dashboard">Go to Dashboard</RouterLink>
      </div>
    </UiCard>

    <UiCard v-if="monitor && !notFound">
      <UiPanelHeader :title="monitor.name" />
      <p><strong>URL:</strong> {{ monitor.url }}</p>
      <p><strong>Accepted HTTP codes:</strong> <code>{{ monitor.accepted_status_codes }}</code></p>
      <p><strong>Regions:</strong> <code>{{ monitor.probe_regions.join(", ") }}</code></p>
      <p><strong>Active region:</strong> <code>{{ monitor.active_region }}</code></p>
      <p><strong>Status:</strong> <UiBadge :tone="checkStatusTone(monitor.current_status)">● {{ monitor.current_status }}</UiBadge></p>
      <p><strong>Last checked:</strong> {{ fmtDateTime(monitor.last_checked_at) }}</p>
      <p><strong>Last success:</strong> {{ fmtDateTime(monitor.last_success_at) }}</p>
      <p><strong>Last error:</strong> {{ monitor.last_error_message ?? "n/a" }}</p>
      <div class="actions">
        <label>
          Active region
          <select v-model="activeRegionDraft" @change="handleActiveRegionChange">
            <option v-for="region in monitor.probe_regions" :key="region" :value="region">
              {{ region }}
            </option>
          </select>
        </label>
        <UiButton
          @click="handleRunCheck"
          :disabled="runCheckPhase === 'queued' || runCheckPhase === 'checking'"
        >
          {{ runCheckPhase === "queued" ? "Queued..." : runCheckPhase === "checking" ? "Checking..." : "Run Check" }}
        </UiButton>
        <UiButton @click="loadDetail" :disabled="loading">Refresh</UiButton>
      </div>
    </UiCard>

    <UiCard v-if="monitor && !notFound">
      <UiPanelHeader title="SSL / Domain Expiry" />
      <p>
        <strong>SSL state:</strong>
        <UiBadge :tone="expiryTone(expiry?.ssl_state ?? 'unknown')">{{ expiry?.ssl_state ?? "unknown" }}</UiBadge>
        <span class="muted"> · days left: {{ expiry?.ssl_days_left ?? "n/a" }}</span>
      </p>
      <p><strong>SSL expires at:</strong> {{ fmtDateTime(expiry?.ssl_expires_at ?? null) }}</p>
      <p>
        <strong>Domain state:</strong>
        <UiBadge :tone="expiryTone(expiry?.domain_state ?? 'unknown')">{{ expiry?.domain_state ?? "unknown" }}</UiBadge>
        <span class="muted"> · days left: {{ expiry?.domain_days_left ?? "n/a" }}</span>
      </p>
      <p><strong>Domain expires at:</strong> {{ fmtDateTime(expiry?.domain_expires_at ?? null) }}</p>
      <p><strong>Last expiry check:</strong> {{ fmtDateTime(expiry?.last_checked_at ?? null) }}</p>
      <p><strong>Last expiry error:</strong> {{ expiry?.last_error ?? "n/a" }}</p>
      <div class="actions">
        <UiButton @click="handleRunExpiryCheck">Run Expiry Check</UiButton>
      </div>
    </UiCard>

    <UiCard v-if="uptime && !notFound">
      <UiPanelHeader title="Uptime" />
      <p>
        <strong>{{ uptime.uptime_percent != null ? uptime.uptime_percent.toFixed(2) + "%" : "n/a" }}</strong>
        ({{ uptime.success_checks }} / {{ uptime.total_checks }} successful checks)
      </p>
      <p class="muted">
        Window: {{ fmtDateTime(uptime.window_from) }} → {{ fmtDateTime(uptime.window_to) }}
      </p>
      <div class="range">
        <label>From <input v-model="rangeFrom" type="datetime-local" step="1" /></label>
        <label>To <input v-model="rangeTo" type="datetime-local" step="1" /></label>
        <UiButton variant="primary" @click="loadDetail">Apply range</UiButton>
        <UiButton variant="ghost" class="ghost" @click="clearRange">Default (30d)</UiButton>
      </div>
      <div class="chart-head">
        <h3>Response Time</h3>
        <label>
          Window
          <select v-model="chartWindow">
            <option value="24h">24h</option>
            <option value="7d">7d</option>
          </select>
        </label>
      </div>
      <div class="chart-wrap">
        <svg v-if="chartPolyline" viewBox="0 0 640 140" preserveAspectRatio="none" class="chart-svg">
          <polyline :points="chartPolyline" fill="none" stroke="currentColor" stroke-width="2" />
        </svg>
        <p v-else class="muted">Not enough successful checks in selected window.</p>
      </div>
    </UiCard>

    <UiCard v-if="!notFound">
      <UiPanelHeader title="Checks" />
      <div class="table-tools">
        <label>Status
          <select v-model="checksStatusFilter">
            <option value="all">all</option>
            <option value="up">up</option>
            <option value="slow">slow</option>
            <option value="down">down</option>
            <option value="pending">pending</option>
          </select>
        </label>
        <label>Sort
          <select v-model="checksSort">
            <option value="finished_desc">newest</option>
            <option value="finished_asc">oldest</option>
            <option value="latency_desc">latency high→low</option>
            <option value="latency_asc">latency low→high</option>
          </select>
        </label>
        <UiButton variant="ghost" class="ghost" @click="exportChecksCsv">Export CSV</UiButton>
      </div>
      <UiPanelHeader title="Region Summary" />
      <UiTable>
        <table class="history-table">
          <thead>
            <tr>
              <th>Region</th>
              <th>Total</th>
              <th>UP</th>
              <th>SLOW</th>
              <th>DOWN/ERR</th>
              <th>AVG ms</th>
              <th>Last check</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in regionSummaryRows" :key="r.probe_region">
              <td><code>{{ r.probe_region }}</code></td>
              <td>{{ r.total_checks }}</td>
              <td>{{ r.up_checks }}</td>
              <td>{{ r.slow_checks }}</td>
              <td>{{ r.down_checks }}</td>
              <td>{{ r.avg_response_time_ms != null ? r.avg_response_time_ms.toFixed(1) : "n/a" }}</td>
              <td>{{ fmtDateTime(r.last_finished_at) }}</td>
            </tr>
            <tr v-if="regionSummaryRows.length === 0">
              <td class="muted empty-row" colspan="7">No regional checks available yet.</td>
            </tr>
          </tbody>
        </table>
      </UiTable>
      <div class="table-scroll checks-list">
        <UiTable>
        <table class="history-table">
          <thead>
            <tr>
              <th>Finished</th>
              <th>Region</th>
              <th>Status</th>
              <th>Code</th>
              <th>Total</th>
              <th>DNS</th>
              <th>TCP</th>
              <th>TLS</th>
              <th>TTFB</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filteredChecks" :key="c.id">
              <td>{{ fmtDateTime(c.finished_at) }}</td>
              <td><code>{{ c.probe_region || "global" }}</code></td>
              <td><UiBadge :tone="checkStatusTone(c.status)">● {{ c.status }}</UiBadge></td>
              <td>{{ c.status_code ?? "n/a" }}</td>
              <td>{{ c.response_time_ms ?? "n/a" }}ms</td>
              <td>{{ c.dns_resolve_ms ?? "n/a" }}ms</td>
              <td>{{ c.tcp_connect_ms ?? "n/a" }}ms</td>
              <td>{{ c.tls_handshake_ms ?? "n/a" }}ms</td>
              <td>{{ c.ttfb_ms ?? "n/a" }}ms</td>
            </tr>
            <tr v-if="filteredChecks.length === 0">
              <td class="muted empty-row" colspan="9">No checks found for this range/filter.</td>
            </tr>
          </tbody>
        </table>
        </UiTable>
      </div>
    </UiCard>

    <UiCard v-if="!notFound">
      <UiPanelHeader title="Incidents" />
      <div class="table-tools">
        <label>Status
          <select v-model="incidentsStatusFilter">
            <option value="all">all</option>
            <option value="open">open</option>
            <option value="closed">closed</option>
          </select>
        </label>
        <label>Sort
          <select v-model="incidentsSort">
            <option value="opened_desc">newest</option>
            <option value="opened_asc">oldest</option>
          </select>
        </label>
      </div>
      <div class="table-scroll history-list">
        <UiTable>
        <table class="history-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Opened</th>
              <th>Closed</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inc in filteredIncidents" :key="inc.id">
              <td><UiBadge :tone="inc.status === 'open' ? 'danger' : 'success'">● {{ inc.status }}</UiBadge></td>
              <td>{{ fmtDateTime(inc.opened_at) }}</td>
              <td>{{ fmtDateTime(inc.closed_at) }}</td>
              <td>{{ inc.open_reason ?? "n/a" }}</td>
            </tr>
            <tr v-if="filteredIncidents.length === 0">
              <td class="muted empty-row" colspan="4">No incidents found.</td>
            </tr>
          </tbody>
        </table>
        </UiTable>
      </div>
    </UiCard>

    <UiCard v-if="!notFound">
      <UiPanelHeader title="Alerts" />
      <div class="table-tools">
        <label>Event
          <select v-model="alertsEventFilter">
            <option value="all">all</option>
            <option value="incident_opened">incident_opened</option>
            <option value="incident_recovered">incident_recovered</option>
            <option value="still_down">still_down</option>
          </select>
        </label>
        <label>Sort
          <select v-model="alertsSort">
            <option value="created_desc">newest</option>
            <option value="created_asc">oldest</option>
          </select>
        </label>
      </div>
      <div class="table-scroll history-list">
        <UiTable>
        <table class="history-table">
          <thead>
            <tr>
              <th>Event</th>
              <th>Status</th>
              <th>Sent To</th>
              <th>Sent At</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in filteredAlerts" :key="a.id">
              <td><UiBadge :tone="a.event_type === 'incident_opened' ? 'danger' : a.event_type === 'still_down' ? 'warning' : 'success'">● {{ a.event_type }}</UiBadge></td>
              <td>{{ a.send_status }}</td>
              <td>{{ a.sent_to ?? "n/a" }}</td>
              <td>{{ fmtDateTime(a.sent_at) }}</td>
            </tr>
            <tr v-if="filteredAlerts.length === 0">
              <td class="muted empty-row" colspan="4">No alerts sent yet.</td>
            </tr>
          </tbody>
        </table>
        </UiTable>
      </div>
    </UiCard>
  </div>
  </AppLayout>
</template>

<style scoped>
.page { width: 100%; font-family: var(--sans), system-ui, sans-serif; }
.back { margin: 0 0 0.5rem; font-size: 0.9rem; }
.back a { color: var(--accent); text-decoration: none; font-weight: 500; }
.back a:hover { text-decoration: underline; }
.panel { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; }
.panel ul { padding-left: 1rem; margin: 0; }
.panel li { margin-bottom: 0.4rem; }
.chart-head { margin-top: 0.75rem; display: flex; justify-content: space-between; align-items: end; gap: 0.75rem; }
.chart-head h3 { margin: 0; font-size: 0.95rem; }
.chart-head label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.8rem; }
.chart-wrap { margin-top: 0.5rem; border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem; }
.chart-svg { width: 100%; height: 140px; color: #2563eb; display: block; }
.table-tools { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.5rem; }
.table-tools label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.8rem; }
.table-tools :deep(.ui-btn) { align-self: end; }
.table-scroll { border: 1px solid var(--border); border-radius: 8px; }
.history-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.history-table th, .history-table td { text-align: left; padding: 0.35rem 0.45rem; border-bottom: 1px solid var(--border); }
.history-table th { position: sticky; top: 0; background: var(--bg); z-index: 1; }
.empty-row { text-align: center; }
.checks-list {
  height: 20rem;
  overflow-y: scroll;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-right: 0.2rem;
}
.history-list {
  height: 11rem;
  overflow-y: scroll;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-right: 0.2rem;
}
.err { color: #b91c1c; }
.ok { color: #15803d; }
.muted { color: #64748b; font-size: 0.9rem; }
.actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.range { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; margin-top: 0.5rem; }
.range label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; }
.range input[type="datetime-local"] { font-size: 0.85rem; }
.ghost { background: transparent; border: 1px solid var(--border); }
</style>
