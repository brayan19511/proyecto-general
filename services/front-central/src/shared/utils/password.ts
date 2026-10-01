// Contraseñas temporales que un administrador entrega a mano (alta o
// restablecimiento). Sin caracteres que se confunden al dictarla (0/O, 1/l/I).
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'

export const TEMP_PASSWORD_MIN = 12 // más que el mínimo de auth (3)

export function generatePassword(length = 14) {
  const bytes = crypto.getRandomValues(new Uint32Array(length))
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join('')
}
