// Textos de las acciones del historial de auth ("recurso.verbo").

export const RESOURCE_LABEL: Record<string, string> = {
  membership: 'Miembro',
  assignment: 'Puesto de un miembro',
  area: 'Área',
  position: 'Puesto',
  position_role: 'Rol de un puesto',
  role: 'Rol',
  role_permission: 'Permiso de un rol',
  api_key: 'API key',
  company: 'Empresa',
}

const VERB_LABEL: Record<string, string> = {
  created: 'creado',
  updated: 'modificado',
  deleted: 'dado de baja',
  restored: 'restaurado',
  suspended: 'suspendido',
  reactivated: 'reactivado',
  revoked: 'revocado',
  activated: 'activada',
  deactivated: 'desactivada',
}

// Filtro por tipo de recurso (prefijo de la acción).
export const ACTION_FILTERS = Object.entries(RESOURCE_LABEL).map(([key, label]) => ({ value: `${key}.`, label }))

export function actionLabel(action: string) {
  const [resource, verb] = action.split('.')
  return `${RESOURCE_LABEL[resource] ?? resource} ${VERB_LABEL[verb] ?? verb}`
}

// Tono del badge según el verbo.
export function actionTone(action: string): 'success' | 'danger' | 'warning' | 'info' | 'secondary' {
  const verb = action.split('.')[1]
  if (verb === 'created' || verb === 'restored' || verb === 'reactivated' || verb === 'activated') return 'success'
  if (verb === 'deleted' || verb === 'revoked' || verb === 'deactivated') return 'danger'
  if (verb === 'suspended') return 'warning'
  return 'info'
}
