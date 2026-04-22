<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue"
import { RouterLink, useRoute } from "vue-router"
import AppLayout from "../components/AppLayout.vue"
import UiBadge from "../components/ui/UiBadge.vue"
import UiButton from "../components/ui/UiButton.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import UiTable from "../components/ui/UiTable.vue"
import {
  createMonitor,
  getMonitorChecks,
  getMonitorDetail,
  listMonitors,
  runCheckNow,
  updateMonitor,
  type ChecksItem,
  type MonitorItem,
} from "../api/monitors"

const monitors = ref<MonitorItem[]>([])
const route = useRoute()
const listTotal = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedId = ref<string | null>(null)
const checks = ref<ChecksItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const actionMsg = ref<string | null>(null)
const statusFilter = ref("")
const searchText = ref("")
const searchInputRef = ref<HTMLInputElement | null>(null)
let passiveRefreshTimer: number | null = null
type RunCheckPhase = "idle" | "queued" | "checking" | "completed" | "failed" | "timeout"
const runCheckState = ref<Record<string, { phase: RunCheckPhase; message?: string }>>({})
const runCheckPollTimers = new Map<string, number>()
const runCheckTimeoutTimers = new Map<string, number>()
const editingId = ref<string | null>(null)
const editForm = ref({
  name: "",
  url: "",
  interval_seconds: 60,
  timeout_seconds: 10,
  is_paused: false,
})
const selectedMonitorName = computed(() => {
  if (!selectedId.value) return null
  const monitor = monitors.value.find((m) => m.id === selectedId.value)
  return monitor?.name ?? null
})

const totalPages = computed(() => Math.max(1, Math.ceil(listTotal.value / pageSize.value)))

const form = ref({
  name: "",
  url: "https://www.wikipedia.org",
  interval_seconds: 60,
  timeout_seconds: 10,
  max_retries: 2,
  slow_threshold_ms: 1500,
  probe_region: "global",
})

async function loadMonitors() {
  loading.value = true
  error.value = null
  try {
    const data = await listMonitors({
      status: statusFilter.value || undefined,
      q: searchText.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    listTotal.value = data.total
    const maxPage = Math.max(1, Math.ceil(data.total / pageSize.value) || 1)
    if (page.value > maxPage) {
      page.value = maxPage
      const data2 = await listMonitors({
        status: statusFilter.value || undefined,
        q: searchText.value.trim() || undefined,
        page: page.value,
        page_size: pageSize.value,
      })
      listTotal.value = data2.total
      monitors.value = data2.items
    } else {
      monitors.value = data.items
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load monitors"
  } finally {
    loading.value = false
  }
}

function applyListFilters() {
  page.value = 1
  void loadMonitors()
}

function goPrevPage() {
  if (page.value <= 1) return
  page.value -= 1
  void loadMonitors()
}

function goNextPage() {
  if (page.value >= totalPages.value) return
  page.value += 1
  void loadMonitors()
}

function onPageSizeChange() {
  page.value = 1
  void loadMonitors()
}

async function handleCreate() {
  error.value = null
  actionMsg.value = null
  try {
    await createMonitor({
      ...form.value,
      monitor_type: "http",
      detect_content_change: false,
    })
    actionMsg.value = "Monitor created"
    page.value = 1
    await loadMonitors()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Create failed"
  }
}

async function handleRunCheck(monitorId: string) {
  error.value = null
  actionMsg.value = null
  try {
    const before = await getMonitorDetail(monitorId)
    const res = await runCheckNow(monitorId)
    runCheckState.value[monitorId] = { phase: "queued", message: `Task ${res.task_id}` }
    actionMsg.value = `Queued check task ${res.task_id}`
    startRunCheckPolling(monitorId, before.last_checked_at)
    await loadMonitors()
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Run check failed"
    runCheckState.value[monitorId] = { phase: "failed", message: msg }
    error.value = msg
  }
}

function startEdit(monitor: MonitorItem) {
  editingId.value = monitor.id
  editForm.value = {
    name: monitor.name,
    url: monitor.url,
    interval_seconds: monitor.interval_seconds,
    timeout_seconds: monitor.timeout_seconds,
    is_paused: monitor.is_paused,
  }
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(monitorId: string) {
  error.value = null
  actionMsg.value = null
  try {
    await updateMonitor(monitorId, {
      name: editForm.value.name.trim(),
      url: editForm.value.url.trim(),
      interval_seconds: Number(editForm.value.interval_seconds),
      timeout_seconds: Number(editForm.value.timeout_seconds),
      is_paused: editForm.value.is_paused,
    })
    actionMsg.value = "Monitor updated"
    editingId.value = null
    await loadMonitors()
    if (selectedId.value === monitorId) {
      await handleLoadChecks(monitorId)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Update failed"
  }
}

async function handleLoadChecks(monitorId: string) {
  selectedId.value = monitorId
  error.value = null
  try {
    checks.value = await getMonitorChecks(monitorId, { limit: 10 })
    startPassiveRefresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Load checks failed"
  }
}

function stopPassiveRefresh() {
  if (passiveRefreshTimer !== null) {
    window.clearInterval(passiveRefreshTimer)
    passiveRefreshTimer = null
  }
}

function startPassiveRefresh() {
  stopPassiveRefresh()
  if (!selectedId.value) return
  passiveRefreshTimer = window.setInterval(() => {
    if (!selectedId.value) return
    void loadMonitors()
    void handleLoadChecks(selectedId.value)
  }, 15000)
}

function closeChecksPanel() {
  stopPassiveRefresh()
  selectedId.value = null
  checks.value = []
}

function clearRunCheckPolling(monitorId: string) {
  const t = runCheckPollTimers.get(monitorId)
  if (t != null) {
    window.clearInterval(t)
    runCheckPollTimers.delete(monitorId)
  }
  const to = runCheckTimeoutTimers.get(monitorId)
  if (to != null) {
    window.clearTimeout(to)
    runCheckTimeoutTimers.delete(monitorId)
  }
}

function startRunCheckPolling(monitorId: string, baselineLastCheckedAt: string | null) {
  clearRunCheckPolling(monitorId)
  const poll = window.setInterval(async () => {
    try {
      const m = await getMonitorDetail(monitorId)
      const hasNewCheck = (m.last_checked_at ?? null) !== (baselineLastCheckedAt ?? null)
      if (m.current_status === "checking") {
        runCheckState.value[monitorId] = { phase: "checking" }
      } else if (hasNewCheck) {
        runCheckState.value[monitorId] = { phase: "completed", message: `Final status ${m.current_status}` }
        clearRunCheckPolling(monitorId)
      } else {
        runCheckState.value[monitorId] = { phase: "queued" }
      }
      await loadMonitors()
      if (selectedId.value === monitorId) {
        checks.value = await getMonitorChecks(monitorId, { limit: 10 })
      }
    } catch (e) {
      runCheckState.value[monitorId] = {
        phase: "failed",
        message: e instanceof Error ? e.message : "Polling failed",
      }
      clearRunCheckPolling(monitorId)
    }
  }, 2000)
  runCheckPollTimers.set(monitorId, poll)

  const timeout = window.setTimeout(() => {
    runCheckState.value[monitorId] = { phase: "timeout", message: "Polling timeout after 60s" }
    clearRunCheckPolling(monitorId)
  }, 60000)
  runCheckTimeoutTimers.set(monitorId, timeout)
}

function runCheckLabel(monitorId: string): string {
  const s = runCheckState.value[monitorId]
  if (!s) return "Run Check"
  if (s.phase === "queued") return "Queued..."
  if (s.phase === "checking") return "Checking..."
  return "Run Check"
}

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const s = status.toLowerCase()
  if (s === "up") return "success"
  if (s === "slow" || s === "checking" || s === "pending") return "warning"
  if (s === "down") return "danger"
  return "neutral"
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "n/a"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

onMounted(async () => {
  const qParam = route.query.q
  if (typeof qParam === "string" && qParam.trim()) {
    searchText.value = qParam.trim()
  }
  const statusParam = route.query.status
  if (typeof statusParam === "string" && statusParam.trim()) {
    statusFilter.value = statusParam.trim()
  }
  await loadMonitors()
  const focusSearch = route.query.focusSearch
  if (focusSearch === "1") {
    await nextTick()
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  }
})
onUnmounted(() => {
  Array.from(runCheckPollTimers.keys()).forEach(clearRunCheckPolling)
  stopPassiveRefresh()
})
</script>

<template>
  <AppLayout>
  <div class="page">
    <h1>Monitors</h1>

    <UiCard>
      <UiPanelHeader title="Create monitor" />
      <div class="grid">
        <input v-model.trim="form.name" placeholder="Name" />
        <input v-model.trim="form.url" placeholder="https://example.com" />
      </div>
      <UiButton variant="primary" @click="handleCreate" :disabled="!form.name || !form.url">Create</UiButton>
    </UiCard>

    <p v-if="loading">Loading…</p>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="actionMsg" class="ok">{{ actionMsg }}</p>

    <UiCard>
      <UiPanelHeader title="Monitor list" />
      <div class="toolbar">
        <select v-model="statusFilter">
          <option value="">All statuses</option>
          <option value="up">UP</option>
          <option value="down">DOWN</option>
          <option value="slow">SLOW</option>
          <option value="pending">PENDING</option>
          <option value="checking">CHECKING</option>
          <option value="paused">PAUSED</option>
        </select>
        <input ref="searchInputRef" v-model.trim="searchText" placeholder="Search name or URL" />
        <UiButton @click="applyListFilters" :disabled="loading">Apply</UiButton>
      </div>
      <UiTable>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>URL</th>
            <th>Interval/Timeout</th>
            <th>Status</th>
            <th>Last ms</th>
            <th>Risk</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in monitors" :key="m.id">
            <td v-if="editingId !== m.id">{{ m.name }}</td>
            <td v-else><input v-model.trim="editForm.name" /></td>
            <td v-if="editingId !== m.id"><small>{{ m.url }}</small></td>
            <td v-else><input v-model.trim="editForm.url" /></td>
            <td v-if="editingId !== m.id">{{ m.interval_seconds }}s / {{ m.timeout_seconds }}s</td>
            <td v-else class="mini-edit">
              <input v-model.number="editForm.interval_seconds" type="number" min="30" />
              <input v-model.number="editForm.timeout_seconds" type="number" min="1" />
              <label><input v-model="editForm.is_paused" type="checkbox" /> paused</label>
            </td>
            <td><UiBadge :tone="statusTone(m.current_status)">● {{ m.current_status }}</UiBadge></td>
            <td>{{ m.last_response_time_ms ?? "n/a" }}</td>
            <td>
              <span v-if="m.consecutive_failures > 0" class="risk">
                {{ m.consecutive_failures }} fail(s)
                <small> since {{ fmtDateTime(m.last_failure_at ?? "") }}</small>
              </span>
              <span v-else class="ok-risk">stable</span>
            </td>
            <td class="actions">
              <UiButton
                @click="handleRunCheck(m.id)"
                :disabled="runCheckState[m.id]?.phase === 'queued' || runCheckState[m.id]?.phase === 'checking'"
              >
                {{ runCheckLabel(m.id) }}
              </UiButton>
              <small v-if="runCheckState[m.id]" class="run-state">{{ runCheckState[m.id].phase }}</small>
              <UiButton @click="handleLoadChecks(m.id)">Last Checks</UiButton>
              <RouterLink :to="`/monitors/${m.id}`">Detail</RouterLink>
              <UiButton v-if="editingId !== m.id" @click="startEdit(m)">Edit</UiButton>
              <UiButton v-else variant="primary" @click="saveEdit(m.id)">Save</UiButton>
              <UiButton v-if="editingId === m.id" variant="ghost" @click="cancelEdit">Cancel</UiButton>
            </td>
          </tr>
        </tbody>
      </table>
      </UiTable>
      <div v-if="listTotal > 0" class="pager">
        <UiButton @click="goPrevPage" :disabled="loading || page <= 1">Prev</UiButton>
        <span class="pager-meta">
          Page {{ page }} / {{ totalPages }} · {{ listTotal }} monitor(s)
        </span>
        <UiButton @click="goNextPage" :disabled="loading || page >= totalPages">Next</UiButton>
        <label class="pager-size">
          Per page
          <select v-model.number="pageSize" @change="onPageSizeChange">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
        </label>
      </div>
    </UiCard>

    <UiCard v-if="selectedId">
      <UiPanelHeader :title="`Checks (${selectedId})`" />
      <p class="muted" v-if="selectedMonitorName">Monitor: <strong>{{ selectedMonitorName }}</strong></p>
      <p class="muted">Checks list auto-refreshes every 15s while opened.</p>
      <p><UiButton variant="ghost" @click="closeChecksPanel">Close Last Checks</UiButton></p>
      <ul>
        <li v-for="c in checks" :key="c.id">
          <code>{{ c.status }}</code>
          - started={{ fmtDateTime(c.started_at) }}
          - finished={{ fmtDateTime(c.finished_at) }}
          - status={{ c.status_code ?? "n/a" }}
          - total={{ c.response_time_ms ?? "n/a" }}ms
          - dns={{ c.dns_resolve_ms ?? "n/a" }}ms
          - tcp={{ c.tcp_connect_ms ?? "n/a" }}ms
          - tls={{ c.tls_handshake_ms ?? "n/a" }}ms
          - ttfb={{ c.ttfb_ms ?? "n/a" }}ms
          - retry={{ c.retry_count }}
          <span v-if="c.error_type || c.error_message">
            - err={{ c.error_type ?? "unknown" }} {{ c.error_message ?? "" }}
          </span>
        </li>
      </ul>
    </UiCard>
  </div>
  </AppLayout>
</template>

<style scoped>
.page { width: 100%; font-family: var(--sans), system-ui, sans-serif; }
.page h1 { color: var(--color-text-strong); }
.panel { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; }
.grid { display: grid; grid-template-columns: 1fr 2fr; gap: 0.5rem; margin-bottom: 0.5rem; }
.toolbar { display: grid; grid-template-columns: 11rem 1fr auto; gap: 0.5rem; margin-bottom: 0.75rem; }
.pager { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }
.pager-meta { font-size: 0.9rem; color: var(--color-text); }
.pager-size { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; }
.pager-size select { font: inherit; padding: 0.2rem 0.35rem; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 0.4rem; border-bottom: 1px solid var(--border); }
.actions { display: flex; gap: 0.5rem; }
.run-state { text-transform: capitalize; color: #64748b; }
.risk { color: var(--color-danger); font-weight: 600; }
.risk small { margin-left: 0.25rem; font-weight: 400; color: var(--color-text-muted); }
.ok-risk { color: var(--color-success); }
.mini-edit { display: flex; gap: 0.35rem; align-items: center; }
.mini-edit input[type="number"] { width: 4.25rem; }
.err { color: #b91c1c; }
.ok { color: #15803d; }
.muted { color: #64748b; }
</style>
