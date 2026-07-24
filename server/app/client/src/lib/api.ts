// Empty string means "same origin as the page" — correct once the backend
// serves the built frontend itself. An absolute URL is only needed for
// local dev, when the Vite dev server and the API run on different ports.
const API_URL = import.meta.env.VITE_API_URL ?? ""

export type Me = {
  id: number
  email: string
  name: string
  is_admin: boolean
}

export type ApiKey = {
  id: number
  label: string
  prefix: string
  created_at: string
  last_used_at: string | null
  status: "active" | "revoked"
}

// Returned only when a key is created — carries the plaintext secret once.
export type CreatedKey = {
  id: number
  label: string
  prefix: string
  key: string
}

export type UserSummary = {
  email: string
  account_email: string
  sessions: number
  input_tokens: number
  output_tokens: number
  cache_read: number
  cache_write: number
  cost_usd: number
  last_seen: string
}

export type SessionRow = {
  email: string
  account_email: string
  session_id: string
  cwd: string
  model: string
  started_at: string
  last_turn_at: string
  turns: number
  input_tokens: number
  output_tokens: number
  cache_read: number
  cache_write: number
  cost_usd: number
}

export type DailyPoint = {
  date: string
  tokens: number
  cost_usd: number
}

export type DateRange = {
  from?: string
  to?: string
}

// Thrown when the server rejects a request as unauthenticated, so the UI can
// distinguish "please log in" from a genuine error.
export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized")
    this.name = "UnauthorizedError"
  }
}

/** Fired whenever any request returns 401 (e.g. the session token expired), so
 *  the app shell can send the user back to the login screen. */
export const AUTH_EXPIRED_EVENT = "auth:unauthorized"

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value)
  }
  const query = search.toString()
  return query ? `?${query}` : ""
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // `credentials: "include"` sends the session cookie so the server can
  // identify the logged-in user across requests. The ngrok header skips the
  // free-tier browser interstitial so fetch() gets JSON, not an HTML warning.
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: { "ngrok-skip-browser-warning": "true", ...(init?.headers ?? {}) },
  })
  if (res.status === 401) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    throw new UnauthorizedError()
  }
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`)
  }
  // DELETE and other empty responses may have no JSON body.
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

// --- auth ------------------------------------------------------------------

/** Absolute URL that starts the Entra login flow (a full-page redirect). */
export function loginUrl(): string {
  return `${API_URL}/api/auth/microsoft/login`
}

export function fetchMe(): Promise<Me> {
  return request<Me>("/api/me")
}

export function logout(): Promise<void> {
  return request<void>("/api/auth/logout", { method: "POST" })
}

// --- API keys --------------------------------------------------------------

export function fetchKeys(): Promise<ApiKey[]> {
  return request<ApiKey[]>("/api/keys")
}

export function createKey(label: string): Promise<CreatedKey> {
  return request<CreatedKey>("/api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  })
}

export function revokeKey(id: number): Promise<void> {
  return request<void>(`/api/keys/${id}`, { method: "DELETE" })
}

// --- usage -----------------------------------------------------------------

export function fetchSummary(
  params: DateRange & { email?: string } = {}
): Promise<UserSummary[]> {
  return request<UserSummary[]>(`/api/summary${buildQuery(params)}`)
}

export function fetchSessions(
  range: DateRange & { email?: string; limit?: number } = {}
): Promise<SessionRow[]> {
  const { limit, ...rest } = range
  return request<SessionRow[]>(
    `/api/sessions${buildQuery({ ...rest, limit: limit?.toString() })}`
  )
}

export function fetchDaily(
  params: DateRange & { email?: string } = {}
): Promise<DailyPoint[]> {
  return request<DailyPoint[]>(`/api/usage/daily${buildQuery(params)}`)
}
