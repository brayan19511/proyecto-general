import { ApiError, apiRequest } from '../../../shared/api/apiClient'
import type { AdminCompany, SapCompany } from '../types'

// Empresas (auth, solo platform admin). No hay borrado: se desactivan.
const id = encodeURIComponent

export function listCompanies() {
  return apiRequest<AdminCompany[]>('/auth/admin/companies?limit=500')
}

export function createCompany(code: string, name: string) {
  return apiRequest<AdminCompany>('/auth/admin/companies', { method: 'POST', body: { code, name } })
}

// El código es el identificador estable: solo cambia el nombre.
export function renameCompany(companyId: string, name: string) {
  return apiRequest<AdminCompany>(`/auth/admin/companies/${id(companyId)}`, { method: 'PATCH', body: { name } })
}

export function setCompanyActive(companyId: string, active: boolean) {
  return apiRequest<AdminCompany>(`/auth/admin/companies/${id(companyId)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' })
}

// Compañía SAP de libro-mayor: se pide con el X-Company-Id de ESA empresa
// (no necesariamente la activa del selector).
const SAP = '/libro-mayor/admin/sap-company'

// null = la empresa aún no tiene compañía SAP (libro-mayor responde 404).
export async function getSapCompany(companyId: string): Promise<SapCompany | null> {
  try {
    return await apiRequest<SapCompany>(SAP, { companyId })
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function createSapCompany(companyId: string, data: Omit<SapCompany, 'id' | 'company_id' | 'created_at'>) {
  return apiRequest<SapCompany>(SAP, { method: 'POST', body: data, companyId })
}

// sap_schema solo cambia si la empresa aún no tiene líneas sincronizadas.
export function updateSapCompany(companyId: string, changes: Partial<Omit<SapCompany, 'id' | 'company_id' | 'created_at'>>) {
  return apiRequest<SapCompany>(SAP, { method: 'PATCH', body: changes, companyId })
}

// Baja lógica: la empresa deja de sincronizarse; las líneas se conservan.
export function deleteSapCompany(companyId: string) {
  return apiRequest<void>(SAP, { method: 'DELETE', companyId })
}
