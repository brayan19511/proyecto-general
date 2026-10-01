// Configuración leída del entorno de Vite. Falla al arrancar si falta,
// para no llamar en silencio a una URL equivocada.
// - Desarrollo: http://localhost:8001 (la central directa).
// - Docker detrás de caddy: "/" = mismo origen que el front (queda "").
const apiUrl = import.meta.env.VITE_API_URL

if (!apiUrl) {
  throw new Error('Falta VITE_API_URL (ver .env.example).')
}

export const API_URL = apiUrl.replace(/\/+$/, '') // sin "/" final
