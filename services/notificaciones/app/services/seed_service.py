"""Carga inicial de plantillas de una empresa (app/seeds/data.py).

Mismas reglas que los seeds de auth y libro-mayor. Idempotente y en una sola
transacción: si algo falla, no se guarda nada.
- Una plantilla activa con ese código ya existe → se deja como está ("existing"),
  aunque su contenido sea distinto: puede haberla ajustado un administrador.
- Solo hay una dada de baja → no se reactiva ni se crea otra ("kept_deactivated"):
  una baja es una decisión de un administrador.
- No existe → se crea ("created"), validada igual que por la API.
Cada alta queda en change_history atribuida al administrador que lo ejecuta.
"""

from pathlib import Path

from platform_audit import step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Template
from app.seeds.data import SEED_COMPANIES
from app.services.actors import user_actor_id
from app.services.errors import NotFoundError
from app.services.history import record_change
from app.services.template_service import apply_recipients, snapshot, validate_template

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "seeds" / "templates"


def _load(item: dict) -> dict:
    """Datos de una plantilla del seed, con el HTML leído de su archivo."""
    data = dict(item)
    html_file = data.pop("body_html_file", None)
    data["body_html_template"] = (TEMPLATES_DIR / html_file).read_text(encoding="utf-8") if html_file else None
    return data


class SeedService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, *, company_id: str, company_code: str | None, user_id: str) -> dict:
        company = SEED_COMPANIES.get(company_code or "")
        if company is None:
            raise NotFoundError(f"No hay datos de seed para la empresa {company_code}.")
        items = [_load(item) for item in company["templates"]]

        result = {"created": [], "existing": [], "kept_deactivated": []}
        with step("seed"), self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            for data in items:
                states = set(self.db.scalars(
                    select(Template.is_active).where(Template.company_id == company_id, Template.code == data["code"])
                ))
                if True in states:
                    result["existing"].append(data["code"])
                    continue
                if False in states:
                    result["kept_deactivated"].append(data["code"])
                    continue
                template = Template(
                    company_id=company_id, code=data["code"], name=data["name"], description=data.get("description"),
                    subject_template=data["subject_template"], body_html_template=data["body_html_template"],
                    body_text_template=data.get("body_text_template"), reply_to=data.get("reply_to"),
                    to_addresses=[], cc_addresses=[], bcc_addresses=[], created_at=now, created_by=actor_id,
                )
                apply_recipients(template, data)
                validate_template(template)  # Sintaxis y cuerpo, como por la API.
                self.db.add(template)
                self.db.flush()
                record_change(
                    self.db, action="seed.template.create", resource_type="template", resource_id=template.id,
                    company_id=company_id, actor_id=actor_id, now=now, before={}, after=snapshot(template),
                )
                result["created"].append(data["code"])
        return {"templates": result}
