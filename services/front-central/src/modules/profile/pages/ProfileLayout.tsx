import { Outlet } from 'react-router'
import PageHeader from '../../../shared/components/PageHeader'
import RouteTabs from '../../../shared/components/RouteTabs'

const TABS = [
  { label: 'Información', to: '/perfil/informacion', icon: 'person-vcard' },
  { label: 'Empresas y puestos', to: '/perfil/empresas', icon: 'buildings' },
  { label: 'Seguridad', to: '/perfil/seguridad', icon: 'key' },
  { label: 'Sesiones', to: '/perfil/sesiones', icon: 'laptop' },
  { label: 'API keys', to: '/perfil/api-keys', icon: 'key-fill' },
]

// Contenedor de Mi perfil: cabecera y pestañas; cada pestaña es una ruta hija.
export default function ProfileLayout() {
  return (
    <>
      <PageHeader title="Mi perfil" description="Tus datos, empresas, puestos y seguridad de la cuenta." />
      <RouteTabs tabs={TABS} />
      <Outlet />
    </>
  )
}
