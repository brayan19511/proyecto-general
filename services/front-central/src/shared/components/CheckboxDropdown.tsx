type Option = { key: string; label: string }

type CheckboxDropdownProps = {
  label: string // texto del botón; se agrega la cantidad elegida
  icon?: string
  options: Option[]
  selected: string[]
  onChange: (selected: string[]) => void
  emptyText?: string // qué significa no elegir nada (p. ej. "Todas")
  align?: 'start' | 'end'
}

// Menú de casillas (selección múltiple). Usa <details> nativo: abre y cierra
// sin JavaScript de Bootstrap. Devuelve la selección en el orden de `options`.
export default function CheckboxDropdown({
  label,
  icon,
  options,
  selected,
  onChange,
  emptyText,
  align = 'end',
}: CheckboxDropdownProps) {
  const toggle = (key: string) => {
    const next = selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]
    onChange(options.map((o) => o.key).filter((k) => next.includes(k)))
  }

  const summary = selected.length === 0 && emptyText ? emptyText : String(selected.length)

  return (
    <details className="app-dropdown">
      <summary className="btn btn-sm btn-outline-secondary text-nowrap">
        {icon && <i className={`bi bi-${icon} me-1`} aria-hidden="true" />}
        {label} ({summary})
      </summary>
      <div className={`app-dropdown-menu app-dropdown-${align} border rounded-3 shadow-sm p-2`}>
        <div className="d-flex gap-3 mb-2">
          <button type="button" className="btn btn-sm btn-link p-0" onClick={() => onChange(options.map((o) => o.key))}>
            Todas
          </button>
          <button type="button" className="btn btn-sm btn-link p-0" onClick={() => onChange([])}>
            Ninguna
          </button>
        </div>
        {options.length === 0 && <div className="small text-body-secondary">Sin opciones</div>}
        {options.map((o) => (
          <div key={o.key} className="form-check">
            <input
              id={`dd-${label}-${o.key}`}
              type="checkbox"
              className="form-check-input"
              checked={selected.includes(o.key)}
              onChange={() => toggle(o.key)}
            />
            <label htmlFor={`dd-${label}-${o.key}`} className="form-check-label text-nowrap">{o.label}</label>
          </div>
        ))}
      </div>
    </details>
  )
}
