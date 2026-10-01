// Códigos de auth (áreas, puestos, roles): mayúsculas, números y _ (schemas/common.py).
export const CODE_PATTERN = /^[A-Z0-9_]{1,50}$/

// Lo que se escribe → código válido: mayúsculas y espacios como _.
export function toCode(text: string) {
  return text.toUpperCase().replace(/\s+/g, '_').replace(/[^A-Z0-9_]/g, '')
}
