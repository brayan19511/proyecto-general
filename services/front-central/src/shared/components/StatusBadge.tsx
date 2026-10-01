export type BadgeTone = 'success' | 'danger' | 'warning' | 'info' | 'secondary'

// Badge de estado con los colores comunes de la app:
// verde correcto, rojo error, ámbar advertencia, azul en curso, gris neutro.
export default function StatusBadge({ tone, label }: { tone: BadgeTone; label: string }) {
  return (
    <span className={`badge bg-${tone}-subtle text-${tone}-emphasis border border-${tone}-subtle`}>
      {label}
    </span>
  )
}
