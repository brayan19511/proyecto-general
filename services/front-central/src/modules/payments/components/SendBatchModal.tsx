import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { PAYMENTS_ADMIN, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as paymentsService from '../services/paymentsService'
import type { Batch } from '../types'
import TemplatePicker from './TemplatePicker'

// Envía un correo por proveedor con sus constancias (lo manda notificaciones).
// La plantilla es la por defecto de la empresa (o la del servicio); solo
// payments.admin puede elegir otra para este envío (lo valida el servicio: 403).
export default function SendBatchModal({ batch, onClose, onSent }: { batch: Batch; onClose: () => void; onSent: () => void }) {
  const can = useCanAccess()
  const canChooseTemplate = can({ anyOf: PAYMENTS_ADMIN })
  const settings = useApi(() => paymentsService.getSettings())
  const [templateCode, setTemplateCode] = useState('')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Reintentar un lote "Enviando" manda lo ya congelado: las opciones se ignoran.
  const retrying = batch.status === 'sending'

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await paymentsService.sendBatch(
        batch.id,
        retrying
          ? {}
          : {
              template_code: canChooseTemplate ? templateCode.trim() || undefined : undefined,
              subject: subject.trim() || undefined,
              message: message.trim() || undefined,
            },
      )
      toast.success('Avisos en cola de envío')
      onSent()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 not_ready; 502 notificaciones no disponible (queda "Enviando": reintentar)
      onSent() // el estado del lote pudo cambiar
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={retrying ? 'Reintentar envío' : 'Enviar avisos de pago'} submitLabel={retrying ? 'Reintentar' : 'Enviar'}
      busy={busy} error={error} canSubmit onSubmit={submit} onClose={onClose}>
      <p>
        Se envía un correo a cada uno de los {batch.counts.groups} proveedores con sus constancias adjuntas.
        {retrying && ' El intento anterior no terminó: se reintenta con el mismo contenido (no se duplica).'}
      </p>
      {!retrying && (
        <>
          <div className="mb-3">
            <label htmlFor="s-template" className="form-label">Plantilla</label>
            {canChooseTemplate ? (
              <TemplatePicker id="s-template" value={templateCode} onChange={setTemplateCode}
                emptyLabel={`La por defecto${settings.data ? ` (${settings.data.effective_template_code})` : ''}`} />
            ) : (
              <div className="form-control-plaintext font-monospace small">{settings.data?.effective_template_code ?? '…'}</div>
            )}
          </div>
          <div className="mb-3">
            <label htmlFor="s-subject" className="form-label">Asunto <span className="text-body-secondary">(opcional)</span></label>
            <input id="s-subject" className="form-control" maxLength={998} placeholder="El de la plantilla" value={subject}
              onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div>
            <label htmlFor="s-message" className="form-label">Mensaje adicional <span className="text-body-secondary">(opcional)</span></label>
            <textarea id="s-message" className="form-control" rows={3} maxLength={5000} value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
        </>
      )}
    </FormModal>
  )
}
