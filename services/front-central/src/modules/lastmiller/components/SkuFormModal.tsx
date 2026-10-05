import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import type { Channel } from '../channels'
import * as lastmillerService from '../services/lastmillerService'

// Alta de un SKU. El id externo (id de Rappi/PedidosYa) hoy es el mismo sku
// (acuerdo 2026-10-04): se muestra sin poder editarlo y copia lo que se escribe.
export default function SkuFormModal({ channel, onClose, onSaved }: { channel: Channel; onClose: () => void; onSaved: () => void }) {
  const [sku, setSku] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const value = sku.trim()

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await lastmillerService.createSku(channel, value, isActive)
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 si ya existe
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={`Nuevo SKU en ${channel.name}`} submitLabel="Crear" busy={busy} error={error}
      canSubmit={value.length > 0} onSubmit={submit} onClose={onClose}>
      <div className="mb-3">
        <label htmlFor="sku-code" className="form-label">SKU</label>
        <input id="sku-code" className="form-control font-monospace" maxLength={255} autoFocus required
          value={sku} onChange={(e) => setSku(e.target.value)} />
      </div>
      <div className="mb-3">
        <label htmlFor="sku-external" className="form-label">ID en {channel.provider === 'peya' ? 'PedidosYa' : 'Rappi'}</label>
        <input id="sku-external" className="form-control font-monospace" value={value} readOnly disabled />
        <div className="form-text">Por ahora es el mismo SKU.</div>
      </div>
      <div className="form-check form-switch">
        <input id="sku-active" type="checkbox" className="form-check-input" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
        <label htmlFor="sku-active" className="form-check-label">Activo (on)</label>
      </div>
    </FormModal>
  )
}
