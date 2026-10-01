import { apiRequest } from '../../../shared/api/apiClient'
import type { Account } from '../types'

// Cuentas que libro-mayor sincroniza desde SAP. Ver: ledger.view. Crear, editar
// y dar de baja: ledger.admin. Sin restaurar: para volver, se registra otra.

export function listAccounts(includeInactive = false) {
  return apiRequest<Account[]>(`/libro-mayor/accounts?limit=500${includeInactive ? '&include_inactive=true' : ''}`)
}

// 409 si se superpone con otra activa (p. ej. 95 por prefijo y 959005993) o si
// la empresa no tiene compañía SAP configurada.
export function createAccount(code: string, matchMode: 'exact' | 'prefix', name: string | null) {
  return apiRequest<Account>('/libro-mayor/accounts', { method: 'POST', body: { code, match_mode: matchMode, name } })
}

// Código y modo solo cambian si aún no tiene líneas (si no, 409: baja y alta).
export function updateAccount(id: string, changes: { code?: string; match_mode?: 'exact' | 'prefix'; name?: string | null }) {
  return apiRequest<Account>(`/libro-mayor/accounts/${encodeURIComponent(id)}`, { method: 'PATCH', body: changes })
}

// Deja de sincronizarse; las líneas ya traídas se conservan.
export function deactivateAccount(id: string) {
  return apiRequest<void>(`/libro-mayor/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
