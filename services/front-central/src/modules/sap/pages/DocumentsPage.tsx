import { useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDate, toIsoDate } from '../../../shared/utils/format'
import AttachmentsDialog from '../components/AttachmentsDialog'
import type { Criterion, DocumentSearch, DocumentType, SapDocument } from '../documentTypes'
import * as documentsService from '../services/documentsService'
import * as sapService from '../services/sapService'

const CRITERION_LABEL: Record<Criterion, string> = {
  doc_num: 'Número de documento',
  folio: 'Folio (serie-número)',
  num_at_card: 'Referencia del socio',
  doc_entry: 'DocEntry (id interno)',
}

const PARTNER_LABEL = { customer: 'Cliente', supplier: 'Proveedor', none: 'Socio' }

type Mode = 'exact' | 'partner'

// SAP › Documentos: buscar un documento (por número o por cliente/proveedor y
// fechas), ver sus anexos y descargarlos. Permiso sap_documents.view.
export default function DocumentsPage() {
  const databases = useApi(() => sapService.listDatabases())
  const types = useApi(() => documentsService.listTypes())
  const [companyDb, setCompanyDb] = useState('')
  const [typeCode, setTypeCode] = useState('')
  const [mode, setMode] = useState<Mode>('exact')
  const [criterion, setCriterion] = useState<Criterion>('doc_num')
  const [value, setValue] = useState('')
  const [cardCode, setCardCode] = useState('')
  const [cardName, setCardName] = useState('')
  // Fechas calculadas una vez al abrir la página (por defecto, los últimos 30 días).
  const [today] = useState(() => toIsoDate(new Date()))
  const [dateFrom, setDateFrom] = useState(() => toIsoDate(new Date(Date.now() - 30 * 86_400_000)))
  const [dateTo, setDateTo] = useState(today)
  // Búsqueda enviada: solo cambia al pulsar Buscar (no en cada tecla).
  const [submitted, setSubmitted] = useState<DocumentSearch | null>(null)
  // Cada clic en Buscar consulta de nuevo, aunque los filtros no cambien.
  const [searchCount, setSearchCount] = useState(0)
  const [offset, setOffset] = useState(0)
  const [open, setOpen] = useState<SapDocument | null>(null)

  const results = useApi(
    () => (submitted ? documentsService.search(submitted, offset) : Promise.resolve(undefined)),
    [JSON.stringify(submitted), offset, searchCount],
  )

  // Búsqueda en curso (incluye cambiar de página): SAP puede tardar unos segundos.
  const searching = submitted !== null && results.loading
  const typeList = types.data ?? []
  const docType: DocumentType | undefined = typeList.find((t) => t.code === (typeCode || typeList[0]?.code))
  const db = companyDb || databases.data?.[0]?.company_db || ''
  const partnerLabel = PARTNER_LABEL[docType?.partner ?? 'none']
  const canSearchPartner = docType?.partner !== 'none'
  const activeCriterion = docType?.criteria.includes(criterion) ? criterion : (docType?.criteria[0] ?? 'doc_entry')

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!docType || !db || searching) return
    const base = { company_db: db, type: docType.code }
    setSubmitted(mode === 'exact' || !canSearchPartner
      ? { ...base, [activeCriterion]: value }
      : { ...base, card_code: cardCode, card_name: cardName, date_from: dateFrom, date_to: dateTo })
    setOffset(0)
    setSearchCount((n) => n + 1)
  }

  const typeLabel = (code: string) => typeList.find((t) => t.code === code)?.label ?? code
  const columns: Column<SapDocument>[] = [
    { header: 'Fecha', className: 'small text-nowrap', render: (d) => (d.doc_date ? formatDate(d.doc_date) : '—') },
    { header: 'Número', className: 'font-monospace', render: (d) => d.doc_num ?? '—' },
    { header: 'Folio', className: 'font-monospace small', render: (d) => d.folio ?? '—' },
    { header: 'Referencia', className: 'small', render: (d) => d.num_at_card ?? '—' },
    {
      header: partnerLabel,
      className: 'small',
      render: (d) => (d.card_code ? <><span className="font-monospace">{d.card_code}</span> {d.card_name}</> : '—'),
    },
    {
      header: 'Anexos',
      className: 'text-end',
      render: (d) => d.has_attachments
        ? <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setOpen(d)}>
            <i className="bi bi-paperclip me-1" aria-hidden="true" />Ver anexos
          </button>
        : <span className="small text-body-secondary">Sin anexos</span>,
    },
  ]

  const noDatabases = databases.data !== undefined && databases.data.length === 0
  return (
    <>
      <PageHeader title="Documentos SAP" description="Busca un documento, revisa sus anexos y descárgalos. Cada descarga queda registrada." />
      <AsyncState loading={databases.loading || types.loading} error={databases.error ?? types.error}
        onRetry={() => { databases.reload(); types.reload() }} hasData={databases.data !== undefined && types.data !== undefined}>
        {noDatabases ? (
          <div className="alert alert-warning">La empresa no tiene Bases SAP registradas. Pídelas en SAP › Configuración SAP.</div>
        ) : (
          <form className="card card-body mb-3" onSubmit={submit}>
            <div className="row g-2">
              <div className="col-sm-6 col-lg-3">
                <label htmlFor="ds-db" className="form-label small">Base SAP</label>
                <select id="ds-db" className="form-select form-select-sm font-monospace" value={db} onChange={(e) => setCompanyDb(e.target.value)}>
                  {(databases.data ?? []).map((d) => <option key={d.id} value={d.company_db}>{d.company_db}{d.label ? ` · ${d.label}` : ''}</option>)}
                </select>
              </div>
              <div className="col-sm-6 col-lg-3">
                <label htmlFor="ds-type" className="form-label small">Tipo de documento</label>
                <select id="ds-type" className="form-select form-select-sm" value={docType?.code ?? ''} onChange={(e) => setTypeCode(e.target.value)}>
                  {typeList.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
                </select>
              </div>
              <div className="col-lg-6 d-flex align-items-end gap-3">
                <div className="form-check">
                  <input id="ds-mode-exact" type="radio" className="form-check-input" checked={mode === 'exact' || !canSearchPartner} onChange={() => setMode('exact')} />
                  <label htmlFor="ds-mode-exact" className="form-check-label small">Por número</label>
                </div>
                <div className="form-check">
                  <input id="ds-mode-partner" type="radio" className="form-check-input" checked={mode === 'partner' && canSearchPartner}
                    disabled={!canSearchPartner} onChange={() => setMode('partner')} />
                  <label htmlFor="ds-mode-partner" className="form-check-label small">Por {partnerLabel.toLowerCase()} y fechas</label>
                </div>
              </div>

              {mode === 'exact' || !canSearchPartner ? (
                <>
                  <div className="col-sm-6 col-lg-3">
                    <label htmlFor="ds-criterion" className="form-label small">Buscar por</label>
                    <select id="ds-criterion" className="form-select form-select-sm" value={activeCriterion} onChange={(e) => setCriterion(e.target.value as Criterion)}>
                      {(docType?.criteria ?? []).map((c) => <option key={c} value={c}>{CRITERION_LABEL[c]}</option>)}
                    </select>
                  </div>
                  <div className="col-sm-6 col-lg-3">
                    <label htmlFor="ds-value" className="form-label small">Valor</label>
                    <input id="ds-value" className="form-control form-control-sm font-monospace" required maxLength={100}
                      inputMode={activeCriterion === 'doc_num' || activeCriterion === 'doc_entry' ? 'numeric' : 'text'}
                      pattern={activeCriterion === 'doc_num' || activeCriterion === 'doc_entry' ? '[0-9]+' : undefined}
                      placeholder={activeCriterion === 'folio' ? 'F001-47012' : ''} value={value} onChange={(e) => setValue(e.target.value)} />
                  </div>
                </>
              ) : (
                <>
                  <div className="col-sm-6 col-lg-2">
                    <label htmlFor="ds-code" className="form-label small">Código contiene (p. ej. RUC)</label>
                    <input id="ds-code" className="form-control form-control-sm font-monospace" minLength={3} maxLength={100} value={cardCode} onChange={(e) => setCardCode(e.target.value)} />
                  </div>
                  <div className="col-sm-6 col-lg-4">
                    <label htmlFor="ds-name" className="form-label small">Nombre contiene (mín. 3 letras)</label>
                    <input id="ds-name" className="form-control form-control-sm" minLength={3} maxLength={100} value={cardName} onChange={(e) => setCardName(e.target.value)} />
                  </div>
                  <div className="col-6 col-lg-3">
                    <label htmlFor="ds-from" className="form-label small">Desde</label>
                    <input id="ds-from" type="date" className="form-control form-control-sm" required max={dateTo} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                  </div>
                  <div className="col-6 col-lg-3">
                    <label htmlFor="ds-to" className="form-label small">Hasta</label>
                    <input id="ds-to" type="date" className="form-control form-control-sm" required min={dateFrom} max={today} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                  </div>
                  <div className="col-12 form-text mt-0">Parte del código (el RUC basta, sin la letra inicial), parte del nombre o ambos; mínimo 3 caracteres. Trae documentos abiertos y cerrados. Rango máximo: un año.</div>
                </>
              )}
              <div className="col-12 d-flex justify-content-end">
                <button type="submit" className="btn btn-sm btn-primary"
                  disabled={searching || !docType || !db || (mode === 'partner' && canSearchPartner && cardCode.trim().length < 3 && cardName.trim().length < 3)}>
                  {searching
                    ? <><span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />Buscando…</>
                    : <><i className="bi bi-search me-1" aria-hidden="true" />Buscar</>}
                </button>
              </div>
            </div>
          </form>
        )}
      </AsyncState>

      {submitted && (
        <AsyncState loading={results.loading} error={results.error} onRetry={results.reload} hasData={results.data !== undefined}>
          {/* Con resultados anteriores en pantalla, AsyncState no muestra "Cargando": se avisa
              aquí y los resultados viejos se atenúan y bloquean hasta que llegue la respuesta. */}
          {searching && results.data !== undefined && (
            <div className="alert alert-info d-flex align-items-center gap-2 py-2 mb-2" role="status">
              <span className="spinner-border spinner-border-sm" aria-hidden="true" />Buscando en SAP…
            </div>
          )}
          <div style={searching ? { opacity: 0.4, pointerEvents: 'none' } : undefined} aria-busy={searching}>
            <DataTable columns={columns} rows={results.data?.items ?? []} rowKey={(d) => `${d.type_code}-${d.doc_entry}`}
              emptyMessage="No se encontraron documentos." />
            <Pager offset={offset} limit={documentsService.SEARCH_PAGE_SIZE} count={results.data?.items.length ?? 0} onChange={setOffset} />
          </div>
        </AsyncState>
      )}

      {open && submitted && (
        <AttachmentsDialog companyDb={submitted.company_db} typeLabel={typeLabel(open.type_code)} document={open} onClose={() => setOpen(null)} />
      )}
    </>
  )
}
