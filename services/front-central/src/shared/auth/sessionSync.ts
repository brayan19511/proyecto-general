import type { SessionTokens } from './tokens'

// Sesión compartida entre pestañas del mismo navegador (decisión del usuario,
// 2026-09-30): una sola sesión de auth por navegador en lugar de una por pestaña.
//
// - BroadcastChannel: mensajes entre pestañas del mismo origen. Una pestaña
//   nueva pide la sesión; tras login o renovación se avisa a las demás; cerrar
//   sesión en una la cierra en todas.
// - Web Locks: solo una pestaña renueva a la vez. El refresh es rotativo: si dos
//   pestañas usaran el mismo, auth revocaría la sesión por reutilización.
//
// Los tokens viajan solo por mensajes en memoria; nada en localStorage.

type Message =
  | { type: 'request' } // "¿quién tiene la sesión?"
  | { type: 'tokens'; tokens: SessionTokens }
  | { type: 'logout' }

type Handlers = {
  current: () => SessionTokens | null // lo que esta pestaña responde si se lo piden
  onTokens: (tokens: SessionTokens) => void // otra pestaña inició o renovó la sesión
  onLogout: () => void // otra pestaña cerró la sesión
}

const PEER_WAIT_MS = 150 // cuánto se espera la respuesta de las otras pestañas
const LOCK_NAME = 'front-central-session-refresh'

const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('front-central-session')
let handlers: Handlers | null = null
const collectors = new Set<(tokens: SessionTokens) => void>()

channel?.addEventListener('message', (event: MessageEvent<Message>) => {
  const message = event.data
  if (message.type === 'request') {
    const tokens = handlers?.current()
    if (tokens) channel.postMessage({ type: 'tokens', tokens } satisfies Message)
  } else if (message.type === 'tokens') {
    collectors.forEach((collect) => collect(message.tokens))
    handlers?.onTokens(message.tokens)
  } else if (message.type === 'logout') {
    handlers?.onLogout()
  }
})

export function setSyncHandlers(next: Handlers) {
  handlers = next
}

export function broadcastTokens(tokens: SessionTokens) {
  channel?.postMessage({ type: 'tokens', tokens } satisfies Message)
}

export function broadcastLogout() {
  channel?.postMessage({ type: 'logout' } satisfies Message)
}

// Pide la sesión a las otras pestañas y devuelve la copia más nueva (o null).
export function askPeers(): Promise<SessionTokens | null> {
  if (!channel) return Promise.resolve(null)
  return new Promise((resolve) => {
    let newest: SessionTokens | null = null
    const collect = (tokens: SessionTokens) => {
      if (!newest || tokens.issuedAt > newest.issuedAt) newest = tokens
    }
    collectors.add(collect)
    channel.postMessage({ type: 'request' } satisfies Message)
    setTimeout(() => {
      collectors.delete(collect)
      resolve(newest)
    }, PEER_WAIT_MS)
  })
}

// Ejecuta fn con el candado de renovación (una pestaña a la vez). Web Locks solo
// existe en contextos seguros (HTTPS o localhost); por HTTP en la red se usa un
// candado en localStorage (storageLock).
export function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator !== 'undefined' && navigator.locks) return navigator.locks.request(LOCK_NAME, fn)
  return storageLock(fn)
}

// --- Candado sin Web Locks ---
// En localStorage va SOLO quién tiene el candado y hasta cuándo, nunca tokens.
// localStorage es compartido y síncrono entre pestañas del mismo origen: se
// escribe, se espera un momento y se relee; si otra pestaña escribió a la vez,
// gana la última y la otra reintenta. El vencimiento evita quedar trabado si una
// pestaña se cierra con el candado tomado.
const STORAGE_LOCK_KEY = 'front-central-refresh-lock'
const STORAGE_LOCK_TTL_MS = 10_000
const SETTLE_MS = 50
const TAB_ID = `${Date.now()}-${Math.random().toString(36).slice(2)}`

type StoredLock = { owner: string; until: number }

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function readLock(): StoredLock | null {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_LOCK_KEY) ?? 'null') as StoredLock | null
  } catch {
    return null
  }
}

async function storageLock<T>(fn: () => Promise<T>): Promise<T> {
  try {
    localStorage.getItem(STORAGE_LOCK_KEY)
  } catch {
    return fn() // sin almacenamiento (modo privado estricto): sin candado
  }
  const giveUpAt = Date.now() + STORAGE_LOCK_TTL_MS
  while (Date.now() < giveUpAt) {
    const current = readLock()
    if (!current || current.until < Date.now()) {
      const mine: StoredLock = { owner: TAB_ID, until: Date.now() + STORAGE_LOCK_TTL_MS }
      localStorage.setItem(STORAGE_LOCK_KEY, JSON.stringify(mine))
      await sleep(SETTLE_MS)
      if (readLock()?.owner === TAB_ID) break // quedó el nuestro
    }
    await sleep(100 + Math.random() * 100)
  }
  try {
    return await fn()
  } finally {
    if (readLock()?.owner === TAB_ID) localStorage.removeItem(STORAGE_LOCK_KEY)
  }
}
