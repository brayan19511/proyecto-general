import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { SCOPE_LABEL, withTexts, type PermissionInfo } from '../permissionCatalog'
import * as orgService from '../services/orgService'
import type { Role, RoleGrant } from '../types'
import GrantModal, { type GrantAction } from './GrantModal'

// Permisos: el catálogo lo define auth (no se crean ni borran permisos) y se
// pide a auth, así aparece todo permiso registrado; aquí se ve quién tiene cada
// uno y se concede, cambia de alcance o quita por rol.
export default function PermissionsTab() {
  const [search, setSearch] = useState('')
  const roles = useApi(() => orgService.listRoles())
  const catalog = useApi(() => orgService.listPermissionCatalog())
  const permissions = withTexts(catalog.data ?? [])
  const [grant, setGrant] = useState<GrantAction | null>(null)
  const [toRevoke, setToRevoke] = useState<{ role: Role; grant: RoleGrant } | null>(null)
  const [busy, setBusy] = useState(false)

  const activeRoles = (roles.data ?? []).filter((r) => r.is_active)
  const holders = (p: PermissionInfo) =>
    activeRoles.flatMap((role) => role.permissions.filter((g) => g.permission === p.code).map((g) => ({ role, grant: g })))

  const term = search.trim().toLowerCase()
  const visible = permissions.filter(
    (p) => !term || `${p.label} ${p.code} ${p.description} ${holders(p).map((h) => h.role.name).join(' ')}`.toLowerCase().includes(term),
  )
  const groups = [...new Set(visible.map((p) => p.group))]

  const revoke = async () => {
    if (!toRevoke) return
    setBusy(true)
    try {
      await orgService.revokePermission(toRevoke.role.id, toRevoke.grant.id)
      toast.success('Permiso quitado')
      roles.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 la empresa quedaría sin administradores
    } finally {
      setBusy(false)
      setToRevoke(null)
    }
  }

  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 320 }} placeholder="Buscar permiso o rol…"
          aria-label="Buscar permisos" value={search} onChange={(e) => setSearch(e.target.value)} />
        <span className="small text-body-secondary">
          {permissions.length > 0 && `${permissions.length} permisos registrados. `}
          Cada permiso existe porque un servicio lo comprueba en su código: se agregan en auth junto con ese
          servicio (y su seed), no desde aquí. Aquí decides qué roles los tienen y con qué alcance.
        </span>
      </div>

      <AsyncState loading={roles.loading || catalog.loading} error={roles.error ?? catalog.error}
        onRetry={() => { roles.reload(); catalog.reload() }} hasData={roles.data !== undefined && catalog.data !== undefined}>
        {groups.length === 0 && <p className="text-body-secondary">Ningún permiso coincide con la búsqueda.</p>}
        {groups.map((group) => (
          <div key={group} className="mb-4">
            <h2 className="h6 text-body-secondary">{group}</h2>
            <div className="table-responsive border rounded-3">
              <table className="table align-middle mb-0">
                <thead className="table-light">
                  <tr><th>Permiso</th><th>Alcances posibles</th><th>Roles que lo tienen</th><th className="text-end">Acciones</th></tr>
                </thead>
                <tbody>
                  {visible.filter((p) => p.group === group).map((p) => (
                    <tr key={p.code}>
                      <td style={{ minWidth: 260 }}>
                        <div>
                          {p.label}
                          {!p.loaded && (
                            <span className="badge text-bg-warning fw-normal ms-2" title="Está en auth pero no en su base: ejecuta el seed de auth para poder concederlo.">
                              Falta ejecutar el seed
                            </span>
                          )}
                        </div>
                        <div className="small text-body-secondary"><span className="font-monospace">{p.code}</span> · {p.description}</div>
                      </td>
                      <td className="small text-nowrap">{p.scopes.map((s) => SCOPE_LABEL[s]).join(', ')}</td>
                      <td>
                        <div className="d-flex flex-wrap gap-1">
                          {holders(p).length === 0 && <span className="small text-body-secondary">Ningún rol</span>}
                          {holders(p).map(({ role, grant: g }) => (
                            <span key={g.id} className="badge bg-primary-subtle text-primary-emphasis fw-normal d-inline-flex align-items-center gap-1">
                              {role.name} · {SCOPE_LABEL[g.scope]}
                              {p.scopes.length > 1 && (
                                <button type="button" className="btn btn-link p-0 lh-1 text-primary-emphasis" title="Cambiar alcance"
                                  aria-label={`Cambiar alcance de ${role.name}`} onClick={() => setGrant({ kind: 'change', role, grant: g })}>
                                  <i className="bi bi-pencil" style={{ fontSize: '0.7rem' }} aria-hidden="true" />
                                </button>
                              )}
                              <button type="button" className="btn btn-link p-0 lh-1 text-danger" title="Quitar este permiso del rol"
                                aria-label={`Quitar a ${role.name}`} onClick={() => setToRevoke({ role, grant: g })}>
                                <i className="bi bi-x-lg" aria-hidden="true" />
                              </button>
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="text-end">
                        <button type="button" className="btn btn-sm btn-outline-primary text-nowrap" disabled={activeRoles.length === 0 || !p.loaded}
                          onClick={() => setGrant({ kind: 'grant', permission: p.code })}>
                          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
                          Conceder
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </AsyncState>

      {grant && <GrantModal action={grant} roles={activeRoles} catalog={permissions} onClose={() => setGrant(null)} onSaved={roles.reload} />}

      <ConfirmDialog
        open={toRevoke !== null}
        title="Quitar permiso"
        message={`Quienes tengan un puesto con ${toRevoke?.role.name ?? ''} pierden este permiso (${toRevoke ? SCOPE_LABEL[toRevoke.grant.scope] : ''}) desde su próxima solicitud, salvo que otro rol se lo dé.`}
        confirmLabel="Quitar"
        danger
        busy={busy}
        onConfirm={revoke}
        onCancel={() => setToRevoke(null)}
      />
    </>
  )
}
