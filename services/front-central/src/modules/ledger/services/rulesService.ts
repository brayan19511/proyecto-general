import { apiRequest } from '../../../shared/api/apiClient'
import type { Category, ClassificationRun, Rule, RuleInput } from '../types'

// Leer: ledger.view. Crear, editar y dar de baja: ledger.update. DELETE es baja
// lógica y libro-mayor no ofrece restaurar. Cada cambio de regla registra una
// reclasificación que hace el worker.

const inactive = (includeInactive: boolean) => (includeInactive ? '?include_inactive=true' : '')

export function listCategories(includeInactive = false) {
  return apiRequest<Category[]>(`/libro-mayor/categories${inactive(includeInactive)}`)
}

export function createCategory(name: string, parentId: string | null) {
  return apiRequest<Category>('/libro-mayor/categories', { method: 'POST', body: { name, parent_id: parentId } })
}

export function renameCategory(id: string, name: string) {
  return apiRequest<Category>(`/libro-mayor/categories/${encodeURIComponent(id)}`, { method: 'PATCH', body: { name } })
}

// 409 si tiene subcategorías o reglas activas.
export function deactivateCategory(id: string) {
  return apiRequest<void>(`/libro-mayor/categories/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// En orden de evaluación (priority, id).
export function listRules(includeInactive = false) {
  return apiRequest<Rule[]>(`/libro-mayor/rules${inactive(includeInactive)}`)
}

export function createRule(rule: RuleInput) {
  return apiRequest<Rule>('/libro-mayor/rules', { method: 'POST', body: rule })
}

// Se envían todos los campos del formulario: null borra una condición.
export function updateRule(id: string, rule: RuleInput) {
  return apiRequest<Rule>(`/libro-mayor/rules/${encodeURIComponent(id)}`, { method: 'PATCH', body: rule })
}

export function deactivateRule(id: string) {
  return apiRequest<void>(`/libro-mayor/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export const CLASSIFICATION_PAGE_SIZE = 20

export function listClassificationRuns(offset: number) {
  return apiRequest<ClassificationRun[]>(
    `/libro-mayor/classification-runs?limit=${CLASSIFICATION_PAGE_SIZE}&offset=${offset}`,
  )
}

// Sin fechas: todas las líneas de la empresa.
export function createClassificationRun(dateFrom: string | null, dateTo: string | null) {
  return apiRequest<ClassificationRun>('/libro-mayor/classification-runs', {
    method: 'POST',
    body: { date_from: dateFrom, date_to: dateTo },
  })
}
