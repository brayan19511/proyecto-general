import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toIsoDate } from '../../../shared/utils/format'
import { SUGGESTED_ACTIONS, SUGGESTED_ENTITIES } from '../labels'
import * as sapService from '../services/sapService'
import type { Job, JobKind, Preview } from '../types'
import CompanyDbField from './CompanyDbField'

type Props = { kind: JobKind; onClose: () => void; onCreated: (job: Job) => void }

// Paso 1 de un trabajo: datos y vista previa. Si es válido queda en borrador y
// se abre su detalle para revisarlo y ejecutarlo con las credenciales SAP.
export default function NewJobModal({ kind, onClose, onCreated }: Props) {
  const [companyDb, setCompanyDb] = useState('')
  const [entity, setEntity] = useState('')
  const [action, setAction] = useState('')
  const [documents, setDocuments] = useState('')
  const [reconDate, setReconDate] = useState(toIsoDate(new Date()))
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)

  const fileProblem = file && !file.name.toLowerCase().endsWith('.xlsx') ? 'Solo se admiten archivos .xlsx.'
    : file && file.size > sapService.MAX_FILE_BYTES ? 'El archivo supera 20 MB.' : null
  const ready = companyDb.trim() !== '' && (kind === 'document_action'
    ? entity.trim() !== '' && action.trim() !== '' && documents.trim() !== ''
    : file !== null && fileProblem === null && reconDate !== '')

  const submit = async () => {
    setBusy(true)
    setError(null)
    setPreview(null)
    try {
      const result = kind === 'document_action'
        ? await sapService.previewDocumentAction({ company_db: companyDb.trim(), entity: entity.trim(), action: action.trim(), documents })
        : await sapService.previewReconciliation(companyDb.trim(), reconDate, file!)
      if (result.job) {
        onCreated(result.job)
        onClose()
      } else {
        setPreview(result)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={kind === 'document_action' ? 'Nueva acción sobre documentos' : 'Nueva conciliación interna'}
      submitLabel="Ver vista previa" busy={busy} error={error ?? fileProblem} canSubmit={ready} onSubmit={submit} onClose={onClose}>
      <div className="mb-3"><CompanyDbField id="job-db" value={companyDb} onChange={setCompanyDb} /></div>
      {kind === 'document_action' ? (
        <>
          <div className="row g-2 mb-3">
            <div className="col">
              <label htmlFor="job-entity" className="form-label">Entidad</label>
              <input id="job-entity" className="form-control font-monospace" list="job-entities" maxLength={100} placeholder="Invoices"
                value={entity} onChange={(e) => setEntity(e.target.value)} />
              <datalist id="job-entities">{SUGGESTED_ENTITIES.map((e) => <option key={e} value={e} />)}</datalist>
            </div>
            <div className="col">
              <label htmlFor="job-action" className="form-label">Acción</label>
              <input id="job-action" className="form-control font-monospace" list="job-actions" maxLength={100} placeholder="Cancel"
                value={action} onChange={(e) => setAction(e.target.value)} />
              <datalist id="job-actions">{SUGGESTED_ACTIONS.map((a) => <option key={a} value={a} />)}</datalist>
            </div>
          </div>
          <label htmlFor="job-docs" className="form-label">Documentos (DocEntry)</label>
          <textarea id="job-docs" className="form-control font-monospace" rows={6} placeholder={'1520\n1521\n1522'}
            value={documents} onChange={(e) => setDocuments(e.target.value)} />
          <div className="form-text">
            Uno por línea, o separados por comas o espacios (puedes pegar una columna de Excel). Se llamará a
            {' '}<span className="font-monospace">{entity || 'Entidad'}(DocEntry)/{action || 'Acción'}</span> por cada uno.
          </div>
        </>
      ) : (
        <>
          <div className="mb-3">
            <label htmlFor="job-date" className="form-label">Fecha de conciliación</label>
            <input id="job-date" type="date" className="form-control" value={reconDate} onChange={(e) => setReconDate(e.target.value)} />
          </div>
          <label htmlFor="job-file" className="form-label">Archivo (.xlsx)</label>
          <input id="job-file" type="file" className="form-control" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="form-text">
            Columnas: ReconNum, SrcObjAbs, SrcObjTyp, TransRowId, TransId, ShortName, ReconcileAmount. Cada ReconNum es una
            conciliación y sus montos deben sumar 0 (el signo define débito o crédito).
          </div>
        </>
      )}
      {preview && (
        <div className="alert alert-danger mt-3 mb-0">
          <p className="fw-semibold mb-2">No se creó el trabajo. Corrige y vuelve a intentar:</p>
          <ul className="mb-0 small">
            {preview.errors.map((e, i) => <li key={i}>{e.row ? `Fila ${e.row}: ` : ''}{e.message}</li>)}
          </ul>
        </div>
      )}
    </FormModal>
  )
}
