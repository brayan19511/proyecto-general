import { Outlet, useOutletContext, useParams } from 'react-router'
import EmptyState from '../../../shared/components/EmptyState'
import PageHeader from '../../../shared/components/PageHeader'
import RouteTabs from '../../../shared/components/RouteTabs'
import { channelPath, findChannel, type Channel } from '../channels'

// Canales de venta › un canal de lastmiller (/ventas/lastmiller/:country/:provider).
// Ver: lastmiller.view; editar: edit; cargas masivas: import. Cada pestaña
// muestra los botones según el permiso; canales-venta valida igual.
export default function ChannelLayout() {
  const { country, provider } = useParams()
  const channel = findChannel(country, provider)
  if (!channel) return <EmptyState icon="question-circle" title="Canal no encontrado" />

  const path = channelPath(channel)
  return (
    <>
      <PageHeader
        title={channel.name}
        description={channel.hasPromotions
          ? 'SKU que lastmiller publica en el canal: estado on/off y promociones.'
          : 'SKU que lastmiller publica en el canal: estado on/off.'}
      />
      <RouteTabs tabs={[
        { label: 'SKU', to: path, icon: 'upc-scan' },
        { label: 'Cargas masivas', to: `${path}/cargas`, icon: 'file-earmark-spreadsheet' },
        { label: 'Historial', to: `${path}/historial`, icon: 'clock-history' },
      ]} />
      {/* key: al cambiar de canal se reinician filtros y datos de las pestañas. */}
      <Outlet key={path} context={channel} />
    </>
  )
}

export function useChannel() {
  return useOutletContext<Channel>()
}
