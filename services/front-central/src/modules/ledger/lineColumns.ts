import { formatAmount, parseAmount } from '../../shared/utils/decimal'
import { formatDate } from '../../shared/utils/format'
import type { LedgerLine } from './types'

// Columnas del detalle de líneas. `show` da el texto en pantalla; en la
// descarga se usa el valor crudo (importes con punto y signo, fechas ISO)
// para que Excel o Power BI no pierdan precisión.
export type LineColumn = {
  key: keyof LedgerLine
  label: string
  amount?: boolean // alinear a la derecha y formatear
  date?: boolean
  default?: boolean // visible si el usuario aún no eligió
}

export const LINE_COLUMNS: LineColumn[] = [
  { key: 'posting_date', label: 'Fecha contable', date: true, default: true },
  { key: 'document_date', label: 'Fecha documento', date: true },
  { key: 'sap_transaction_id', label: 'N.º transacción', default: true },
  { key: 'sap_line', label: 'Línea' },
  { key: 'document_number', label: 'N.º documento' },
  { key: 'transaction_type', label: 'Tipo transacción' },
  { key: 'document_type', label: 'Tipo documento' },
  { key: 'folio', label: 'Folio' },
  { key: 'account_code', label: 'Cuenta', default: true },
  { key: 'account_name', label: 'Nombre cuenta SAP' },
  { key: 'nombre_cuenta', label: 'Nombre de cuenta' }, // el de la regla o, si no tiene, el de la cuenta SAP
  { key: 'codigo', label: 'Categoría', default: true },
  { key: 'subcodigo', label: 'Subcategoría', default: true },
  { key: 'supplier', label: 'Proveedor', default: true },
  { key: 'description', label: 'Glosa', default: true },
  { key: 'line_comment', label: 'Comentario' },
  { key: 'counter_account_code', label: 'Contracuenta' },
  { key: 'counter_account_name', label: 'Nombre contracuenta' },
  { key: 'reference_1', label: 'Referencia 1' },
  { key: 'reference_2', label: 'Referencia 2' },
  { key: 'reference_3', label: 'Referencia 3' },
  { key: 'cost_center_code', label: 'Centro de costo', default: true },
  { key: 'cost_center_name', label: 'Nombre centro de costo' },
  { key: 'cost_center_area', label: 'Área SAP' },
  { key: 'area_name', label: 'Área homologada' },
  { key: 'amount_local', label: 'Importe local', amount: true, default: true },
  { key: 'amount_foreign', label: 'Importe extranjero', amount: true },
  { key: 'sap_created_at', label: 'Creado en SAP' },
  { key: 'sap_updated_at', label: 'Actualizado en SAP' },
]

export const DEFAULT_COLUMN_KEYS = LINE_COLUMNS.filter((c) => c.default).map((c) => c.key as string)

export function showValue(column: LineColumn, line: LedgerLine): string {
  const value = line[column.key]
  if (value === null || value === undefined || value === '') return '—'
  if (column.amount) return formatAmount(parseAmount(value as string))
  if (column.date) return formatDate(String(value))
  return String(value)
}
