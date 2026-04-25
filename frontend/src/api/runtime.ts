import { authFetch } from "./auth"
import { parseJsonOrThrow } from "./error"

const base = import.meta.env.VITE_API_BASE_URL ?? ""
const HEALTH_TTL_MS = 10_000
const QUEUE_PROFILE_TTL_MS = 15_000

export type RuntimeHealth = {
  status: "ok" | "degraded"
  checked_at: string
  redis_ok: boolean
  worker_ok: boolean
  beat_ok: boolean
  beat_last_seen_at: string | null
  beat_heartbeat_age_seconds: number | null
  degraded_reasons: string[]
}

export type RuntimeQueueProfile = {
  checked_at: string
  window_minutes: number
  active_monitors: number
  expected_checks_in_window: number
  checks_observed: number
  timeout_checks: number
  checks_with_retry: number
  timeout_ratio: number
  retry_ratio: number
  avg_response_time_ms: number | null
  avg_interval_seconds: number | null
  avg_timeout_seconds: number | null
  avg_max_retries: number | null
  recommendations: string[]
}

let runtimeHealthCache: { value: RuntimeHealth; fetchedAtMs: number } | null = null
const queueProfileCache = new Map<number, { value: RuntimeQueueProfile; fetchedAtMs: number }>()

export function getCachedRuntimeHealth(maxAgeMs = HEALTH_TTL_MS): RuntimeHealth | null {
  if (!runtimeHealthCache) return null
  if (Date.now() - runtimeHealthCache.fetchedAtMs > maxAgeMs) return null
  return runtimeHealthCache.value
}

export function getCachedRuntimeQueueProfile(windowMinutes = 60, maxAgeMs = QUEUE_PROFILE_TTL_MS): RuntimeQueueProfile | null {
  const cached = queueProfileCache.get(windowMinutes)
  if (!cached) return null
  if (Date.now() - cached.fetchedAtMs > maxAgeMs) return null
  return cached.value
}

export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  const cached = getCachedRuntimeHealth()
  if (cached) return cached
  const res = await authFetch(`${base}/api/v1/runtime/health`)
  const parsed = await parseJsonOrThrow<RuntimeHealth>(res)
  runtimeHealthCache = { value: parsed, fetchedAtMs: Date.now() }
  return parsed
}

export async function getRuntimeQueueProfile(windowMinutes = 60): Promise<RuntimeQueueProfile> {
  const cached = getCachedRuntimeQueueProfile(windowMinutes)
  if (cached) return cached
  const res = await authFetch(`${base}/api/v1/runtime/queue-profile?window_minutes=${windowMinutes}`)
  const parsed = await parseJsonOrThrow<RuntimeQueueProfile>(res)
  queueProfileCache.set(windowMinutes, { value: parsed, fetchedAtMs: Date.now() })
  return parsed
}
