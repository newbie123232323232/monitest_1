import { authFetch } from "./auth"
import { parseJsonOrThrow } from "./error"

const base = import.meta.env.VITE_API_BASE_URL ?? ""

export type ProbeRegionItem = {
  code: string
  name: string
}

export async function listProbeRegions(): Promise<ProbeRegionItem[]> {
  const res = await authFetch(`${base}/api/v1/probe-regions`)
  return parseJsonOrThrow(res)
}
