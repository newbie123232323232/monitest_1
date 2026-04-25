<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue"
import { RouterLink, useRoute } from "vue-router"
import AppLayout from "../components/AppLayout.vue"
import UiBadge from "../components/ui/UiBadge.vue"
import UiButton from "../components/ui/UiButton.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import UiTable from "../components/ui/UiTable.vue"
import { getRuntimeHealth, type RuntimeHealth } from "../api/runtime"
import { listProbeRegions, type ProbeRegionItem } from "../api/probeRegions"
import {
  createMonitor,
  deleteMonitor,
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
const pageSize = ref(10)
const selectedId = ref<string | null>(null)
const checks = ref<ChecksItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const actionMsg = ref<string | null>(null)
const runtimeHealth = ref<RuntimeHealth | null>(null)
const configuredProbeRegions = ref<ProbeRegionItem[]>([])
const statusFilter = ref("")
const searchText = ref("")
const searchInputRef = ref<HTMLInputElement | null>(null)
let passiveRefreshTimer: number | null = null
let runtimeHealthTimer: number | null = null
type RunCheckPhase = "idle" | "queued" | "checking" | "completed" | "failed" | "timeout"
const runCheckState = ref<Record<string, { phase: RunCheckPhase; message?: string }>>({})
const activeRegionByMonitor = ref<Record<string, string>>({})
const runCheckPollTimers = new Map<string, number>()
const runCheckTimeoutTimers = new Map<string, number>()
const editingId = ref<string | null>(null)
const editForm = ref({
  name: "",
  url: "",
  interval_seconds: 60,
  timeout_seconds: 10,
  accepted_status_codes: "200-399",
  probe_regions: ["global"] as string[],
  active_region: "global",
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
  accepted_status_codes: "200-399",
  probe_regions: ["global"] as string[],
  active_region: "global",
})

function normalizedProbeRegions(input: string[] | null | undefined): string[] {
  const tokens = Array.from(
    new Set((input ?? []).map((v) => v.trim().toLowerCase()).filter(Boolean)),
  )
  return tokens.length > 0 ? tokens : ["global"]
}

function normalizeActiveRegion(activeRegion: string | null | undefined, probeRegions: string[]): string {
  const normalized = (activeRegion ?? "").trim().toLowerCase()
  return normalized && probeRegions.includes(normalized) ? normalized : probeRegions[0]
}

function toggleRegionSelection(current: string[], region: string, checked: boolean): string[] {
  const next = new Set(normalizedProbeRegions(current))
  if (checked) {
    next.add(region)
  } else {
    next.delete(region)
  }
  const out = Array.from(next)
  return out.length > 0 ? normalizedProbeRegions(out) : ["global"]
}

function onCreateRegionToggle(region: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  form.value.probe_regions = toggleRegionSelection(form.value.probe_regions, region, checked)
  form.value.active_region = normalizeActiveRegion(form.value.active_region, normalizedProbeRegions(form.value.probe_regions))
}

function onEditRegionToggle(region: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  editForm.value.probe_regions = toggleRegionSelection(editForm.value.probe_regions, region, checked)
  editForm.value.active_region = normalizeActiveRegion(
    editForm.value.active_region,
    normalizedProbeRegions(editForm.value.probe_regions),
  )
}

const probeRegionOptions = computed(() => {
  const out = configuredProbeRegions.value.map((r) => r.code)
  if (!out.includes("global")) {
    out.unshift("global")
  }
  if (out.length === 1) {
    const seen = new Set<string>(out)
    for (const monitor of monitors.value) {
      for (const token of monitor.probe_regions ?? []) {
        seen.add(token)
      }
    }
    return Array.from(seen).sort((a, b) => (a === "global" ? -1 : b === "global" ? 1 : a.localeCompare(b)))
  }
  return out
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
    activeRegionByMonitor.value = Object.fromEntries(
      monitors.value.map((m) => [m.id, m.active_region || (m.probe_regions[0] ?? "global")]),
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load monitors"
  } finally {
    loading.value = false
  }
}

async function handleActiveRegionChange(monitor: MonitorItem) {
  const nextRegion = activeRegionByMonitor.value[monitor.id]
  if (!nextRegion || !monitor.probe_regions.includes(nextRegion)) {
    error.value = "Active region must be one of configured monitor regions."
    activeRegionByMonitor.value[monitor.id] = monitor.active_region || (monitor.probe_regions[0] ?? "global")
    return
  }
  error.value = null
  actionMsg.value = null
  try {
    await updateMonitor(monitor.id, { active_region: nextRegion })
    actionMsg.value = `Active region for ${monitor.name} updated to ${nextRegion}`
    await loadMonitors()
    if (selectedId.value === monitor.id) {
      await handleLoadChecks(monitor.id)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Update active region failed"
    activeRegionByMonitor.value[monitor.id] = monitor.active_region || (monitor.probe_regions[0] ?? "global")
  }
}

async function loadRuntimeHealth() {
  try {
    runtimeHealth.value = await getRuntimeHealth()
  } catch {
    runtimeHealth.value = null
  }
}

async function loadProbeRegions() {
  try {
    configuredProbeRegions.value = await listProbeRegions()
  } catch {
    configuredProbeRegions.value = []
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
      probe_regions: normalizedProbeRegions(form.value.probe_regions),
      active_region: normalizeActiveRegion(form.value.active_region, normalizedProbeRegions(form.value.probe_regions)),
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
    accepted_status_codes: monitor.accepted_status_codes,
    probe_regions: normalizedProbeRegions(monitor.probe_regions),
    active_region: normalizeActiveRegion(monitor.active_region, normalizedProbeRegions(monitor.probe_regions)),
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
      accepted_status_codes: editForm.value.accepted_status_codes.trim(),
      probe_regions: normalizedProbeRegions(editForm.value.probe_regions),
      active_region: normalizeActiveRegion(
        editForm.value.active_region,
        normalizedProbeRegions(editForm.value.probe_regions),
      ),
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

async function handleDeleteMonitor(monitor: MonitorItem) {
  if (!window.confirm(`Delete monitor "${monitor.name}"?`)) return
  error.value = null
  actionMsg.value = null
  try {
    await deleteMonitor(monitor.id)
    clearRunCheckPolling(monitor.id)
    delete runCheckState.value[monitor.id]
    if (selectedId.value === monitor.id) {
      closeChecksPanel()
    }
    if (editingId.value === monitor.id) {
      editingId.value = null
    }
    actionMsg.value = "Monitor deleted"
    await loadMonitors()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Delete failed"
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
  await loadRuntimeHealth()
  await loadProbeRegions()
  runtimeHealthTimer = window.setInterval(() => {
    void loadRuntimeHealth()
  }, 30000)
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
  if (runtimeHealthTimer !== null) {
    window.clearInterval(runtimeHealthTimer)
    runtimeHealthTimer = null
  }
})
</script>

<template>
  <AppLayout>
  <div class="page">
    <h1>Monitors</h1>
    <UiCard v-if="runtimeHealth && runtimeHealth.status !== 'ok'">
      <UiPanelHeader title="Runtime Degraded" subtitle="Redis/Celery khong on dinh, run-check co the bi tre" />
      <p class="err">{{ runtimeHealth.degraded_reasons.join(", ") }}</p>
    </UiCard>

    <UiCard>
      <UiPanelHeader title="Create monitor" />
      <div class="grid">
        <input v-model.trim="form.name" placeholder="Name" />
        <input v-model.trim="form.url" placeholder="https://example.com" />
        <input v-model.trim="form.accepted_status_codes" placeholder="Accepted codes (e.g. 200-399,401)" />
        <details class="region-picker">
          <summary>Regions (tick to select)</summary>
          <div class="region-options">
            <label v-for="region in probeRegionOptions" :key="`create-region-${region}`" class="region-option">
              <input
                type="checkbox"
                :checked="normalizedProbeRegions(form.probe_regions).includes(region)"
                @change="onCreateRegionToggle(region, $event)"
              />
              {{ region }}
            </label>
          </div>
        </details>
        <select v-model="form.active_region">
          <option
            v-for="region in normalizedProbeRegions(form.probe_regions)"
            :key="`create-${region}`"
            :value="region"
          >
            active: {{ region }}
          </option>
        </select>
      </div>
      <table class="selected-region-table">
        <thead>
          <tr>
            <th>Selected regions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="region in normalizedProbeRegions(form.probe_regions)" :key="`create-selected-${region}`">
            <td>{{ region }}</td>
          </tr>
        </tbody>
      </table>
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
            <th>Interval/Timeout/Codes</th>
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
            <td v-if="editingId !== m.id">
              {{ m.interval_seconds }}s / {{ m.timeout_seconds }}s
              <small class="codes">{{ m.accepted_status_codes }}</small>
              <small class="codes">regions: {{ (m.probe_regions && m.probe_regions.length ? m.probe_regions.join(", ") : "global") }}</small>
              <small class="codes">active: {{ m.active_region || "global" }}</small>
            </td>
            <td v-else class="mini-edit">
              <input v-model.number="editForm.interval_seconds" type="number" min="30" />
              <input v-model.number="editForm.timeout_seconds" type="number" min="1" />
              <input v-model.trim="editForm.accepted_status_codes" placeholder="200-399" />
              <details class="region-picker">
                <summary>Regions (tick to select)</summary>
                <div class="region-options">
                  <label v-for="region in probeRegionOptions" :key="`edit-region-${region}`" class="region-option">
                    <input
                      type="checkbox"
                      :checked="normalizedProbeRegions(editForm.probe_regions).includes(region)"
                      @change="onEditRegionToggle(region, $event)"
                    />
                    {{ region }}
                  </label>
                </div>
              </details>
              <select v-model="editForm.active_region">
                <option
                  v-for="region in normalizedProbeRegions(editForm.probe_regions)"
                  :key="`edit-${region}`"
                  :value="region"
                >
                  active: {{ region }}
                </option>
              </select>
              <table class="selected-region-table selected-region-table--compact">
                <thead>
                  <tr>
                    <th>Selected regions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="region in normalizedProbeRegions(editForm.probe_regions)" :key="`edit-selected-${region}`">
                    <td>{{ region }}</td>
                  </tr>
                </tbody>
              </table>
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
              <select
                v-model="activeRegionByMonitor[m.id]"
                @change="handleActiveRegionChange(m)"
                :disabled="editingId === m.id"
                class="active-region-select"
              >
                <option v-for="region in m.probe_regions" :key="`row-${m.id}-${region}`" :value="region">
                  active: {{ region }}
                </option>
              </select>
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
              <UiButton variant="danger" @click="handleDeleteMonitor(m)">Delete</UiButton>
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
            <option :value="5">5</option>
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
          - region={{ c.probe_region || "global" }}
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
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { text-align: left; padding: 0.4rem; border-bottom: 1px solid var(--border); }
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  max-width: 20rem;
}
.actions :deep(button),
.actions a {
  font-size: 0.78rem;
  line-height: 1.1;
}
.actions a {
  color: var(--color-primary);
  text-decoration: none;
}
.actions a:hover { text-decoration: underline; }
.run-state { text-transform: capitalize; color: #64748b; }
.risk { color: var(--color-danger); font-weight: 600; }
.risk small { margin-left: 0.25rem; font-weight: 400; color: var(--color-text-muted); }
.ok-risk { color: var(--color-success); }
.mini-edit {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
.mini-edit input[type="number"] { width: 4.25rem; }
.region-picker { min-width: 12rem; position: relative; z-index: 2; }
.region-picker summary { cursor: pointer; color: var(--color-text); font-size: 0.85rem; }
.region-options {
  margin-top: 0.35rem;
  display: grid;
  gap: 0.2rem;
  max-height: 9rem;
  overflow: auto;
}
.region-picker[open] .region-options {
  position: absolute;
  left: 0;
  top: 100%;
  min-width: 12rem;
  background: #0b1730;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.35rem;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.35);
}
.region-option { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.85rem; color: var(--color-text); }
.selected-region-table { width: 100%; margin-bottom: 0.5rem; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.selected-region-table th,
.selected-region-table td { padding: 0.3rem 0.45rem; font-size: 0.85rem; border-bottom: 1px solid var(--border); }
.selected-region-table tbody tr:last-child td { border-bottom: none; }
.selected-region-table--compact { min-width: 12rem; max-width: 16rem; margin-bottom: 0; }
.codes { display: block; color: var(--color-text-muted); }
.active-region-select {
  min-width: 7.2rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: #0f172a;
  padding: 0.22rem 0.35rem;
}
td:nth-child(1),
td:nth-child(2),
td:nth-child(3) {
  overflow-wrap: anywhere;
  word-break: break-word;
}
td:nth-child(1) { width: 18%; }
td:nth-child(2) { width: 24%; }
td:nth-child(3) { width: 23%; }
td:nth-child(4) { width: 10%; }
td:nth-child(5) { width: 8%; }
td:nth-child(6) { width: 8%; }
td:nth-child(7) { width: 27%; }
.err { color: #b91c1c; }
.ok { color: #15803d; }
.muted { color: #64748b; }
</style>
