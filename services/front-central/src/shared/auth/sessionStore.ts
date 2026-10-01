import { create } from 'zustand'
import { refreshSession, setActiveCompanyId, setSessionExpiredHandler } from '../api/apiClient'
import { broadcastLogout, broadcastTokens, setSyncHandlers } from './sessionSync'
import { clearTokens, getIssuedAt, getRefreshToken, getTokens, saveTokens } from './tokens'
import * as authService from '../../modules/auth/services/authService'
import type { Company, Me, PermissionGrant, Profile } from '../../modules/auth/types'

type SessionStatus = 'loading' | 'authenticated' | 'anonymous'

type SessionState = {
  status: SessionStatus
  me: Me | null
  companies: Company[] // empresas que puede elegir en el selector
  companyId: string | null // empresa activa (X-Company-Id)
  permissions: PermissionGrant[] // permisos efectivos en la empresa activa
  notice: string | null // aviso para la pantalla de login (p. ej. sesión vencida)
  initialize: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  selectCompany: (companyId: string) => Promise<void>
  setProfile: (profile: Profile) => void
  reloadCompanies: () => Promise<void>
}

const EMPTY_SESSION = { me: null, companies: [], companyId: null, permissions: [] }

// Última empresa elegida en esta pestaña. Solo comodidad: el backend valida.
const COMPANY_KEY = 'company_id'

function readSavedCompany(): string | null {
  try {
    return sessionStorage.getItem(COMPANY_KEY)
  } catch {
    return null
  }
}

function activateCompany(companyId: string | null) {
  setActiveCompanyId(companyId)
  try {
    if (companyId) sessionStorage.setItem(COMPANY_KEY, companyId)
    else sessionStorage.removeItem(COMPANY_KEY)
  } catch {
    // sin almacenamiento se elige la primera empresa al recargar
  }
}

// Platform admin: todas las empresas activas. Resto: las de sus membresías.
async function loadCompanies(me: Me): Promise<Company[]> {
  const ownCompanies = me.memberships.map((m) => m.company)
  if (!me.is_platform_admin) return ownCompanies
  try {
    const all = await authService.listAllCompanies()
    return all.filter((c) => c.is_active).map(({ id, code, name }) => ({ id, code, name }))
  } catch {
    return ownCompanies
  }
}

// El platform admin tiene acceso a todo: no necesita consultar permisos.
async function loadPermissions(me: Me, companyId: string | null): Promise<PermissionGrant[]> {
  if (me.is_platform_admin || !companyId) return []
  try {
    const result = await authService.getMyPermissions(companyId)
    return result.permissions
  } catch {
    // Sin permisos legibles (p. ej. membresía dada de baja) solo ve Mi perfil.
    return []
  }
}

// Todo lo que se carga después de obtener /auth/me.
async function buildSession(me: Me) {
  const companies = await loadCompanies(me)
  const saved = readSavedCompany()
  const companyId = companies.find((c) => c.id === saved)?.id ?? companies[0]?.id ?? null
  const permissions = await loadPermissions(me, companyId)
  activateCompany(companyId)
  return { me, companies, companyId, permissions }
}

function resetSession() {
  clearTokens()
  activateCompany(null)
}

// Con tokens ya guardados: carga /auth/me, empresas y permisos.
async function enterSession(set: (state: Partial<SessionState>) => void) {
  const me = await authService.getMe()
  set({ status: 'authenticated', notice: null, ...(await buildSession(me)) })
}

// Una sola inicialización por carga de página. StrictMode ejecuta los efectos
// dos veces en desarrollo: sin esto se usaría dos veces el mismo refresh y
// auth revocaría la sesión.
let initializing: Promise<void> | null = null

export const useSessionStore = create<SessionState>()((set, get) => ({
  status: 'loading',
  ...EMPTY_SESSION,
  notice: null,

  initialize: () => {
    initializing ??= (async () => {
      // Al abrir o recargar la pestaña no hay access en memoria: se toma la
      // sesión de otra pestaña abierta o se renueva con el refresh guardado.
      if (!(await refreshSession())) {
        set({ status: 'anonymous' })
        return
      }
      try {
        await enterSession(set)
      } catch {
        set({ status: 'anonymous' })
      }
    })()
    return initializing
  },

  login: async (email, password) => {
    const tokens = await authService.login(email, password)
    const saved = saveTokens(tokens)
    try {
      await enterSession(set)
      broadcastTokens(saved) // las otras pestañas abiertas entran con esta sesión
    } catch (error) {
      resetSession()
      throw error
    }
  },

  logout: async () => {
    const refreshToken = getRefreshToken()
    resetSession()
    broadcastLogout() // una sola sesión por navegador: se cierra en todas las pestañas
    set({ status: 'anonymous', ...EMPTY_SESSION, notice: null })
    if (refreshToken) {
      // Si falla (red), la sesión vence sola en el servidor; no se bloquea la salida.
      await authService.logout(refreshToken).catch(() => {})
    }
  },

  // Consulta los permisos de la nueva empresa antes de activarla, para que
  // menú, rutas y X-Company-Id cambien juntos.
  selectCompany: async (companyId) => {
    const { me, companies } = get()
    if (!me || !companies.some((c) => c.id === companyId)) return
    const permissions = await loadPermissions(me, companyId)
    activateCompany(companyId)
    set({ companyId, permissions })
  },

  // Tras crear, renombrar o desactivar empresas (Plataforma): actualiza el
  // selector. Si la empresa activa ya no está, pasa a la primera.
  reloadCompanies: async () => {
    const { me, companyId } = get()
    if (!me) return
    const companies = await loadCompanies(me)
    if (companies.some((c) => c.id === companyId)) {
      set({ companies })
      return
    }
    const next = companies[0]?.id ?? null
    const permissions = await loadPermissions(me, next)
    activateCompany(next)
    set({ companies, companyId: next, permissions })
  },

  // Tras editar el perfil: la topbar (iniciales) usa estos datos.
  setProfile: (profile) => set((s) => ({ me: s.me && { ...s.me, profile } })),
}))

// El cliente HTTP avisa aquí cuando ya no puede renovar la sesión. La sesión
// es la misma en todas las pestañas: se avisa a las demás.
setSessionExpiredHandler(() => {
  resetSession()
  broadcastLogout()
  useSessionStore.setState({
    status: 'anonymous',
    ...EMPTY_SESSION,
    notice: 'Tu sesión terminó. Inicia sesión nuevamente.',
  })
})

// Lo que hacen las otras pestañas del navegador (ver sessionSync.ts).
setSyncHandlers({
  current: getTokens,
  onTokens: (tokens) => {
    if (tokens.issuedAt <= getIssuedAt()) return // copia vieja o igual
    saveTokens(tokens, tokens.issuedAt)
    // Se inició sesión en otra pestaña y esta estaba en el login: entra también.
    if (useSessionStore.getState().status === 'anonymous') {
      enterSession(useSessionStore.setState).catch(() => {})
    }
  },
  onLogout: () => {
    if (useSessionStore.getState().status === 'anonymous') return
    resetSession()
    useSessionStore.setState({
      status: 'anonymous',
      ...EMPTY_SESSION,
      notice: 'Se cerró la sesión en otra pestaña.',
    })
  },
})
