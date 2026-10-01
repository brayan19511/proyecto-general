type PagerProps = {
  offset: number
  limit: number
  count: number // filas recibidas en esta página
  total?: number // si el servicio lo devuelve
  onChange: (offset: number) => void
}

// Paginación limit/offset. Si el servicio no devuelve el total, hay página
// siguiente mientras llegue una página completa (count === limit).
export default function Pager({ offset, limit, count, total, onChange }: PagerProps) {
  const hasPrevious = offset > 0
  const hasNext = total !== undefined ? offset + count < total : count === limit
  if (!hasPrevious && !hasNext) return null

  const range = count === 0 ? 'Sin resultados' : `${offset + 1}–${offset + count}`
  const numberFormat = new Intl.NumberFormat('es-PE')

  return (
    <div className="d-flex align-items-center justify-content-end gap-2 mt-3">
      <span className="small text-body-secondary">
        {total !== undefined ? `${range} de ${numberFormat.format(total)}` : range}
      </span>
      <button
        type="button"
        className="btn btn-sm btn-outline-secondary"
        onClick={() => onChange(Math.max(0, offset - limit))}
        disabled={!hasPrevious}
        aria-label="Página anterior"
      >
        <i className="bi bi-chevron-left" aria-hidden="true" />
      </button>
      <button
        type="button"
        className="btn btn-sm btn-outline-secondary"
        onClick={() => onChange(offset + limit)}
        disabled={!hasNext}
        aria-label="Página siguiente"
      >
        <i className="bi bi-chevron-right" aria-hidden="true" />
      </button>
    </div>
  )
}
