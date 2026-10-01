import { absAmount, parseAmount } from '../../shared/utils/decimal'
import type { LedgerLine, NodeFilters, SummaryRow } from './types'

// Arma el árbol tipo tablix a partir de /ledger/summary?by_supplier=true:
//   filas    = Categoría › Subcategoría › Proveedor
//              (las líneas sin regla: "Sin categoría asignada" › Proveedor)
//   columnas = meses del rango, más el total
// Cada nodo lleva los filtros exactos de sus líneas: ninguna línea queda fuera
// ni se mezcla con otra rama. Importes como BigInt (shared/utils/decimal.ts).

export type AmountField = 'amount_local' | 'amount_foreign'

export type Month = { key: string; year: number; month: number; label: string }

export type TreeNode = {
  key: string
  level: number // 0, 1 o 2 (sangría)
  label: string
  unassigned: boolean // "Sin … asignado": se muestra en cursiva y al final
  filters: NodeFilters // para pedir el detalle de este nodo
  byMonth: Map<string, bigint> // clave "AAAA-MM"
  total: bigint
  lines: number
  children: TreeNode[]
}

const MONTH_NAMES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic']
export const NO_CATEGORY = 'Sin categoría asignada'
export const NO_SUBCATEGORY = 'Sin subcategoría asignada'
export const NO_SUPPLIER = 'Sin proveedor asignado'

export const monthKey = (year: number, month: number) => `${year}-${String(month).padStart(2, '0')}`
export const monthLabel = (year: number, month: number) => `${MONTH_NAMES[month - 1]}-${year}`

// Hijo con esa clave dentro de `children`, o uno nuevo.
function childOf(children: TreeNode[], key: string, make: () => Omit<TreeNode, 'byMonth' | 'total' | 'lines' | 'children'>) {
  let node = children.find((c) => c.key === key)
  if (!node) {
    node = { ...make(), byMonth: new Map(), total: 0n, lines: 0, children: [] }
    children.push(node)
  }
  return node
}

function add(node: TreeNode, month: string, amount: bigint, lines: number) {
  node.byMonth.set(month, (node.byMonth.get(month) ?? 0n) + amount)
  node.total += amount
  node.lines += lines
}

// Alfabético, con los "sin asignar" al final.
function sortTree(nodes: TreeNode[]) {
  nodes.sort((a, b) => Number(a.unassigned) - Number(b.unassigned) || a.label.localeCompare(b.label, 'es'))
  nodes.forEach((n) => sortTree(n.children))
}

export function buildSummaryTree(rows: SummaryRow[], field: AmountField) {
  const months = new Map<string, Month>()
  const roots: TreeNode[] = []

  for (const row of rows) {
    const mk = monthKey(row.year, row.month)
    if (!months.has(mk)) months.set(mk, { key: mk, year: row.year, month: row.month, label: monthLabel(row.year, row.month) })
    const amount = parseAmount(row[field])
    // Sin campo supplier (resumen sin by_supplier): el árbol llega hasta subcategoría.
    const bySupplier = row.supplier !== undefined
    const supplier = row.supplier && row.supplier.trim() ? row.supplier : null

    const path: TreeNode[] = []
    if (row.codigo === null) {
      // Sin regla: Sin categoría asignada › Proveedor.
      const root = childOf(roots, '∅', () => ({
        key: '∅', level: 0, label: NO_CATEGORY, unassigned: true, filters: { unclassified: true },
      }))
      path.push(root)
      if (bySupplier) path.push(supplierNode(root, { unclassified: true }, supplier, 1))
    } else {
      const codigo = row.codigo
      const root = childOf(roots, `c:${codigo}`, () => ({
        key: `c:${codigo}`, level: 0, label: codigo, unassigned: false, filters: { codigo },
      }))
      const subFilters: NodeFilters = row.subcodigo === null
        ? { codigo, noSubcodigo: true }
        : { codigo, subcodigo: row.subcodigo }
      const sub = childOf(root.children, `${root.key}›${row.subcodigo ?? '∅'}`, () => ({
        key: `${root.key}›${row.subcodigo ?? '∅'}`,
        level: 1,
        label: row.subcodigo ?? NO_SUBCATEGORY,
        unassigned: row.subcodigo === null,
        filters: subFilters,
      }))
      path.push(root, sub)
      if (bySupplier) path.push(supplierNode(sub, subFilters, supplier, 2))
    }
    path.forEach((node) => add(node, mk, amount, row.lines))
  }

  sortTree(roots)
  return { months: [...months.values()].sort((a, b) => a.key.localeCompare(b.key)), tree: roots }
}

function supplierNode(parent: TreeNode, parentFilters: NodeFilters, supplier: string | null, level: number) {
  const key = `${parent.key}›p:${supplier ?? '∅'}`
  return childOf(parent.children, key, () => ({
    key,
    level,
    label: supplier ?? NO_SUPPLIER,
    unassigned: supplier === null,
    filters: supplier === null ? { ...parentFilters, noSupplier: true } : { ...parentFilters, supplier },
  }))
}

// Líneas (consulta en vivo) → filas de resumen con proveedor, una por línea:
// buildSummaryTree las acumula igual que el resumen del servidor.
export function linesToRows(lines: LedgerLine[]): SummaryRow[] {
  return lines.map((l) => {
    const [year, month] = l.posting_date.split('-').map(Number)
    return {
      year, month, codigo: l.codigo, subcodigo: l.subcodigo, supplier: l.supplier,
      lines: 1, amount_local: l.amount_local, amount_foreign: l.amount_foreign,
    }
  })
}

// Omite los nodos cuyo total absoluto sea menor que el mínimo, en cualquier nivel.
export function filterByMinAmount(tree: TreeNode[], min: bigint): TreeNode[] {
  if (min <= 0n) return tree
  return tree
    .filter((node) => absAmount(node.total) >= min)
    .map((node) => ({ ...node, children: filterByMinAmount(node.children, min) }))
}

// Total general por mes (suma de las raíces visibles).
export function totalsByMonth(tree: TreeNode[]) {
  const byMonth = new Map<string, bigint>()
  let total = 0n
  for (const node of tree) {
    node.byMonth.forEach((value, key) => byMonth.set(key, (byMonth.get(key) ?? 0n) + value))
    total += node.total
  }
  return { byMonth, total }
}
