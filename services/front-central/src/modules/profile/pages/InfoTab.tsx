import { useState, type FormEvent } from 'react'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import AsyncState from '../../../shared/components/AsyncState'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import type { Profile } from '../../auth/types'
import * as profileService from '../services/profileService'
import type { ProfileUpdate } from '../types'

// Texto vacío del formulario → null (borra el valor en el backend).
const orNull = (value: string) => value.trim() || null

function toForm(profile: Profile | null) {
  return {
    first_names: profile?.first_names ?? '',
    last_names: profile?.last_names ?? '',
    birth_date: profile?.birth_date ?? '',
    nationality_country_code: profile?.nationality_country_code ?? '',
  }
}

export default function InfoTab() {
  const email = useSessionStore((s) => s.me?.email ?? '')
  const setProfile = useSessionStore((s) => s.setProfile)
  const profileQuery = useApi(profileService.getMyProfile)
  const countriesQuery = useApi(profileService.listCountries)

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(toForm(null))
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const profile = profileQuery.data?.profile ?? null
  const countries = countriesQuery.data ?? []
  const countryName = (code: string | null) =>
    countries.find((c) => c.code === code)?.name ?? code ?? '—'

  const startEditing = () => {
    setForm(toForm(profile))
    setFormError(null)
    setEditing(true)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setFormError(null)
    const data: ProfileUpdate = {
      first_names: orNull(form.first_names),
      last_names: orNull(form.last_names),
      birth_date: orNull(form.birth_date),
      nationality_country_code: orNull(form.nationality_country_code),
    }
    try {
      const updated = await profileService.updateMyProfile(data)
      profileQuery.setData({ profile: updated, documents: profileQuery.data?.documents ?? [] })
      setProfile(updated)
      setEditing(false)
      toast.success('Datos actualizados')
    } catch (error) {
      setFormError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const field = (name: keyof typeof form) => ({
    id: name,
    value: form[name],
    onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [name]: e.target.value })),
  })

  return (
    <AsyncState
      loading={profileQuery.loading}
      error={profileQuery.error}
      onRetry={profileQuery.reload}
      hasData={profileQuery.data !== undefined}
    >
      <div className="card" style={{ maxWidth: 640 }}>
        <div className="card-header d-flex align-items-center justify-content-between bg-transparent">
          <span className="fw-semibold">Datos personales</span>
          {!editing && (
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={startEditing}>
              <i className="bi bi-pencil me-1" aria-hidden="true" />
              Editar
            </button>
          )}
        </div>

        <div className="card-body">
          {!editing ? (
            <dl className="row mb-0">
              <dt className="col-sm-4 text-body-secondary fw-normal">Correo</dt>
              <dd className="col-sm-8">{email}</dd>
              <dt className="col-sm-4 text-body-secondary fw-normal">Nombres</dt>
              <dd className="col-sm-8">{profile?.first_names ?? '—'}</dd>
              <dt className="col-sm-4 text-body-secondary fw-normal">Apellidos</dt>
              <dd className="col-sm-8">{profile?.last_names ?? '—'}</dd>
              <dt className="col-sm-4 text-body-secondary fw-normal">Fecha de nacimiento</dt>
              <dd className="col-sm-8">{profile?.birth_date ? formatDate(profile.birth_date) : '—'}</dd>
              <dt className="col-sm-4 text-body-secondary fw-normal">Nacionalidad</dt>
              <dd className="col-sm-8 mb-0">{countryName(profile?.nationality_country_code ?? null)}</dd>
            </dl>
          ) : (
            <form onSubmit={handleSubmit}>
              {formError && <div className="alert alert-danger py-2" role="alert">{formError}</div>}

              <div className="row g-3">
                <div className="col-sm-6">
                  <label htmlFor="first_names" className="form-label">Nombres</label>
                  <input className="form-control" maxLength={100} {...field('first_names')} />
                </div>
                <div className="col-sm-6">
                  <label htmlFor="last_names" className="form-label">Apellidos</label>
                  <input className="form-control" maxLength={100} {...field('last_names')} />
                </div>
                <div className="col-sm-6">
                  <label htmlFor="birth_date" className="form-label">Fecha de nacimiento</label>
                  <input type="date" className="form-control" {...field('birth_date')} />
                </div>
                <div className="col-sm-6">
                  <label htmlFor="nationality_country_code" className="form-label">Nacionalidad</label>
                  <select className="form-select" {...field('nationality_country_code')}>
                    <option value="">Sin especificar</option>
                    {countries.map((c) => (
                      <option key={c.code} value={c.code}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="d-flex justify-content-end gap-2 mt-4">
                <button type="button" className="btn btn-outline-secondary" onClick={() => setEditing(false)} disabled={saving}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
                  Guardar cambios
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </AsyncState>
  )
}
