import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import GatewayHistory from '../components/GatewayHistory'
import IpBlockFormModal from '../components/IpBlockFormModal'
import * as gatewayService from '../services/gatewayService'
import * as usersService from '../services/usersService'
import type { IpBlock } from '../types'

// Estado mostrado: activo, vencido (sigue en la lista pero ya no bloquea) o quitado.
function blockStatus(b: IpBlock) {
  if (!b.is_active) return { tone: 'secondary' as const, label: 'Desbloqueada' }
  if (b.expires_at && new Date(b.expires_at).getTime() <= Date.now()) return { tone: 'warning' as const, label: 'Vencida' }
  return { tone: 'danger' as const, label: 'Bloqueada' }
}

// Plataforma › IPs bloqueadas (solo platform admin): lista negra de la central.
export default function IpBlocksPage() {
  const [includeInactive, setIncludeInactive] = useState(false)
  const [search, setSearch] = useState('')
  const blocks = useApi(() => gatewayService.listIpBlocks(includeInactive), [includeInactive])
  const emails = useApi(usersService.emailsById)
  const [creating, setCreating] = useState(false)
  const [toDelete, setToDelete] = useState<IpBlock | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  const emailOf = (id: string | null) => (id ? emails.data?.get(id) ?? id.slice(0, 8) : '—')

  const reload = () => {
    blocks.reload()
    setVersion((v) => v + 1)
  }

  const term = search.trim().toLowerCase()
  const rows = (blocks.data ?? []).filter((b) => !term || `${b.network} ${b.reason ?? ''}`.toLowerCase().includes(term))

  const unblock = async () => {
    if (!toDelete) return
    setBusy(true)
    try {
      await gatewayService.deleteIpBlock(toDelete.id)
      toast.success(`${toDelete.network} desbloqueada`)
      reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToDelete(null)
    }
  }

  const columns: Column<IpBlock>[] = [
    { header: 'IP o rango', render: (b) => <span className="font-monospace">{b.network}</span> },
    { header: 'Motivo', render: (b) => b.reason ?? <span className="text-body-secondary">—</span> },
    { header: 'Vence', className: 'text-nowrap', render: (b) => (b.expires_at ? formatDateTime(b.expires_at) : 'Sin vencimiento') },
    {
      header: 'Creada',
      className: 'text-nowrap small',
      render: (b) => (
        <>
          <div>{formatDateTime(b.created_at)}</div>
          <div className="text-body-secondary">{emailOf(b.created_by)}</div>
        </>
      ),
    },
    { header: 'Estado', render: (b) => <StatusBadge {...blockStatus(b)} /> },
    {
      header: 'Acciones',
      className: 'text-end',
      render: (b) =>
        b.is_active && (
          <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setToDelete(b)}>Desbloquear</button>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="IPs bloqueadas"
        description="La central rechaza (403) las solicitudes de estas IPs o rangos antes de llegar a cualquier servicio."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            <i className="bi bi-shield-x me-1" aria-hidden="true" />
            Bloquear IP
          </button>
        }
      />

      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar IP o motivo…"
          aria-label="Buscar bloqueos" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="ip-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="ip-inactive" className="form-check-label">Ver desbloqueadas</label>
        </div>
      </div>
      <p className="small text-body-secondary">
        Para ver desde qué IPs se conecta alguien, usa Monitoreo › Actividad y logs. Si alguna vez quedaras bloqueado,
        se recupera con IP_BLOCKS_ENABLED=false en la configuración de la central y reiniciándola.
      </p>

      <AsyncState loading={blocks.loading} error={blocks.error} onRetry={blocks.reload} hasData={blocks.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(b) => b.id}
          emptyMessage={term ? 'Ningún bloqueo coincide.' : 'No hay IPs bloqueadas.'} />
      </AsyncState>

      <GatewayHistory resourceType="ip_block" version={version} emails={emails.data ?? new Map()} />

      {creating && <IpBlockFormModal onClose={() => setCreating(false)} onSaved={reload} />}

      <ConfirmDialog
        open={toDelete !== null}
        title="Desbloquear"
        message={`${toDelete?.network ?? ''} podrá volver a usar la plataforma. El bloqueo queda en el historial.`}
        confirmLabel="Desbloquear"
        busy={busy}
        onConfirm={unblock}
        onCancel={() => setToDelete(null)}
      />
    </>
  )
}
