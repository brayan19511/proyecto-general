import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { parseAddresses } from '../compose'
import * as notificationsService from '../services/notificationsService'
import type { Template, TemplateInput } from '../types'

type Props = { template: Template | null; onClose: () => void; onSaved: () => void }

const CODE = /^[a-z0-9][a-z0-9_.-]{0,99}$/

// Alta o edición de una plantilla. Asunto y cuerpos usan {{ parametro }}; los
// destinatarios fijos se suman a los de cada mensaje.
export default function TemplateFormModal({ template, onClose, onSaved }: Props) {
  const [code, setCode] = useState(template?.code ?? '')
  const [name, setName] = useState(template?.name ?? '')
  const [description, setDescription] = useState(template?.description ?? '')
  const [subject, setSubject] = useState(template?.subject_template ?? '')
  const [html, setHtml] = useState(template?.body_html_template ?? '')
  const [text, setText] = useState(template?.body_text_template ?? '')
  const [to, setTo] = useState(template?.to.join(', ') ?? '')
  const [cc, setCc] = useState(template?.cc.join(', ') ?? '')
  const [bcc, setBcc] = useState(template?.bcc.join(', ') ?? '')
  const [replyTo, setReplyTo] = useState(template?.reply_to ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const valid = CODE.test(code) && name.trim() !== '' && subject.trim() !== '' && (html.trim() !== '' || text.trim() !== '')

  const submit = async () => {
    setBusy(true)
    setError(null)
    const input: TemplateInput = {
      code,
      name: name.trim(),
      description: description.trim() || null,
      subject_template: subject.trim(),
      body_html_template: html.trim() ? html : null,
      body_text_template: text.trim() ? text : null,
      to: parseAddresses(to),
      cc: parseAddresses(cc),
      bcc: parseAddresses(bcc),
      reply_to: replyTo.trim() || null,
    }
    try {
      if (template) {
        const changes: Partial<TemplateInput> = {}
        for (const k of Object.keys(input) as (keyof TemplateInput)[]) {
          if (JSON.stringify(input[k]) !== JSON.stringify(template[k])) Object.assign(changes, { [k]: input[k] })
        }
        await notificationsService.updateTemplate(template.id, changes)
      } else {
        await notificationsService.createTemplate(input)
      }
      toast.success(template ? 'Plantilla actualizada' : 'Plantilla creada')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 código repetido, 422 sintaxis de plantilla
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={template ? `Editar ${template.code}` : 'Nueva plantilla'} submitLabel="Guardar" busy={busy}
      error={error} canSubmit={valid} onSubmit={submit} onClose={onClose}>
      <div className="row g-3">
        <div className="col-sm-5">
          <label htmlFor="t-code" className="form-label">Código</label>
          <input id="t-code" className={`form-control font-monospace ${code && !CODE.test(code) ? 'is-invalid' : ''}`} maxLength={100}
            placeholder="payment_provider_summary" value={code} onChange={(e) => setCode(e.target.value.toLowerCase())} />
          <div className="form-text">Minúsculas, dígitos, punto, guion o guion bajo. Lo usan los servicios.</div>
        </div>
        <div className="col-sm-7">
          <label htmlFor="t-name" className="form-label">Nombre</label>
          <input id="t-name" className="form-control" maxLength={150} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="col-12">
          <label htmlFor="t-desc" className="form-label">Descripción <span className="text-body-secondary">(opcional)</span></label>
          <input id="t-desc" className="form-control" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="col-12">
          <label htmlFor="t-subject" className="form-label">Asunto</label>
          <input id="t-subject" className="form-control" maxLength={998} placeholder="CONSTANCIA DE PAGO {{ proveedor }}" value={subject}
            onChange={(e) => setSubject(e.target.value)} />
        </div>
        <div className="col-12">
          <label htmlFor="t-html" className="form-label">Cuerpo HTML</label>
          <textarea id="t-html" className="form-control font-monospace small" rows={8} value={html} onChange={(e) => setHtml(e.target.value)} />
        </div>
        <div className="col-12">
          <label htmlFor="t-text" className="form-label">Cuerpo de texto <span className="text-body-secondary">(para clientes sin HTML)</span></label>
          <textarea id="t-text" className="form-control font-monospace small" rows={4} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="form-text">Al menos uno de los dos cuerpos.</div>
        </div>
        <div className="col-sm-6">
          <label htmlFor="t-to" className="form-label">Para fijo <span className="text-body-secondary">(opcional)</span></label>
          <input id="t-to" className="form-control" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="t-reply" className="form-label">Responder a <span className="text-body-secondary">(opcional)</span></label>
          <input id="t-reply" className="form-control" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="t-cc" className="form-label">CC fijo</label>
          <input id="t-cc" className="form-control" value={cc} onChange={(e) => setCc(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="t-bcc" className="form-label">CCO fijo</label>
          <input id="t-bcc" className="form-control" value={bcc} onChange={(e) => setBcc(e.target.value)} />
        </div>
      </div>
    </FormModal>
  )
}
