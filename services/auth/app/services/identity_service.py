"""Catálogo de países y documentos, y documentos de identidad del usuario.

Diseño internacional (docs/requisitos.md): el documento no es una columna
"dni". Cada documento tiene un tipo, y cada tipo pertenece a un país emisor
(PE/DNI, CL/RUT, ES/DNI, PE/PASAPORTE...). Agregar un país es agregar datos
al catálogo (data.py), no cambiar modelos.

Reglas:
  - El número es texto: se conservan ceros iniciales.
  - Se normaliza quitando espacios, puntos y guiones, en mayúsculas, y se
    valida con el formato del tipo. Formato válido no es identidad verificada.
  - Un documento por tipo y usuario. No hay unicidad entre personas: eso
    exigiría antes decidir un proceso de verificación.
  - Cada usuario gestiona solo los suyos.
"""

import re
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import IdentityDocumentType, User, UserIdentityDocument
from app.repositories.identity_repository import IdentityRepository
from app.schemas.identity import CountryOut, DocumentCreate, DocumentOut, DocumentTypeOut
from app.services.common import audit_create, history_event, restore, soft_delete, touch


class DocumentTypeNotFoundError(Exception):
    """El tipo de documento no existe en el catálogo."""


class InvalidDocumentNumberError(Exception):
    """El número no cumple el formato del tipo."""


class DocumentExistsError(Exception):
    """Ya hay un documento de ese tipo: se elimina antes de registrar otro."""


class DocumentNotFoundError(Exception):
    """El documento no existe, está dado de baja o es de otro usuario."""


class InvalidExpirationError(Exception):
    """La fecha de vencimiento ya pasó."""


def normalize_number(number: str) -> str:
    return re.sub(r"[\s.\-]", "", number).upper()


def _type_out(doc_type: IdentityDocumentType) -> DocumentTypeOut:
    return DocumentTypeOut(
        id=doc_type.id,
        issuing_country_code=doc_type.issuing_country_code,
        code=doc_type.code,
        name=doc_type.name,
        category=doc_type.category,
    )


def document_out(document: UserIdentityDocument, doc_type: IdentityDocumentType) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        type=_type_out(doc_type),
        document_number=document.document_number,
        expires_at=document.expires_at,
    )


class IdentityService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = IdentityRepository(session)

    # --- Catálogo

    def list_countries(self) -> list[CountryOut]:
        with self.session.begin():
            return [CountryOut(code=c.code, name=c.name) for c in self.repository.list_countries()]

    def list_document_types(self, country_code: str | None) -> list[DocumentTypeOut]:
        with self.session.begin():
            return [_type_out(t) for t in self.repository.list_document_types(country_code)]

    def country_exists(self, code: str) -> bool:
        """Para validar la nacionalidad del perfil (se llama dentro de una transacción)."""
        return self.repository.get_country(code) is not None

    # --- Documentos propios

    def list_documents(self, user: User) -> list[DocumentOut]:
        with self.session.begin():
            rows = self.repository.list_user_documents(user.id)
        return [document_out(document, doc_type) for document, doc_type in rows]

    def add_document(self, user: User, data: DocumentCreate) -> DocumentOut:
        if data.expires_at is not None and data.expires_at < date.today():
            raise InvalidExpirationError()
        now = utcnow()
        normalized = normalize_number(data.document_number)
        try:
            with self.session.begin():
                doc_type = self.repository.get_document_type(data.document_type_id)
                if doc_type is None:
                    raise DocumentTypeNotFoundError()
                # El patrón viene del catálogo del seed; se aplica al número normalizado.
                if not normalized or (doc_type.pattern and not re.fullmatch(doc_type.pattern, normalized)):
                    raise InvalidDocumentNumberError()

                document = self.repository.find_user_document(user.id, doc_type.id)
                if document is not None and document.deleted_at is None:
                    raise DocumentExistsError()

                values = {
                    "document_number": data.document_number,
                    "normalized_number": normalized,
                    "expires_at": data.expires_at,
                }
                if document is None:
                    document = self.repository.add(
                        UserIdentityDocument(
                            user_id=user.id,
                            document_type_id=doc_type.id,
                            **values,
                            **audit_create(user.id, now),
                        )
                    )
                    action = "identity_document.created"
                else:
                    # Se registró antes y se eliminó: se restaura la misma fila con el número nuevo.
                    restore(document, user.id, now)
                    for field, value in values.items():
                        setattr(document, field, value)
                    touch(document, user.id, now)
                    action = "identity_document.restored"

                self.repository.add_history(
                    history_event(
                        action, document.id, None, user.id, now,
                        before={},
                        # Datos personales permitidos por decisión de diseño: tipo y
                        # vencimiento. El número no se copia al historial.
                        after={
                            "document_type": f"{doc_type.issuing_country_code}/{doc_type.code}",
                            "expires_at": data.expires_at.isoformat() if data.expires_at else None,
                        },
                    )
                )
        except IntegrityError as exc:
            raise DocumentExistsError() from exc
        return document_out(document, doc_type)

    def delete_document(self, user: User, document_id: str) -> None:
        now = utcnow()
        with self.session.begin():
            document = self.repository.get_user_document(user.id, document_id)
            if document is None:
                raise DocumentNotFoundError()
            soft_delete(document, user.id, now)
            self.repository.add_history(
                history_event(
                    "identity_document.deleted", document.id, None, user.id, now,
                    before={"is_active": True},
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )
