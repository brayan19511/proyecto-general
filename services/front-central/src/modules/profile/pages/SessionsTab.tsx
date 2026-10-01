import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { countLabel, formatDateTime } from '../../../shared/utils/format'
import * as profileService from '../services/profileService'
import type { MySession } from '../types'

// Qué se está por confirmar: una sesión concreta o "todas las demás".
type Pending = { kind: 'one'; session: MySession } | { kind: 'others' } | null

export default function SessionsTab() {
  const { data, loading, error, reload } = useApi(profileService.listMySessions)
  const [pending, setPending] = useState<Pending>(null)
  const [busy, setBusy] = useState(false)

  const sessions = data ?? []
  const hasOthers = sessions.some((s) => !s.current)

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'one') {
        await profileService.revokeMySession(pending.session.id)
        toast.success('Sesión cerrada')
      } else {
        const { revoked } = await profileService.revokeMyOtherSessions()
        toast.success(revoked === 1 ? 'Se cerró 1 sesión' : `Se cerraron ${countLabel(revoked, 'sesión', 'sesiones')}`)
      }
      reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  return (
    <>
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <p className="text-body-secondary mb-0">
          Dispositivos con tu sesión abierta. Cierra las que no reconozcas.
        </p>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          onClick={() => setPending({ kind: 'others' })}
          disabled={!hasOthers}
        >
          Cerrar las demás sesiones
        </button>
      </div>

      <AsyncState loading={loading} error={error} onRetry={reload} hasData={data !== undefined}>
        <div className="table-responsive border rounded-3">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th>Dispositivo</th>
                <th>Última IP</th>
                <th>Inicio</th>
                <th>Última actividad</th>
                <th>Vence</th>
                <th aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div className="text-truncate" style={{ maxWidth: 280 }} title={s.client_description}>
                      {s.client_description || 'Desconocido'}
                    </div>
                    {s.current && <span className="badge text-bg-success">Esta sesión</span>}
                  </td>
                  <td className="text-nowrap">{s.last_ip}</td>
                  <td className="text-nowrap">{formatDateTime(s.created_at)}</td>
                  <td className="text-nowrap">{formatDateTime(s.last_seen_at)}</td>
                  <td className="text-nowrap">{formatDateTime(s.expires_at)}</td>
                  <td className="text-end">
                    {!s.current && (
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => setPending({ kind: 'one', session: s })}
                      >
                        Cerrar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AsyncState>

      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'others' ? 'Cerrar las demás sesiones' : 'Cerrar sesión'}
        message={
          pending?.kind === 'others'
            ? 'Se cerrarán todas tus sesiones excepto esta. Esos dispositivos tendrán que volver a iniciar sesión.'
            : 'Ese dispositivo tendrá que volver a iniciar sesión.'
        }
        confirmLabel="Cerrar"
        danger
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
