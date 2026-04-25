<script setup lang="ts">
import { computed, onMounted, watch, ref } from "vue"
import { useRoute } from "vue-router"
import UiBadge from "../components/ui/UiBadge.vue"
import UiCard from "../components/ui/UiCard.vue"
import UiPanelHeader from "../components/ui/UiPanelHeader.vue"
import { getPublicStatusPage, type PublicStatusPage } from "../api/statusPages"

const route = useRoute()
const slug = computed(() => String(route.params.slug || ""))
const loading = ref(false)
const error = ref<string | null>(null)
const page = ref<PublicStatusPage | null>(null)

function statusTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const s = status.toLowerCase()
  if (s === "up") return "success"
  if (s === "slow" || s === "checking" || s === "pending") return "warning"
  if (s === "down") return "danger"
  return "neutral"
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/a"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function load() {
  if (!slug.value) return
  loading.value = true
  error.value = null
  try {
    page.value = await getPublicStatusPage(slug.value)
  } catch (e) {
    page.value = null
    error.value = e instanceof Error ? e.message : "Failed to load status page"
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.slug,
  () => void load(),
  { immediate: true },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="public-page">
    <h1>{{ page?.name ?? "Status Page" }}</h1>
    <p class="muted">Slug: <code>{{ slug }}</code></p>
    <p v-if="loading">Loading...</p>
    <p v-if="error" class="err">{{ error }}</p>
    <UiCard v-if="page?.maintenance_notes">
      <UiPanelHeader title="Maintenance notes" />
      <p class="notes">{{ page.maintenance_notes }}</p>
    </UiCard>

    <UiCard v-if="page">
      <UiPanelHeader title="Current monitor status" />
      <div v-if="page.monitors.length === 0" class="muted">No monitors configured.</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>Monitor</th>
            <th>URL</th>
            <th>Status</th>
            <th>Last checked</th>
            <th>Last ms</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in page.monitors" :key="m.id">
            <td>{{ m.name }}</td>
            <td><small>{{ m.url }}</small></td>
            <td><UiBadge :tone="statusTone(m.current_status)">{{ m.current_status }}</UiBadge></td>
            <td>{{ fmtDateTime(m.last_checked_at) }}</td>
            <td>{{ m.last_response_time_ms ?? "n/a" }}</td>
          </tr>
        </tbody>
      </table>
    </UiCard>

    <UiCard v-if="page">
      <UiPanelHeader title="Incident timeline" />
      <div v-if="page.incidents.length === 0" class="muted">No incidents recorded.</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>Opened</th>
            <th>Status</th>
            <th>Monitor</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in page.incidents" :key="i.id">
            <td>{{ fmtDateTime(i.opened_at) }}</td>
            <td><UiBadge :tone="i.status === 'open' ? 'danger' : 'success'">{{ i.status }}</UiBadge></td>
            <td><small>{{ i.monitor_id }}</small></td>
            <td>{{ i.open_reason ?? i.close_reason ?? "n/a" }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted">Generated at: {{ fmtDateTime(page.generated_at) }}</p>
    </UiCard>
  </div>
</template>

<style scoped>
.public-page { width: 100%; max-width: 72rem; margin: 0 auto; padding: 1.25rem; box-sizing: border-box; }
.muted { color: var(--color-text-muted); }
.err { color: var(--color-danger); }
.notes { margin: 0; white-space: pre-wrap; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.4rem; border-bottom: 1px solid var(--color-border); vertical-align: top; }
</style>
