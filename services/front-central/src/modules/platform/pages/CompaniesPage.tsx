import { useState } from 'react'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { copyText } from '../../../shared/utils/clipboard'
import { formatDate } from '../../../shared/utils/format'
import CodeNameFormModal from '../../company/components/CodeNameFormModal'
import SapCompanyModal from '../components/SapCompanyModal'
import SapSummary from '../components/SapSummary'
import SeedCompanyModal from '../components/SeedCompanyModal'
import * as companiesService from '../services/companiesService'
import type { AdminCompany } from '../types'

// Plataforma › Empresas (solo platform admin): empresas de auth y, para cada
// una, su compañía SAP en libro-mayor.
export default function CompaniesPage() {
  const reloadSessionCompanies = useSessionStore((s) => s.reloadCompanies)
  const [search, setSearch] = useState('')
  const companies = useApi(companiesService.listCompanies)
  const [form, setForm] = useState<{ company: AdminCompany | null } | null>(null)
  const [sapFor, setSapFor] = useState<AdminCompany | null>(null)
  const [sapVersion, setSapVersion] = useState(0)
  const [seedFor, setSeedFor] = useState<AdminCompany | null>(null)
  const [toggle, setToggle] = useState<AdminCompany | null>(null)
  const [busy, setBusy] = useState(false)

  // Cambios en empresas también cambian el selector de la barra superior.
  const reloadAll = () => {
    companies.reload()
    reloadSessionCompanies().catch(() => {})
  }

  const term = search.trim().toLowerCase()
  const rows = [...(companies.data ?? [])]
    .sort((a, b) => a.name.localeCompare(b.name, 'es'))
    .filter((c) => !term || `${c.code} ${c.name}`.toLowerCase().includes(term))

  const confirmToggle = async () => {
    if (!toggle) return
    setBusy(true)
    try {
      await companiesService.setCompanyActive(toggle.id, !toggle.is_active)
      toast.success(toggle.is_active ? 'Empresa desactivada' : 'Empresa activada')
      reloadAll()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToggle(null)
    }
  }

  // El id lo piden pgAdmin, soporte y las llamadas por API (X-Company-Id).
  // copyText funciona también por HTTP en la red (sin navigator.clipboard).
  const copyId = async (company: AdminCompany) => {
    if (await copyText(company.id)) toast.info(`Id de ${company.code} copiado`)
    else toast.error('No se pudo copiar el id')
  }

  const columns: Column<AdminCompany>[] = [
    {
      header: 'Empresa',
      render: (c) => (
        <>
          <div>{c.name}</div>
          <div className="small text-body-secondary font-monospace">{c.code}</div>
          <button type="button" className="btn btn-link btn-sm p-0 small text-body-secondary font-monospace text-decoration-none"
            onClick={() => copyId(c)} title="Copiar id" aria-label={`Copiar id de ${c.name}`}>
            {c.id}
            <i className="bi bi-clipboard ms-1" aria-hidden="true" />
          </button>
        </>
      ),
    },
    {
      header: 'Compañía SAP',
      // Desactivada: auth no da contexto para ella, libro-mayor no la consulta.
      render: (c) => (c.is_active ? <SapSummary companyId={c.id} version={sapVersion} /> : <span className="text-body-secondary">—</span>),
    },
    { header: 'Creada', className: 'text-nowrap', render: (c) => formatDate(c.created_at.slice(0, 10)) },
    {
      header: 'Estado',
      render: (c) => <StatusBadge tone={c.is_active ? 'success' : 'secondary'} label={c.is_active ? 'Activa' : 'Desactivada'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (c) => (
        <>
          <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setSapFor(c)} disabled={!c.is_active}
            title={c.is_active ? 'Configurar compañía SAP' : 'Activa la empresa para configurarla'}>
            <i className="bi bi-database-gear me-1" aria-hidden="true" />
            SAP
          </button>
          <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setSeedFor(c)} disabled={!c.is_active}
            title={c.is_active ? 'Carga inicial de los servicios' : 'Activa la empresa para ejecutar su carga inicial'}>
            <i className="bi bi-box-arrow-in-down me-1" aria-hidden="true" />
            Carga inicial
          </button>
          <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ company: c })}
            aria-label={`Renombrar ${c.name}`} title="Renombrar">
            <i className="bi bi-pencil" aria-hidden="true" />
          </button>
          <button type="button" className={`btn btn-sm ${c.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`} onClick={() => setToggle(c)}>
            {c.is_active ? 'Desactivar' : 'Activar'}
          </button>
        </>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Empresas"
        description="Empresas de la plataforma y la compañía SAP de la que libro-mayor lee sus líneas."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setForm({ company: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva empresa
          </button>
        }
      />

      <input className="form-control form-control-sm mb-3" style={{ maxWidth: 280 }} placeholder="Buscar código o nombre…"
        aria-label="Buscar empresas" value={search} onChange={(e) => setSearch(e.target.value)} />

      <AsyncState loading={companies.loading} error={companies.error} onRetry={companies.reload} hasData={companies.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(c) => c.id}
          emptyMessage={term ? 'Ninguna empresa coincide.' : 'Aún no hay empresas.'} />
      </AsyncState>

      {form && (
        <CodeNameFormModal
          title={form.company ? `Renombrar ${form.company.code}` : 'Nueva empresa'}
          existing={form.company}
          codePlaceholder="RASH"
          namePlaceholder="RASH Perú"
          save={(code, name) => (form.company ? companiesService.renameCompany(form.company.id, name) : companiesService.createCompany(code, name))}
          doneMessage={form.company ? 'Empresa actualizada' : 'Empresa creada. Configura su compañía SAP y sus áreas.'}
          onClose={() => setForm(null)}
          onSaved={reloadAll}
        />
      )}
      {sapFor && (
        <SapCompanyModal company={sapFor} onClose={() => setSapFor(null)} onChanged={() => setSapVersion((v) => v + 1)} />
      )}
      {seedFor && (
        // El seed de libro-mayor puede crear la compañía SAP: refresca su resumen.
        <SeedCompanyModal company={seedFor} onClose={() => setSeedFor(null)} onDone={() => setSapVersion((v) => v + 1)} />
      )}

      <ConfirmDialog
        open={toggle !== null}
        title={toggle?.is_active ? 'Desactivar empresa' : 'Activar empresa'}
        message={
          toggle?.is_active
            ? `Nadie podrá trabajar en ${toggle.name} (sus miembros pierden el acceso) hasta que se active de nuevo. No se borra nada.`
            : `${toggle?.name ?? ''} vuelve a estar disponible para sus miembros.`
        }
        confirmLabel={toggle?.is_active ? 'Desactivar' : 'Activar'}
        danger={toggle?.is_active ?? false}
        busy={busy}
        onConfirm={confirmToggle}
        onCancel={() => setToggle(null)}
      />
    </>
  )
}
