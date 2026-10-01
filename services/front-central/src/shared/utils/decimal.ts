// Importes exactos. libro-mayor guarda Numeric(19, 4) y los envía como texto
// ("-1234.5600"). Para sumarlos sin errores de redondeo de float se trabajan
// como enteros BigInt en diezmilésimos (4 decimales).

const SCALE = 4
const FACTOR = 10n ** BigInt(SCALE)

// "-1234.56" → -12345600n
export function parseAmount(value: string | number | null | undefined): bigint {
  if (value === null || value === undefined || value === '') return 0n
  const text = String(value).trim()
  const negative = text.startsWith('-')
  const [integer, fraction = ''] = text.replace(/^[-+]/, '').split('.')
  const units = BigInt(integer || '0') * FACTOR + BigInt((fraction + '0000').slice(0, SCALE))
  return negative ? -units : units
}

export function absAmount(units: bigint): bigint {
  return units < 0n ? -units : units
}

const integerFormat = new Intl.NumberFormat('es-PE')

// -12345600n → "-1,234.56" (redondeo a 2 decimales, mitad hacia afuera).
export function formatAmount(units: bigint): string {
  const negative = units < 0n
  const cents = (absAmount(units) + 50n) / 100n // de 4 a 2 decimales
  const integer = cents / 100n
  const fraction = String(cents % 100n).padStart(2, '0')
  const text = `${integerFormat.format(integer)}.${fraction}`
  return negative && cents !== 0n ? `-${text}` : text
}
