import { Outlet } from 'react-router'
import PageHeader from '../../../shared/components/PageHeader'
import RouteTabs from '../../../shared/components/RouteTabs'

const TABS = [
  { label: 'Reglas', to: '/contabilidad/reglas', icon: 'list-check' },
  { label: 'Categorías', to: '/contabilidad/reglas/categorias', icon: 'tags' },
  { label: 'Reclasificaciones', to: '/contabilidad/reglas/reclasificaciones', icon: 'shuffle' },
]

// Ver: ledger.view. Crear, editar y dar de baja: ledger.update (cada pestaña
// muestra los botones solo si corresponde; libro-mayor valida igual).
export default function RulesLayout() {
  return (
    <>
      <PageHeader
        title="Reglas y categorías"
        description="Cómo se clasifica cada línea del libro mayor: gana la primera regla que cumple."
      />
      <RouteTabs tabs={TABS} />
      <Outlet />
    </>
  )
}
