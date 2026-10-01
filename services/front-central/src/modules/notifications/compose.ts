// Ayudas de los formularios de correo (fuera del .tsx por react-refresh).

// "a@x.com, b@x.com; c@x.com" → lista sin vacíos. El formato lo valida notificaciones.
export function parseAddresses(text: string): string[] {
  return text.split(/[,;\s]+/).map((a) => a.trim()).filter(Boolean)
}

// JSON de parámetros de plantilla; null si no es un objeto válido.
export function parseParameters(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text.trim() || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
  } catch {
    return null
  }
}
