import { apiRequest } from '../../../shared/api/apiClient'
import type { CostCenter, CostCenterMapping } from '../types'

// Ver: ledger.view. Crear, cambiar el área y dar de baja: ledger.admin.
// El área de cada línea se resuelve al consultar: los cambios valen desde la
// siguiente consulta, sin reprocesar.

export function listCostCenters(unmapped = false) {
  return apiRequest<CostCenter[]>(`/libro-mayor/cost-centers${unmapped ? '?unmapped=true' : ''}`)
}

export function listMappings(includeInactive = false) {
  return apiRequest<CostCenterMapping[]>(`/libro-mayor/cost-center-mappings${includeInactive ? '?include_inactive=true' : ''}`)
}

export function createMapping(costCenterCode: string, matchMode: 'exact' | 'prefix', areaId: string) {
  return apiRequest<CostCenterMapping>('/libro-mayor/cost-center-mappings', {
    method: 'POST',
    body: { cost_center_code: costCenterCode, match_mode: matchMode, area_id: areaId },
  })
}

// Solo cambia el área; código y modo no se editan (dar de baja y crear otra).
export function changeMappingArea(id: string, areaId: string) {
  return apiRequest<CostCenterMapping>(`/libro-mayor/cost-center-mappings/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { area_id: areaId },
  })
}

export function deactivateMapping(id: string) {
  return apiRequest<void>(`/libro-mayor/cost-center-mappings/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
