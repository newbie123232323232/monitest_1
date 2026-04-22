import { authFetch } from "./auth"
import { parseJsonOrThrow } from "./error"
import type { MonitorItem } from "./monitors"

const base = import.meta.env.VITE_API_BASE_URL ?? ""

export type DashboardSummary = {
  total_monitors: number
  up: number
  down: number
  pending: number
  checking: number
  slow: number
  paused: number
  avg_response_time_ms: number | null
  uptime_window_from: string | null
  uptime_window_to: string | null
  uptime_total_checks: number | null
  uptime_success_checks: number | null
  average_uptime_percent: number | null
}

export async function getDashboardSummary(params?: {
  uptime_from?: string
  uptime_to?: string
}): Promise<DashboardSummary> {
  const sp = new URLSearchParams()
  if (params?.uptime_from) sp.set("uptime_from", params.uptime_from)
  if (params?.uptime_to) sp.set("uptime_to", params.uptime_to)
  const q = sp.toString()
  const res = await authFetch(`${base}/api/v1/dashboard/summary${q ? `?${q}` : ""}`)
  return parseJsonOrThrow(res)
}

export async function getRecentMonitors(limit = 10): Promise<MonitorItem[]> {
  const res = await authFetch(`${base}/api/v1/dashboard/recent-monitors?limit=${limit}`)
  return parseJsonOrThrow(res)
}

export async function getRecentFailures(limit = 10): Promise<MonitorItem[]> {
  const res = await authFetch(`${base}/api/v1/dashboard/recent-failures?limit=${limit}`)
  return parseJsonOrThrow(res)
}
