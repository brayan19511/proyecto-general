import { Outlet } from 'react-router'
import PageHeader from '../../../shared/components/PageHeader'
import RouteTabs from '../../../shared/components/RouteTabs'

const TABS = [
  { label: 'Roles', to: '/empresa/roles', icon: 'person-badge' },
  { label: 'Permisos', to: '/empresa/roles/permisos', icon: 'key' },
]

// Empresa › Roles y permisos (fase 1: solo platform admin). Un rol agrupa
// permisos con su alcance; se asigna a puestos y de ahí llega a las personas.
export default function RolesLayout() {
  return (
    <>
      <PageHeader
        title="Roles y permisos"
        description="Un rol agrupa permisos con su alcance. Se asigna a puestos, y las personas lo reciben por su puesto."
      />
      <RouteTabs tabs={TABS} />
      <Outlet />
    </>
  )
}
