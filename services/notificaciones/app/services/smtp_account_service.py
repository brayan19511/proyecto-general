"""Cuentas SMTP por empresa (notificaciones.smtp_accounts).

Toda consulta filtra por la empresa validada por auth: una cuenta de otra
empresa responde lo mismo que una inexistente (404). La contraseña se cifra
al guardarla (app/core/crypto.py) y nunca sale de aquí ni entra al historial:
el historial solo registra has_password y, si cambió, password_changed.

username y password van juntos: los dos o ninguno (relay sin autenticación).
from_email no tiene que coincidir con username, pero varios proveedores
(Office 365, Gmail) solo envían como el usuario autenticado o con permiso
"enviar como": si no coinciden, el envío puede fallar con un error 5xx.
"""

from platform_audit import step
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import SecretDecryptionError, decrypt_secret, encrypt_secret
from app.models.common.mixin_model import utcnow
from app.models.entities import SmtpAccount
from app.schemas.smtp_accounts import SmtpAccountOut
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change
from app.services.smtp_transport import (
    BlockedDestinationError,
    SmtpEndpoint,
    check_port,
    classify_error,
    open_connection,
)

RESOURCE = "smtp_account"
# Campos que se pueden editar y entran al historial (sin la contraseña).
_PLAIN_FIELDS = (
    "name", "host", "port", "security", "username", "from_email", "from_name", "priority", "timeout_seconds",
)


def to_out(account: SmtpAccount) -> SmtpAccountOut:
    return SmtpAccountOut(
        id=account.id, name=account.name, host=account.host, port=account.port, security=account.security,
        username=account.username, has_password=account.password_encrypted is not None,
        from_email=account.from_email, from_name=account.from_name, priority=account.priority,
        timeout_seconds=account.timeout_seconds, is_active=account.is_active,
        created_at=account.created_at, updated_at=account.updated_at, deleted_at=account.deleted_at,
    )


def _snapshot(account: SmtpAccount) -> dict:
    """Valores permitidos para el historial: nunca la contraseña ni su cifrado."""
    data = {field: getattr(account, field) for field in _PLAIN_FIELDS}
    data["has_password"] = account.password_encrypted is not None
    return data


def _check_credentials(username: str | None, has_password: bool) -> None:
    if (username is None) != (not has_password):
        raise InvalidDataError("username y password van juntos: envía los dos o ninguno.")


def _check_allowed_port(port: int) -> None:
    """El puerto se valida al guardar (y otra vez al conectar, por si cambia la configuración)."""
    try:
        check_port(port)
    except BlockedDestinationError as error:
        raise InvalidDataError(f"port: {error}") from None


class SmtpAccountService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool, limit: int, offset: int) -> tuple[list[SmtpAccount], int]:
        """Cuentas en orden de uso (priority, created_at) y el total sin paginar."""
        with self.db.begin():
            condition = [SmtpAccount.company_id == company_id]
            if not include_inactive:
                condition.append(SmtpAccount.is_active.is_(True))
            total = self.db.scalar(select(func.count()).select_from(SmtpAccount).where(*condition))
            query = (
                select(SmtpAccount).where(*condition)
                .order_by(SmtpAccount.priority, SmtpAccount.created_at).limit(limit).offset(offset)
            )
            return list(self.db.scalars(query)), total

    def get(self, company_id: str, account_id: str) -> SmtpAccount:
        """Una cuenta de la empresa, activa o dada de baja."""
        with self.db.begin():
            return self._find(company_id, account_id, active=None)

    def create(self, *, company_id: str, user_id: str, data: dict) -> SmtpAccount:
        password = data.pop("password", None)
        _check_credentials(data.get("username"), password is not None)
        _check_allowed_port(data["port"])
        with step("smtp_account.create"), self.db.begin():
            self._check_name_free(company_id, data["name"])
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account = SmtpAccount(
                company_id=company_id, **data,
                password_encrypted=encrypt_secret(password) if password is not None else None,
                created_at=now, created_by=actor_id,
            )
            self.db.add(account)
            self._flush_or_conflict()  # Asigna el id para el historial.
            record_change(
                self.db, action=f"{RESOURCE}.create", resource_type=RESOURCE, resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(account),
            )
        return account

    def update(self, *, company_id: str, user_id: str, account_id: str, changes: dict) -> SmtpAccount:
        """Solo cambian los campos enviados. password: texto la reemplaza, null la borra."""
        if "port" in changes:
            _check_allowed_port(changes["port"])
        with step("smtp_account.update"), self.db.begin():
            account = self._find(company_id, account_id, active=True)
            before = _snapshot(account)
            password_changed = "password" in changes
            if password_changed:
                password = changes.pop("password")
                account.password_encrypted = encrypt_secret(password) if password is not None else None
            if "name" in changes and changes["name"] != account.name:
                self._check_name_free(company_id, changes["name"])
            for field, value in changes.items():
                setattr(account, field, value)
            _check_credentials(account.username, account.password_encrypted is not None)

            after = _snapshot(account)
            if after == before and not password_changed:
                return account  # Sin cambios: ni actualización ni historial.
            if password_changed:
                after["password_changed"] = True
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account.updated_at, account.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.update", resource_type=RESOURCE, resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return account

    def deactivate(self, *, company_id: str, user_id: str, account_id: str) -> None:
        """Baja lógica: deja de usarse para enviar; la fila y su historial se conservan.

        Se permite dar de baja la última cuenta activa: los envíos pendientes
        fallarán con no_account y se reintentarán según la regla.
        """
        with step("smtp_account.delete"), self.db.begin():
            account = self._find(company_id, account_id, active=True)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account.is_active = False
            account.deleted_at = account.updated_at = now
            account.deleted_by = account.updated_by = actor_id
            record_change(
                self.db, action=f"{RESOURCE}.delete", resource_type=RESOURCE, resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(account), after={},
            )

    def restore(self, *, company_id: str, user_id: str, account_id: str) -> SmtpAccount:
        """Reactiva una cuenta dada de baja. 409 si otra activa ya usa su nombre."""
        with step("smtp_account.restore"), self.db.begin():
            account = self._find(company_id, account_id, active=False)
            self._check_name_free(company_id, account.name)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            account.is_active = True
            account.deleted_at = account.deleted_by = None
            account.updated_at, account.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.restore", resource_type=RESOURCE, resource_id=account.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(account),
            )
        return account

    def test(self, company_id: str, account_id: str) -> str | None:
        """Conecta, cifra y autentica sin enviar correo. Devuelve None si todo funcionó
        o la categoría del error (classify_error). No cambia nada: sin historial.

        La transacción se cierra antes de conectar: no se mantiene una conexión a
        la base abierta mientras se espera al servidor SMTP.
        """
        with self.db.begin():
            account = self._find(company_id, account_id, active=True)
            endpoint = SmtpEndpoint(account.host, account.port, account.security, account.timeout_seconds)
            username, encrypted = account.username, account.password_encrypted
        with step("smtp_account.test"):
            try:
                password = decrypt_secret(encrypted) if encrypted is not None else None
            except SecretDecryptionError:
                return "credentials_unreadable"
            try:
                smtp = open_connection(endpoint, username, password)
            except Exception as error:  # noqa: BLE001 - se informa solo la categoría.
                return classify_error(error)
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001 - la prueba ya pasó; cerrar mal no la invalida.
                smtp.close()
            return None

    def _find(self, company_id: str, account_id: str, *, active: bool | None) -> SmtpAccount:
        """Cuenta de la empresa; active=None acepta activas y dadas de baja."""
        query = select(SmtpAccount).where(SmtpAccount.id == account_id, SmtpAccount.company_id == company_id)
        if active is not None:
            query = query.where(SmtpAccount.is_active.is_(active))
        account = self.db.scalar(query)
        if account is None:
            raise NotFoundError("Cuenta SMTP no encontrada.")
        return account

    def _check_name_free(self, company_id: str, name: str) -> None:
        taken = self.db.scalar(
            select(SmtpAccount.id).where(
                SmtpAccount.company_id == company_id, SmtpAccount.name == name, SmtpAccount.is_active.is_(True)
            )
        )
        if taken is not None:
            raise ConflictError("Ya existe una cuenta SMTP activa con ese nombre.")

    def _flush_or_conflict(self) -> None:
        """Dos solicitudes simultáneas con el mismo nombre: el índice único decide y
        la segunda recibe el mismo 409 que la comprobación previa."""
        try:
            self.db.flush()
        except IntegrityError:
            raise ConflictError("Ya existe una cuenta SMTP activa con ese nombre.") from None
