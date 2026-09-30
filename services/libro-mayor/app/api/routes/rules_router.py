from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import RULES_MANAGE
from app.schemas.accounts import not_null_changes
from app.schemas.page import Page
from app.schemas.rules import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ClassificationRunCreate,
    ClassificationRunOut,
    RuleCreate,
    RuleOut,
    RuleUpdate,
)
from app.services.category_service import CategoryService
from app.services.classification_service import ClassificationService
from app.services.rule_service import RuleService

# Categorías, reglas y reclasificaciones de la empresa activa (X-Company-Id).
# Exige ledger.rules.manage con alcance company (o administrador de plataforma).
router = APIRouter(tags=["rules"])
can_manage = require_company_permission(RULES_MANAGE)


# --- Categorías ---


@router.get("/categories", response_model=list[CategoryOut], operation_id="listCategories")
def list_categories(include_inactive: bool = False, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    return CategoryService(db).list(ctx.company_id, include_inactive=include_inactive)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, operation_id="createCategory")
def create_category(body: CategoryCreate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Sin parent_id: categoría. Con parent_id: subcategoría (solo dos niveles). 409 si el código ya existe."""
    return CategoryService(db).create(
        company_id=ctx.company_id, user_id=ctx.user_id, code=body.code, name=body.name, parent_id=body.parent_id
    )


@router.get("/categories/{category_id}", response_model=CategoryOut, operation_id="getCategory")
def get_category(category_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    return CategoryService(db).get(ctx.company_id, category_id)


@router.patch("/categories/{category_id}", response_model=CategoryOut, operation_id="updateCategory")
def update_category(
    category_id: str, body: CategoryUpdate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return CategoryService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, category_id=category_id,
        changes=not_null_changes(body, "code", "name"),
    )


@router.delete(
    "/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    operation_id="deleteCategory",
)
def delete_category(category_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Baja lógica. 409 si tiene subcategorías o reglas activas."""
    CategoryService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, category_id=category_id)


# --- Reglas ---


@router.get("/rules", response_model=list[RuleOut], operation_id="listRules")
def list_rules(include_inactive: bool = False, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """En orden de evaluación (priority, id): gana la primera que cumple."""
    return RuleService(db).list(ctx.company_id, include_inactive=include_inactive)


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, operation_id="createRule")
def create_rule(body: RuleCreate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Registra además una reclasificación de las líneas afectadas (la hace el worker)."""
    return RuleService(db).create(company_id=ctx.company_id, user_id=ctx.user_id, values=body.model_dump())


@router.get("/rules/{rule_id}", response_model=RuleOut, operation_id="getRule")
def get_rule(rule_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    return RuleService(db).get(ctx.company_id, rule_id)


@router.patch("/rules/{rule_id}", response_model=RuleOut, operation_id="updateRule")
def update_rule(rule_id: str, body: RuleUpdate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Solo cambian los campos enviados; si algo cambia, registra una reclasificación."""
    return RuleService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, rule_id=rule_id,
        changes=not_null_changes(body, "priority", "category_id"),
    )


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteRule"
)
def delete_rule(rule_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Baja lógica; sus líneas se reclasifican con las reglas que quedan."""
    RuleService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, rule_id=rule_id)


# --- Reclasificaciones ---


@router.post(
    "/classification-runs", response_model=ClassificationRunOut, status_code=status.HTTP_202_ACCEPTED,
    operation_id="createClassificationRun",
)
def create_classification_run(
    body: ClassificationRunCreate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)
):
    """Reclasifica las líneas sincronizadas (todas o un rango) con las reglas activas. La hace el worker."""
    return ClassificationService(db).request(
        company_id=ctx.company_id, user_id=ctx.user_id, date_from=body.date_from, date_to=body.date_to
    )


@router.get("/classification-runs", response_model=list[ClassificationRunOut], operation_id="listClassificationRuns")
def list_classification_runs(page: Page = Depends(), ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    return ClassificationService(db).list(ctx.company_id, limit=page.limit, offset=page.offset)


@router.get("/classification-runs/{run_id}", response_model=ClassificationRunOut, operation_id="getClassificationRun")
def get_classification_run(run_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    return ClassificationService(db).get(ctx.company_id, run_id)
