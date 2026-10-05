"""Rutas de lastmiller: /canales-venta/lastmiller/...

Permisos (acumulativos, en la empresa dueña de lastmiller; ver
require_lastmiller en app/api/dependencies.py):
- view: canales, SKU, historial y cargas.
- edit: alta, on/off, baja y promoción de un SKU.
- import: vista previa y aplicación de cargas masivas.
"""

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_lastmiller
from app.core.db.connection import get_db
from app.core.permissions import CAN_EDIT, CAN_IMPORT, CAN_VIEW
from app.lastmiller import sku_repository, sku_service
from app.lastmiller.channels import CHANNELS, Channel, Country, Provider
from app.lastmiller.excel_reader import MAX_FILE_BYTES
from app.models.entities import SkuImport
from app.schemas.lastmiller import (
    ChannelOut,
    EventPage,
    ImportKind,
    ImportOut,
    ImportPage,
    ImportSummaryOut,
    SkuCreate,
    SkuOut,
    SkuPage,
    SkuUpdate,
)
from app.schemas.page import Page
from app.services.errors import InvalidDataError, NotFoundError
from app.services.csv_export import csv_response

router = APIRouter(prefix="/lastmiller", tags=["lastmiller"])

CHANNEL_PATH = "/{country}/{provider}"


def get_channel(country: Country, provider: Provider) -> Channel:
    channel = CHANNELS.get((country, provider))
    if channel is None:
        raise NotFoundError(f"No existe el canal {provider.value} en {country.value}.")
    return channel


def _import_out(record: SkuImport) -> ImportOut:
    return ImportOut(
        **ImportSummaryOut.model_validate(record).model_dump(),
        errors=record.errors,
        plan=record.plan,
        can_apply=record.status == "previewed" and not record.plan.get("blocking") and record.total_changes > 0,
    )


@router.get("/channels", response_model=list[ChannelOut], operation_id="listChannels")
def list_channels(_: CompanyContext = Depends(require_lastmiller(*CAN_VIEW))):
    """Canales configurados. No consulta Ofisis."""
    return [
        ChannelOut(
            country=channel.country,
            provider=channel.provider,
            name=channel.name,
            has_promotions=channel.promotions is not None,
        )
        for channel in CHANNELS.values()
    ]


# --- SKU


@router.get(f"{CHANNEL_PATH}/skus", response_model=SkuPage, operation_id="listSkus")
def list_skus(
    search: str | None = Query(default=None, max_length=255, description="Contiene el texto en sku o id externo."),
    active: bool | None = Query(default=None, description="true = activos; false = inactivos; vacío = todos."),
    promotion: bool | None = Query(default=None, description="Solo canales con promociones (PedidosYa)."),
    page: Page = Depends(),
    channel: Channel = Depends(get_channel),
    _: CompanyContext = Depends(require_lastmiller(*CAN_VIEW)),
):
    if promotion is not None and channel.promotions is None:
        raise InvalidDataError(f"{channel.name} no maneja promociones.")
    items, total = sku_repository.list_skus(
        channel,
        search=(search or "").strip() or None,
        active=active,
        promotion=promotion,
        limit=page.limit,
        offset=page.offset,
    )
    return SkuPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total), items=items)


@router.get(f"{CHANNEL_PATH}/skus/export", operation_id="exportSkus",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_skus(
    search: str | None = Query(default=None, max_length=255),
    active: bool | None = None,
    promotion: bool | None = None,
    channel: Channel = Depends(get_channel),
    _: CompanyContext = Depends(require_lastmiller(*CAN_VIEW)),
):
    """Consolidado en CSV: todos los SKU que cumplen los filtros (sin paginar). Fechas de
    Ofisis tal como están (hora del servidor de Ofisis)."""
    if promotion is not None and channel.promotions is None:
        raise InvalidDataError(f"{channel.name} no maneja promociones.")
    items, _total = sku_repository.list_skus(
        channel, search=(search or "").strip() or None, active=active, promotion=promotion, limit=None, offset=0
    )
    headers = ["SKU", "ID externo", "Estado"] + (["Promoción"] if channel.promotions is not None else []) + ["Creado", "Modificado"]
    rows = (
        [s["sku"], s["external_id"], "On" if s["is_active"] else "Off"]
        + (["Sí" if s["has_promotion"] else "No"] if channel.promotions is not None else [])
        + [s["created_at"], s["updated_at"]]
        for s in items
    )
    # Sin fecha en el nombre: el contenedor está en UTC y podría mostrar otro día que en Lima.
    return csv_response(f"skus-{channel.country.value}-{channel.provider.value}.csv", headers, rows)


@router.post(f"{CHANNEL_PATH}/skus", response_model=SkuOut, status_code=status.HTTP_201_CREATED, operation_id="createSku")
def create_sku(
    data: SkuCreate,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_EDIT)),
    db: Session = Depends(get_db),
):
    """Alta de un SKU; su id externo es el mismo sku."""
    return sku_service.create_sku(db, ctx, channel, data.sku, data.is_active)


@router.patch(f"{CHANNEL_PATH}/skus/{{sku}}", response_model=SkuOut, operation_id="updateSku")
def update_sku(
    sku: str,
    data: SkuUpdate,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_EDIT)),
    db: Session = Depends(get_db),
):
    """On/off de un SKU."""
    return sku_service.set_sku_active(db, ctx, channel, sku, data.is_active)


@router.delete(f"{CHANNEL_PATH}/skus/{{sku}}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteSku")
def delete_sku(
    sku: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_EDIT)),
    db: Session = Depends(get_db),
):
    """Elimina el SKU de Ofisis (la tabla es de lastmiller, ver readme). El cambio
    queda en el historial. Con promoción: 409 (quitarla antes)."""
    sku_service.delete_sku(db, ctx, channel, sku)


@router.post(f"{CHANNEL_PATH}/skus/{{sku}}/promotion", response_model=SkuOut, operation_id="addSkuPromotion")
def add_promotion(
    sku: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_EDIT)),
    db: Session = Depends(get_db),
):
    """Agrega la promoción al SKU (solo PedidosYa). Si ya la tiene, no cambia nada."""
    return sku_service.set_promotion(db, ctx, channel, sku, True)


@router.delete(f"{CHANNEL_PATH}/skus/{{sku}}/promotion", response_model=SkuOut, operation_id="removeSkuPromotion")
def remove_promotion(
    sku: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_EDIT)),
    db: Session = Depends(get_db),
):
    """Quita la promoción del SKU (solo PedidosYa)."""
    return sku_service.set_promotion(db, ctx, channel, sku, False)


# --- Cargas masivas


@router.post(f"{CHANNEL_PATH}/imports/preview", response_model=ImportOut, status_code=status.HTTP_201_CREATED,
             operation_id="previewImport")
def preview_import(
    kind: ImportKind = Form(description="sku_full (completa), sku_partial (parcial) o promotions (solo PedidosYa)."),
    create_missing: bool = Form(default=True, description="Crear los SKU del archivo que no existen (cargas de SKU)."),
    file: UploadFile = File(description=".xlsx con columna sku y, según el tipo, on/off."),
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_IMPORT)),
    db: Session = Depends(get_db),
):
    """Lee el archivo y muestra qué cambiaría. No modifica Ofisis: se aplica después
    con POST /imports/{id}/apply."""
    content = file.file.read(MAX_FILE_BYTES + 1)
    record = sku_service.preview_import(
        db, ctx, channel, kind=kind, create_missing=create_missing, content=content, filename=file.filename
    )
    return _import_out(record)


@router.post(f"{CHANNEL_PATH}/imports/{{import_id}}/apply", response_model=ImportOut, operation_id="applyImport")
def apply_import(
    import_id: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_IMPORT)),
    db: Session = Depends(get_db),
):
    """Aplica una vista previa. Si los datos del canal cambiaron desde entonces: 409."""
    return _import_out(sku_service.apply_import(db, ctx, channel, import_id))


@router.post(f"{CHANNEL_PATH}/imports/{{import_id}}/cancel", response_model=ImportOut, operation_id="cancelImport")
def cancel_import(
    import_id: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_IMPORT)),
    db: Session = Depends(get_db),
):
    """Descarta una vista previa sin aplicarla. Queda registrada como "cancelled"."""
    return _import_out(sku_service.cancel_import(db, ctx, channel, import_id))


@router.get(f"{CHANNEL_PATH}/imports", response_model=ImportPage, operation_id="listImports")
def list_imports(
    page: Page = Depends(),
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = sku_service.list_imports(db, ctx, channel, page.limit, page.offset)
    return ImportPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total), items=items)


@router.get(f"{CHANNEL_PATH}/imports/{{import_id}}", response_model=ImportOut, operation_id="getImport")
def get_import(
    import_id: str,
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_VIEW)),
    db: Session = Depends(get_db),
):
    return _import_out(sku_service.get_import(db, ctx, channel, import_id))


# --- Historial


@router.get(f"{CHANNEL_PATH}/history", response_model=EventPage, operation_id="listSkuHistory")
def list_history(
    sku: str | None = Query(default=None, max_length=255, description="Solo este SKU (exacto)."),
    import_id: str | None = Query(default=None, max_length=36, description="Solo los cambios de esta carga."),
    page: Page = Depends(),
    channel: Channel = Depends(get_channel),
    ctx: CompanyContext = Depends(require_lastmiller(*CAN_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = sku_service.list_events(
        db, ctx, channel, sku=sku, import_id=import_id, limit=page.limit, offset=page.offset
    )
    return EventPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total), items=items)
