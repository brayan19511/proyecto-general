import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as paymentsService from '../services/paymentsService'
import type { PaymentSettings } from '../types'
import TemplatePicker from './TemplatePicker'

// Plantilla por defecto de los lotes de la empresa (solo payments.admin).
export default function SettingsModal({ current, onClose, onSaved }: { current: PaymentSettings; onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = useState(current.default_template_code ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await paymentsService.updateSettings(code || null)
      toast.success('Plantilla por defecto guardada')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title="Plantilla de los avisos de pago" submitLabel="Guardar" busy={busy} error={error}
      canSubmit={code !== (current.default_template_code ?? '')} onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Se usa en cada envío de lote de esta empresa. Quien envía no la elige; un administrador puede cambiarla en un envío puntual.
      </p>
      <label htmlFor="set-template" className="form-label">Plantilla por defecto</label>
      <TemplatePicker id="set-template" value={code} onChange={setCode}
        emptyLabel={`La del servicio (${current.service_template_code})`} />
    </FormModal>
  )
}
