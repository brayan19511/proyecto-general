// Dónde viven los tokens (acuerdo, fase 1):
// - access: solo en memoria (variable del módulo). Se pierde al recargar.
// - refresh: sessionStorage, para recuperar la sesión al recargar la pestaña.
// Nunca en localStorage, en la URL ni en la consola. Entre pestañas se comparten
// por mensajes (ver sessionSync.ts), no por almacenamiento compartido.

export type TokenResponse = {
  access_token: string
  token_type: 'bearer'
  expires_in: number // segundos de vida del access
  refresh_token: string
}

// issuedAt (ms) ordena las copias: con el refresh rotativo solo la más nueva sirve.
export type SessionTokens = TokenResponse & { issuedAt: number }

const STORAGE_KEY = 'refresh_token'
const EXPIRY_MARGIN_MS = 30_000 // renovar un poco antes de que venza

type Stored = { refresh_token: string; issuedAt: number }

let current: SessionTokens | null = null

function readStored(): Stored | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as Stored
    } catch {
      return { refresh_token: raw, issuedAt: 0 } // formato anterior (solo el token)
    }
  } catch {
    return null
  }
}

export function getAccessToken() {
  return current?.access_token ?? null
}

export function getRefreshToken(): string | null {
  return current?.refresh_token ?? readStored()?.refresh_token ?? null
}

// Cuándo se emitió la copia que tiene esta pestaña (0 = ninguna).
export function getIssuedAt(): number {
  return current?.issuedAt ?? readStored()?.issuedAt ?? 0
}

// Tokens completos en memoria, para pasarlos a otra pestaña que los pida.
export function getTokens(): SessionTokens | null {
  return current
}

export function accessStillValid(tokens: SessionTokens): boolean {
  return tokens.issuedAt + tokens.expires_in * 1000 - EXPIRY_MARGIN_MS > Date.now()
}

export function saveTokens(tokens: TokenResponse, issuedAt = Date.now()): SessionTokens {
  current = { ...tokens, issuedAt }
  try {
    const stored: Stored = { refresh_token: tokens.refresh_token, issuedAt }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
  } catch {
    // sin almacenamiento la sesión dura hasta recargar
  }
  return current
}

export function clearTokens() {
  current = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // nada que limpiar
  }
}
