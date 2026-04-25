<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue"
import { RouterLink } from "vue-router"
import AppLayout from "../components/AppLayout.vue"
import UiButton from "../components/ui/UiButton.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import UiBadge from "../components/ui/UiBadge.vue"
import {
  getDashboardSummary,
  getDashboardRegionSummary,
  getExpirySummary,
  getRecentFailures,
  getRecentMonitors,
  type DashboardRegionSummaryItem,
  type DashboardSummary,
  type ExpirySummary,
} from "../api/dashboard"
import type { MonitorItem } from "../api/monitors"
import {
  getCachedRuntimeHealth,
  getCachedRuntimeQueueProfile,
  getRuntimeHealth,
  getRuntimeQueueProfile,
  type RuntimeHealth,
  type RuntimeQueueProfile,
} from "../api/runtime"

const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<DashboardSummary | null>(null)
const expirySummary = ref<ExpirySummary | null>(null)
const regionSummary = ref<DashboardRegionSummaryItem[]>([])
const recentMonitors = ref<MonitorItem[]>([])
const recentFailures = ref<MonitorItem[]>([])
const lastUpdatedAt = ref<Date | null>(null)
const runtimeHealth = ref<RuntimeHealth | null>(null)
const queueProfile = ref<RuntimeQueueProfile | null>(null)
/** Empty = backend default uptime window (last 30 days). */
const uptimeFrom = ref("")
const uptimeTo = ref("")
let refreshTimer: number | null = null
let runtimeLoadSeq = 0

function uptimeRangeQuery(): { uptime_from: string; uptime_to: string } | undefined {
  const f = uptimeFrom.value.trim()
  const t = uptimeTo.value.trim()
  if (!f && !t) return undefined
  if (f && t) {
    return { uptime_from: new Date(f).toISOString(), uptime_to: new Date(t).toISOString() }
  }
  error.value = "Chọn cả From và To, hoặc để trống cả hai (mặc định 30 ngày)."
  return undefined
}

function clearUptimeRange() {
  uptimeFrom.value = ""
  uptimeTo.value = ""
  error.value = null
  void load()
}

async function load() {
  loading.value = true
  error.value = null
  const uq = uptimeRangeQuery()
  if ((uptimeFrom.value.trim() || uptimeTo.value.trim()) && !uq) {
    loading.value = false
    return
  }
  try {
    const [s, m, f, e, r] = await Promise.all([
      getDashboardSummary(uq),
      getRecentMonitors(8),
      getRecentFailures(8),
      getExpirySummary(),
      getDashboardRegionSummary({ from: uq?.uptime_from, to: uq?.uptime_to }),
    ])
    summary.value = s
    recentMonitors.value = m
    recentFailures.value = f
    expirySummary.value = e
    regionSummary.value = r
    // Render runtime cards from cache immediately to avoid blocking dashboard first paint.
    runtimeHealth.value = getCachedRuntimeHealth()
    queueProfile.value = getCachedRuntimeQueueProfile(60)
    lastUpdatedAt.value = new Date()
    void loadRuntimePanels()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load dashboard"
  } finally {
    loading.value = false
  }
}

async function loadRuntimePanels() {
  const seq = ++runtimeLoadSeq
  const [rhRes, qpRes] = await Promise.allSettled([getRuntimeHealth(), getRuntimeQueueProfile(60)])
  if (seq !== runtimeLoadSeq) return
  runtimeHealth.value = rhRes.status === "fulfilled" ? rhRes.value : runtimeHealth.value
  queueProfile.value = qpRes.status === "fulfilled" ? qpRes.value : queueProfile.value
}

function fmtTime(d: Date | null): string {
  if (!d) return "n/a"
  return d.toLocaleTimeString()
}

function fmtIso(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function fmtAvgMs(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "n/a"
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function fmtPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "n/a"
  return `${(value * 100).toFixed(1)}%`
}

function riskText(consecutive: number | undefined): string {
  if (!consecutive || consecutive <= 0) return "stable"
  return `${consecutive} fail(s)`
}

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const s = status.toLowerCase()
  if (s === "up") return "success"
  if (s === "slow" || s === "checking" || s === "pending") return "warning"
  if (s === "down") return "danger"
  return "neutral"
}

onMounted(async () => {
  await load()
  refreshTimer = window.setInterval(() => {
    void load()
  }, 15000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <AppLayout>
    <div class="page">
    <h1>Dashboard</h1>
    <UiCard v-if="runtimeHealth && runtimeHealth.status !== 'ok'" class="runtime-alert">
      <UiPanelHeader title="Runtime Degraded" subtitle="Worker/beat/Redis khong on dinh, check tasks co the bi tre" />
      <p class="err">
        {{ runtimeHealth.degraded_reasons.join(", ") }}
      </p>
    </UiCard>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="loading">Loading…</p>

    <UiCard class="uptime-panel">
      <UiPanelHeader title="Uptime window" subtitle="Thong ke Avg uptime theo range" />
      <p class="muted small">
        Để trống = 30 ngày gần nhất. Hoặc chọn khoảng thời gian (From và To).
      </p>
      <div class="uptime-row">
        <label>
          From
          <input v-model="uptimeFrom" type="datetime-local" />
        </label>
        <label>
          To
          <input v-model="uptimeTo" type="datetime-local" />
        </label>
        <UiButton variant="primary" @click="load" :disabled="loading">Áp dụng</UiButton>
        <UiButton @click="clearUptimeRange" :disabled="loading">Mặc định (30d)</UiButton>
      </div>
    </UiCard>

    <section v-if="summary" class="cards">
      <UiCard compact class="card"><strong>Total</strong><span>{{ summary.total_monitors }}</span></UiCard>
      <UiCard compact class="card"><strong>UP</strong><span>{{ summary.up }}</span></UiCard>
      <UiCard compact class="card"><strong>DOWN</strong><span>{{ summary.down }}</span></UiCard>
      <UiCard compact class="card"><strong>PENDING</strong><span>{{ summary.pending }}</span></UiCard>
      <UiCard compact class="card"><strong>AVG ms</strong><span>{{ fmtAvgMs(summary.avg_response_time_ms) }}</span></UiCard>
      <UiCard compact class="card">
        <strong>Avg uptime</strong>
        <span>{{ summary.average_uptime_percent != null ? summary.average_uptime_percent.toFixed(2) + "%" : "n/a" }}</span>
        <small v-if="summary.uptime_window_from && summary.uptime_window_to" class="muted">
          (checks {{ summary.uptime_success_checks ?? 0 }}/{{ summary.uptime_total_checks ?? 0 }},
          {{ fmtIso(summary.uptime_window_from) }} → {{ fmtIso(summary.uptime_window_to) }})
        </small>
      </UiCard>
    </section>

    <UiCard>
      <UiPanelHeader title="Queue Runtime Profile (60m)" />
      <div v-if="queueProfile" class="cards expiry-cards">
        <UiCard compact class="card"><strong>Active Monitors</strong><span>{{ queueProfile.active_monitors }}</span></UiCard>
        <UiCard compact class="card"><strong>Expected Checks</strong><span>{{ queueProfile.expected_checks_in_window }}</span></UiCard>
        <UiCard compact class="card"><strong>Observed Checks</strong><span>{{ queueProfile.checks_observed }}</span></UiCard>
        <UiCard compact class="card"><strong>Timeout Ratio</strong><span>{{ fmtPercent(queueProfile.timeout_ratio) }}</span></UiCard>
        <UiCard compact class="card"><strong>Retry Ratio</strong><span>{{ fmtPercent(queueProfile.retry_ratio) }}</span></UiCard>
      </div>
      <div v-if="queueProfile?.recommendations?.length" class="muted">
        Recommendations: {{ queueProfile.recommendations.join(", ") }}
      </div>
      <div v-else-if="queueProfile" class="muted">No immediate queue risk flags in this window.</div>
    </UiCard>

    <UiCard>
      <UiPanelHeader title="SSL Expiry Summary" />
      <div v-if="!expirySummary" class="muted">No expiry data yet.</div>
      <div v-else class="cards expiry-cards">
        <UiCard compact class="card"><strong>Total</strong><span>{{ expirySummary.total_with_ssl_data }}</span></UiCard>
        <UiCard compact class="card"><strong>OK</strong><span>{{ expirySummary.ok }}</span></UiCard>
        <UiCard compact class="card"><strong>30d</strong><span>{{ expirySummary.warn_30d }}</span></UiCard>
        <UiCard compact class="card"><strong>14d</strong><span>{{ expirySummary.warn_14d }}</span></UiCard>
        <UiCard compact class="card"><strong>7d</strong><span>{{ expirySummary.warn_7d }}</span></UiCard>
        <UiCard compact class="card"><strong>1d</strong><span>{{ expirySummary.warn_1d }}</span></UiCard>
        <UiCard compact class="card"><strong>Expired</strong><span>{{ expirySummary.expired }}</span></UiCard>
        <UiCard compact class="card"><strong>Unknown</strong><span>{{ expirySummary.unknown }}</span></UiCard>
      </div>
    </UiCard>

    <UiCard>
      <UiPanelHeader title="Region Summary" subtitle="Global view by probe region" />
      <table v-if="regionSummary.length > 0" class="region-table">
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
          <tr v-for="r in regionSummary" :key="r.probe_region">
            <td><code>{{ r.probe_region }}</code></td>
            <td>{{ r.total_checks }}</td>
            <td>{{ r.up_checks }}</td>
            <td>{{ r.slow_checks }}</td>
            <td>{{ r.down_error_checks }}</td>
            <td>{{ fmtAvgMs(r.avg_response_time_ms) }}</td>
            <td>{{ r.last_finished_at ? fmtIso(r.last_finished_at) : "n/a" }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">No regional checks in current window.</div>
    </UiCard>

    <UiCard>
      <UiPanelHeader title="Recent Monitors" />
      <ul>
        <li v-for="m in recentMonitors" :key="m.id">
          <RouterLink :to="`/monitors/${m.id}`">{{ m.name }}</RouterLink>
          <UiBadge :tone="statusTone(m.current_status)">● {{ m.current_status }}</UiBadge>
          <small class="muted">· {{ riskText(m.consecutive_failures) }}</small>
        </li>
      </ul>
    </UiCard>

    <UiCard>
      <UiPanelHeader title="Recent Failures" />
      <ul>
        <li v-for="m in recentFailures" :key="m.id">
          <RouterLink :to="`/monitors/${m.id}`">{{ m.name }}</RouterLink>
          <UiBadge :tone="statusTone(m.current_status)">● {{ m.current_status }}</UiBadge>
          <small class="muted">
            · {{ riskText(m.consecutive_failures) }}
            <span v-if="m.last_failure_at"> since {{ fmtIso(m.last_failure_at) }}</span>
          </small>
        </li>
        <li v-if="recentFailures.length === 0" class="muted empty-row">
          No active failures in this window.
        </li>
      </ul>
    </UiCard>

    <p class="muted">Auto-refresh 15s. Last updated: {{ fmtTime(lastUpdatedAt) }}</p>
    <UiButton @click="load" :disabled="loading">Refresh now</UiButton>
    </div>
  </AppLayout>
</template>

<style scoped>
.page { width: 100%; font-family: var(--sans), system-ui, sans-serif; }
.page h1 { color: var(--color-text-strong); }
.panel { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; }
.panel h2 { margin: 0 0 0.5rem; font-size: 1rem; }
.uptime-panel .small { margin: 0 0 0.5rem; font-size: 0.85rem; }
.uptime-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: flex-end;
}
.uptime-row label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8rem; }
.uptime-row input[type="datetime-local"] { font: inherit; padding: 0.25rem 0.35rem; }
.btn-primary { font-weight: 600; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.expiry-cards { margin-bottom: 0; }
.region-table { width: 100%; border-collapse: collapse; }
.region-table th, .region-table td { text-align: left; padding: 0.38rem; border-bottom: 1px solid var(--border); }
.panel li a { margin-right: 0.5rem; color: var(--color-primary); font-weight: 500; text-decoration: none; }
.panel li a:hover { text-decoration: underline; }
.card { border: 1px solid var(--border); padding: 0.75rem; border-radius: 8px; display: flex; flex-direction: column; gap: 0.4rem; }
.card small { font-size: 0.7rem; line-height: 1.2; }
.panel ul { padding-left: 1rem; margin: 0; }
.panel li { margin-bottom: 0.35rem; }
.empty-row { list-style: none; margin-left: -1rem; }
.err { color: #b91c1c; }
.muted { color: #64748b; }
</style>
