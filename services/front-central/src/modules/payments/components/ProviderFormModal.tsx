import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { splitLines } from '../labels'
import * as paymentsService from '../services/paymentsService'
import type { Provider, ProviderInput } from '../types'

type Props = {
  provider: Provider | null // null = nuevo
  initial?: Partial<ProviderInput> // al crear desde un lote: lo leído en la constancia
  onClose: () => void
  onSaved: (provider: Provider) => void
}

// Alta o edición de un proveedor del maestro. Los nombres comerciales sirven
// para reconocerlo en constancias sin RUC; los correos reciben los avisos.
export default function ProviderFormModal({ provider, initial, onClose, onSaved }: Props) {
  const [taxId, setTaxId] = useState(provider?.tax_id ?? initial?.tax_id ?? '')
  const [legalName, setLegalName] = useState(provider?.legal_name ?? initial?.legal_name ?? '')
  const [names, setNames] = useState((provider?.commercial_names ?? initial?.commercial_names ?? []).join('\n'))
  const [emails, setEmails] = useState((provider?.payment_emails ?? initial?.payment_emails ?? []).join('\n'))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const valid = taxId.trim() !== '' && legalName.trim() !== ''

  const submit = async () => {
    setBusy(true)
    setError(null)
    const input: ProviderInput = {
      tax_id: taxId.trim(),
      legal_name: legalName.trim(),
      commercial_names: splitLines(names),
      payment_emails: splitLines(emails),
    }
    try {
      let saved: Provider
      if (provider) {
        const changes: Partial<ProviderInput> = {}
        for (const k of Object.keys(input) as (keyof ProviderInput)[]) {
          if (JSON.stringify(input[k]) !== JSON.stringify(provider[k])) Object.assign(changes, { [k]: input[k] })
        }
        saved = Object.keys(changes).length > 0 ? await paymentsService.updateProvider(provider.id, changes) : provider
      } else {
        saved = await paymentsService.createProvider(input)
      }
      toast.success(provider ? 'Proveedor actualizado' : 'Proveedor registrado')
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 RUC o nombre ya usado por otro activo
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={provider ? `Editar ${provider.legal_name}` : 'Nuevo proveedor'} submitLabel="Guardar" busy={busy}
      error={error} canSubmit={valid} onSubmit={submit} onClose={onClose}>
      <div className="row g-3">
        <div className="col-sm-5">
          <label htmlFor="p-tax" className="form-label">RUC o DNI</label>
          <input id="p-tax" className="form-control font-monospace" maxLength={30} autoFocus value={taxId} onChange={(e) => setTaxId(e.target.value)} />
        </div>
        <div className="col-sm-7">
          <label htmlFor="p-name" className="form-label">Razón social</label>
          <input id="p-name" className="form-control" maxLength={255} value={legalName} onChange={(e) => setLegalName(e.target.value)} />
        </div>
        <div className="col-12">
          <label htmlFor="p-names" className="form-label">Nombres comerciales <span className="text-body-secondary">(uno por línea)</span></label>
          <textarea id="p-names" className="form-control" rows={3} value={names} onChange={(e) => setNames(e.target.value)} />
          <div className="form-text">Cómo puede aparecer el titular en las constancias. Hasta 20.</div>
        </div>
        <div className="col-12">
          <label htmlFor="p-emails" className="form-label">Correos para avisos de pago <span className="text-body-secondary">(uno por línea)</span></label>
          <textarea id="p-emails" className="form-control" rows={3} value={emails} onChange={(e) => setEmails(e.target.value)} />
          <div className="form-text">Sin correo, sus pagos quedan "Sin correo" y el lote no se puede enviar.</div>
        </div>
      </div>
    </FormModal>
  )
}
