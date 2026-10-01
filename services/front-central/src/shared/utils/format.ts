const dateTimeFormat = new Intl.DateTimeFormat('es-PE', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

// Fecha y hora local a partir de un instante ISO del backend.
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

// Fecha sin hora ("AAAA-MM-DD"). No se pasa por Date para evitar que la zona
// horaria la corra un día.
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-')
  return `${day}/${month}/${year}`
}

// Fecha local en formato "AAAA-MM-DD" (el de <input type="date"> y de la API).
export function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

// "1 sesión", "3 sesiones".
export function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`
}
