import { useApi } from '../../../shared/hooks/useApi'
import * as sapService from '../services/sapService'

// Base SAP (CompanyDB): se elige de la lista de la empresa o se escribe otra
// (decisión 2026-10-04). sap-operaciones valida el formato.
export default function CompanyDbField({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  const databases = useApi(() => sapService.listDatabases())
  return (
    <>
      <label htmlFor={id} className="form-label">Base SAP (CompanyDB)</label>
      <input id={id} className="form-control font-monospace" list={`${id}-list`} maxLength={100} required autoComplete="off"
        placeholder="SBO_EMPRESA" value={value} onChange={(e) => onChange(e.target.value)} />
      <datalist id={`${id}-list`}>
        {(databases.data ?? []).map((d) => <option key={d.id} value={d.company_db}>{d.label ?? ''}</option>)}
      </datalist>
      <div className="form-text">Elige una de la lista de la empresa o escribe otra (letras, números y _).</div>
    </>
  )
}
