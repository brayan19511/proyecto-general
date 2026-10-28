import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Dialog from '../../../shared/components/Dialog'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge, { type BadgeTone } from '../../../shared/components/StatusBadge'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import type { DownloadFileStatus, DownloadListItem, DownloadMode } from '../documentTypes'
import * as documentsService from '../services/documentsService'

const MODE_LABEL: Record<DownloadMode, string> = { single: 'Un archivo', sequential: 'Uno por uno', zip: 'ZIP' }

const FILE_STATUS: Record<DownloadFileStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: 'No descargado', tone: 'secondary' },
  delivered: { label: 'Descargado', tone: 'success' },
  failed: { label: 'Falló', tone: 'danger' },
}

// SAP › Descargas: registro de anexos descargados (quién, cuándo y qué archivos,
// también los de cada ZIP). Cada uno ve los suyos; el administrador de
// plataforma, los de toda la empresa (lo decide sap-operaciones).
export default function DownloadsPage() {
  const myId = useSessionStore((s) => s.me?.id)
  const [offset, setOffset] = useState(0)
  const downloads = useApi(() => documentsService.listDownloads(offset), [offset])
  const [openId, setOpenId] = useState<string | null>(null)

  const columns: Column<DownloadListItem>[] = [
    { header: 'Fecha', className: 'small text-nowrap', render: (d) => formatDateTime(d.created_at) },
    { header: 'Usuario', className: 'small', render: (d) => (d.user_id === myId ? 'Tú' : <span className="font-monospace">{d.user_id.slice(0, 8)}</span>) },
    { header: 'Base SAP', className: 'small font-monospace', render: (d) => d.company_db },
    { header: 'Modo', className: 'text-nowrap', render: (d) => MODE_LABEL[d.mode] },
    {
      header: 'Archivos',
      className: 'small text-nowrap',
      render: (d) => `${d.delivered_count} de ${d.file_count} descargados`,
    },
    { header: '', className: 'text-end', render: (d) => <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setOpenId(d.id)}>Ver archivos</button> },
  ]

  return (
    <>
      <PageHeader title="Descargas de anexos" description="Qué anexos de SAP se descargaron, cuándo y por quién." />
      <AsyncState loading={downloads.loading} error={downloads.error} onRetry={downloads.reload} hasData={downloads.data !== undefined}>
        <DataTable columns={columns} rows={downloads.data?.items ?? []} rowKey={(d) => d.id} emptyMessage="Aún no hay descargas." />
        <Pager offset={offset} limit={documentsService.DOWNLOADS_PAGE_SIZE} count={downloads.data?.items.length ?? 0}
          total={downloads.data?.total} onChange={setOffset} />
      </AsyncState>
      {openId && <DownloadDialog downloadId={openId} onClose={() => setOpenId(null)} />}
    </>
  )
}

function DownloadDialog({ downloadId, onClose }: { downloadId: string; onClose: () => void }) {
  const download = useApi(() => documentsService.getDownload(downloadId), [downloadId])
  const d = download.data
  return (
    <Dialog open onClose={onClose} labelledBy="download-title" wide>
      <div className="card-header bg-transparent">
        <h2 id="download-title" className="h5 mb-0">Archivos de la descarga</h2>
        {d && (
          <div className="small text-body-secondary">
            {formatDateTime(d.created_at)} · {MODE_LABEL[d.mode]} · <span className="font-monospace">{d.company_db}</span>
          </div>
        )}
      </div>
      <div className="card-body">
        <AsyncState loading={download.loading} error={download.error} onRetry={download.reload} hasData={d !== undefined}>
          <div className="table-responsive border rounded-3">
            <table className="table align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>Documento</th>
                  <th>Archivo</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {(d?.files ?? []).map((f) => (
                  <tr key={f.seq}>
                    <td className="small text-nowrap"><span className="font-monospace">{f.type_code} {f.doc_num ?? f.doc_entry}</span></td>
                    <td className="text-break">{f.file_name}</td>
                    <td>
                      <StatusBadge tone={FILE_STATUS[f.status].tone} label={FILE_STATUS[f.status].label} />
                      {f.delivered_at && <div className="small text-body-secondary">{formatDateTime(f.delivered_at)}</div>}
                      {f.error && <div className="small text-danger">{f.error}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d?.trace_id && <p className="small text-body-secondary mt-2 mb-0">Solicitud: <span className="font-monospace">{d.trace_id}</span> (Monitoreo › Actividad y logs).</p>}
        </AsyncState>
      </div>
      <div className="card-footer bg-transparent d-flex justify-content-end">
        <button type="button" className="btn btn-outline-secondary" onClick={onClose}>Cerrar</button>
      </div>
    </Dialog>
  )
}
