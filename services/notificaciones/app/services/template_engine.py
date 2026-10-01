"""Motor de plantillas: Jinja2 en modo sandbox (acuerdos 1 a 3 del paso 2).

- Sandbox: las plantillas las escribe un admin de empresa. Sin sandbox, una
  expresión como {{ ''.__class__.__mro__ }} podría llegar a ejecutar código en el
  servidor; SandboxedEnvironment bloquea el acceso a atributos internos.
- HTML con autoescape: los VALORES de parameters se escapan (un proveedor
  "<b>ACME</b>" se ve como texto). El HTML propio de la plantilla no se toca.
- Parámetro faltante: si la plantilla lo IMPRIME ({{ proveedor }}) o lo recorre
  ({% for p in pagos %}), es un error (422), no un hueco vacío en el correo. En
  una condición o con respaldo cuenta como falso, así funcionan los campos
  opcionales: {{ pago.suggested_filename or pago.archivo }}, {% if nota %},
  {{ nota | default('-') }} (patrón de las plantillas de proyecto-05).
- El asunto se arma sin escapar (no es HTML) y debe quedar en una sola línea.
"""

from functools import cache

from jinja2 import StrictUndefined, TemplateError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment, SecurityError

from app.services.errors import InvalidDataError


class _OptionalAwareUndefined(StrictUndefined):
    """Estricto al imprimir, recorrer o comparar; falso en condiciones y con "or"."""

    def __bool__(self) -> bool:
        return False


@cache
def _environment(html: bool) -> SandboxedEnvironment:
    return SandboxedEnvironment(autoescape=html, undefined=_OptionalAwareUndefined, keep_trailing_newline=False)


def check_syntax(label: str, source: str | None, *, html: bool) -> None:
    """422 si la plantilla no se puede interpretar (se valida al guardarla)."""
    if source is None:
        return
    try:
        _environment(html).parse(source)
    except TemplateError as error:
        line = f" (línea {error.lineno})" if getattr(error, "lineno", None) else ""
        raise InvalidDataError(f"{label}: plantilla no válida{line}: {error.message}", code="template_error") from None


def render(label: str, source: str | None, parameters: dict, *, html: bool) -> str | None:
    if source is None:
        return None
    try:
        return _environment(html).from_string(source).render(**parameters)
    except UndefinedError as error:
        raise InvalidDataError(f"{label}: falta un parámetro ({error.message}).", code="template_parameter_missing") from None
    except SecurityError:
        raise InvalidDataError(f"{label}: la plantilla usa una operación no permitida.", code="template_error") from None
    except TemplateError as error:
        raise InvalidDataError(f"{label}: no se pudo armar la plantilla ({error.message}).", code="template_error") from None
    except (TypeError, ValueError, ArithmeticError) as error:  # p. ej. iterar un número, dividir por cero.
        raise InvalidDataError(f"{label}: error al armar la plantilla ({type(error).__name__}).", code="template_error") from None


def render_subject(source: str, parameters: dict) -> str:
    subject = (render("subject_template", source, parameters, html=False) or "").strip()
    if not subject:
        raise InvalidDataError("subject_template: el asunto quedó vacío.", code="template_error")
    if "\r" in subject or "\n" in subject:
        raise InvalidDataError("subject_template: el asunto armado no puede tener saltos de línea.", code="template_error")
    if len(subject) > 998:
        raise InvalidDataError("subject_template: el asunto armado supera 998 caracteres.", code="template_error")
    return subject
