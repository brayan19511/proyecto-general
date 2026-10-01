import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as gatewayService from '../services/gatewayService'
import type { GatewayService } from '../types'

type ServiceToggleModalProps = {
  service: GatewayService
  onClose: () => void
  onSaved: () => void
}

// Habilitar o deshabilitar un servicio en la central, con un motivo que queda
// en el historial. Deshabilitado: la central responde 503 a sus rutas.
export default function ServiceToggleModal({ service, onClose, onSaved }: ServiceToggleModalProps) {
  const enabling = !service.enabled
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await gatewayService.setServiceEnabled(service.service, enabling, reason.trim() || null)
      toast.success(enabling ? `${service.service} habilitado` : `${service.service} deshabilitado`)
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 solo por configuración
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={`${enabling ? 'Habilitar' : 'Deshabilitar'} ${service.service}`}
      submitLabel={enabling ? 'Habilitar' : 'Deshabilitar'} busy={busy} error={error}
      canSubmit={enabling || reason.trim() !== ''} onSubmit={submit} onClose={onClose}>
      {enabling ? (
        <p>La central vuelve a enviar las solicitudes a <strong>{service.service}</strong>.</p>
      ) : (
        <div className="alert alert-warning">
          La central dejará de enviar solicitudes a <strong>{service.service}</strong>: todas sus pantallas y consultas
          (también las de Excel o Power BI) responderán "servicio deshabilitado" hasta que lo habilites de nuevo. Los
          trabajos del worker no se detienen.
        </div>
      )}
      <label htmlFor="svc-reason" className="form-label">Motivo {enabling ? '(opcional)' : ''}</label>
      <input id="svc-reason" className="form-control" maxLength={300} autoFocus
        placeholder={enabling ? 'Mantenimiento terminado' : 'Mantenimiento de SAP'} value={reason}
        onChange={(e) => setReason(e.target.value)} />
      <div className="form-text">Queda en el historial de la central junto con quién lo hizo.</div>
    </FormModal>
  )
}
