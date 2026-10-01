export default function FullPageSpinner() {
  return (
    <div className="d-flex align-items-center justify-content-center min-vh-100">
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">Cargando…</span>
      </div>
    </div>
  )
}
