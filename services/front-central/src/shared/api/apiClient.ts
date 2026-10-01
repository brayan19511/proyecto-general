import { API_URL } from '../config'
import { askPeers, broadcastTokens, withRefreshLock } from '../auth/sessionSync'
import {
  accessStillValid,
  clearTokens,
  getAccessToken,
  getIssuedAt,
  getRefreshToken,
  saveTokens,
  type TokenResponse,
} from '../auth/tokens'

// Error de la API con un mensaje apto para mostrar al usuario.
export class ApiError extends Error {
  status: number // 0 = no hubo respuesta (red, CORS, servidor caído)
  retryAfterSeconds: number | null
  traceId: string | null

  constructor(status: number, message: string, retryAfterSeconds: number | null = null, traceId: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfterSeconds = retryAfterSeconds
    this.traceId = traceId
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean // false en login y refresh: no llevan Bearer
  companyId?: string // otra empresa que la activa (p. ej. al validar un cambio)
}

// Empresa activa: viaja en X-Company-Id. La valida el backend (membresía o
// platform admin); el front solo la elige. La fija el store de sesión.
let activeCompanyId: string | null = null

export function setActiveCompanyId(companyId: string | null) {
  activeCompanyId = companyId
}

// El store de sesión se registra aquí para enterarse cuando la sesión venció.
// Así este módulo no importa el store (evita dependencias circulares).
let onSessionExpired: () => void = () => {}

export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler
}

// Respuesta JSON (o nada si es 204).
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

// Archivo (CSV, etc.): el contenido y el nombre que propone el servidor.
export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await request(path, {})
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? null
  return { blob: await response.blob(), filename }
}

async function request(path: string, options: RequestOptions): Promise<Response> {
  const { auth = true } = options
  let response = await send(path, options)

  // Access vencido: se renueva una vez con el refresh y se repite la solicitud.
  if (response.status === 401 && auth) {
    const renewed = await refreshSession()
    if (!renewed) {
      onSessionExpired()
      throw await toApiError(response)
    }
    response = await send(path, options)
  }

  if (!response.ok) throw await toApiError(response)
  return response
}

async function send(path: string, { method = 'GET', body, auth = true, companyId }: RequestOptions) {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const token = auth ? getAccessToken() : null
  if (token) headers.Authorization = `Bearer ${token}`

  const company = auth ? (companyId ?? activeCompanyId) : null
  if (company) headers['X-Company-Id'] = company

  try {
    return await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor. Revisa tu conexión.')
  }
}

// Renovación compartida: si varias solicitudes reciben 401 a la vez, todas
// esperan la misma renovación. Usar dos veces el mismo refresh hace que auth
// revoque la sesión (detección de reutilización).
let refreshing: Promise<boolean> | null = null

export function refreshSession(): Promise<boolean> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

// Con el candado, una pestaña a la vez (ver auth/sessionSync.ts).
function doRefresh(): Promise<boolean> {
  return withRefreshLock(async () => {
    // Otra pestaña pudo renovar mientras se esperaba el candado (o esta pestaña
    // recién se abre o recarga): se adopta su copia si es más nueva. Así nunca
    // se usa un refresh ya rotado.
    const peer = await askPeers()
    if (peer && peer.issuedAt > getIssuedAt()) {
      saveTokens(peer, peer.issuedAt)
      if (accessStillValid(peer)) return true
    }

    const refreshToken = getRefreshToken()
    if (!refreshToken) return false

    try {
      const tokens = await apiRequest<TokenResponse>('/auth/refresh', {
        method: 'POST',
        body: { refresh_token: refreshToken },
        auth: false,
      })
      broadcastTokens(saveTokens(tokens))
      return true
    } catch (error) {
      // Solo un 401 significa refresh inválido o sesión terminada. Ante un fallo
      // de red se conserva el refresh para reintentar más tarde.
      if (error instanceof ApiError && error.status === 401) clearTokens()
      return false
    }
  })
}

async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number(response.headers.get('Retry-After'))
  const traceId = response.headers.get('X-Trace-Id')
  return new ApiError(
    response.status,
    await readMessage(response),
    Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    traceId,
  )
}

// FastAPI responde {"detail": "texto"} o, en validaciones (422), {"detail": [...]}.
async function readMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) return 'Revisa los datos ingresados.'
  } catch {
    // respuesta sin JSON
  }
  if (response.status >= 500) return 'El servicio no está disponible. Intenta más tarde.'
  return 'No se pudo completar la solicitud.'
}
