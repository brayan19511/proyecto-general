"""Compañía SAP de cada empresa (libro_mayor.sap_companies).

Solo la administra el administrador de plataforma. sap_schema y source_view se
usarán como identificadores SQL al consultar HANA, por eso se validan aquí con
una lista cerrada de caracteres antes de guardarlos.
"""

import re
from datetime import date

from platform_audit import step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import SapCompany
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change
from app.services.ledger_lines import has_lines

# Letra o _ inicial, luego letras, dígitos o _. Sin comillas, puntos ni espacios.
SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _snapshot(company: SapCompany) -> dict:
    return {
        "sap_schema": company.sap_schema,
        "source_view": company.source_view,
        "sync_start_date": company.sync_start_date.isoformat(),
    }


class SapCompanyService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, company_id: str) -> SapCompany:
        with self.db.begin():
            company = active_sap_company(self.db, company_id)
        if company is None:
            raise NotFoundError("La empresa no tiene compañía SAP configurada.")
        return company

    def create(
        self, *, company_id: str, user_id: str, sap_schema: str, source_view: str, sync_start_date: date
    ) -> SapCompany:
        sap_schema, source_view = validate_identifier("sap_schema", sap_schema), validate_identifier("source_view", source_view)
        with step("sap_company.create"), self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            return add_sap_company(
                self.db, company_id=company_id, actor_id=actor_id, now=utcnow(),
                sap_schema=sap_schema, source_view=source_view, sync_start_date=sync_start_date,
            )

    def update(self, *, company_id: str, user_id: str, changes: dict) -> SapCompany:
        """Modifica solo los campos enviados (sap_schema, source_view, sync_start_date).

        source_view y sync_start_date se cambian siempre (sync_start_date solo
        afecta a las primeras cargas futuras). sap_schema es el origen de los
        datos: solo se cambia si la empresa aún no tiene líneas sincronizadas;
        si ya las tiene, las líneas vendrían de dos compañías SAP distintas.
        """
        with step("sap_company.update"), self.db.begin():
            company = active_sap_company(self.db, company_id, lock=True)
            if company is None:
                raise NotFoundError("La empresa no tiene compañía SAP configurada.")
            before = _snapshot(company)
            if "sap_schema" in changes:
                sap_schema = validate_identifier("sap_schema", changes["sap_schema"])
                if sap_schema != company.sap_schema:
                    if has_lines(self.db, company_id=company_id):
                        raise ConflictError("La empresa ya tiene líneas sincronizadas: no se puede cambiar el schema SAP.")
                    if self.db.scalar(
                        select(SapCompany.id).where(SapCompany.sap_schema == sap_schema, SapCompany.is_active.is_(True))
                    ):
                        raise ConflictError("Ese schema SAP ya está asignado a otra empresa.")
                    company.sap_schema = sap_schema
            if "source_view" in changes:
                company.source_view = validate_identifier("source_view", changes["source_view"])
            if "sync_start_date" in changes:
                company.sync_start_date = changes["sync_start_date"]
            after = _snapshot(company)
            if after == before:
                return company  # Sin cambios: ni actualización ni historial.
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            company.updated_at, company.updated_by = now, actor_id
            record_change(
                self.db, action="sap_company.update", resource_type="sap_company", resource_id=company.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return company

    def deactivate(self, *, company_id: str, user_id: str) -> None:
        """Baja lógica. Las cuentas y líneas se conservan; sin compañía activa no se sincroniza."""
        with step("sap_company.delete"), self.db.begin():
            company = active_sap_company(self.db, company_id, lock=True)
            if company is None:
                raise NotFoundError("La empresa no tiene compañía SAP configurada.")
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            company.is_active = False
            company.deleted_at = company.updated_at = now
            company.deleted_by = company.updated_by = actor_id
            record_change(
                self.db, action="sap_company.delete", resource_type="sap_company", resource_id=company.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(company), after={},
            )


def validate_identifier(name: str, value: str) -> str:
    value = value.strip()
    if not SQL_IDENTIFIER.fullmatch(value):
        raise InvalidDataError(f"{name}: solo letras, dígitos y _ (sin empezar por dígito).")
    return value


def active_sap_company(db: Session, company_id: str, lock: bool = False) -> SapCompany | None:
    query = select(SapCompany).where(SapCompany.company_id == company_id, SapCompany.is_active.is_(True))
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def add_sap_company(
    db: Session, *, company_id: str, actor_id: str, now, sap_schema: str, source_view: str, sync_start_date: date
) -> SapCompany:
    """Inserta una compañía SAP ya validada, con su historial, en la transacción en curso."""
    if active_sap_company(db, company_id) is not None:
        raise ConflictError("La empresa ya tiene una compañía SAP activa; dala de baja primero.")
    if db.scalar(select(SapCompany.id).where(SapCompany.sap_schema == sap_schema, SapCompany.is_active.is_(True))):
        raise ConflictError("Ese schema SAP ya está asignado a otra empresa.")
    # Si dos solicitudes pasan estas comprobaciones a la vez, los índices únicos
    # activos rechazan la segunda (error 500 genérico, sin datos).
    company = SapCompany(
        company_id=company_id, sap_schema=sap_schema, source_view=source_view,
        sync_start_date=sync_start_date, created_at=now, created_by=actor_id,
    )
    db.add(company)
    db.flush()  # Asigna el id para el historial.
    record_change(
        db, action="sap_company.create", resource_type="sap_company", resource_id=company.id,
        company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(company),
    )
    return company
