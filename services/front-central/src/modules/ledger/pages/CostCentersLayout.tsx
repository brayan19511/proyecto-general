import { Outlet } from 'react-router'
import PageHeader from '../../../shared/components/PageHeader'
import RouteTabs from '../../../shared/components/RouteTabs'

const TABS = [
  { label: 'Centros de costo', to: '/contabilidad/centros-costo', icon: 'pin-map' },
  { label: 'Homologaciones', to: '/contabilidad/centros-costo/homologaciones', icon: 'signpost-2' },
]

// Ver: ledger.view. Homologar: ledger.admin. Sin reproceso: el área de cada
// línea se resuelve al consultar, así que los cambios valen desde la próxima consulta.
export default function CostCentersLayout() {
  return (
    <>
      <PageHeader
        title="Centros de costo"
        description="A qué área pertenece cada centro de costo de SAP. Los cambios se aplican desde la próxima consulta, sin reprocesar."
      />
      <RouteTabs tabs={TABS} />
      <Outlet />
    </>
  )
}
