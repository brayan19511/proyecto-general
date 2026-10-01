from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_UPDATE, CAN_VIEW
from app.schemas.accounts import not_null_changes
from app.schemas.page import Page
from app.schemas.rules import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ClassificationRunCreate,
    ClassificationRunOut,
    RuleCreate,
    RuleImportRequest,
    RuleImportResult,
    RuleOut,
    RuleUpdate,
)
from app.services.category_service import CategoryService
from app.services.classification_service import ClassificationService
from app.services.rule_import_service import RuleImportService
from app.services.rule_service import RuleService

# Categorías, reglas y reclasificaciones de la empresa activa (X-Company-Id).
# Ver: ledger.view (o superior). Crear, editar, dar de baja, importar y
# reclasificar: ledger.update (o ledger.admin). Alcance company.
router = APIRouter(tags=["rules"])
can_view = require_company_permission(*CAN_VIEW)
can_update = require_company_permission(*CAN_UPDATE)


# --- Categorías ---


@router.get("/categories", response_model=list[CategoryOut], operation_id="listCategories")
def list_categories(include_inactive: bool = False, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return CategoryService(db).list(ctx.company_id, include_inactive=include_inactive)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, operation_id="createCategory")
def create_category(body: CategoryCreate, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Sin parent_id: categoría. Con parent_id: subcategoría (solo dos niveles).
    409 si ya hay una activa con ese nombre en el mismo nivel."""
    return CategoryService(db).create(
        company_id=ctx.company_id, user_id=ctx.user_id, name=body.name, parent_id=body.parent_id
    )


@router.get("/categories/{category_id}", response_model=CategoryOut, operation_id="getCategory")
def get_category(category_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return CategoryService(db).get(ctx.company_id, category_id)


@router.patch("/categories/{category_id}", response_model=CategoryOut, operation_id="updateCategory")
def update_category(
    category_id: str, body: CategoryUpdate, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)
):
    return CategoryService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, category_id=category_id,
        changes=body.model_dump(),
    )


@router.delete(
    "/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    operation_id="deleteCategory",
)
def delete_category(category_id: str, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Baja lógica. 409 si tiene subcategorías o reglas activas."""
    CategoryService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, category_id=category_id)


# --- Reglas ---


@router.get("/rules", response_model=list[RuleOut], operation_id="listRules")
def list_rules(include_inactive: bool = False, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """En orden de evaluación (priority, id): gana la primera que cumple."""
    return RuleService(db).list(ctx.company_id, include_inactive=include_inactive)


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, operation_id="createRule")
def create_rule(body: RuleCreate, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Registra además una reclasificación de las líneas afectadas (la hace el worker)."""
    return RuleService(db).create(company_id=ctx.company_id, user_id=ctx.user_id, values=body.model_dump())


@router.post("/rules/import", response_model=RuleImportResult, operation_id="importRules")
def import_rules(body: RuleImportRequest, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Carga masiva en una transacción (todo o nada). Categorías por nombre: se crean si faltan.

    mode=replace da de baja las reglas activas y crea estas (sin borrar filas);
    mode=append solo agrega. dry_run=true muestra qué pasaría sin guardar.
    Al final registra una reclasificación de todas las líneas (la hace el worker).
    """
    return RuleImportService(db).run(
        company_id=ctx.company_id, user_id=ctx.user_id, mode=body.mode, dry_run=body.dry_run,
        rules=[rule.model_dump() for rule in body.rules],
    )


@router.get("/rules/{rule_id}", response_model=RuleOut, operation_id="getRule")
def get_rule(rule_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return RuleService(db).get(ctx.company_id, rule_id)


@router.patch("/rules/{rule_id}", response_model=RuleOut, operation_id="updateRule")
def update_rule(rule_id: str, body: RuleUpdate, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Solo cambian los campos enviados; si algo cambia, registra una reclasificación."""
    return RuleService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, rule_id=rule_id,
        changes=not_null_changes(body, "priority", "category_id"),
    )


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteRule"
)
def delete_rule(rule_id: str, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)):
    """Baja lógica; sus líneas se reclasifican con las reglas que quedan."""
    RuleService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, rule_id=rule_id)


# --- Reclasificaciones ---


@router.post(
    "/classification-runs", response_model=ClassificationRunOut, status_code=status.HTTP_202_ACCEPTED,
    operation_id="createClassificationRun",
)
def create_classification_run(
    body: ClassificationRunCreate, ctx: CompanyContext = Depends(can_update), db: Session = Depends(get_db)
):
    """Reclasifica las líneas sincronizadas (todas o un rango) con las reglas activas. La hace el worker."""
    return ClassificationService(db).request(
        company_id=ctx.company_id, user_id=ctx.user_id, date_from=body.date_from, date_to=body.date_to
    )


@router.get("/classification-runs", response_model=list[ClassificationRunOut], operation_id="listClassificationRuns")
def list_classification_runs(page: Page = Depends(), ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return ClassificationService(db).list(ctx.company_id, limit=page.limit, offset=page.offset)


@router.get("/classification-runs/{run_id}", response_model=ClassificationRunOut, operation_id="getClassificationRun")
def get_classification_run(run_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    return ClassificationService(db).get(ctx.company_id, run_id)
