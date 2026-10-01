import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { PERMISSIONS, SCOPE_HELP, SCOPE_LABEL, permissionInfo, type PermissionScope } from '../permissionCatalog'
import * as orgService from '../services/orgService'
import type { Role, RoleGrant } from '../types'

// Conceder un permiso a un rol, o cambiar el alcance de una concesión.
// Desde Roles se fija el rol; desde Permisos, el permiso.
export type GrantAction =
  | { kind: 'grant'; roleId?: string; permission?: string }
  | { kind: 'change'; role: Role; grant: RoleGrant }

type GrantModalProps = {
  action: GrantAction
  roles: Role[] // activos
  onClose: () => void
  onSaved: () => void
}

const GROUPS = [...new Set(PERMISSIONS.map((p) => p.group))]

export default function GrantModal({ action, roles, onClose, onSaved }: GrantModalProps) {
  const changing = action.kind === 'change' ? action : null
  const [roleId, setRoleId] = useState(changing?.role.id ?? (action.kind === 'grant' ? action.roleId : '') ?? roles[0]?.id ?? '')
  const [permission, setPermission] = useState(
    changing?.grant.permission ?? (action.kind === 'grant' ? action.permission : '') ?? PERMISSIONS[0].code,
  )
  const role = roles.find((r) => r.id === roleId)
  const has = (scope: PermissionScope) => role?.permissions.some((g) => g.permission === permission && g.scope === scope) ?? false
  const scopes = (permissionInfo(permission)?.scopes ?? []).filter((s) => !has(s))
  const [scope, setScope] = useState<PermissionScope | ''>('')
  // El elegido si sigue siendo válido; si no, el primero disponible.
  const chosen: PermissionScope | '' = scope && scopes.includes(scope) ? scope : (scopes.at(0) ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lockRole = changing !== null || (action.kind === 'grant' && action.roleId !== undefined)
  const lockPermission = changing !== null || (action.kind === 'grant' && action.permission !== undefined)
  const info = permissionInfo(permission)

  const submit = async () => {
    if (!chosen) return
    setBusy(true)
    setError(null)
    try {
      await orgService.grantPermission(roleId, permission, chosen)
      if (changing) {
        // Primero se concede el nuevo alcance y luego se quita el anterior:
        // así nadie pierde acceso en medio del cambio.
        try {
          await orgService.revokePermission(changing.role.id, changing.grant.id)
        } catch (err) {
          throw new Error(`Se concedió el nuevo alcance, pero no se pudo quitar el anterior: ${errorMessage(err)}`, { cause: err })
        }
      }
      toast.success(changing ? 'Alcance cambiado' : 'Permiso concedido. Aplica a quienes tengan un puesto con este rol.')
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error && !('status' in err) ? err.message : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={changing ? 'Cambiar alcance' : 'Conceder permiso'} submitLabel={changing ? 'Cambiar' : 'Conceder'}
      busy={busy} error={error} canSubmit={roleId !== '' && chosen !== ''} onSubmit={submit} onClose={onClose}>
      <div className="mb-3">
        <label htmlFor="grant-role" className="form-label">Rol</label>
        <select id="grant-role" className="form-select" value={roleId} disabled={lockRole} onChange={(e) => setRoleId(e.target.value)}>
          {roles.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.code})</option>)}
        </select>
      </div>

      <div className="mb-3">
        <label htmlFor="grant-permission" className="form-label">Permiso</label>
        <select id="grant-permission" className="form-select" value={permission} disabled={lockPermission}
          onChange={(e) => setPermission(e.target.value)}>
          {GROUPS.map((group) => (
            <optgroup key={group} label={group}>
              {PERMISSIONS.filter((p) => p.group === group).map((p) => (
                <option key={p.code} value={p.code}>{p.label} ({p.code})</option>
              ))}
            </optgroup>
          ))}
        </select>
        {info && <div className="form-text">{info.description}</div>}
      </div>

      <fieldset>
        <legend className="form-label fs-6">{changing ? `Nuevo alcance (hoy: ${SCOPE_LABEL[changing.grant.scope]})` : 'Alcance'}</legend>
        {scopes.length === 0 && (
          <p className="small text-body-secondary mb-0">El rol ya tiene este permiso con todos los alcances que admite.</p>
        )}
        {scopes.map((s) => (
          <div key={s} className="form-check">
            <input id={`scope-${s}`} type="radio" name="scope" className="form-check-input" checked={chosen === s}
              onChange={() => setScope(s)} />
            <label htmlFor={`scope-${s}`} className="form-check-label">
              {SCOPE_LABEL[s]} <span className="small text-body-secondary">— {SCOPE_HELP[s]}</span>
            </label>
          </div>
        ))}
      </fieldset>
    </FormModal>
  )
}
