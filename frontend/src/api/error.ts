export async function readJsonError(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return {}
  try {
    return JSON.parse(text) as unknown
  } catch {
    return { message: text.slice(0, 1200) }
  }
}

export function errMsg(data: unknown, fallback: string): string {
  const d = data as {
    code?: string
    message?: string
    detail?:
      | string
      | { message?: string; code?: string }
      | { type?: string; message?: string; traceback?: string }
      | Array<{ msg?: string }>
  }
  if (typeof d.message === "string" && d.message.trim()) {
    const code = typeof d.code === "string" ? `[${d.code}] ` : ""
    return `${code}${d.message}`
  }
  if (!d.detail) return fallback
  if (typeof d.detail === "string") return d.detail
  if (Array.isArray(d.detail)) {
    const first = d.detail[0] as { msg?: string } | undefined
    return typeof first?.msg === "string" ? first.msg : fallback
  }
  const o = d.detail as Record<string, unknown>
  if (typeof o.traceback === "string") {
    const msg = typeof o.message === "string" ? o.message : ""
    const typ = typeof o.type === "string" ? o.type : "Error"
    return `${typ}: ${msg}\n${String(o.traceback).slice(0, 2000)}`
  }
  if (typeof o.message === "string") {
    const code = typeof o.code === "string" ? `[${o.code}] ` : ""
    return code + o.message
  }
  return fallback
}

export async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const data = await readJsonError(res)
  if (!res.ok) {
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
  return data as T
}
