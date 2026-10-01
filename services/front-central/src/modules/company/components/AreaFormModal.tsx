import * as orgService from '../services/orgService'
import type { Area } from '../types'
import CodeNameFormModal from './CodeNameFormModal'

type AreaFormModalProps = {
  area: Area | null // null = nueva
  onClose: () => void
  onSaved: (area: Area) => void
}

// Crear un área (código + nombre) o renombrarla (el código no cambia).
export default function AreaFormModal({ area, onClose, onSaved }: AreaFormModalProps) {
  return (
    <CodeNameFormModal
      title={area ? `Renombrar ${area.code}` : 'Nueva área'}
      existing={area}
      codePlaceholder="VENTAS"
      namePlaceholder="Ventas"
      save={(code, name) => (area ? orgService.renameArea(area.id, name) : orgService.createArea(code, name))}
      doneMessage={area ? 'Área actualizada' : 'Área creada'}
      onClose={onClose}
      onSaved={onSaved}
    />
  )
}
