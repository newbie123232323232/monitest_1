import { errMsg, readJsonError } from "./error"

const base = import.meta.env.VITE_API_BASE_URL ?? ""
const jsonHeaders = { "Content-Type": "application/json" }

export async function register(email: string, password: string): Promise<{ message: string }> {
  const res = await fetch(`${base}/api/v1/auth/register`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ email, password }),
  })
  const data = await readJsonError(res)
  if (!res.ok) {
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
  return data as { message: string }
}

export async function login(email: string, password: string) {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ email, password }),
  })
  const data = await readJsonError(res)
  if (!res.ok) {
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
  return data as { access_token: string; refresh_token: string; token_type: string }
}

export async function verifyEmailToken(token: string): Promise<{ message: string }> {
  const res = await fetch(`${base}/api/v1/auth/verify-email`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ token }),
  })
  const data = await readJsonError(res)
  if (!res.ok) {
    throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
  }
  return data as { message: string }
}

export async function logout(): Promise<void> {
  const refreshToken = localStorage.getItem("refresh_token")
  if (!refreshToken) {
    clearTokens()
    return
  }

  try {
    const res = await fetch(`${base}/api/v1/auth/logout`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) {
      const data = await readJsonError(res)
      throw new Error(errMsg(data, `${res.status} ${res.statusText}`))
    }
  } finally {
    clearTokens()
  }
}

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem("refresh_token")
  if (!refreshToken) {
    throw new Error("Missing refresh token. Please login again.")
  }

  const res = await fetch(`${base}/api/v1/auth/refresh`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  const data = await readJsonError(res)
  if (!res.ok) {
    clearTokens()
    throw new Error(errMsg(data, "Session expired. Please login again."))
  }
  const tokenData = data as { access_token: string; refresh_token: string }
  saveTokens(tokenData.access_token, tokenData.refresh_token)
  return tokenData.access_token
}

export async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  const token = getAccessToken()
  if (!token) {
    throw new Error("Missing access token. Please login again.")
  }

  const first = await fetch(input, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  })
  if (first.status !== 401) {
    return first
  }

  const newAccess = await refreshAccessToken()
  return fetch(input, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${newAccess}`,
    },
  })
}

export function saveTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access)
  localStorage.setItem("refresh_token", refresh)
}

export function clearTokens() {
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

export function getAccessToken(): string | null {
  return localStorage.getItem("access_token")
}
