"""Canales de lastmiller y sus tablas en Ofisis (EcommDB, schema dbo).

Este registro es la única fuente de los pares país/proveedor admitidos: el
cliente elige país y proveedor, nunca una base ni una tabla.

Las tablas son de Ofisis (las lee lastmiller), no de este servicio: se declaran
con SQLAlchemy Core solo para armar consultas; nunca se crean ni se migran
desde aquí. Columnas verificadas contra Ofisis el 2026-10-03.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, Unicode

_metadata = MetaData(schema="dbo")

_rappi_pe = Table(
    "rappi_sku",
    _metadata,
    Column("sku", String(255), primary_key=True),
    Column("id_rappi", String(255)),
    Column("is_active", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

_rappi_mx = Table(
    "mx_rappi_sku",
    _metadata,
    Column("sku", Unicode(255), primary_key=True),  # nvarchar, a diferencia de las otras.
    Column("id_rappi", String(255)),
    Column("is_active", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

_peya_pe = Table(
    "peya_sku",
    _metadata,
    Column("sku", String(255), primary_key=True),
    Column("id_peya", String(255)),
    Column("is_active", Boolean),
    Column("created_at", DateTime),
    Column("modified_at", DateTime),
)

# SKU de peya_sku con promoción: la sola presencia de la fila es la promoción.
_peya_pe_promotions = Table(
    "peya_promo_sku",
    _metadata,
    Column("sku", String(255), primary_key=True),
)


class Country(StrEnum):
    PE = "pe"
    MX = "mx"


class Provider(StrEnum):
    RAPPI = "rappi"
    PEYA = "peya"


@dataclass(frozen=True)
class Channel:
    country: Country
    provider: Provider
    name: str
    table: Table
    external_id: Column  # Id del SKU en la plataforma del proveedor.
    updated_at: Column  # Cada tabla nombra distinto su fecha de modificación.
    promotions: Table | None = None  # Solo los canales con promociones.


_CHANNELS = (
    Channel(Country.PE, Provider.RAPPI, "Rappi Perú", _rappi_pe, _rappi_pe.c.id_rappi, _rappi_pe.c.updated_at),
    Channel(Country.MX, Provider.RAPPI, "Rappi México", _rappi_mx, _rappi_mx.c.id_rappi, _rappi_mx.c.updated_at),
    Channel(
        Country.PE,
        Provider.PEYA,
        "PedidosYa Perú",
        _peya_pe,
        _peya_pe.c.id_peya,
        _peya_pe.c.modified_at,
        promotions=_peya_pe_promotions,
    ),
)
CHANNELS = {(channel.country, channel.provider): channel for channel in _CHANNELS}
