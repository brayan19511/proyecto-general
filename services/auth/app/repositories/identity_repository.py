from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ChangeHistory, Country, IdentityDocumentType, UserIdentityDocument


def _usable(model) -> tuple:
    return (model.is_active.is_(True), model.deleted_at.is_(None))


class IdentityRepository:
    """Catálogo de países y tipos de documento, y documentos de cada usuario."""

    def __init__(self, session: Session):
        self.session = session

    def list_countries(self) -> list[Country]:
        return list(self.session.scalars(select(Country).where(*_usable(Country)).order_by(Country.name)))

    def get_country(self, code: str) -> Country | None:
        return self.session.scalar(select(Country).where(Country.code == code, *_usable(Country)))

    def list_document_types(self, country_code: str | None) -> list[IdentityDocumentType]:
        statement = (
            select(IdentityDocumentType)
            .where(*_usable(IdentityDocumentType))
            .order_by(IdentityDocumentType.issuing_country_code, IdentityDocumentType.name)
        )
        if country_code is not None:
            statement = statement.where(IdentityDocumentType.issuing_country_code == country_code)
        return list(self.session.scalars(statement))

    def get_document_type(self, type_id: str) -> IdentityDocumentType | None:
        return self.session.scalar(
            select(IdentityDocumentType).where(IdentityDocumentType.id == type_id, *_usable(IdentityDocumentType))
        )

    def list_user_documents(self, user_id: str) -> list[tuple[UserIdentityDocument, IdentityDocumentType]]:
        statement = (
            select(UserIdentityDocument, IdentityDocumentType)
            .join(IdentityDocumentType, IdentityDocumentType.id == UserIdentityDocument.document_type_id)
            .where(UserIdentityDocument.user_id == user_id, UserIdentityDocument.deleted_at.is_(None))
            .order_by(IdentityDocumentType.issuing_country_code, IdentityDocumentType.name)
        )
        return list(self.session.execute(statement).tuples())

    def find_user_document(self, user_id: str, type_id: str) -> UserIdentityDocument | None:
        """Incluye documentos dados de baja: la unicidad (usuario, tipo) es permanente."""
        return self.session.scalar(
            select(UserIdentityDocument).where(
                UserIdentityDocument.user_id == user_id,
                UserIdentityDocument.document_type_id == type_id,
            )
        )

    def get_user_document(self, user_id: str, document_id: str) -> UserIdentityDocument | None:
        return self.session.scalar(
            select(UserIdentityDocument).where(
                UserIdentityDocument.id == document_id,
                UserIdentityDocument.user_id == user_id,
                UserIdentityDocument.deleted_at.is_(None),
            )
        )

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
