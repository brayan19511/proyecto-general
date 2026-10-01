import type { ReactNode } from 'react'

export type Column<T> = {
  header: string
  render: (row: T) => ReactNode
  className?: string // p. ej. "text-end" o "text-nowrap"
}

type DataTableProps<T> = {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  emptyMessage?: string
}

// Tabla de solo presentación: las columnas dicen qué mostrar de cada fila.
// Carga y errores los resuelve AsyncState alrededor; paginación, Pager debajo.
export default function DataTable<T>({ columns, rows, rowKey, emptyMessage = 'No hay registros.' }: DataTableProps<T>) {
  return (
    <div className="table-responsive border rounded-3">
      <table className="table table-hover align-middle mb-0">
        <thead className="table-light">
          <tr>
            {columns.map((c) => (
              <th key={c.header} className={`text-nowrap ${c.className ?? ''}`}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="text-center text-body-secondary py-4">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((c) => (
                  <td key={c.header} className={c.className}>{c.render(row)}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
