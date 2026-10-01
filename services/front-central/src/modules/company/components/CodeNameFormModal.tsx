import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { CODE_PATTERN, toCode } from '../codes'

type CodeNameFormModalProps<T> = {
  title: string
  // null = crear (pide código); con valor = renombrar (el código no cambia).
  existing: { code: string; name: string } | null
  codePlaceholder: string
  namePlaceholder: string
  save: (code: string, name: string) => Promise<T>
  doneMessage: string
  onClose: () => void
  onSaved: (saved: T) => void
}

// Formulario común de áreas y roles de auth: código estable + nombre.
export default function CodeNameFormModal<T>({
  title,
  existing,
  codePlaceholder,
  namePlaceholder,
  save,
  doneMessage,
  onClose,
  onSaved,
}: CodeNameFormModalProps<T>) {
  const [code, setCode] = useState(existing?.code ?? '')
  const [name, setName] = useState(existing?.name ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const validCode = existing !== null || CODE_PATTERN.test(code)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const saved = await save(code, name.trim())
      toast.success(doneMessage)
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 código repetido
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={title} submitLabel="Guardar" busy={busy} error={error}
      canSubmit={validCode && name.trim() !== ''} onSubmit={submit} onClose={onClose}>
      {!existing && (
        <div className="mb-3">
          <label htmlFor="cn-code" className="form-label">Código</label>
          <input id="cn-code" className={`form-control font-monospace ${code && !validCode ? 'is-invalid' : ''}`}
            maxLength={50} placeholder={codePlaceholder} autoFocus value={code} onChange={(e) => setCode(toCode(e.target.value))}
            aria-describedby="cn-code-help" />
          <div id="cn-code-help" className="form-text">Mayúsculas, números y _. Único en la empresa; no se cambia después.</div>
        </div>
      )}
      <label htmlFor="cn-name" className="form-label">Nombre</label>
      <input id="cn-name" className="form-control" maxLength={150} placeholder={namePlaceholder} autoFocus={existing !== null}
        value={name} onChange={(e) => setName(e.target.value)} />
    </FormModal>
  )
}
