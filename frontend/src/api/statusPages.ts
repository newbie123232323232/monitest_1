import { authFetch } from "./auth"
import { parseJsonOrThrow, readJsonError, errMsg } from "./error"

const base = import.meta.env.VITE_API_BASE_URL ?? ""

export type StatusPageMonitor = {
  id: string
  name: string
  url: string
  current_status: "pending" | "checking" | "up" | "down" | "slow" | "paused"
  last_checked_at: string | null
  last_response_time_ms: number | null
}

export type StatusPageIncident = {
  id: string
  monitor_id: string
  status: string
  opened_at: string
  closed_at: string | null
  open_reason: string | null
  close_reason: string | null
}

export type StatusPage = {
  id: string
  user_id: string
  name: string
  slug: string
  is_public: boolean
  maintenance_notes: string | null
  created_at: string
  updated_at: string
  monitors: StatusPageMonitor[]
}

export type PublicStatusPage = {
  name: string
  slug: string
  maintenance_notes: string | null
  monitors: StatusPageMonitor[]
  incidents: StatusPageIncident[]
  generated_at: string
}

export async function listStatusPages(): Promise<StatusPage[]> {
  const res = await authFetch(`${base}/api/v1/status-pages`)
  return parseJsonOrThrow(res)
}

export async function createStatusPage(input: {
  name: string
  slug: string
  is_public: boolean
  maintenance_notes?: string | null
  monitor_ids: string[]
}): Promise<StatusPage> {
  const res = await authFetch(`${base}/api/v1/status-pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
  return parseJsonOrThrow(res)
}

export async function updateStatusPage(
  pageId: string,
  input: Partial<{
    name: string
    slug: string
    is_public: boolean
    maintenance_notes: string | null
    monitor_ids: string[]
  }>,
): Promise<StatusPage> {
  const res = await authFetch(`${base}/api/v1/status-pages/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
  return parseJsonOrThrow(res)
}

export async function deleteStatusPage(pageId: string): Promise<void> {
  const res = await authFetch(`${base}/api/v1/status-pages/${pageId}`, { method: "DELETE" })
  if (!res.ok) {
    const data = await readJsonError(res)
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
}

export async function getPublicStatusPage(slug: string): Promise<PublicStatusPage> {
  const res = await fetch(`${base}/api/v1/public/status-pages/${encodeURIComponent(slug)}`)
  if (!res.ok) {
    const data = await readJsonError(res)
    if (res.status === 404) {
      throw new Error("Status page not found or you do not have permission to view this page.")
    }
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
  return (await readJsonError(res)) as PublicStatusPage
}
