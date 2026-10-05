// Canales de lastmiller que el front sabe mostrar. La fuente de verdad es
// canales-venta (app/lastmiller/channels.py): un canal que no esté allí
// responde 404 aunque aparezca aquí.

export type Channel = {
  country: string
  provider: string
  name: string
  hasPromotions: boolean
}

export const CHANNELS: Channel[] = [
  { country: 'pe', provider: 'rappi', name: 'Rappi Perú', hasPromotions: false },
  { country: 'mx', provider: 'rappi', name: 'Rappi México', hasPromotions: false },
  { country: 'pe', provider: 'peya', name: 'PedidosYa Perú', hasPromotions: true },
]

// Rutas del front: /ventas/... (nunca /canales-venta, que el borde envía a la API).
export function channelPath(channel: Channel) {
  return `/ventas/lastmiller/${channel.country}/${channel.provider}`
}

export function findChannel(country: string | undefined, provider: string | undefined) {
  return CHANNELS.find((c) => c.country === country && c.provider === provider)
}
