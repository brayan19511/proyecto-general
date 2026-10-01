import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { SCOPE_HELP, SCOPE_LABEL, type PermissionInfo, type PermissionScope } from '../permissionCatalog'
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
  catalog: PermissionInfo[] // catálogo de auth con sus textos (withTexts)
  onClose: () => void
  onSaved: () => void
}

export default function GrantModal({ action, roles, catalog, onClose, onSaved }: GrantModalProps) {
  const groups = [...new Set(catalog.map((p) => p.group))]
  const changing = action.kind === 'change' ? action : null
  const [roleId, setRoleId] = useState(changing?.role.id ?? (action.kind === 'grant' ? action.roleId : '') ?? roles[0]?.id ?? '')
  const [permission, setPermission] = useState(
    changing?.grant.permission ?? (action.kind === 'grant' ? action.permission : '') ?? catalog.find((p) => p.loaded)?.code ?? '',
  )
  const role = roles.find((r) => r.id === roleId)
  const has = (scope: PermissionScope) => role?.permissions.some((g) => g.permission === permission && g.scope === scope) ?? false
  const info = catalog.find((p) => p.code === permission)
  // Sin cargar en la base (falta el seed) auth respondería 422: no se ofrece.
  const scopes = info?.loaded ? info.scopes.filter((s) => !has(s)) : []
  const [scope, setScope] = useState<PermissionScope | ''>('')
  // El elegido si sigue siendo válido; si no, el primero disponible.
  const chosen: PermissionScope | '' = scope && scopes.includes(scope) ? scope : (scopes.at(0) ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lockRole = changing !== null || (action.kind === 'grant' && action.roleId !== undefined)
  const lockPermission = changing !== null || (action.kind === 'grant' && action.permission !== undefined)

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
          {groups.map((group) => (
            <optgroup key={group} label={group}>
              {catalog.filter((p) => p.group === group).map((p) => (
                <option key={p.code} value={p.code} disabled={!p.loaded}>
                  {p.label} ({p.code}){p.loaded ? '' : ' — falta ejecutar el seed de auth'}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {info && <div className="form-text">{info.description}</div>}
      </div>

      <fieldset>
        <legend className="form-label fs-6">{changing ? `Nuevo alcance (hoy: ${SCOPE_LABEL[changing.grant.scope]})` : 'Alcance'}</legend>
        {info && !info.loaded && (
          <p className="small text-warning-emphasis mb-0">Este permiso aún no está cargado en auth: ejecuta su seed para poder concederlo.</p>
        )}
        {info?.loaded && scopes.length === 0 && (
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
