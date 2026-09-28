"""Cuentas SAP que se sincronizan por empresa (libro_mayor.accounts).

Una cuenta es exacta (979005400) o un prefijo (95 = todas las que empiezan
por 95). Dos cuentas activas de una empresa no pueden superponerse, es decir,
cubrir una misma cuenta SAP: así cada línea sincronizada pertenece a una sola
cuenta registrada. La base solo impide repetir el mismo código; la
superposición se valida aquí.
"""

import re

from platform_audit import step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Account, SapCompany, SyncRun
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change
from app.services.ledger_lines import has_lines

# Las cuentas observadas en SAP son numéricas (95, 979005400, 701110002).
CODE_PATTERN = re.compile(r"^\d{1,20}$")
MATCH_MODES = ("exact", "prefix")


def overlaps(code_a: str, mode_a: str, code_b: str, mode_b: str) -> bool:
    """True si ambas cuentas registradas pueden traer una misma cuenta SAP.

    - Dos exactas: solo si son la misma cuenta.
    - Un prefijo y otra cuenta: si el código de la otra empieza por el prefijo
      (97 cubre 979005400; con dos prefijos, 97 cubre 979).
    """
    if mode_a == "exact" and mode_b == "exact":
        return code_a == code_b
    if mode_a == "prefix" and code_b.startswith(code_a):
        return True
    return mode_b == "prefix" and code_a.startswith(code_b)


def _snapshot(account: Account) -> dict:
    return {"code": account.code, "match_mode": account.match_mode, "name": account.name}


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool = False, limit: int, offset: int) -> list[Account]:
        with self.db.begin():
            query = select(Account).where(Account.company_id == company_id)
            if not include_inactive:
                query = query.where(Account.is_active.is_(True))
            query = query.order_by(Account.code, Account.created_at).limit(limit).offset(offset)
            return list(self.db.scalars(query))

    def create(self, *, company_id: str, user_id: str, code: str, match_mode: str, name: str | None) -> Account:
        code = validate_account(code, match_mode)
        with step("account.create"), self.db.begin():
            lock_company(self.db, company_id)
            actor_id = user_actor_id(self.db, user_id)
            return add_account(
                self.db, company_id=company_id, actor_id=actor_id, now=utcnow(),
                code=code, match_mode=match_mode, name=name,
            )

    def get(self, company_id: str, account_id: str) -> Account:
        """Una cuenta de la empresa (activa o dada de baja)."""
        with self.db.begin():
            account = self.db.scalar(select(Account).where(Account.id == account_id, Account.company_id == company_id))
        if account is None:
            raise NotFoundError("Cuenta no encontrada.")
        return account

    def update(self, *, company_id: str, user_id: str, account_id: str, changes: dict) -> Account:
        """Modifica solo los campos enviados (name, code, match_mode).

        name se cambia siempre. code y match_mode definen qué líneas trae la
        cuenta: solo se cambian si todavía no tiene líneas sincronizadas ni una
        sincronización abierta; si ya las tiene, se da de baja y se registra
        otra (las líneas traídas siguen perteneciendo a la cuenta original).
        """
        with step("account.update"), self.db.begin():
            lock_company(self.db, company_id)
            account = self.db.scalar(
                select(Account).where(
                    Account.id == account_id, Account.company_id == company_id, Account.is_active.is_(True)
                )
            )
            if account is None:
                raise NotFoundError("Cuenta no encontrada.")
            before = _snapshot(account)
            code = changes.get("code", account.code)
            match_mode = changes.get("match_mode", account.match_mode)
            if (code, match_mode) != (account.code, account.match_mode):
                code = validate_account(code, match_mode)
                if has_lines(self.db, account_id=account.id) or has_open_run(self.db, account.id):
                    raise ConflictError(
                        "La cuenta ya tiene líneas o una sincronización abierta: para cambiar código o modo, "
                        "dala de baja y registra otra."
                    )
                check_overlap(self.db, company_id, code, match_mode, exclude_id=account.id)
                account.code, account.match_mode = code, match_mode
            if "name" in changes:
                account.name = changes["name"]
            after = _snapshot(account)
            if after == before:
                return account  # Sin cambios: ni actualización ni historial.
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account.updated_at, account.updated_by = now, actor_id
            record_change(
                self.db, action="account.update", resource_type="account", resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return account

    def deactivate(self, *, company_id: str, user_id: str, account_id: str) -> None:
        """Baja lógica: deja de sincronizarse; sus líneas ya traídas se conservan."""
        with step("account.delete"), self.db.begin():
            lock_company(self.db, company_id)
            account = self.db.scalar(
                select(Account).where(
                    Account.id == account_id, Account.company_id == company_id, Account.is_active.is_(True)
                )
            )
            if account is None:
                raise NotFoundError("Cuenta no encontrada.")
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account.is_active = False
            account.deleted_at = account.updated_at = now
            account.deleted_by = account.updated_by = actor_id
            record_change(
                self.db, action="account.delete", resource_type="account", resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(account), after={},
            )


def validate_account(code: str, match_mode: str) -> str:
    """Formato de una cuenta a registrar; devuelve el código normalizado."""
    code = code.strip()
    if not CODE_PATTERN.fullmatch(code):
        raise InvalidDataError("code: solo dígitos, entre 1 y 20.")
    if match_mode not in MATCH_MODES:
        raise InvalidDataError("match_mode: exact o prefix.")
    return code


def lock_company(db: Session, company_id: str) -> None:
    """Bloquea la compañía SAP de la empresa hasta el fin de la transacción.

    Serializa los cambios de cuentas de una misma empresa: dos altas
    simultáneas (97 y 979005400) no pueden pasar ambas la validación de
    superposición. Sin compañía SAP activa no se registran cuentas.
    """
    locked = db.scalar(
        select(SapCompany.id)
        .where(SapCompany.company_id == company_id, SapCompany.is_active.is_(True))
        .with_for_update()
    )
    if locked is None:
        raise ConflictError("La empresa no tiene compañía SAP configurada.")


def active_accounts(db: Session, company_id: str) -> list[Account]:
    return list(db.scalars(select(Account).where(Account.company_id == company_id, Account.is_active.is_(True))))


def check_overlap(db: Session, company_id: str, code: str, match_mode: str, exclude_id: str | None = None) -> None:
    """ConflictError si la cuenta se superpone con otra activa (exclude_id: la que se está editando)."""
    for active in active_accounts(db, company_id):
        if active.id != exclude_id and overlaps(code, match_mode, active.code, active.match_mode):
            raise ConflictError(f"{code} ({match_mode}) se superpone con la cuenta activa {active.code} ({active.match_mode}).")


def has_open_run(db: Session, account_id: str) -> bool:
    """¿La cuenta tiene una sincronización pendiente o en curso?"""
    query = select(SyncRun.id).where(SyncRun.account_id == account_id, SyncRun.status.in_(("pending", "running")))
    return db.scalar(query) is not None


def add_account(
    db: Session, *, company_id: str, actor_id: str, now, code: str, match_mode: str, name: str | None
) -> Account:
    """Inserta una cuenta ya validada, con su historial, en la transacción en curso.

    Requiere haber llamado a lock_company en esta transacción. Rechaza la
    superposición con las cuentas activas (incluidas las agregadas antes en la
    misma transacción).
    """
    check_overlap(db, company_id, code, match_mode)
    account = Account(
        company_id=company_id, code=code, match_mode=match_mode, name=name, created_at=now, created_by=actor_id,
    )
    db.add(account)
    db.flush()  # Asigna el id para el historial.
    record_change(
        db, action="account.create", resource_type="account", resource_id=account.id,
        company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(account),
    )
    return account
