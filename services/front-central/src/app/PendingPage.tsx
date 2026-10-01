import PageHeader from '../shared/components/PageHeader'
import EmptyState from '../shared/components/EmptyState'

// Provisional: ocupa el lugar de los módulos que aún no existen.
export default function PendingPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState
        icon="cone-striped"
        title="Módulo en construcción"
        description="Esta sección se habilita en una fase siguiente."
      />
    </>
  )
}
