import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as gatewayService from '../services/gatewayService'

type IpBlockFormModalProps = {
  onClose: () => void
  onSaved: () => void
}

// Validación básica en el navegador; la central valida de verdad (IPv4/IPv6/CIDR).
const IPV4 = /^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/
const IPV6 = /^[0-9a-fA-F:]+(\/\d{1,3})?$/

// Bloquea una IP o un rango en la central: sus solicitudes reciben 403 antes de
// llegar a cualquier servicio. La central no deja bloquear tu propia IP.
export default function IpBlockFormModal({ onClose, onSaved }: IpBlockFormModalProps) {
  const [network, setNetwork] = useState('')
  const [reason, setReason] = useState('')
  const [expires, setExpires] = useState('') // datetime-local (hora local)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Hora de apertura del formulario: el render debe ser puro (sin Date.now()).
  // La central vuelve a validar que el vencimiento sea futuro.
  const [openedAt] = useState(() => Date.now())

  const cleanNetwork = network.trim()
  const validNetwork = IPV4.test(cleanNetwork) || (cleanNetwork.includes(':') && IPV6.test(cleanNetwork))
  const expiresInPast = expires !== '' && new Date(expires).getTime() <= openedAt

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      // La hora local se envía como instante UTC (con zona), como pide la central.
      await gatewayService.createIpBlock(cleanNetwork, reason.trim() || null, expires ? new Date(expires).toISOString() : null)
      toast.success(`${cleanNetwork} bloqueada`)
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 incluye tu IP / ya bloqueado, 422 inválida
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title="Bloquear IP o rango" submitLabel="Bloquear" busy={busy} error={error}
      canSubmit={validNetwork && !expiresInPast} onSubmit={submit} onClose={onClose}>
      <div className="mb-3">
        <label htmlFor="ip-network" className="form-label">IP o rango (CIDR)</label>
        <input id="ip-network" className={`form-control font-monospace ${cleanNetwork && !validNetwork ? 'is-invalid' : ''}`}
          placeholder="203.0.113.7 o 203.0.113.0/24" autoFocus value={network} onChange={(e) => setNetwork(e.target.value)}
          aria-describedby="ip-network-help" />
        <div id="ip-network-help" className="form-text">Un rango /24 bloquea 256 direcciones. Revisa que no incluya la red de la oficina.</div>
      </div>
      <div className="mb-3">
        <label htmlFor="ip-reason" className="form-label">Motivo</label>
        <input id="ip-reason" className="form-control" maxLength={300} placeholder="Intentos de login repetidos"
          value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <label htmlFor="ip-expires" className="form-label">Vence (opcional)</label>
      <input id="ip-expires" type="datetime-local" className={`form-control ${expiresInPast ? 'is-invalid' : ''}`}
        value={expires} onChange={(e) => setExpires(e.target.value)} aria-describedby="ip-expires-help" />
      <div id="ip-expires-help" className={expiresInPast ? 'invalid-feedback d-block' : 'form-text'}>
        {expiresInPast ? 'Debe ser una fecha futura.' : 'Vacío = sin vencimiento: queda bloqueada hasta que la desbloquees.'}
      </div>
    </FormModal>
  )
}
