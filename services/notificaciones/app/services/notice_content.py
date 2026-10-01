"""Contenido del aviso previo a la cancelación (formato acordado el 2026-10-01).

Texto y HTML. Todo dato que viene de un envío (asuntos, direcciones,
referencias) se escapa en el HTML: un asunto con etiquetas no se interpreta en
el correo de aviso. Se listan como máximo MAX_LISTED mensajes.
"""

from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.core.config import settings

MAX_LISTED = 20
_STATUS_LABEL = {"failed": "fallido", "uncertain": "incierto: quizá sí llegó"}


@dataclass(frozen=True)
class NoticeItem:
    to: list[str]
    subject: str
    status: str


@dataclass(frozen=True)
class NoticeContent:
    subject: str
    body_text: str
    body_html: str


def _local(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(settings.NOTICE_TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def build_notice(
    *,
    dispatch_id: str,
    consumer: str | None,
    consumer_reference: str | None,
    dispatch_created_at: datetime,
    items: list[NoticeItem],
    cancel_at: datetime,
) -> NoticeContent:
    total = len(items)
    plural = "correos no se pudieron" if total != 1 else "correo no se pudo"
    when = _local(cancel_at)
    zone = settings.NOTICE_TIMEZONE
    reference = consumer_reference or dispatch_id
    origin = f' ({consumer})' if consumer else ""

    subject = f"{total} {plural} enviar y se cancelarán el {when}"
    intro = (
        f'Del envío "{reference}"{origin}, creado el {_local(dispatch_created_at)}, '
        f"{total} {plural} entregar tras sus reintentos:"
    )
    listed = items[:MAX_LISTED]
    rest = total - len(listed)
    warning = (
        f"Si no se reprocesan antes del {when} (hora {zone}), se cancelarán y sus "
        "adjuntos se eliminarán. Después no se podrán reprocesar."
    )
    link = settings.NOTICE_LINK_TEMPLATE.replace("{dispatch_id}", dispatch_id) if settings.NOTICE_LINK_TEMPLATE else None

    lines = [f"  • {', '.join(i.to)}: {i.subject} ({_STATUS_LABEL[i.status]})" for i in listed]
    if rest:
        lines.append(f"  … y {rest} más.")
    text = ["Hola,", "", intro, "", *lines, "", warning]
    if link:
        text += ["", f"Revisar el envío: {link}"]

    html_items = "".join(
        f"<li>{escape(', '.join(i.to))}: {escape(i.subject)} <em>({escape(_STATUS_LABEL[i.status])})</em></li>"
        for i in listed
    )
    if rest:
        html_items += f"<li>… y {rest} más.</li>"
    html = (
        f"<p>Hola,</p><p>{escape(intro)}</p><ul>{html_items}</ul><p>{escape(warning)}</p>"
        + (f'<p><a href="{escape(link)}">Revisar el envío</a></p>' if link else "")
    )
    return NoticeContent(subject=subject, body_text="\n".join(text), body_html=html)
