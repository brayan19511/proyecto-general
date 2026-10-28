import { useState } from 'react'
import { Link } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import Dialog from '../../../shared/components/Dialog'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import type { DownloadMode, SapDocument } from '../documentTypes'
import * as documentsService from '../services/documentsService'

type Props = { companyDb: string; typeLabel: string; document: SapDocument; onClose: () => void }

// Anexos de un documento: bajar uno, o los seleccionados en ZIP o uno por uno.
// Cada descarga se registra antes de bajar (SAP › Descargas muestra qué se bajó).
export default function AttachmentsDialog({ companyDb, typeLabel, document, onClose }: Props) {
  const attachments = useApi(
    () => documentsService.listAttachments(companyDb, document.type_code, document.doc_entry),
    [companyDb, document.type_code, document.doc_entry],
  )
  const [selected, setSelected] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const lines = attachments.data ?? []
  const allSelected = lines.length > 0 && selected.length === lines.length

  function toggle(line: number) {
    setSelected((s) => (s.includes(line) ? s.filter((l) => l !== line) : [...s, line]))
  }

  async function download(mode: DownloadMode, chosen: number[]) {
    setBusy(true)
    try {
      const files = chosen.map((line) => ({ type_code: document.type_code, doc_entry: document.doc_entry, line }))
      const created = await documentsService.createDownload(companyDb, mode, files)
      if (mode === 'zip') {
        await documentsService.saveZip(created.id)
        toast.success(`ZIP con ${created.file_count} archivos descargado.`)
        return
      }
      // Uno por uno: si uno falla, se sigue con los demás (el registro guarda cuál falló).
      let failed = 0
      for (const file of created.files) {
        try {
          await documentsService.saveFile(created.id, file.seq, file.file_name)
        } catch (error) {
          failed += 1
          toast.error(`${file.file_name}: ${errorMessage(error)}`)
        }
      }
      if (failed === 0) toast.success(created.file_count === 1 ? 'Archivo descargado.' : `${created.file_count} archivos descargados.`)
      else toast.warning(`${created.file_count - failed} de ${created.file_count} archivos descargados.`)
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const number = document.doc_num ?? document.doc_entry
  return (
    <Dialog open onClose={onClose} busy={busy} labelledBy="attachments-title" wide>
      <div className="card-header bg-transparent">
        <h2 id="attachments-title" className="h5 mb-0">Anexos · {typeLabel} {number}</h2>
        <div className="small text-body-secondary">
          {[document.folio, document.card_name, document.doc_date && formatDate(document.doc_date)].filter(Boolean).join(' · ')}
        </div>
      </div>
      <div className="card-body">
        <AsyncState loading={attachments.loading} error={attachments.error} onRetry={attachments.reload} hasData={attachments.data !== undefined}>
          {lines.length === 0 ? (
            <p className="text-body-secondary mb-0">Este documento no tiene anexos.</p>
          ) : (
            <div className="table-responsive border rounded-3">
              <table className="table table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th style={{ width: 40 }}>
                      <input type="checkbox" className="form-check-input" aria-label="Seleccionar todos" checked={allSelected}
                        disabled={busy} onChange={() => setSelected(allSelected ? [] : lines.map((a) => a.line))} />
                    </th>
                    <th>Archivo</th>
                    <th className="text-nowrap">Fecha</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((a) => (
                    <tr key={a.line}>
                      <td>
                        <input type="checkbox" className="form-check-input" aria-label={`Seleccionar ${a.file_name}`}
                          checked={selected.includes(a.line)} disabled={busy} onChange={() => toggle(a.line)} />
                      </td>
                      <td className="text-break">{a.file_name}</td>
                      <td className="small text-nowrap">{a.attached_on ? formatDate(a.attached_on) : '—'}</td>
                      <td className="text-end">
                        <button type="button" className="btn btn-sm btn-outline-primary" disabled={busy}
                          onClick={() => download('single', [a.line])}>
                          <i className="bi bi-download me-1" aria-hidden="true" />Descargar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncState>
        <p className="small text-body-secondary mt-2 mb-0">
          Cada descarga queda registrada en <Link to="/sap/descargas">Descargas</Link>.
          Al bajar varios uno por uno, el navegador puede pedir permiso para descargar varios archivos.
        </p>
      </div>
      <div className="card-footer bg-transparent d-flex flex-wrap justify-content-end gap-2">
        {busy && <span className="spinner-border spinner-border-sm align-self-center" aria-label="Descargando" />}
        <button type="button" className="btn btn-outline-secondary" disabled={busy} onClick={onClose}>Cerrar</button>
        <button type="button" className="btn btn-outline-primary" disabled={busy || selected.length === 0}
          onClick={() => download('sequential', [...selected].sort((a, b) => a - b))}>
          Bajar seleccionados uno por uno
        </button>
        <button type="button" className="btn btn-primary" disabled={busy || selected.length === 0}
          onClick={() => download('zip', [...selected].sort((a, b) => a - b))}>
          <i className="bi bi-file-zip me-1" aria-hidden="true" />ZIP ({selected.length})
        </button>
      </div>
    </Dialog>
  )
}
