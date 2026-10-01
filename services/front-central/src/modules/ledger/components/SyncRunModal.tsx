import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { toIsoDate } from '../../../shared/utils/format'
import * as syncService from '../services/syncService'
import type { SyncStatus } from '../types'

type SyncRunModalProps = {
  accounts: SyncStatus[]
  onClose: () => void
  onCreated: () => void
}

// Por defecto: del primer día del mes hasta hoy.
function defaultForm(accounts: SyncStatus[]) {
  const today = new Date()
  return {
    accountId: accounts[0]?.account_id ?? '',
    dateFrom: toIsoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    dateTo: toIsoDate(today),
  }
}

// Formulario de sincronización manual (ledger.admin). Las reglas del rango
// (máximo de días, sin fechas futuras) las valida libro-mayor y su mensaje se
// muestra tal cual; aquí solo se evita un rango invertido.
// Se monta solo mientras está abierto: cada apertura empieza con valores limpios.
export default function SyncRunModal({ accounts, onClose, onCreated }: SyncRunModalProps) {
  const [form, setForm] = useState(() => defaultForm(accounts))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reversed = form.dateFrom !== '' && form.dateTo !== '' && form.dateFrom > form.dateTo
  const canSubmit = form.accountId !== '' && form.dateFrom !== '' && form.dateTo !== '' && !reversed

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await syncService.createSyncRun(form.accountId, form.dateFrom, form.dateTo)
      toast.success('Sincronización registrada. El proceso la tomará en breve.')
      onCreated()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 ya hay una abierta, 422 rango inválido…
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal
      open
      title="Sincronizar cuenta"
      submitLabel="Sincronizar"
      busy={busy}
      error={error}
      canSubmit={canSubmit}
      onSubmit={submit}
      onClose={onClose}
    >
      <p className="small text-body-secondary">
        Lee de SAP las líneas de la cuenta en el rango de fechas de contabilización y
        actualiza las ya cargadas. No cambia la fecha del próximo delta programado.
      </p>

      <div className="mb-3">
        <label htmlFor="sync-account" className="form-label">Cuenta</label>
        <select
          id="sync-account"
          className="form-select"
          value={form.accountId}
          onChange={(e) => setForm((f) => ({ ...f, accountId: e.target.value }))}
          required
        >
          {accounts.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.code}{a.name ? ` — ${a.name}` : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="row g-3">
        <div className="col-sm-6">
          <label htmlFor="sync-from" className="form-label">Desde</label>
          <input
            id="sync-from"
            type="date"
            className="form-control"
            value={form.dateFrom}
            onChange={(e) => setForm((f) => ({ ...f, dateFrom: e.target.value }))}
            required
          />
        </div>
        <div className="col-sm-6">
          <label htmlFor="sync-to" className="form-label">Hasta</label>
          <input
            id="sync-to"
            type="date"
            className={`form-control ${reversed ? 'is-invalid' : ''}`}
            value={form.dateTo}
            max={toIsoDate(new Date())}
            onChange={(e) => setForm((f) => ({ ...f, dateTo: e.target.value }))}
            aria-describedby="sync-to-help"
            required
          />
          <div id="sync-to-help" className="invalid-feedback">Debe ser igual o posterior a "Desde".</div>
        </div>
      </div>
    </FormModal>
  )
}
