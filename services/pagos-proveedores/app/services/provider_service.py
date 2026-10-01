"""Maestro de proveedores por empresa (pagos_proveedores.providers).

Mismo patrón que las cuentas SMTP de notificaciones: todo filtrado por la
empresa validada por auth (otra empresa = 404), baja lógica, restaurar e
historial de cada cambio en la misma transacción.

Reglas propias:
- tax_id se guarda normalizado (document_key) y es único entre los activos (409).
- match_names = name_key de legal_name y commercial_names, sin repetidos. Ninguna
  clave puede pertenecer a otro proveedor activo de la empresa (409): el lector
  de constancias no sabría a cuál asignarla.
- payment_emails se validan y normalizan (dominio en minúsculas) y se quitan
  duplicados sin distinguir mayúsculas.
"""

from email_validator import EmailNotValidError, validate_email
from platform_audit import step
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Provider
from app.schemas.providers import ProviderOut
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change
from app.services.text_keys import document_key, name_key

RESOURCE = "provider"
_FIELDS = ("tax_id", "legal_name", "commercial_names", "payment_emails")


def to_out(provider: Provider) -> ProviderOut:
    return ProviderOut(
        id=provider.id, tax_id=provider.tax_id, legal_name=provider.legal_name,
        commercial_names=provider.commercial_names, payment_emails=provider.payment_emails,
        is_active=provider.is_active, created_at=provider.created_at, updated_at=provider.updated_at,
        deleted_at=provider.deleted_at,
    )


def _snapshot(provider: Provider) -> dict:
    return {field: getattr(provider, field) for field in _FIELDS}


def _normalize_tax_id(value: str) -> str:
    key = document_key(value)
    if not 1 <= len(key) <= 20:
        raise InvalidDataError("tax_id: entre 1 y 20 letras o dígitos (sin contar guiones ni espacios).")
    return key


def _normalize_emails(emails: list[str]) -> list[str]:
    result, seen = [], set()
    for email in emails:
        try:
            normalized = validate_email(email, check_deliverability=False).normalized
        except EmailNotValidError:
            raise InvalidDataError(f"Correo no válido: {email!r}.") from None
        if normalized.lower() not in seen:
            seen.add(normalized.lower())
            result.append(normalized)
    return result


def _unique_names(names: list[str]) -> list[str]:
    """Quita nombres comerciales repetidos (misma clave), conservando el primero."""
    result, seen = [], set()
    for name in names:
        if name_key(name) not in seen:
            seen.add(name_key(name))
            result.append(name)
    return result


def _apply(provider: Provider, data: dict) -> None:
    if "tax_id" in data:
        provider.tax_id = _normalize_tax_id(data["tax_id"])
    if "legal_name" in data:
        provider.legal_name = data["legal_name"]
    if "commercial_names" in data:
        provider.commercial_names = _unique_names(data["commercial_names"])
    if "payment_emails" in data:
        provider.payment_emails = _normalize_emails(data["payment_emails"])
    keys = [name_key(provider.legal_name), *(name_key(n) for n in provider.commercial_names or [])]
    provider.match_names = list(dict.fromkeys(k for k in keys if k))


class ProviderService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self, company_id: str, *, search: str | None, include_inactive: bool, limit: int, offset: int
    ) -> tuple[list[Provider], int]:
        """Por razón social. search busca en el RUC/DNI y en la razón social."""
        with self.db.begin():
            condition = [Provider.company_id == company_id]
            if not include_inactive:
                condition.append(Provider.is_active.is_(True))
            if search and search.strip():
                pattern = f"%{search.strip()}%"
                condition.append(or_(Provider.tax_id.ilike(f"%{document_key(search)}%"), Provider.legal_name.ilike(pattern)))
            total = self.db.scalar(select(func.count()).select_from(Provider).where(*condition))
            rows = self.db.scalars(
                select(Provider).where(*condition).order_by(Provider.legal_name, Provider.id).limit(limit).offset(offset)
            )
            return list(rows), total

    def get(self, company_id: str, provider_id: str) -> Provider:
        with self.db.begin():
            return self._find(company_id, provider_id, active=None)

    def create(self, *, company_id: str, user_id: str, data: dict) -> Provider:
        with step("provider.create"), self.db.begin():
            provider = Provider(company_id=company_id, commercial_names=[], payment_emails=[])
            _apply(provider, data)
            self._check_free(provider)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            provider.created_at, provider.created_by = now, actor_id
            self.db.add(provider)
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.create", resource_type=RESOURCE, resource_id=provider.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(provider),
            )
        return provider

    def update(self, *, company_id: str, user_id: str, provider_id: str, changes: dict) -> Provider:
        with step("provider.update"), self.db.begin():
            provider = self._find(company_id, provider_id, active=True)
            before = _snapshot(provider)
            _apply(provider, changes)
            after = _snapshot(provider)
            if after == before:
                return provider  # Sin cambios: ni actualización ni historial.
            self._check_free(provider)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            provider.updated_at, provider.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.update", resource_type=RESOURCE, resource_id=provider.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return provider

    def deactivate(self, *, company_id: str, user_id: str, provider_id: str) -> None:
        """Baja lógica: deja de identificarse en lotes nuevos; lo ya enviado no cambia."""
        with step("provider.delete"), self.db.begin():
            provider = self._find(company_id, provider_id, active=True)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            provider.is_active = False
            provider.deleted_at = provider.updated_at = now
            provider.deleted_by = provider.updated_by = actor_id
            record_change(
                self.db, action=f"{RESOURCE}.delete", resource_type=RESOURCE, resource_id=provider.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(provider), after={},
            )

    def restore(self, *, company_id: str, user_id: str, provider_id: str) -> Provider:
        """409 si otro proveedor activo ya usa su RUC/DNI o uno de sus nombres."""
        with step("provider.restore"), self.db.begin():
            provider = self._find(company_id, provider_id, active=False)
            self._check_free(provider)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            provider.is_active = True
            provider.deleted_at = provider.deleted_by = None
            provider.updated_at, provider.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.restore", resource_type=RESOURCE, resource_id=provider.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(provider),
            )
        return provider

    def _find(self, company_id: str, provider_id: str, *, active: bool | None) -> Provider:
        query = select(Provider).where(Provider.id == provider_id, Provider.company_id == company_id)
        if active is not None:
            query = query.where(Provider.is_active.is_(active))
        provider = self.db.scalar(query)
        if provider is None:
            raise NotFoundError("Proveedor no encontrado.")
        return provider

    def _check_free(self, provider: Provider) -> None:
        """RUC/DNI y nombres que no use otro proveedor activo de la empresa."""
        condition = [Provider.company_id == provider.company_id, Provider.is_active.is_(True)]
        if provider.id is not None:  # Al editar o restaurar: excluirse a sí mismo.
            condition.append(Provider.id != provider.id)
        others = list(self.db.scalars(select(Provider).where(*condition)))
        for other in others:
            if other.tax_id == provider.tax_id:
                raise ConflictError(f"El RUC/DNI {provider.tax_id} ya es del proveedor activo {other.legal_name}.")
            shared = set(other.match_names or []) & set(provider.match_names or [])
            if shared:
                raise ConflictError(
                    f"El nombre {sorted(shared)[0]!r} ya identifica al proveedor activo {other.legal_name}: "
                    "las constancias con ese nombre no sabrían a quién asignarse."
                )

    def _flush_or_conflict(self) -> None:
        """Dos altas simultáneas con el mismo RUC/DNI: decide el índice único."""
        try:
            self.db.flush()
        except IntegrityError:
            raise ConflictError("Ya existe un proveedor activo con ese RUC/DNI.") from None
