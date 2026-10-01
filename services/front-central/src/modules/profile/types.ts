import type { Profile } from '../auth/types'

// GET /auth/me/profile. Los documentos se verán en una fase siguiente.
export type MyProfile = {
  profile: Profile | null
  documents: unknown[]
}

// PATCH /auth/me/profile: null borra el valor.
export type ProfileUpdate = {
  first_names: string | null
  last_names: string | null
  birth_date: string | null
  nationality_country_code: string | null
}

export type Country = { code: string; name: string }

// GET /auth/me/sessions
export type MySession = {
  id: string
  created_at: string
  expires_at: string
  last_seen_at: string
  initial_ip: string
  last_ip: string
  client_description: string // lo declara el navegador: orientativo
  current: boolean
}
