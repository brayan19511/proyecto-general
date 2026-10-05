import { useState } from 'react'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import Dialog from '../../../shared/components/Dialog'
import { ApiError } from '../../../shared/api/apiClient'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as companiesService from '../services/companiesService'
import type { AdminCompany, SeedItems } from '../types'

type SeedCompanyModalProps = {
  company: AdminCompany
  onClose: () => void
  onDone: () => void // p. ej. refrescar el resumen SAP de la tabla
}

type SeedKey = 'ledger' | 'notifications'

// Qué carga cada servicio y cómo resumir su respuesta en líneas legibles.
const SEEDS: Record<SeedKey, { title: string; description: string; run: (companyId: string) => Promise<string[]> }> = {
  ledger: {
    title: 'Libro mayor',
    description: 'Compañía SAP y cuentas de la empresa.',
    run: async (companyId) => {
      const result = await companiesService.runLedgerSeed(companyId)
      return [`Compañía SAP: ${result.sap_company === 'created' ? 'creada' : 'ya existía'}`, ...summary('Cuentas', result.accounts)]
    },
  },
  notifications: {
    title: 'Notificaciones',
    description: 'Plantillas de correo de la empresa.',
    run: async (companyId) => summary('Plantillas', (await companiesService.runNotificationsSeed(companyId)).templates),
  },
}

function summary(label: string, items: SeedItems): string[] {
  const lines = [`${label}: ${items.created.length} creadas, ${items.existing.length} ya existían`]
  if (items.kept_deactivated.length > 0) {
    lines.push(`Dadas de baja (no se reactivan): ${items.kept_deactivated.join(', ')}`)
  }
  return lines
}

// Con SEED_ENABLED=false el servicio no registra la ruta: 404 genérico de
// FastAPI. Un 404 con otro mensaje es del seed (p. ej. sin datos para la empresa).
function seedError(err: unknown): string {
  if (err instanceof ApiError && err.status === 404 && err.message === 'Not Found') {
    return 'La carga inicial está deshabilitada en el servicio (SEED_ENABLED=false).'
  }
  return errorMessage(err)
}

// Plataforma › Empresas › Carga inicial: ejecuta el seed de cada servicio para
// una empresa, con la sesión del administrador de plataforma. El seed de auth
// (permisos, empresas y primer administrador) no va aquí: usa X-Seed-Token y
// corre antes de que exista alguien que pueda iniciar sesión.
export default function SeedCompanyModal({ company, onClose, onDone }: SeedCompanyModalProps) {
  const [confirm, setConfirm] = useState<SeedKey | null>(null)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<Partial<Record<SeedKey, { ok: boolean; lines: string[] }>>>({})

  const run = async () => {
    if (!confirm) return
    const key = confirm
    setBusy(true)
    try {
      const lines = await SEEDS[key].run(company.id)
      setResults((r) => ({ ...r, [key]: { ok: true, lines } }))
      toast.success(`Carga inicial de ${SEEDS[key].title} ejecutada`)
      onDone()
    } catch (err) {
      // 409: algo choca con lo existente; el servicio no guardó nada.
      setResults((r) => ({ ...r, [key]: { ok: false, lines: [seedError(err)] } }))
    } finally {
      setBusy(false)
      setConfirm(null)
    }
  }

  return (
    <>
      <Dialog open={confirm === null} onClose={onClose} labelledBy="seed-title">
        <div className="card-header bg-transparent">
          <h2 id="seed-title" className="h5 mb-0">Carga inicial de {company.name}</h2>
        </div>
        <div className="card-body">
          <p className="small text-body-secondary">
            Carga los datos predefinidos de cada servicio para esta empresa. Se puede repetir: no duplica, no modifica
            ni reactiva lo existente. Requiere SEED_ENABLED=true en el servicio.
          </p>
          <ul className="list-group">
            {(Object.keys(SEEDS) as SeedKey[]).map((key) => {
              const result = results[key]
              return (
                <li key={key} className="list-group-item">
                  <div className="d-flex justify-content-between align-items-center gap-3">
                    <div>
                      <div className="fw-semibold">{SEEDS[key].title}</div>
                      <div className="small text-body-secondary">{SEEDS[key].description}</div>
                    </div>
                    <button type="button" className="btn btn-sm btn-outline-primary text-nowrap" onClick={() => setConfirm(key)}>
                      Ejecutar
                    </button>
                  </div>
                  {result && (
                    <div className={`small mt-2 ${result.ok ? 'text-success' : 'text-danger'}`} role="status">
                      {result.lines.map((line) => <div key={line}>{line}</div>)}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
        <div className="card-footer bg-transparent d-flex justify-content-end">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </Dialog>

      <ConfirmDialog
        open={confirm !== null}
        title="Ejecutar carga inicial"
        message={confirm ? `¿Ejecutar la carga inicial de ${SEEDS[confirm].title} para ${company.name} (${company.code})?` : ''}
        confirmLabel="Ejecutar"
        busy={busy}
        onConfirm={run}
        onCancel={() => setConfirm(null)}
      />
    </>
  )
}
