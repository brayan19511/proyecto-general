// Configuración leída del entorno de Vite. Falla al arrancar si falta,
// para no llamar en silencio a una URL equivocada.
const apiUrl = import.meta.env.VITE_API_URL

if (!apiUrl) {
  throw new Error('Falta VITE_API_URL (ver .env.example).')
}

export const API_URL = apiUrl.replace(/\/+$/, '') // sin "/" final
