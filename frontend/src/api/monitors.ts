import { authFetch } from "./auth"
import { parseJsonOrThrow } from "./error"

const base = import.meta.env.VITE_API_BASE_URL ?? ""

type MonitorStatus = "pending" | "checking" | "up" | "down" | "slow" | "paused"

export type MonitorItem = {
  id: string
  name: string
  url: string
  monitor_type: "http" | "tcp" | "icmp"
  current_status: MonitorStatus
  interval_seconds: number
  timeout_seconds: number
  probe_region: string
  is_paused: boolean
  last_checked_at: string | null
  last_response_time_ms: number | null
  last_failure_at: string | null
  consecutive_failures: number
  created_at: string
}

export type MonitorDetail = MonitorItem & {
  user_id: string
  max_retries: number
  slow_threshold_ms: number
  detect_content_change: boolean
  last_status_code: number | null
  last_error_message: string | null
  last_success_at: string | null
  updated_at: string
  deleted_at: string | null
}

export type ChecksItem = {
  id: string
  status: string
  started_at: string
  finished_at: string
  response_time_ms: number | null
  status_code: number | null
  error_type: string | null
  error_message: string | null
  dns_resolve_ms: number | null
  tcp_connect_ms: number | null
  tls_handshake_ms: number | null
  ttfb_ms: number | null
  retry_count: number
}

export type IncidentItem = {
  id: string
  monitor_id: string
  opened_at: string
  closed_at: string | null
  status: "open" | "closed"
  open_reason: string | null
  close_reason: string | null
}

export type MonitorUptime = {
  window_from: string
  window_to: string
  total_checks: number
  success_checks: number
  uptime_percent: number | null
}

export type AlertItem = {
  id: string
  incident_id: string | null
  monitor_id: string
  channel: "email"
  event_type: "incident_opened" | "incident_recovered" | "still_down"
  sent_to: string | null
  sent_at: string | null
  send_status: "sent" | "failed"
  error_message: string | null
  created_at: string
}

export async function createMonitor(input: {
  name: string
  url: string
  monitor_type: "http"
  interval_seconds: number
  timeout_seconds: number
  max_retries: number
  slow_threshold_ms: number
  probe_region: string
  detect_content_change: boolean
}): Promise<MonitorDetail> {
  const res = await authFetch(`${base}/api/v1/monitors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
  return parseJsonOrThrow<MonitorDetail>(res)
}

export async function listMonitors(params?: {
  status?: string
  q?: string
  page?: number
  page_size?: number
}): Promise<{
  items: MonitorItem[]
  total: number
  page: number
  page_size: number
}> {
  const sp = new URLSearchParams()
  if (params?.status) sp.set("status", params.status)
  if (params?.q) sp.set("q", params.q)
  if (params?.page != null) sp.set("page", String(params.page))
  if (params?.page_size != null) sp.set("page_size", String(params.page_size))
  const query = sp.toString()
  const res = await authFetch(`${base}/api/v1/monitors${query ? `?${query}` : ""}`)
  return parseJsonOrThrow(res)
}

export async function getMonitorDetail(monitorId: string): Promise<MonitorDetail> {
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}`)
  return parseJsonOrThrow(res)
}

export async function updateMonitor(
  monitorId: string,
  input: Partial<{
    name: string
    url: string
    interval_seconds: number
    timeout_seconds: number
    max_retries: number
    slow_threshold_ms: number
    probe_region: string
    detect_content_change: boolean
    is_paused: boolean
  }>,
): Promise<MonitorDetail> {
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
  return parseJsonOrThrow(res)
}

export async function runCheckNow(monitorId: string): Promise<{ monitor_id: string; task_id: string; status: string }> {
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}/run-check`, { method: "POST" })
  return parseJsonOrThrow(res)
}

export async function getMonitorChecks(
  monitorId: string,
  opts?: { limit?: number; from?: string; to?: string },
): Promise<ChecksItem[]> {
  const sp = new URLSearchParams()
  sp.set("limit", String(opts?.limit ?? 50))
  if (opts?.from) sp.set("from", opts.from)
  if (opts?.to) sp.set("to", opts.to)
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}/checks?${sp.toString()}`)
  return parseJsonOrThrow(res)
}

export async function getMonitorUptime(
  monitorId: string,
  opts?: { from?: string; to?: string },
): Promise<MonitorUptime> {
  const sp = new URLSearchParams()
  if (opts?.from) sp.set("from", opts.from)
  if (opts?.to) sp.set("to", opts.to)
  const q = sp.toString()
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}/uptime${q ? `?${q}` : ""}`)
  return parseJsonOrThrow(res)
}

export async function getMonitorIncidents(monitorId: string, limit = 20): Promise<IncidentItem[]> {
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}/incidents?limit=${limit}`)
  return parseJsonOrThrow(res)
}

export async function getMonitorAlerts(monitorId: string, limit = 20): Promise<AlertItem[]> {
  const res = await authFetch(`${base}/api/v1/monitors/${monitorId}/alerts?limit=${limit}`)
  return parseJsonOrThrow(res)
}
