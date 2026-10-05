import { useState } from 'react'
import { Link } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { LASTMILLER_IMPORT, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import { channelPath } from '../channels'
import { KIND_LABEL, STATUS } from '../labels'
import { useChannel } from '../pages/ChannelLayout'
import * as lastmillerService from '../services/lastmillerService'
import type { ImportDetail, ImportSummary } from '../types'
import ImportModal from './ImportModal'

// Cargas masivas del canal: cada vista previa queda registrada, se haya
// aplicado o no. Una "Por aplicar" se puede abrir y aplicar desde aquí.
export default function ImportsTab() {
  const channel = useChannel()
  const canImport = useCanAccess()({ anyOf: LASTMILLER_IMPORT })
  const [offset, setOffset] = useState(0)
  const imports = useApi(() => lastmillerService.listImports(channel, offset), [offset])
  const [creating, setCreating] = useState(false)
  const [opened, setOpened] = useState<ImportDetail | null>(null)

  const open = async (item: ImportSummary) => {
    try {
      setOpened(await lastmillerService.getImport(channel, item.id))
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const columns: Column<ImportSummary>[] = [
    { header: 'Fecha', className: 'small text-nowrap', render: (i) => formatDateTime(i.created_at) },
    { header: 'Tipo', className: 'text-nowrap', render: (i) => KIND_LABEL[i.kind] },
    { header: 'Archivo', className: 'small', render: (i) => i.filename },
    { header: 'Estado', render: (i) => <StatusBadge tone={STATUS[i.status].tone} label={STATUS[i.status].label} /> },
    {
      header: 'Cambios',
      className: 'text-nowrap small',
      render: (i) => (i.status === 'applied' || i.applied_changes > 0 ? `${i.applied_changes} de ${i.total_changes}` : i.total_changes),
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (i) => (
        <>
          {i.applied_changes > 0 && (
            <Link className="btn btn-sm btn-outline-secondary me-1" to={`${channelPath(channel)}/historial?carga=${i.id}`}>Ver cambios</Link>
          )}
          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => open(i)}>
            {i.status === 'previewed' && canImport ? 'Revisar, aplicar o descartar' : 'Detalle'}
          </button>
        </>
      ),
    },
  ]

  return (
    <>
      {canImport && (
        <div className="d-flex justify-content-end mb-3">
          <button type="button" className="btn btn-sm btn-primary" onClick={() => setCreating(true)}>
            <i className="bi bi-file-earmark-arrow-up me-1" aria-hidden="true" />Nueva carga
          </button>
        </div>
      )}
      <AsyncState loading={imports.loading} error={imports.error} onRetry={imports.reload} hasData={imports.data !== undefined}>
        <DataTable columns={columns} rows={imports.data?.items ?? []} rowKey={(i) => i.id} emptyMessage="Aún no hay cargas en este canal." />
        <Pager offset={offset} limit={lastmillerService.PAGE_SIZE} count={imports.data?.items.length ?? 0} total={imports.data?.total} onChange={setOffset} />
      </AsyncState>

      {creating && <ImportModal channel={channel} onClose={() => setCreating(false)} onApplied={imports.reload} />}
      {opened && (
        <ImportModal channel={channel} initial={{ ...opened, can_apply: opened.can_apply && canImport }} canDiscard={canImport}
          onClose={() => { setOpened(null); imports.reload() }} onApplied={imports.reload} />
      )}
    </>
  )
}
