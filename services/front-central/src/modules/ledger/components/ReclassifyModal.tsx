import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as rulesService from '../services/rulesService'

type ReclassifyModalProps = {
  onClose: () => void
  onCreated: () => void
}

// Reclasificación manual (ledger.update): vuelve a aplicar las reglas activas a
// las líneas ya sincronizadas. Sin fechas, a todas las de la empresa.
export default function ReclassifyModal({ onClose, onCreated }: ReclassifyModalProps) {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Las dos fechas o ninguna.
  const partial = (dateFrom === '') !== (dateTo === '')
  const reversed = dateFrom !== '' && dateTo !== '' && dateFrom > dateTo

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await rulesService.createClassificationRun(dateFrom || null, dateTo || null)
      toast.success('Reclasificación registrada. El proceso la tomará en breve.')
      onCreated()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title="Reclasificar líneas" submitLabel="Reclasificar" busy={busy} error={error}
      canSubmit={!partial && !reversed} onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Aplica otra vez las reglas activas a las líneas sincronizadas. Los cambios de reglas ya lo hacen solos; úsalo
        si necesitas forzarlo. Deja las fechas vacías para todas las líneas de la empresa.
      </p>
      <div className="row g-3">
        <div className="col-sm-6">
          <label htmlFor="rc-from" className="form-label">Desde</label>
          <input id="rc-from" type="date" className="form-control" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="rc-to" className="form-label">Hasta</label>
          <input id="rc-to" type="date" className={`form-control ${reversed ? 'is-invalid' : ''}`} value={dateTo}
            onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>
      {partial && <div className="form-text">Completa las dos fechas o déjalas vacías.</div>}
    </FormModal>
  )
}
