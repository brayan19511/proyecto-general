import { NOTIFICATIONS_ADMIN, useCanAccess } from '../../../shared/auth/access'
import { useApi } from '../../../shared/hooks/useApi'
import * as notificationsService from '../../notifications/services/notificationsService'

type TemplatePickerProps = {
  id: string
  value: string // '' = sin elegir
  emptyLabel: string // texto de la opción vacía
  onChange: (code: string) => void
}

// Plantilla de notificaciones: lista si puede verlas (notifications.admin);
// si no, el código a mano. Lo valida notificaciones al enviar.
export default function TemplatePicker({ id, value, emptyLabel, onChange }: TemplatePickerProps) {
  const can = useCanAccess()
  const canList = can({ anyOf: NOTIFICATIONS_ADMIN })
  const templates = useApi(() => (canList ? notificationsService.listTemplates(false) : Promise.resolve(null)), [canList])

  if (!templates.data) {
    return (
      <input id={id} className="form-control font-monospace" placeholder={emptyLabel} value={value}
        onChange={(e) => onChange(e.target.value.trim())} />
    )
  }
  const known = templates.data.items.some((t) => t.code === value)
  return (
    <select id={id} className="form-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{emptyLabel}</option>
      {value && !known && <option value={value}>{value} (no está entre las activas)</option>}
      {templates.data.items.map((t) => <option key={t.id} value={t.code}>{t.name} ({t.code})</option>)}
    </select>
  )
}
