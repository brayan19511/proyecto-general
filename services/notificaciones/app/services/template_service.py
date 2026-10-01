"""Plantillas generales por empresa (notificaciones.templates).

Mismo patrón que las cuentas SMTP: todo filtrado por la empresa validada (404
si es de otra), código único entre las activas (409), baja lógica, restaurar e
historial de cada cambio en la misma transacción. Al guardar se valida la
sintaxis de las tres plantillas y se normalizan los destinatarios fijos.
"""

from platform_audit import step
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Template
from app.schemas.templates import PreviewOut, TemplateOut
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change
from app.services.recipients import normalize_address, normalize_fixed
from app.services.template_engine import check_syntax, render, render_subject

RESOURCE = "template"
_FIELDS = (
    "code", "name", "description", "subject_template", "body_html_template", "body_text_template",
    "to_addresses", "cc_addresses", "bcc_addresses", "reply_to",
)


def to_out(template: Template) -> TemplateOut:
    return TemplateOut(
        id=template.id, code=template.code, name=template.name, description=template.description,
        subject_template=template.subject_template, body_html_template=template.body_html_template,
        body_text_template=template.body_text_template, to=template.to_addresses, cc=template.cc_addresses,
        bcc=template.bcc_addresses, reply_to=template.reply_to, is_active=template.is_active,
        created_at=template.created_at, updated_at=template.updated_at, deleted_at=template.deleted_at,
    )


def snapshot(template: Template) -> dict:
    """Para el historial: la plantilla completa (no tiene secretos)."""
    return {field: getattr(template, field) for field in _FIELDS}


def validate_template(template: Template) -> None:
    """Reglas que dependen de varios campos; se aplican después de crear o editar."""
    if template.body_html_template is None and template.body_text_template is None:
        raise InvalidDataError("La plantilla necesita body_html_template o body_text_template.")
    check_syntax("subject_template", template.subject_template, html=False)
    check_syntax("body_html_template", template.body_html_template, html=True)
    check_syntax("body_text_template", template.body_text_template, html=False)


def apply_recipients(template: Template, data: dict) -> None:
    """to/cc/bcc del body → listas normalizadas y sin duplicados de la plantilla."""
    if not any(key in data for key in ("to", "cc", "bcc")):
        return
    fixed = normalize_fixed(
        data.get("to", template.to_addresses or []),
        data.get("cc", template.cc_addresses or []),
        data.get("bcc", template.bcc_addresses or []),
    )
    template.to_addresses, template.cc_addresses, template.bcc_addresses = fixed.to, fixed.cc, fixed.bcc


class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool, limit: int, offset: int) -> tuple[list[Template], int]:
        with self.db.begin():
            condition = [Template.company_id == company_id]
            if not include_inactive:
                condition.append(Template.is_active.is_(True))
            total = self.db.scalar(select(func.count()).select_from(Template).where(*condition))
            rows = self.db.scalars(
                select(Template).where(*condition).order_by(Template.code, Template.created_at).limit(limit).offset(offset)
            )
            return list(rows), total

    def get(self, company_id: str, template_id: str) -> Template:
        with self.db.begin():
            return self._find(company_id, template_id, active=None)

    def create(self, *, company_id: str, user_id: str, data: dict) -> Template:
        with step("template.create"), self.db.begin():
            self._check_code_free(company_id, data["code"])
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            template = Template(
                company_id=company_id, code=data["code"], name=data["name"], description=data.get("description"),
                subject_template=data["subject_template"], body_html_template=data.get("body_html_template"),
                body_text_template=data.get("body_text_template"),
                reply_to=normalize_address(data["reply_to"]) if data.get("reply_to") else None,
                to_addresses=[], cc_addresses=[], bcc_addresses=[], created_at=now, created_by=actor_id,
            )
            apply_recipients(template, data)
            validate_template(template)
            self.db.add(template)
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.create", resource_type=RESOURCE, resource_id=template.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=snapshot(template),
            )
        return template

    def update(self, *, company_id: str, user_id: str, template_id: str, changes: dict) -> Template:
        with step("template.update"), self.db.begin():
            template = self._find(company_id, template_id, active=True)
            before = snapshot(template)
            if "code" in changes and changes["code"] != template.code:
                self._check_code_free(company_id, changes["code"])
            for field in ("code", "name", "description", "subject_template", "body_html_template", "body_text_template"):
                if field in changes:
                    setattr(template, field, changes[field])
            if "reply_to" in changes:
                template.reply_to = normalize_address(changes["reply_to"]) if changes["reply_to"] else None
            apply_recipients(template, changes)
            validate_template(template)
            after = snapshot(template)
            if after == before:
                return template
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            template.updated_at, template.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.update", resource_type=RESOURCE, resource_id=template.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return template

    def deactivate(self, *, company_id: str, user_id: str, template_id: str) -> None:
        """Baja lógica: deja de poder usarse en envíos nuevos; lo ya enviado no cambia."""
        with step("template.delete"), self.db.begin():
            template = self._find(company_id, template_id, active=True)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            template.is_active = False
            template.deleted_at = template.updated_at = now
            template.deleted_by = template.updated_by = actor_id
            record_change(
                self.db, action=f"{RESOURCE}.delete", resource_type=RESOURCE, resource_id=template.id,
                company_id=company_id, actor_id=actor_id, now=now, before=snapshot(template), after={},
            )

    def restore(self, *, company_id: str, user_id: str, template_id: str) -> Template:
        with step("template.restore"), self.db.begin():
            template = self._find(company_id, template_id, active=False)
            self._check_code_free(company_id, template.code)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            template.is_active = True
            template.deleted_at = template.deleted_by = None
            template.updated_at, template.updated_by = now, actor_id
            self._flush_or_conflict()
            record_change(
                self.db, action=f"{RESOURCE}.restore", resource_type=RESOURCE, resource_id=template.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=snapshot(template),
            )
        return template

    def preview(self, company_id: str, template_id: str, parameters: dict) -> PreviewOut:
        """Arma la plantilla con parámetros de ejemplo. No guarda ni envía nada."""
        with self.db.begin():
            template = self._find(company_id, template_id, active=None)
            return render_template(template, parameters)

    def _find(self, company_id: str, template_id: str, *, active: bool | None) -> Template:
        query = select(Template).where(Template.id == template_id, Template.company_id == company_id)
        if active is not None:
            query = query.where(Template.is_active.is_(active))
        template = self.db.scalar(query)
        if template is None:
            raise NotFoundError("Plantilla no encontrada.")
        return template

    def _check_code_free(self, company_id: str, code: str) -> None:
        taken = self.db.scalar(
            select(Template.id).where(Template.company_id == company_id, Template.code == code, Template.is_active.is_(True))
        )
        if taken is not None:
            raise ConflictError("Ya existe una plantilla activa con ese código.")

    def _flush_or_conflict(self) -> None:
        try:
            self.db.flush()
        except IntegrityError:
            raise ConflictError("Ya existe una plantilla activa con ese código.") from None


def render_template(template: Template, parameters: dict) -> PreviewOut:
    """Asunto y cuerpos armados (lo usarán también los envíos con template_code)."""
    return PreviewOut(
        subject=render_subject(template.subject_template, parameters),
        body_html=render("body_html_template", template.body_html_template, parameters, html=True),
        body_text=render("body_text_template", template.body_text_template, parameters, html=False),
    )
