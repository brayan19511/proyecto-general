import { useState, type ReactNode } from 'react'
import { formatAmount } from '../../../shared/utils/decimal'
import type { TreeSelection } from '../detailSelection'
import { totalsByMonth, type Month, type TreeNode } from '../summaryTree'

type SummaryTreeProps = {
  months: Month[]
  tree: TreeNode[] // filas visibles (tras el monto mínimo)
  fullTree: TreeNode[] // todas: el pie suma todo, igual que su detalle
  onSelect?: (selection: TreeSelection) => void // sin él, los importes no abren detalle
}

const INDENT_REM = 1.5

// Todas las claves con hijos (para "Desplegar todo").
function expandableKeys(nodes: TreeNode[]): string[] {
  return nodes.flatMap((n) => (n.children.length > 0 ? [n.key, ...expandableKeys(n.children)] : []))
}

// Tabla tipo tablix: Categoría › Subcategoría › Proveedor, un mes por columna y
// total. Clic en el chevron = desplegar; clic en un importe = detalle.
export default function SummaryTree({ months, tree, fullTree, onSelect }: SummaryTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const totals = totalsByMonth(fullTree)
  const allKeys = expandableKeys(tree)
  const allExpanded = allKeys.length > 0 && allKeys.every((k) => expanded.has(k))

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const amountButton = (value: bigint, selection: TreeSelection, title: string) =>
    onSelect ? (
      <button type="button" className="cell-link" onClick={() => onSelect(selection)} title={title}>
        {formatAmount(value)}
      </button>
    ) : (
      formatAmount(value)
    )

  const amountCell = (node: TreeNode, month: Month | null) => {
    const value = month ? node.byMonth.get(month.key) : node.total
    const key = month?.key ?? 'total'
    if (value === undefined) return <td key={key} className="amount text-body-tertiary">—</td>
    return (
      <td key={key} className={`amount ${month ? '' : 'fw-semibold'}`}>
        {amountButton(value, { node, month }, `Ver detalle${month ? ` de ${month.label}` : ''}`)}
      </td>
    )
  }

  // Fila del nodo y, si está desplegado, las de sus hijos.
  const rows = (node: TreeNode): ReactNode[] => {
    const open = expanded.has(node.key)
    const row = (
      <tr key={node.key} className={`level-${node.level}`}>
        <td className="text-nowrap" style={{ paddingLeft: `${0.5 + node.level * INDENT_REM}rem` }}>
          {node.children.length > 0 ? (
            <button
              type="button"
              className="btn btn-sm btn-link p-0 me-1 text-body"
              onClick={() => toggle(node.key)}
              aria-expanded={open}
              aria-label={`${open ? 'Contraer' : 'Desplegar'} ${node.label}`}
            >
              <i className={`bi bi-chevron-${open ? 'down' : 'right'}`} aria-hidden="true" />
            </button>
          ) : (
            <span className="d-inline-block me-1" style={{ width: '1rem' }} />
          )}
          <span className={node.unassigned ? 'fst-italic text-warning-emphasis' : undefined}>{node.label}</span>
          <span className="small text-body-secondary ms-2">({node.lines})</span>
        </td>
        {months.map((m) => amountCell(node, m))}
        {amountCell(node, null)}
      </tr>
    )
    return [row, ...(open ? node.children.flatMap(rows) : [])]
  }

  return (
    <>
      <div className="d-flex justify-content-end mb-2">
        <button
          type="button"
          className="btn btn-sm btn-link"
          onClick={() => setExpanded(allExpanded ? new Set() : new Set(allKeys))}
          disabled={allKeys.length === 0}
        >
          {allExpanded ? 'Contraer todo' : 'Desplegar todo'}
        </button>
      </div>
      <div className="table-responsive border rounded-3">
        <table className="table table-sm table-hover align-middle mb-0 app-tree">
          <thead className="table-light">
            <tr>
              <th style={{ minWidth: 300 }}>Categoría / subcategoría / proveedor</th>
              {months.map((m) => <th key={m.key} className="amount">{m.label}</th>)}
              <th className="amount">Total</th>
            </tr>
          </thead>
          <tbody>{tree.flatMap(rows)}</tbody>
          <tfoot className="table-light">
            <tr>
              <td className="fw-semibold">Total</td>
              {months.map((m) => (
                <td key={m.key} className="amount fw-semibold">
                  {amountButton(totals.byMonth.get(m.key) ?? 0n, { node: null, month: m }, `Ver todo ${m.label}`)}
                </td>
              ))}
              <td className="amount fw-semibold">
                {amountButton(totals.total, { node: null, month: null }, 'Ver todas las líneas')}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  )
}
