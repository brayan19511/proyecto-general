import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import { describePermission } from '../../company/permissionCatalog'
import { API_KEYS_MAX, API_KEY_SERVICES, keyStatus, listMyApiKeys, revokeApiKey, type ApiKey } from '../apiKeys'
import ApiKeyCreateModal from './ApiKeyCreateModal'

const STATUS = {
  active: { tone: 'success', label: 'Vigente' },
  expired: { tone: 'warning', label: 'Vencida' },
  revoked: { tone: 'secondary', label: 'Revocada' },
} as const

// Mi perfil › API keys: las propias en la empresa activa. Cada key actúa en
// nombre de su dueño con un subconjunto de sus permisos.
export default function ApiKeysTab() {
  const companyId = useSessionStore((s) => s.companyId)
  const companyName = useSessionStore((s) => s.companies.find((c) => c.id === s.companyId)?.name)
  const permissions = useSessionStore((s) => s.permissions)
  const keys = useApi(() => (companyId ? listMyApiKeys() : Promise.resolve([])), [companyId])
  const [now] = useState(() => Date.now())
  const [creating, setCreating] = useState(false)
  const [toRevoke, setToRevoke] = useState<ApiKey | null>(null)
  const [busy, setBusy] = useState(false)

  const available = [...new Set(permissions.map((p) => p.code))].sort()
  const activeCount = (keys.data ?? []).filter((k) => keyStatus(k, now) === 'active').length

  if (!companyId) {
    return <p className="text-body-secondary">Elige una empresa en la barra superior: las API keys son de cada empresa.</p>
  }

  const revoke = async () => {
    if (!toRevoke) return
    setBusy(true)
    try {
      await revokeApiKey(toRevoke.id)
      toast.success('API key revocada')
      keys.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToRevoke(null)
    }
  }

  const columns: Column<ApiKey>[] = [
    {
      header: 'Nombre',
      render: (k) => (
        <>
          <div>{k.name}</div>
          <div className="small text-body-secondary">
            <span className="font-monospace">{k.prefix}…</span>
            {k.description && ` · ${k.description}`}
          </div>
        </>
      ),
    },
    {
      header: 'Permisos',
      render: (k) => (
        <div className="d-flex flex-wrap gap-1">
          {k.scopes.map((s) => (
            <span key={s} className="badge text-bg-light border fw-normal" title={s}>{describePermission(s).label}</span>
          ))}
        </div>
      ),
    },
    { header: 'Vence', className: 'small text-nowrap', render: (k) => (k.expires_at ? formatDateTime(k.expires_at) : 'Sin vencimiento') },
    { header: 'Último uso', className: 'small text-nowrap', render: (k) => (k.last_used_at ? formatDateTime(k.last_used_at) : 'Nunca') },
    { header: 'Estado', render: (k) => <StatusBadge {...STATUS[keyStatus(k, now)]} /> },
    {
      header: '',
      className: 'text-end',
      render: (k) =>
        !k.revoked_at && (
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToRevoke(k)}>Revocar</button>
        ),
    },
  ]

  return (
    <>
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <p className="text-body-secondary mb-0">
          Claves para integraciones en {companyName ?? 'la empresa activa'} (hoy las acepta {API_KEY_SERVICES}).
          Máximo {API_KEYS_MAX} vigentes.
        </p>
        <button type="button" className="btn btn-primary" disabled={activeCount >= API_KEYS_MAX} onClick={() => setCreating(true)}>
          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
          Nueva API key
        </button>
      </div>

      <AsyncState loading={keys.loading} error={keys.error} onRetry={keys.reload} hasData={keys.data !== undefined}>
        <DataTable columns={columns} rows={keys.data ?? []} rowKey={(k) => k.id} emptyMessage="Aún no tienes API keys en esta empresa." />
      </AsyncState>

      {creating && <ApiKeyCreateModal available={available} onClose={() => setCreating(false)} onCreated={keys.reload} />}
      <ConfirmDialog
        open={toRevoke !== null}
        title="Revocar API key"
        message={`${toRevoke?.name ?? ''} deja de funcionar de inmediato. No se puede deshacer: para volver a integrar, crea otra.`}
        confirmLabel="Revocar"
        danger
        busy={busy}
        onConfirm={revoke}
        onCancel={() => setToRevoke(null)}
      />
    </>
  )
}
