import { createBrowserRouter, Navigate } from 'react-router'
import { LEDGER_ADMIN, LEDGER_VIEW } from '../shared/auth/access'
import AppLayout from './layout/AppLayout'
import { NAV_GROUPS } from './layout/navigation'
import NotFoundPage from './NotFoundPage'
import PendingPage from './PendingPage'
import RequireAccess from './RequireAccess'
import RequireAuth from './RequireAuth'
import RequireCompany from './RequireCompany'
import LoginPage from '../modules/auth/pages/LoginPage'
import LedgerPage from '../modules/ledger/pages/LedgerPage'
import LiveQueryPage from '../modules/ledger/pages/LiveQueryPage'
import RulesLayout from '../modules/ledger/pages/RulesLayout'
import CategoriesTab from '../modules/ledger/components/CategoriesTab'
import ClassificationRunsTab from '../modules/ledger/components/ClassificationRunsTab'
import RulesTab from '../modules/ledger/components/RulesTab'
import CostCentersLayout from '../modules/ledger/pages/CostCentersLayout'
import CostCentersTab from '../modules/ledger/components/CostCentersTab'
import MappingsTab from '../modules/ledger/components/MappingsTab'
import MembersPage from '../modules/company/pages/MembersPage'
import AreasPage from '../modules/company/pages/AreasPage'
import RolesLayout from '../modules/company/pages/RolesLayout'
import HistoryPage from '../modules/company/pages/HistoryPage'
import AccountsPage from '../modules/ledger/pages/AccountsPage'
import CompaniesPage from '../modules/platform/pages/CompaniesPage'
import UsersPage from '../modules/platform/pages/UsersPage'
import ServicesPage from '../modules/platform/pages/ServicesPage'
import IpBlocksPage from '../modules/platform/pages/IpBlocksPage'
import PermissionsTab from '../modules/company/components/PermissionsTab'
import RolesTab from '../modules/company/components/RolesTab'
import SyncPage from '../modules/ledger/pages/SyncPage'
import LogsPage from '../modules/monitoring/pages/LogsPage'
import CompaniesTab from '../modules/profile/pages/CompaniesTab'
import InfoTab from '../modules/profile/pages/InfoTab'
import ProfileLayout from '../modules/profile/pages/ProfileLayout'
import SecurityTab from '../modules/profile/pages/SecurityTab'
import SessionsTab from '../modules/profile/pages/SessionsTab'

// Provisional: cada ítem del menú sin módulo propio muestra "en construcción",
// protegido con la misma regla que el menú. Se quita a medida que cada módulo
// agrega su ruta real (también envuelta en RequireAccess).
// Rutas que ya tienen su módulo (se declaran abajo).
const IMPLEMENTED = new Set(['/perfil', '/contabilidad/libro-mayor', '/contabilidad/consulta-sap', '/contabilidad/sincronizacion', '/contabilidad/reglas', '/contabilidad/centros-costo', '/empresa/miembros', '/empresa/areas', '/empresa/roles', '/empresa/historial', '/contabilidad/cuentas', '/plataforma/empresas', '/plataforma/usuarios', '/plataforma/servicios', '/plataforma/ips', '/monitoreo/logs'])

const pendingRoutes = NAV_GROUPS.flatMap((g) => g.items)
  .filter((item) => !IMPLEMENTED.has(item.path))
  .map((item) => ({
    path: item.path,
    element: (
      <RequireAccess rule={item.access}>
        <PendingPage title={item.label} />
      </RequireAccess>
    ),
  }))

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    // Todo lo de adentro exige sesión.
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/perfil" replace /> },
          {
            path: 'perfil',
            element: <ProfileLayout />,
            children: [
              { index: true, element: <Navigate to="informacion" replace /> },
              { path: 'informacion', element: <InfoTab /> },
              { path: 'empresas', element: <CompaniesTab /> },
              { path: 'seguridad', element: <SecurityTab /> },
              { path: 'sesiones', element: <SessionsTab /> },
            ],
          },
          {
            path: 'contabilidad/libro-mayor',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_VIEW }}>
                <RequireCompany>
                  <LedgerPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            path: 'contabilidad/consulta-sap',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_VIEW }}>
                <RequireCompany>
                  <LiveQueryPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            path: 'contabilidad/reglas',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_VIEW }}>
                <RequireCompany>
                  <RulesLayout />
                </RequireCompany>
              </RequireAccess>
            ),
            children: [
              { index: true, element: <RulesTab /> },
              { path: 'categorias', element: <CategoriesTab /> },
              { path: 'reclasificaciones', element: <ClassificationRunsTab /> },
            ],
          },
          {
            path: 'contabilidad/centros-costo',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_VIEW }}>
                <RequireCompany>
                  <CostCentersLayout />
                </RequireCompany>
              </RequireAccess>
            ),
            children: [
              { index: true, element: <CostCentersTab /> },
              { path: 'homologaciones', element: <MappingsTab /> },
            ],
          },
          {
            // Fase 1 (acuerdo): Empresa solo para platform admin.
            path: 'empresa/miembros',
            element: (
              <RequireAccess rule="platformAdmin">
                <RequireCompany>
                  <MembersPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            path: 'empresa/areas',
            element: (
              <RequireAccess rule="platformAdmin">
                <RequireCompany>
                  <AreasPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            path: 'empresa/roles',
            element: (
              <RequireAccess rule="platformAdmin">
                <RequireCompany>
                  <RolesLayout />
                </RequireCompany>
              </RequireAccess>
            ),
            children: [
              { index: true, element: <RolesTab /> },
              { path: 'permisos', element: <PermissionsTab /> },
            ],
          },
          {
            path: 'empresa/historial',
            element: (
              <RequireAccess rule="platformAdmin">
                <RequireCompany>
                  <HistoryPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            path: 'contabilidad/cuentas',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_ADMIN }}>
                <RequireCompany>
                  <AccountsPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            // Plataforma: sin RequireCompany, trabaja sobre todas las empresas.
            path: 'plataforma/empresas',
            element: (
              <RequireAccess rule="platformAdmin">
                <CompaniesPage />
              </RequireAccess>
            ),
          },
          {
            path: 'plataforma/servicios',
            element: (
              <RequireAccess rule="platformAdmin">
                <ServicesPage />
              </RequireAccess>
            ),
          },
          {
            path: 'plataforma/ips',
            element: (
              <RequireAccess rule="platformAdmin">
                <IpBlocksPage />
              </RequireAccess>
            ),
          },
          {
            path: 'plataforma/usuarios',
            element: (
              <RequireAccess rule="platformAdmin">
                <UsersPage />
              </RequireAccess>
            ),
          },
          {
            path: 'contabilidad/sincronizacion',
            element: (
              <RequireAccess rule={{ anyOf: LEDGER_VIEW }}>
                <RequireCompany>
                  <SyncPage />
                </RequireCompany>
              </RequireAccess>
            ),
          },
          {
            // Sin RequireCompany: los logs son de toda la plataforma.
            path: 'monitoreo/logs/:service?',
            element: (
              <RequireAccess rule="platformAdmin">
                <LogsPage />
              </RequireAccess>
            ),
          },
          ...pendingRoutes,
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])
