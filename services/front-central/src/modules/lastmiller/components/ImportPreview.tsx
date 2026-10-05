import { useState } from 'react'
import { saveBlob, toCsv } from '../../../shared/utils/download'
import type { ImportDetail } from '../types'

const SHOWN = 300 // SKU visibles por grupo antes de "ver más"

type Group = { key: string; title: string; tone: string; icon: string; skus: string[]; help?: string }

type CsvRow = { sku: string; estado: string; detalle: string }

// Todas las filas de la vista previa con su estado (y las observaciones del
// archivo), en CSV para Excel. Se arma con lo que ya devolvió canales-venta.
export function previewRows(detail: ImportDetail): CsvRow[] {
  const { plan } = detail
  const rows: CsvRow[] = detail.errors.map((e) => ({ sku: '', estado: 'Error en el archivo', detalle: `${e.row ? `Fila ${e.row}: ` : ''}${e.message}` }))
  const add = (skus: string[] | undefined, estado: string, detalle = '') => (skus ?? []).forEach((sku) => rows.push({ sku, estado, detalle }))
  ;(plan.create ?? []).forEach((c) => rows.push({ sku: c.sku, estado: 'Se crea', detalle: c.active ? 'on' : 'off' }))
  add(plan.activate, 'Pasa a on')
  add(plan.deactivate, 'Pasa a off')
  add(plan.deactivate_unlisted, 'Pasa a off', 'No está en el archivo (carga completa)')
  add(plan.add, 'Se agrega la promoción')
  add(plan.remove, 'Se quita la promoción', 'No está en el archivo')
  add(plan.missing, detail.kind === 'promotions' ? 'No existe (bloquea la carga)' : 'No existe (se omite)')
  add(plan.inactive, 'Aviso', 'Con promoción pero en off')
  return rows
}

export function downloadPreview(detail: ImportDetail) {
  const blob = toCsv(previewRows(detail), [
    { header: 'SKU', value: (r) => r.sku },
    { header: 'Estado', value: (r) => r.estado },
    { header: 'Detalle', value: (r) => r.detalle },
  ])
  saveBlob(blob, `vista-previa-${detail.kind}-${detail.created_at.slice(0, 10)}.csv`)
}

// Qué hará (o hizo) una carga: contadores y, por grupo, la lista de SKU.
export default function ImportPreview({ detail }: { detail: ImportDetail }) {
  const { plan, errors, kind } = detail
  if (errors.length > 0) {
    return (
      <div className="alert alert-danger mb-0">
        <p className="fw-semibold mb-2">El archivo tiene errores y no se puede aplicar. Corrígelo y vuelve a cargarlo:</p>
        <ul className="mb-0 small">
          {errors.slice(0, 50).map((e, i) => <li key={i}>{e.row ? `Fila ${e.row}: ` : ''}{e.message}</li>)}
          {errors.length > 50 && <li>…y {errors.length - 50} errores más.</li>}
        </ul>
      </div>
    )
  }

  const groups: Group[] = kind === 'promotions'
    ? [
        { key: 'add', title: 'Se agrega la promoción', tone: 'success', icon: 'star-fill', skus: plan.add ?? [] },
        { key: 'remove', title: 'Se quita la promoción', tone: 'danger', icon: 'star', skus: plan.remove ?? [], help: 'Tienen promoción y no están en el archivo.' },
        { key: 'missing', title: 'No existen en el canal (bloquean la carga)', tone: 'danger', icon: 'x-octagon', skus: plan.missing ?? [] },
        { key: 'inactive', title: 'Aviso: con promoción pero en off', tone: 'warning', icon: 'exclamation-triangle', skus: plan.inactive ?? [], help: 'Tendrán promoción, pero lastmiller no los ofrece mientras sigan en off.' },
      ]
    : [
        { key: 'create', title: 'Se crean', tone: 'primary', icon: 'plus-circle', skus: (plan.create ?? []).map((c) => `${c.sku} (${c.active ? 'on' : 'off'})`) },
        { key: 'activate', title: 'Pasan a on', tone: 'success', icon: 'toggle-on', skus: plan.activate ?? [] },
        { key: 'deactivate', title: 'Pasan a off', tone: 'danger', icon: 'toggle-off', skus: plan.deactivate ?? [] },
        { key: 'deactivate_unlisted', title: 'Pasan a off por no estar en el archivo', tone: 'danger', icon: 'toggle-off', skus: plan.deactivate_unlisted ?? [], help: 'Carga completa: lo que no vino en el archivo queda off.' },
        { key: 'missing', title: 'No existen y se omiten', tone: 'warning', icon: 'exclamation-triangle', skus: plan.missing ?? [], help: 'Activa "crear SKU nuevos" para crearlos.' },
      ]
  const visible = groups.filter((g) => g.skus.length > 0)

  return (
    <>
      <div className="d-flex flex-wrap gap-3 small mb-3">
        <span><strong>{plan.rows ?? 0}</strong> filas leídas</span>
        <span><strong>{plan.unchanged ?? 0}</strong> sin cambios</span>
        <span><strong>{detail.total_changes}</strong> cambios</span>
      </div>
      {visible.length === 0 && <p className="text-body-secondary mb-0">El archivo no cambia nada en el canal.</p>}
      {visible.map((g) => <GroupList key={g.key} group={g} />)}
    </>
  )
}

function GroupList({ group }: { group: Group }) {
  const [all, setAll] = useState(false)
  const shown = all ? group.skus : group.skus.slice(0, SHOWN)
  return (
    <details className="border rounded-3 mb-2" open={group.skus.length <= 20}>
      <summary className="px-3 py-2">
        <i className={`bi bi-${group.icon} text-${group.tone} me-2`} aria-hidden="true" />
        {group.title} <span className={`badge text-bg-${group.tone} ms-1`}>{group.skus.length}</span>
        {group.help && <span className="small text-body-secondary ms-2">{group.help}</span>}
      </summary>
      <div className="px-3 pb-2 d-flex flex-wrap gap-1 font-monospace small" style={{ maxHeight: 220, overflowY: 'auto' }}>
        {shown.map((sku) => <span key={sku} className="badge bg-body-secondary text-body fw-normal">{sku}</span>)}
        {!all && group.skus.length > SHOWN && (
          <button type="button" className="btn btn-link btn-sm p-0" onClick={() => setAll(true)}>
            Ver los {group.skus.length - SHOWN} restantes
          </button>
        )}
      </div>
    </details>
  )
}
