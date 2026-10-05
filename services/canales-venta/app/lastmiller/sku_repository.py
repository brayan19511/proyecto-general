"""Consultas y escrituras de SKU en Ofisis. Todo el SQL de SKU vive aquí.

Lecturas: cada una abre y cierra su propia conexión (ofisis_read); dentro del
`with` solo se ejecuta el SQL, la conversión a dicts ocurre después.
Escrituras: reciben una conexión con una transacción ya abierta por quien
llama (ofisis_write + connection.begin()), que decide el tamaño del lote.

Las comparaciones de sku no distinguen mayúsculas ni espacios finales: lo
decide la collation de Ofisis (CI), igual que su clave primaria.
"""

from sqlalchemy import Connection, case, delete, exists, false, func, insert, literal, null, or_, select, update

from app.external.ofisis import ofisis_read
from app.lastmiller.channels import Channel


def list_skus(
    channel: Channel,
    *,
    search: str | None,
    active: bool | None,
    promotion: bool | None,
    limit: int | None,
    offset: int,
) -> tuple[list[dict], int]:
    """Una página de SKU ordenada por sku y el total que cumple los filtros.

    - search: contiene el texto en sku o en el id externo. CHARINDEX en lugar
      de LIKE: así %, _ y [ del usuario no actúan como comodines.
      Sin distinguir mayúsculas (lo decide la collation de Ofisis, CI).
    - active: is_active NULL cuenta como inactivo.
    - promotion: solo canales con tabla de promociones (lo valida la ruta).
    """
    table = channel.table
    conditions = []
    if search:
        conditions.append(
            or_(
                func.charindex(search, table.c.sku) > 0,
                func.charindex(search, channel.external_id) > 0,
            )
        )
    if active is not None:
        conditions.append(func.coalesce(table.c.is_active, false()) == active)

    if channel.promotions is not None:
        has_promotion = exists().where(channel.promotions.c.sku == table.c.sku)
        promotion_column = case((has_promotion, literal(True)), else_=literal(False))
        if promotion is not None:
            conditions.append(has_promotion if promotion else ~has_promotion)
    else:
        promotion_column = null()

    count_query = select(func.count()).select_from(table).where(*conditions)
    page_query = (
        select(
            table.c.sku,
            channel.external_id.label("external_id"),
            table.c.is_active,
            table.c.created_at,
            channel.updated_at.label("updated_at"),
            promotion_column.label("has_promotion"),
        )
        .where(*conditions)
        .order_by(table.c.sku)
    )
    if limit is not None:  # None = todos (descarga); los canales tienen pocos miles de SKU.
        page_query = page_query.limit(limit).offset(offset)

    with ofisis_read() as connection:
        total = connection.execute(count_query).scalar_one()
        rows = connection.execute(page_query).mappings().all()

    items = [
        {
            **row,
            "is_active": bool(row["is_active"]),
            "has_promotion": None if row["has_promotion"] is None else bool(row["has_promotion"]),
        }
        for row in rows
    ]
    return items, total


def get_sku(channel: Channel, sku: str) -> dict | None:
    """Un SKU con su estado y, en canales con promociones, si tiene promoción."""
    table = channel.table
    if channel.promotions is not None:
        has_promotion = exists().where(channel.promotions.c.sku == table.c.sku)
        promotion_column = case((has_promotion, literal(True)), else_=literal(False))
    else:
        promotion_column = null()
    query = select(
        table.c.sku,
        channel.external_id.label("external_id"),
        table.c.is_active,
        table.c.created_at,
        channel.updated_at.label("updated_at"),
        promotion_column.label("has_promotion"),
    ).where(table.c.sku == sku)
    with ofisis_read() as connection:
        row = connection.execute(query).mappings().first()
    if row is None:
        return None
    return {
        **row,
        "is_active": bool(row["is_active"]),
        "has_promotion": None if row["has_promotion"] is None else bool(row["has_promotion"]),
    }


def current_states(channel: Channel) -> dict[str, tuple[str, bool]]:
    """Todos los SKU del canal: {sku normalizado: (sku tal como está, activo)}.

    Normalizado = sin espacios extremos y en minúsculas (casefold), para
    comparar igual que la collation de Ofisis.
    """
    query = select(channel.table.c.sku, channel.table.c.is_active)
    with ofisis_read() as connection:
        rows = connection.execute(query).all()
    return {normalize(sku): (sku, bool(active)) for sku, active in rows}


def promotion_skus(channel: Channel) -> dict[str, str]:
    """SKU con promoción: {sku normalizado: sku tal como está}."""
    query = select(channel.promotions.c.sku)
    with ofisis_read() as connection:
        rows = connection.execute(query).scalars().all()
    return {normalize(sku): sku for sku in rows}


def normalize(sku: str) -> str:
    return sku.strip().casefold()


# --- Escrituras (dentro de la transacción de quien llama)


def insert_skus(connection: Connection, channel: Channel, items: list[tuple[str, bool]]) -> None:
    """Alta de SKU. El id externo es el mismo sku (acuerdo del usuario, 2026-10-04).
    Las fechas las pone Ofisis (default getdate())."""
    if not items:
        return
    connection.execute(
        insert(channel.table),
        [{"sku": sku, channel.external_id.name: sku, "is_active": active} for sku, active in items],
    )


def set_active(connection: Connection, channel: Channel, skus: list[str], active: bool) -> int:
    """On/off de varios SKU. La fecha de modificación es la del servidor de Ofisis."""
    if not skus:
        return 0
    result = connection.execute(
        update(channel.table)
        .where(channel.table.c.sku.in_(skus))
        .values({"is_active": active, channel.updated_at.name: func.getdate()})
    )
    return result.rowcount


def delete_sku(connection: Connection, channel: Channel, sku: str) -> int:
    """Borrado real en Ofisis (opción a: estado externo de lastmiller). El
    evento queda en el historial propio."""
    return connection.execute(delete(channel.table).where(channel.table.c.sku == sku)).rowcount


def add_promotions(connection: Connection, channel: Channel, skus: list[str]) -> None:
    if skus:
        connection.execute(insert(channel.promotions), [{"sku": sku} for sku in skus])


def remove_promotions(connection: Connection, channel: Channel, skus: list[str]) -> int:
    if not skus:
        return 0
    return connection.execute(delete(channel.promotions).where(channel.promotions.c.sku.in_(skus))).rowcount
