from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, fetch_areas, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_ADMIN, CAN_VIEW
from app.schemas.cost_centers import (
    AreaRef,
    CostCenterMappingCreate,
    CostCenterMappingImport,
    CostCenterMappingImportResult,
    CostCenterMappingOut,
    CostCenterMappingUpdate,
    CostCenterOut,
)
from app.services.cost_center_service import CostCenterService
from app.services.errors import InvalidDataError

# Homologación de centros de costo a áreas de auth: decide qué líneas ve un
# usuario con ledger.view de alcance area. Ver: ledger.view (company).
# Crear, cambiar, dar de baja e importar: ledger.admin (decide quién ve qué).
router = APIRouter(tags=["cost-centers"])
can_view = require_company_permission(*CAN_VIEW)
can_admin = require_company_permission(*CAN_ADMIN)


def _resolve(ref: AreaRef, areas: dict[str, dict], row: str = "") -> dict:
    """Área activa de la empresa según auth, por código (sin mayúsculas) o id."""
    if ref.area_id:
        area = areas.get(ref.area_id)
    else:
        wanted = ref.area_code.casefold()
        area = next((a for a in areas.values() if a["code"].casefold() == wanted), None)
    if area is None or not area.get("is_active", True):
        raise InvalidDataError(f"{row}área {ref.area_code or ref.area_id} no existe o no está activa en la empresa.")
    return area


@router.get("/cost-centers", response_model=list[CostCenterOut], operation_id="listCostCenters")
def list_cost_centers(unmapped: bool = False, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """Centros de costo que aparecen en las líneas sincronizadas, con su área. unmapped=true: solo los que faltan."""
    return CostCenterService(db).centers(ctx.company_id, unmapped_only=unmapped)


@router.get("/cost-center-mappings", response_model=list[CostCenterMappingOut], operation_id="listCostCenterMappings")
def list_mappings(include_inactive: bool = False, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return CostCenterService(db).list(ctx.company_id, include_inactive=include_inactive)


@router.post(
    "/cost-center-mappings", response_model=CostCenterMappingOut, status_code=status.HTTP_201_CREATED,
    operation_id="createCostCenterMapping",
)
def create_mapping(body: CostCenterMappingCreate, ctx: CompanyContext = Depends(can_admin), db: Session = Depends(get_db)):
    """match_mode exact | prefix. 409 si ese código y modo ya están homologados; 422 si el área no existe en auth."""
    area = _resolve(body, fetch_areas(ctx))
    return CostCenterService(db).create(
        company_id=ctx.company_id, user_id=ctx.user_id, cost_center_code=body.cost_center_code,
        match_mode=body.match_mode, area=area,
    )


@router.post(
    "/cost-center-mappings/import", response_model=CostCenterMappingImportResult,
    operation_id="importCostCenterMappings",
)
def import_mappings(body: CostCenterMappingImport, ctx: CompanyContext = Depends(can_admin), db: Session = Depends(get_db)):
    """Carga masiva (todo o nada). dry_run=true muestra qué pasaría sin guardar."""
    areas = fetch_areas(ctx)
    items = [
        (m.cost_center_code, m.match_mode, _resolve(m, areas, f"fila {i}: ")) for i, m in enumerate(body.mappings, start=1)
    ]
    return CostCenterService(db).import_(
        company_id=ctx.company_id, user_id=ctx.user_id, mode=body.mode, dry_run=body.dry_run, items=items
    )


@router.patch("/cost-center-mappings/{mapping_id}", response_model=CostCenterMappingOut, operation_id="updateCostCenterMapping")
def update_mapping(
    mapping_id: str, body: CostCenterMappingUpdate, ctx: CompanyContext = Depends(can_admin), db: Session = Depends(get_db)
):
    area = _resolve(body, fetch_areas(ctx))
    return CostCenterService(db).update(company_id=ctx.company_id, user_id=ctx.user_id, mapping_id=mapping_id, area=area)


@router.delete(
    "/cost-center-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    operation_id="deleteCostCenterMapping",
)
def delete_mapping(mapping_id: str, ctx: CompanyContext = Depends(can_admin), db: Session = Depends(get_db)):
    """Baja lógica: las líneas de ese centro vuelven a verse solo con alcance company."""
    CostCenterService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, mapping_id=mapping_id)
