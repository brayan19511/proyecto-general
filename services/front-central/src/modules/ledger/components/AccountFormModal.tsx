import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as accountsService from '../services/accountsService'
import type { Account } from '../types'

type AccountFormModalProps = {
  account: Account | null // null = nueva
  onClose: () => void
  onSaved: () => void
}

const CODE = /^\d{1,20}$/ // libro-mayor: solo dígitos, hasta 20

// Alta o edición de una cuenta a sincronizar desde SAP.
export default function AccountFormModal({ account, onClose, onSaved }: AccountFormModalProps) {
  const [code, setCode] = useState(account?.code ?? '')
  const [mode, setMode] = useState<'exact' | 'prefix'>(account?.match_mode ?? 'exact')
  const [name, setName] = useState(account?.name ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const validCode = CODE.test(code)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const cleanName = name.trim() || null
      if (account) {
        // Solo lo que cambió: código y modo exigen que la cuenta no tenga líneas.
        const changes: Parameters<typeof accountsService.updateAccount>[1] = {}
        if (code !== account.code) changes.code = code
        if (mode !== account.match_mode) changes.match_mode = mode
        if (cleanName !== account.name) changes.name = cleanName
        if (Object.keys(changes).length > 0) await accountsService.updateAccount(account.id, changes)
      } else {
        await accountsService.createAccount(code, mode, cleanName)
      }
      toast.success(account ? 'Cuenta actualizada' : 'Cuenta registrada. Se incluirá en la próxima sincronización.')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 superposición, sin compañía SAP o ya tiene líneas
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={account ? `Editar cuenta ${account.code}` : 'Nueva cuenta'} submitLabel="Guardar" busy={busy}
      error={error} canSubmit={validCode} onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Las líneas de estas cuentas se traen de SAP en cada sincronización y se clasifican con las reglas.
      </p>
      <div className="row g-3">
        <div className="col-sm-6">
          <label htmlFor="acc-code" className="form-label">Código</label>
          <input id="acc-code" className={`form-control font-monospace ${code && !validCode ? 'is-invalid' : ''}`} inputMode="numeric"
            maxLength={20} placeholder="959005993" autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="acc-mode" className="form-label">Coincidencia</label>
          <select id="acc-mode" className="form-select" value={mode} onChange={(e) => setMode(e.target.value as 'exact' | 'prefix')}>
            <option value="exact">Cuenta exacta</option>
            <option value="prefix">Empieza con (prefijo)</option>
          </select>
        </div>
        {mode === 'prefix' && code && (
          <div className="col-12 form-text mt-1">Incluye todas las cuentas de SAP que empiezan con {code} (p. ej. {code}0001…).</div>
        )}
        <div className="col-12">
          <label htmlFor="acc-name" className="form-label">Nombre</label>
          <input id="acc-name" className="form-control" maxLength={150} placeholder="UTILES DE ESCRITORIO" value={name}
            onChange={(e) => setName(e.target.value)} />
        </div>
      </div>
      {account && (
        <div className="form-text mt-3">
          El código y la coincidencia solo se pueden cambiar si la cuenta aún no tiene líneas sincronizadas; si ya tiene,
          da de baja esta y registra otra.
        </div>
      )}
    </FormModal>
  )
}
