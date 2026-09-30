"""Categorías de gasto (libro_mayor.expense_categories), dos niveles por empresa."""

from platform_audit import step
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import ExpenseCategory, ExpenseRule
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change


def _snapshot(category: ExpenseCategory) -> dict:
    return {"code": category.code, "name": category.name, "parent_id": category.parent_id}


class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool = False) -> list[ExpenseCategory]:
        with self.db.begin():
            query = select(ExpenseCategory).where(ExpenseCategory.company_id == company_id)
            if not include_inactive:
                query = query.where(ExpenseCategory.is_active.is_(True))
            return list(self.db.scalars(query.order_by(ExpenseCategory.code)))

    def get(self, company_id: str, category_id: str) -> ExpenseCategory:
        with self.db.begin():
            category = self._find(company_id, category_id, active_only=False)
        if category is None:
            raise NotFoundError("Categoría no encontrada.")
        return category

    def create(self, *, company_id: str, user_id: str, code: str, name: str, parent_id: str | None) -> ExpenseCategory:
        code, name = _required("code", code), _required("name", name)
        try:
            with step("category.create"), self.db.begin():
                if parent_id is not None:
                    parent = self._find(company_id, parent_id)
                    if parent is None:
                        raise NotFoundError("Categoría padre no encontrada.")
                    if parent.parent_id is not None:
                        raise InvalidDataError("Solo hay dos niveles: el padre no puede ser una subcategoría.")
                self._check_code_free(company_id, code)
                actor_id = user_actor_id(self.db, user_id)
                now = utcnow()
                category = ExpenseCategory(
                    company_id=company_id, parent_id=parent_id, code=code, name=name, created_at=now, created_by=actor_id
                )
                self.db.add(category)
                self.db.flush()
                record_change(
                    self.db, action="category.create", resource_type="category", resource_id=category.id,
                    company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(category),
                )
        except IntegrityError:
            raise ConflictError("Ya existe una categoría activa con ese código.") from None
        return category

    def update(self, *, company_id: str, user_id: str, category_id: str, changes: dict) -> ExpenseCategory:
        """Cambia code y/o name. No cambia de nivel ni de padre (dar de baja y crear otra)."""
        try:
            with step("category.update"), self.db.begin():
                category = self._find(company_id, category_id, lock=True)
                if category is None:
                    raise NotFoundError("Categoría no encontrada.")
                before = _snapshot(category)
                if "code" in changes:
                    code = _required("code", changes["code"])
                    if code != category.code:
                        self._check_code_free(company_id, code)
                        category.code = code
                if "name" in changes:
                    category.name = _required("name", changes["name"])
                after = _snapshot(category)
                if after == before:
                    return category
                actor_id = user_actor_id(self.db, user_id)
                now = utcnow()
                category.updated_at, category.updated_by = now, actor_id
                record_change(
                    self.db, action="category.update", resource_type="category", resource_id=category.id,
                    company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
                )
        except IntegrityError:
            raise ConflictError("Ya existe una categoría activa con ese código.") from None
        return category

    def deactivate(self, *, company_id: str, user_id: str, category_id: str) -> None:
        """Baja lógica. 409 si tiene subcategorías o reglas activas: darlas de baja o moverlas antes."""
        with step("category.delete"), self.db.begin():
            category = self._find(company_id, category_id, lock=True)
            if category is None:
                raise NotFoundError("Categoría no encontrada.")
            if self.db.scalar(
                select(ExpenseCategory.id).where(
                    ExpenseCategory.parent_id == category.id, ExpenseCategory.is_active.is_(True)
                ).limit(1)
            ):
                raise ConflictError("La categoría tiene subcategorías activas.")
            if self.db.scalar(
                select(ExpenseRule.id).where(ExpenseRule.category_id == category.id, ExpenseRule.is_active.is_(True)).limit(1)
            ):
                raise ConflictError("La categoría tiene reglas activas.")
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            category.is_active = False
            category.deleted_at = category.updated_at = now
            category.deleted_by = category.updated_by = actor_id
            record_change(
                self.db, action="category.delete", resource_type="category", resource_id=category.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(category), after={},
            )

    def _find(self, company_id: str, category_id: str, active_only: bool = True, lock: bool = False):
        query = select(ExpenseCategory).where(ExpenseCategory.id == category_id, ExpenseCategory.company_id == company_id)
        if active_only:
            query = query.where(ExpenseCategory.is_active.is_(True))
        if lock:
            query = query.with_for_update()
        return self.db.scalar(query)

    def _check_code_free(self, company_id: str, code: str) -> None:
        if self.db.scalar(
            select(ExpenseCategory.id).where(
                ExpenseCategory.company_id == company_id, ExpenseCategory.code == code, ExpenseCategory.is_active.is_(True)
            )
        ):
            raise ConflictError("Ya existe una categoría activa con ese código.")


def _required(name: str, value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        raise InvalidDataError(f"{name} no puede estar vacío.")
    return value
