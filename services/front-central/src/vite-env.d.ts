/// <reference types="vite/client" />

// Variables de entorno que usa el front (ver .env.example).
interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
