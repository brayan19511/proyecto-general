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

// Ejecuta fn con el candado de renovación (una pestaña a la vez). Sin Web Locks
// (navegador antiguo) se ejecuta directo.
export function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator === 'undefined' || !navigator.locks) return fn()
  return navigator.locks.request(LOCK_NAME, fn)
}
