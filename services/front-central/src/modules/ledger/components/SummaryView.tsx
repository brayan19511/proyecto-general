import { useState } from 'react'
import EmptyState from '../../../shared/components/EmptyState'
import { parseAmount } from '../../../shared/utils/decimal'
import type { TreeSelection } from '../detailSelection'
import { buildSummaryTree, filterByMinAmount, type AmountField } from '../summaryTree'
import type { SummaryRow } from '../types'
import SummaryTree from './SummaryTree'

type SummaryViewProps = {
  rows: SummaryRow[]
  onSelect?: (selection: TreeSelection) => void
}

// Opciones de presentación (moneda, monto mínimo) + árbol. Se aplican en el
// navegador: no vuelven a consultar. Compartido por Libro mayor y Consulta en SAP.
export default function SummaryView({ rows, onSelect }: SummaryViewProps) {
  const [amountField, setAmountField] = useState<AmountField>('amount_local')
  const [minAmount, setMinAmount] = useState('')

  const { months, tree } = buildSummaryTree(rows, amountField)
  const minUnits = /^\d+(\.\d+)?$/.test(minAmount.trim()) ? parseAmount(minAmount.trim()) : 0n
  const visibleTree = filterByMinAmount(tree, minUnits)

  return (
    <>
      <div className="d-flex flex-wrap align-items-end gap-3 mb-3">
        <div>
          <label htmlFor="amount-field" className="form-label small mb-1">Importe</label>
          <select id="amount-field" className="form-select form-select-sm" value={amountField}
            onChange={(e) => setAmountField(e.target.value as AmountField)}>
            <option value="amount_local">Moneda local</option>
            <option value="amount_foreign">Moneda extranjera</option>
          </select>
        </div>
        <div>
          <label htmlFor="min-amount" className="form-label small mb-1">Omitir menores a</label>
          <input id="min-amount" className="form-control form-control-sm" inputMode="decimal" placeholder="0.00"
            style={{ width: 140 }} value={minAmount} onChange={(e) => setMinAmount(e.target.value)}
            aria-describedby="min-amount-help" />
        </div>
        <div id="min-amount-help" className="form-text mb-1">
          Oculta filas cuyo total (en valor absoluto) sea menor al monto. El total del pie siempre incluye todo.
        </div>
      </div>

      {tree.length === 0 ? (
        <EmptyState icon="journal-x" title="No hay líneas en este rango" description="Prueba con otras fechas o cuentas." />
      ) : visibleTree.length === 0 ? (
        <EmptyState icon="funnel" title="Ninguna fila supera el monto mínimo" description="Baja el monto de “Omitir menores a”." />
      ) : (
        <SummaryTree months={months} tree={visibleTree} fullTree={tree} onSelect={onSelect} />
      )}
    </>
  )
}
