import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { ImportKind, ImportStatus } from './types'

export const KIND_LABEL: Record<ImportKind, string> = {
  sku_full: 'On/off completa',
  sku_partial: 'On/off parcial',
  promotions: 'Promociones',
}

export const KIND_HELP: Record<ImportKind, string> = {
  sku_full: 'El archivo es la lista completa del canal: cada SKU queda on/off según el archivo y los que no estén quedan off. Sin columna on/off, todo lo listado queda on.',
  sku_partial: 'Solo cambian los SKU del archivo (columnas sku y on/off); el resto queda igual.',
  promotions: 'El archivo es la lista completa de SKU con promoción: se quitan las que no estén y se agregan las nuevas. Todos los SKU deben existir en el canal.',
}

export const STATUS: Record<ImportStatus, { label: string; tone: BadgeTone }> = {
  previewed: { label: 'Por aplicar', tone: 'info' },
  invalid: { label: 'Archivo con errores', tone: 'danger' },
  applying: { label: 'Aplicando', tone: 'warning' },
  applied: { label: 'Aplicada', tone: 'success' },
  failed: { label: 'Falló', tone: 'danger' },
  interrupted: { label: 'Interrumpida', tone: 'secondary' },
  cancelled: { label: 'Descartada', tone: 'secondary' },
}

export const ACTION_LABEL: Record<string, string> = {
  'sku.created': 'Creado',
  'sku.activated': 'Activado (on)',
  'sku.deactivated': 'Desactivado (off)',
  'sku.deleted': 'Eliminado',
  'promotion.added': 'Promoción agregada',
  'promotion.removed': 'Promoción quitada',
}
