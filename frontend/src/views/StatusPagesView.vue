<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import AppLayout from "../components/AppLayout.vue"
import UiBadge from "../components/ui/UiBadge.vue"
import UiButton from "../components/ui/UiButton.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import UiTable from "../components/ui/UiTable.vue"
import { listMonitors, type MonitorItem } from "../api/monitors"
import {
  createStatusPage,
  deleteStatusPage,
  listStatusPages,
  updateStatusPage,
  type StatusPage,
} from "../api/statusPages"

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const actionMsg = ref<string | null>(null)
const pages = ref<StatusPage[]>([])
const monitors = ref<MonitorItem[]>([])
const selectedMonitorIds = ref<string[]>([])
const monitorStatusFilter = ref<"" | "up" | "down" | "slow" | "pending" | "checking" | "paused">("")
const monitorSearch = ref("")
const form = ref({
  name: "",
  slug: "",
  is_public: true,
  maintenance_notes: "",
})
const editingId = ref<string | null>(null)
const editForm = ref({
  name: "",
  slug: "",
  is_public: true,
  maintenance_notes: "",
  monitor_ids: [] as string[],
})

const filteredMonitors = computed(() => {
  const search = monitorSearch.value.trim().toLowerCase()
  return monitors.value
    .filter((m) => {
      if (monitorStatusFilter.value && m.current_status !== monitorStatusFilter.value) return false
      if (!search) return true
      return m.name.toLowerCase().includes(search) || m.url.toLowerCase().includes(search)
    })
    .slice()
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
})

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const s = status.toLowerCase()
  if (s === "up") return "success"
  if (s === "slow" || s === "checking" || s === "pending") return "warning"
  if (s === "down") return "danger"
  return "neutral"
}

function publicPath(slug: string): string {
  return `/status/${encodeURIComponent(slug)}`
}

function toggleCreateMonitor(monitorId: string, checked: boolean) {
  if (checked) {
    if (!selectedMonitorIds.value.includes(monitorId)) selectedMonitorIds.value.push(monitorId)
    return
  }
  selectedMonitorIds.value = selectedMonitorIds.value.filter((id) => id !== monitorId)
}

function toggleEditMonitor(monitorId: string, checked: boolean) {
  if (checked) {
    if (!editForm.value.monitor_ids.includes(monitorId)) editForm.value.monitor_ids.push(monitorId)
    return
  }
  editForm.value.monitor_ids = editForm.value.monitor_ids.filter((id) => id !== monitorId)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [pageData, monitorData] = await Promise.all([
      listStatusPages(),
      listMonitors({ page: 1, page_size: 100 }),
    ])
    pages.value = pageData
    monitors.value = monitorData.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load status pages"
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  saving.value = true
  actionMsg.value = null
  error.value = null
  try {
    const page = await createStatusPage({
      name: form.value.name.trim(),
      slug: slugify(form.value.slug || form.value.name),
      is_public: form.value.is_public,
      maintenance_notes: form.value.maintenance_notes.trim() || null,
      monitor_ids: selectedMonitorIds.value,
    })
    actionMsg.value = `Created status page ${page.slug}`
    form.value.name = ""
    form.value.slug = ""
    form.value.is_public = true
    form.value.maintenance_notes = ""
    selectedMonitorIds.value = []
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Create failed"
  } finally {
    saving.value = false
  }
}

function startEdit(page: StatusPage) {
  editingId.value = page.id
  editForm.value = {
    name: page.name,
    slug: page.slug,
    is_public: page.is_public,
    maintenance_notes: page.maintenance_notes ?? "",
    monitor_ids: page.monitors.map((m) => m.id),
  }
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(pageId: string) {
  saving.value = true
  actionMsg.value = null
  error.value = null
  try {
    const updated = await updateStatusPage(pageId, {
      name: editForm.value.name.trim(),
      slug: slugify(editForm.value.slug || editForm.value.name),
      is_public: editForm.value.is_public,
      maintenance_notes: editForm.value.maintenance_notes.trim() || null,
      monitor_ids: editForm.value.monitor_ids,
    })
    actionMsg.value = `Updated ${updated.slug}`
    editingId.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Update failed"
  } finally {
    saving.value = false
  }
}

async function removePage(pageId: string) {
  if (!window.confirm("Delete this status page?")) return
  saving.value = true
  actionMsg.value = null
  error.value = null
  try {
    await deleteStatusPage(pageId)
    actionMsg.value = "Status page deleted"
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Delete failed"
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AppLayout>
    <div class="page">
      <h1>Status Pages</h1>
      <p class="muted">Manage public/private status pages and choose which monitors are exposed.</p>
      <p v-if="loading">Loading...</p>
      <p v-if="error" class="err">{{ error }}</p>
      <p v-if="actionMsg" class="ok">{{ actionMsg }}</p>

      <UiCard>
        <UiPanelHeader title="Create status page" />
        <div class="grid">
          <input v-model.trim="form.name" placeholder="Name (e.g. Production Status)" />
          <input v-model.trim="form.slug" placeholder="Slug (e.g. prod-status)" />
          <label class="chk"><input v-model="form.is_public" type="checkbox" /> Public page</label>
        </div>
        <textarea
          v-model.trim="form.maintenance_notes"
          rows="3"
          maxlength="2000"
          placeholder="Maintenance notes (optional): planned windows, degraded services, contact info"
        />
        <div class="monitor-filters">
          <select v-model="monitorStatusFilter">
            <option value="">All statuses</option>
            <option value="up">up</option>
            <option value="slow">slow</option>
            <option value="down">down</option>
            <option value="pending">pending</option>
            <option value="checking">checking</option>
            <option value="paused">paused</option>
          </select>
          <input
            :value="monitorSearch"
            placeholder="Filter by name or URL (real-time)"
            @input="monitorSearch = (($event.target as HTMLInputElement).value ?? '')"
          />
        </div>
        <p class="muted">Monitors are shown newest first.</p>
        <UiTable>
          <table class="monitor-table">
            <thead>
              <tr>
                <th></th>
                <th>Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in filteredMonitors" :key="m.id">
                <td>
                  <input
                    :checked="selectedMonitorIds.includes(m.id)"
                    type="checkbox"
                    @change="toggleCreateMonitor(m.id, ($event.target as HTMLInputElement).checked)"
                  />
                </td>
                <td>{{ m.name }}</td>
                <td><small>{{ m.url }}</small></td>
                <td><UiBadge :tone="statusTone(m.current_status)">{{ m.current_status }}</UiBadge></td>
                <td><small>{{ new Date(m.created_at).toLocaleString() }}</small></td>
              </tr>
              <tr v-if="filteredMonitors.length === 0">
                <td colspan="5" class="muted empty-row">No monitors match current filter.</td>
              </tr>
            </tbody>
          </table>
        </UiTable>
        <UiButton variant="primary" :disabled="saving || !form.name.trim()" @click="handleCreate">Create</UiButton>
      </UiCard>

      <UiCard>
        <UiPanelHeader title="Existing pages" />
        <div v-if="pages.length === 0" class="muted">No status pages yet.</div>
        <div v-for="p in pages" :key="p.id" class="page-card">
          <template v-if="editingId !== p.id">
            <p><strong>{{ p.name }}</strong> · <code>{{ p.slug }}</code></p>
            <p>
              <UiBadge :tone="p.is_public ? 'success' : 'warning'">
                {{ p.is_public ? "public" : "private" }}
              </UiBadge>
              <span class="muted">· {{ p.monitors.length }} monitor(s)</span>
            </p>
            <p class="muted linkline">
              Public URL:
              <a :href="publicPath(p.slug)" target="_blank" rel="noopener noreferrer">
                <code>{{ publicPath(p.slug) }}</code>
              </a>
            </p>
            <p v-if="p.maintenance_notes" class="muted notes">Maintenance notes: {{ p.maintenance_notes }}</p>
            <div class="mini-monitors">
              <span v-for="m in p.monitors" :key="m.id">
                <UiBadge :tone="statusTone(m.current_status)">{{ m.name }} · {{ m.current_status }}</UiBadge>
              </span>
              <span v-if="p.monitors.length === 0" class="muted">No monitors selected.</span>
            </div>
            <div class="actions">
              <UiButton @click="startEdit(p)">Edit</UiButton>
              <UiButton variant="danger" @click="removePage(p.id)" :disabled="saving">Delete</UiButton>
            </div>
          </template>
          <template v-else>
            <div class="grid">
              <input v-model.trim="editForm.name" />
              <input v-model.trim="editForm.slug" />
              <label class="chk"><input v-model="editForm.is_public" type="checkbox" /> Public page</label>
            </div>
            <textarea
              v-model.trim="editForm.maintenance_notes"
              rows="3"
              maxlength="2000"
              placeholder="Maintenance notes (optional)"
            />
            <UiTable>
              <table class="monitor-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>Name</th>
                    <th>URL</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in filteredMonitors" :key="m.id">
                    <td>
                      <input
                        :checked="editForm.monitor_ids.includes(m.id)"
                        type="checkbox"
                        @change="toggleEditMonitor(m.id, ($event.target as HTMLInputElement).checked)"
                      />
                    </td>
                    <td>{{ m.name }}</td>
                    <td><small>{{ m.url }}</small></td>
                    <td><UiBadge :tone="statusTone(m.current_status)">{{ m.current_status }}</UiBadge></td>
                    <td><small>{{ new Date(m.created_at).toLocaleString() }}</small></td>
                  </tr>
                  <tr v-if="filteredMonitors.length === 0">
                    <td colspan="5" class="muted empty-row">No monitors match current filter.</td>
                  </tr>
                </tbody>
              </table>
            </UiTable>
            <div class="actions">
              <UiButton variant="primary" :disabled="saving" @click="saveEdit(p.id)">Save</UiButton>
              <UiButton variant="ghost" :disabled="saving" @click="cancelEdit">Cancel</UiButton>
            </div>
          </template>
        </div>
      </UiCard>
    </div>
  </AppLayout>
</template>

<style scoped>
.page { width: 100%; font-family: var(--sans), system-ui, sans-serif; }
.muted { color: var(--color-text-muted); }
.err { color: var(--color-danger); }
.ok { color: var(--color-success); }
.grid { display: grid; grid-template-columns: 1fr 1fr auto; gap: 0.5rem; margin-bottom: 0.5rem; }
.page textarea {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 0.5rem;
  font: inherit;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 0.45rem 0.55rem;
  background: var(--color-surface);
  color: var(--color-text);
}
.chk { display: inline-flex; align-items: center; gap: 0.35rem; }
.monitor-filters { display: grid; grid-template-columns: 11rem 1fr; gap: 0.5rem; margin: 0.35rem 0 0.5rem; }
.monitor-table { width: 100%; border-collapse: collapse; margin-bottom: 0.7rem; }
.monitor-table th, .monitor-table td { text-align: left; padding: 0.38rem; border-bottom: 1px solid var(--color-border); }
.empty-row { text-align: center; }
.page-card { border: 1px solid var(--color-border); border-radius: 8px; padding: 0.65rem; margin-bottom: 0.6rem; }
.mini-monitors { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.5rem; }
.actions { display: flex; gap: 0.5rem; }
.linkline { margin-top: -0.2rem; }
.notes { margin-top: -0.15rem; margin-bottom: 0.5rem; }
</style>
