"""Carga inicial de compañía SAP y cuentas de una empresa (app/seeds/data.py).

Idempotente y en una sola transacción: si algo choca, no se guarda nada.
- Lo que ya existe igual se deja como está ("existing").
- Lo dado de baja no se reactiva ni se vuelve a crear ("kept_deactivated"):
  una baja es una decisión de un administrador.
- Lo que existe distinto (otro schema SAP, misma cuenta con otro modo) o se
  superpone es un conflicto (409): se revisa a mano.
Cada alta queda en change_history atribuida al administrador que lo ejecuta.
"""

from platform_audit import step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Account, SapCompany
from app.seeds.data import SEED_COMPANIES
from app.services.account_service import add_account, lock_company, validate_account
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, NotFoundError
from app.services.sap_company_service import active_sap_company, add_sap_company, validate_identifier


class SeedService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, *, company_id: str, company_code: str, user_id: str) -> dict:
        data = SEED_COMPANIES.get(company_code)
        if data is None:
            raise NotFoundError(f"No hay datos de seed para la empresa {company_code}.")
        sap = data["sap_company"]
        sap_schema = validate_identifier("sap_schema", sap["sap_schema"])
        source_view = validate_identifier("source_view", sap["source_view"])
        accounts = [(validate_account(code, mode), mode, name) for code, mode, name in data["accounts"]]

        result = {"sap_company": "", "accounts": {"created": [], "existing": [], "kept_deactivated": []}}
        with step("seed"), self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()

            current = active_sap_company(self.db, company_id)
            if current is not None:
                if (current.sap_schema, current.source_view) != (sap_schema, source_view):
                    raise ConflictError("La empresa tiene otra compañía SAP activa; revisarla a mano.")
                result["sap_company"] = "existing"
            elif self._was_deactivated(SapCompany, company_id):
                raise ConflictError("La compañía SAP de la empresa fue dada de baja; el seed no la reactiva.")
            else:
                add_sap_company(
                    self.db, company_id=company_id, actor_id=actor_id, now=now,
                    sap_schema=sap_schema, source_view=source_view, sync_start_date=sap["sync_start_date"],
                )
                result["sap_company"] = "created"

            lock_company(self.db, company_id)
            for code, mode, name in accounts:
                active = self.db.scalar(
                    select(Account).where(Account.company_id == company_id, Account.code == code, Account.is_active.is_(True))
                )
                if active is not None:
                    if active.match_mode != mode:
                        raise ConflictError(f"La cuenta {code} ya existe como {active.match_mode}; el seed la trae como {mode}.")
                    result["accounts"]["existing"].append(code)
                elif self._was_deactivated(Account, company_id, code=code):
                    result["accounts"]["kept_deactivated"].append(code)
                else:
                    # add_account rechaza superposiciones con las activas, incluidas
                    # las creadas antes en este mismo seed.
                    add_account(
                        self.db, company_id=company_id, actor_id=actor_id, now=now,
                        code=code, match_mode=mode, name=name,
                    )
                    result["accounts"]["created"].append(code)
        return result

    def _was_deactivated(self, model, company_id: str, **filters) -> bool:
        query = select(model.id).where(model.company_id == company_id, model.is_active.is_(False))
        for column, value in filters.items():
            query = query.where(getattr(model, column) == value)
        return self.db.scalar(query.limit(1)) is not None
