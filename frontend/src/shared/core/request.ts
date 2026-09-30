/** 统一请求封装：拼前缀、带开发期身份、把后端的统一错误体转成 Error。 */

export interface ApiError extends Error {
  status: number
  requestId?: string
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  // 本框架不含认证。接入登录后，这里换成携带 token 或 cookie
  const devUserId = import.meta.env.VITE_DEV_USER_ID
  if (devUserId) {
    headers['X-User-Id'] = devUserId
  }
  return headers
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: buildHeaders(init) })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const error = new Error(body.message ?? response.statusText) as ApiError
    error.status = response.status
    error.requestId = body.request_id
    throw error
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}
