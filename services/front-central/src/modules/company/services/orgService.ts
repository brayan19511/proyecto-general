import { apiRequest } from '../../../shared/api/apiClient'
import type { Area, Position, PositionRole, Role } from '../types'

// Áreas, puestos y roles de la empresa activa (X-Company-Id). Leer: cualquier
// miembro. Cambiar: areas.manage / positions.manage (fase 1: el front solo lo
// muestra al platform admin). Bajas lógicas con restaurar. 500 = máximo por página.

const id = encodeURIComponent
const deleted = (include: boolean) => (include ? '&include_deleted=true' : '')

export function listAreas(includeDeleted = false) {
  return apiRequest<Area[]>(`/auth/areas?limit=500${deleted(includeDeleted)}`)
}

export function createArea(code: string, name: string) {
  return apiRequest<Area>('/auth/areas', { method: 'POST', body: { code, name } })
}

// El código es el identificador estable: solo cambia el nombre.
export function renameArea(areaId: string, name: string) {
  return apiRequest<Area>(`/auth/areas/${id(areaId)}`, { method: 'PATCH', body: { name } })
}

// 409 si tiene puestos activos.
export function deleteArea(areaId: string) {
  return apiRequest<void>(`/auth/areas/${id(areaId)}`, { method: 'DELETE' })
}

export function restoreArea(areaId: string) {
  return apiRequest<Area>(`/auth/areas/${id(areaId)}/restore`, { method: 'POST' })
}

export function listPositions(includeDeleted = false) {
  return apiRequest<Position[]>(`/auth/positions?limit=500${deleted(includeDeleted)}`)
}

export function createPosition(code: string, name: string, areaId: string) {
  return apiRequest<Position>('/auth/positions', { method: 'POST', body: { code, name, area_id: areaId } })
}

// Nombre y/o área (mover de área exige alcance de empresa). El código no cambia.
export function updatePosition(positionId: string, changes: { name?: string; area_id?: string }) {
  return apiRequest<Position>(`/auth/positions/${id(positionId)}`, { method: 'PATCH', body: changes })
}

// 409 si tiene personas asignadas.
export function deletePosition(positionId: string) {
  return apiRequest<void>(`/auth/positions/${id(positionId)}`, { method: 'DELETE' })
}

// 409 si su área está dada de baja.
export function restorePosition(positionId: string) {
  return apiRequest<Position>(`/auth/positions/${id(positionId)}/restore`, { method: 'POST' })
}

export function listPositionRoles(positionId: string) {
  return apiRequest<PositionRole[]>(`/auth/positions/${id(positionId)}/roles`)
}

export function addPositionRole(positionId: string, roleId: string) {
  return apiRequest<PositionRole>(`/auth/positions/${id(positionId)}/roles`, { method: 'POST', body: { role_id: roleId } })
}

export function removePositionRole(positionId: string, roleId: string) {
  return apiRequest<void>(`/auth/positions/${id(positionId)}/roles/${id(roleId)}`, { method: 'DELETE' })
}

// Roles: roles.manage (solo alcance empresa: los roles son de la empresa).
export function listRoles(includeDeleted = false) {
  return apiRequest<Role[]>(`/auth/roles?limit=500${deleted(includeDeleted)}`)
}

export function createRole(code: string, name: string) {
  return apiRequest<Role>('/auth/roles', { method: 'POST', body: { code, name } })
}

export function renameRole(roleId: string, name: string) {
  return apiRequest<Role>(`/auth/roles/${id(roleId)}`, { method: 'PATCH', body: { name } })
}

// 409 si está asignado a puestos.
export function deleteRole(roleId: string) {
  return apiRequest<void>(`/auth/roles/${id(roleId)}`, { method: 'DELETE' })
}

export function restoreRole(roleId: string) {
  return apiRequest<Role>(`/auth/roles/${id(roleId)}/restore`, { method: 'POST' })
}

// 422 permiso desconocido o alcance no admitido; 409 ya concedido.
export function grantPermission(roleId: string, permission: string, scope: string) {
  return apiRequest<Role>(`/auth/roles/${id(roleId)}/permissions`, { method: 'POST', body: { permission, scope } })
}

// 409 si la empresa quedaría sin administradores.
export function revokePermission(roleId: string, grantId: string) {
  return apiRequest<void>(`/auth/roles/${id(roleId)}/permissions/${id(grantId)}`, { method: 'DELETE' })
}

// Roles de cada puesto activo (auth no tiene "puestos de un rol"): una consulta
// por puesto, de a 6 en paralelo para no saturar.
export async function listPositionRolesMap(positions: Position[]) {
  const map = new Map<string, PositionRole[]>()
  const queue = positions.filter((p) => p.is_active)
  const worker = async () => {
    for (let p = queue.shift(); p; p = queue.shift()) map.set(p.id, await listPositionRoles(p.id))
  }
  await Promise.all(Array.from({ length: 6 }, worker))
  return map
}
