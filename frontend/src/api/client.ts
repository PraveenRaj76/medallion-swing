import type {
  ForwardTestResponse,
  ProfileResponse,
  ScreenerResponse,
  SectorsResponse,
} from '../types'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      // FastAPI's own HTTPException(detail=...) sends a plain string, but a
      // 422 validation error sends `detail` as an array of {loc, msg, type}
      // objects — passing that straight into Error() silently stringifies
      // to "[object Object]" instead of throwing or showing anything useful.
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(-1)[0] ?? 'field'}: ${e.msg ?? 'invalid'}`)
          .join('; ')
      }
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export interface AuthResult {
  ok: boolean
  message: string
  user_id: number
}

export function login(username: string, password: string) {
  return request<AuthResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function register(username: string, password: string) {
  return request<AuthResult>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function getScreener(params: {
  limit?: number
  min_score?: number
  sector?: string
  ready_only?: boolean
  market?: 'IN' | 'US'
}) {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.min_score) qs.set('min_score', String(params.min_score))
  if (params.sector) qs.set('sector', params.sector)
  if (params.ready_only) qs.set('ready_only', 'true')
  if (params.market) qs.set('market', params.market)
  return request<ScreenerResponse>(`/api/screener?${qs.toString()}`)
}

export function getProfile(ticker: string, live: boolean, userId?: number) {
  const qs = new URLSearchParams()
  if (live) qs.set('live', 'true')
  if (userId) qs.set('user_id', String(userId))
  return request<ProfileResponse>(`/api/profile/${encodeURIComponent(ticker)}?${qs.toString()}`)
}

export function getSectors(market: 'IN' | 'US' = 'IN') {
  return request<SectorsResponse>(`/api/sectors?market=${market}`)
}

export function getForwardTest(userId: number) {
  return request<ForwardTestResponse>(`/api/forward-test?user_id=${userId}`)
}

export function postRefresh(body: {
  tickers?: string[]
  full_universe?: boolean
  with_fundamentals?: boolean
  market?: 'IN' | 'US'
  user_id?: number
}) {
  return request<Record<string, unknown>>('/api/refresh', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function postOpenTrade(body: {
  ticker: string
  entry_price: number
  stop_loss: number
  target: number
  user_id?: number
}) {
  return request<{ status: string; message: string }>('/api/trade', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function postCloseTrade(body: {
  position_id: number
  exit_price: number
  exit_status: string
  user_id?: number
}) {
  return request<{ status: string; message: string; final_pnl: number }>('/api/trade/close', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export { ApiError }
