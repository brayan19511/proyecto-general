import { useState } from 'react'
import Dialog from '../../../shared/components/Dialog'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import type { Channel } from '../channels'
import { KIND_HELP, KIND_LABEL, STATUS } from '../labels'
import * as lastmillerService from '../services/lastmillerService'
import type { ImportDetail, ImportKind } from '../types'
import ImportPreview, { downloadPreview } from './ImportPreview'

type Props = {
  channel: Channel
  initial?: ImportDetail // abrir una carga ya previsualizada (desde la pestaña Cargas)
  canDiscard?: boolean // false para quien solo puede ver (lastmiller.view)
  onClose: () => void
  onApplied: () => void
}

// Carga masiva en dos pasos: 1) subir el .xlsx y ver qué cambiaría (no toca
// Ofisis); 2) aplicar. Si el canal cambió entre ambos pasos, canales-venta
// responde 409 y hay que volver a previsualizar.
export default function ImportModal({ channel, initial, canDiscard = true, onClose, onApplied }: Props) {
  const kinds: ImportKind[] = channel.hasPromotions ? ['sku_full', 'sku_partial', 'promotions'] : ['sku_full', 'sku_partial']
  const [kind, setKind] = useState<ImportKind>('sku_partial')
  const [createMissing, setCreateMissing] = useState(true)
  const [file, setFile] = useState<File | null>(null)
  const [detail, setDetail] = useState<ImportDetail | null>(initial ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fileProblem = !file ? null
    : !file.name.toLowerCase().endsWith('.xlsx') ? 'Solo se admiten archivos .xlsx.'
    : file.size > lastmillerService.MAX_FILE_BYTES ? 'El archivo supera 10 MB.'
    : null

  const preview = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setDetail(await lastmillerService.previewImport(channel, kind, createMissing, file))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const apply = async () => {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      const result = await lastmillerService.applyImport(channel, detail.id)
      setDetail(result)
      toast.success(`Carga aplicada: ${result.applied_changes} cambios en ${channel.name}`)
      onApplied()
    } catch (err) {
      setError(errorMessage(err)) // 409: datos cambiados, otra carga en curso, Ofisis bloqueado
      onApplied() // Pudo quedar aplicada a medias: recargar lo que se ve.
    } finally {
      setBusy(false)
    }
  }

  // Descartar: la vista previa queda registrada como "Descartada" y no se puede aplicar.
  const discard = async () => {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      setDetail(await lastmillerService.cancelImport(channel, detail.id))
      toast.success('Vista previa descartada')
      onApplied()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const status = detail ? STATUS[detail.status] : null
  return (
    <Dialog open onClose={onClose} busy={busy} labelledBy="import-title" wide>
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <h2 id="import-title" className="h5 mb-0">Carga masiva · {channel.name}</h2>
        {detail && status && <StatusBadge tone={status.tone} label={`${KIND_LABEL[detail.kind]} · ${status.label}`} />}
      </div>
      <div className="card-body">
        {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}
        {!detail ? (
          <>
            <fieldset className="mb-3">
              <legend className="form-label fs-6">Tipo de carga</legend>
              {kinds.map((k) => (
                <div key={k} className="form-check mb-2">
                  <input id={`kind-${k}`} type="radio" name="kind" className="form-check-input" checked={kind === k} onChange={() => setKind(k)} />
                  <label htmlFor={`kind-${k}`} className="form-check-label">
                    {KIND_LABEL[k]}
                    <span className="d-block small text-body-secondary">{KIND_HELP[k]}</span>
                  </label>
                </div>
              ))}
            </fieldset>
            {kind !== 'promotions' && (
              <div className="form-check mb-3">
                <input id="create-missing" type="checkbox" className="form-check-input" checked={createMissing} onChange={(e) => setCreateMissing(e.target.checked)} />
                <label htmlFor="create-missing" className="form-check-label">Crear los SKU del archivo que no existen en el canal</label>
              </div>
            )}
            <label htmlFor="import-file" className="form-label">Archivo (.xlsx)</label>
            <input id="import-file" type="file" className="form-control" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <div className={`form-text ${fileProblem ? 'text-danger' : ''}`}>
              {fileProblem ?? (kind === 'promotions'
                ? 'Primera fila: encabezado con la columna sku.'
                : 'Primera fila: encabezados sku y on/off (también active, on_off o estado). Valores: on/off, 1/0, true/false.')}
            </div>
          </>
        ) : (
          <>
            <p className="small text-body-secondary">
              Archivo <span className="fw-semibold">{detail.filename}</span>
              {detail.kind !== 'promotions' && ` · ${detail.create_missing ? 'crea' : 'no crea'} SKU nuevos`}
              {detail.status === 'previewed' && ' · Aún no se aplicó nada.'}
              {detail.error_message && <span className="text-danger"> · {detail.error_message}</span>}
              {(detail.status === 'failed' || detail.status === 'interrupted') &&
                ` · Se aplicaron ${detail.applied_changes} de ${detail.total_changes} cambios (ver Historial).`}
            </p>
            <ImportPreview detail={detail} />
          </>
        )}
      </div>
      <div className="card-footer bg-transparent d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={busy}>Cerrar</button>
        {detail && (
          <button type="button" className="btn btn-outline-secondary me-auto order-first" onClick={() => downloadPreview(detail)}
            title="CSV con cada SKU y su estado (también las observaciones del archivo)">
            <i className="bi bi-download me-1" aria-hidden="true" />Descargar CSV
          </button>
        )}
        {!detail && (
          <button type="button" className="btn btn-primary" disabled={busy || !file || fileProblem !== null} onClick={preview}>
            {busy && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            Ver vista previa
          </button>
        )}
        {detail && !initial && !['applied', 'cancelled'].includes(detail.status) && (
          <button type="button" className="btn btn-outline-primary" disabled={busy} onClick={() => { setDetail(null); setError(null) }}>
            Otro archivo
          </button>
        )}
        {detail && canDiscard && (detail.status === 'previewed' || detail.status === 'invalid') && (
          <button type="button" className="btn btn-outline-danger" disabled={busy} onClick={discard}
            title="No se aplica nada; queda registrada como descartada">
            Descartar
          </button>
        )}
        {detail?.can_apply && (
          <button type="button" className="btn btn-danger" disabled={busy} onClick={apply}>
            {busy && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            Aplicar {detail.total_changes} cambios
          </button>
        )}
      </div>
    </Dialog>
  )
}
