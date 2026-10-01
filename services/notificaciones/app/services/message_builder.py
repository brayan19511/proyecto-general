"""Armado del mensaje MIME: el mismo al crear (para medir el tamaño) y al enviar.

- bcc NUNCA va en los headers: solo en el destino de la entrega SMTP (si no,
  todos verían a quién se envió en copia oculta).
- Con body_html y body_text se arma multipart/alternative: el cliente de correo
  muestra el HTML o, si no puede, el texto.
- El asunto y el reply-to no admiten saltos de línea (inyección de headers).
- Al crear, el From todavía no se conoce (la cuenta se elige al enviar): se mide
  con uno provisional; la diferencia es de unas decenas de bytes frente al límite.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr

from app.core.config import settings
from app.services.errors import InvalidDataError
from app.services.recipients import Recipients

# Remitente provisional para medir el tamaño al crear (longitud típica de una dirección).
PLACEHOLDER_FROM = formataddr(("Remitente de la empresa", "notificaciones@empresa.example"))


@dataclass(frozen=True)
class Attachment:
    filename: str  # Ya saneado.
    content_type: str  # Ya detectado, p. ej. "text/csv; charset=utf-8".
    content: bytes


def _single_line(label: str, value: str) -> str:
    if "\r" in value or "\n" in value:
        raise InvalidDataError(f"{label} no admite saltos de línea.")
    return value


def build_mime(
    *,
    from_header: str,
    recipients: Recipients,
    reply_to: str | None,
    subject: str,
    body_html: str | None,
    body_text: str | None,
    message_id: str,
    attachments: list[Attachment],
) -> EmailMessage:
    message = EmailMessage(policy=SMTP)
    message["From"] = from_header
    message["To"] = ", ".join(recipients.to)
    if recipients.cc:
        message["Cc"] = ", ".join(recipients.cc)
    if reply_to:
        message["Reply-To"] = _single_line("reply_to", reply_to)
    message["Subject"] = _single_line("subject", subject)
    message["Message-ID"] = message_id

    if body_text is not None:
        message.set_content(body_text, subtype="plain", charset="utf-8")
        if body_html is not None:
            message.add_alternative(body_html, subtype="html", charset="utf-8")
    else:
        message.set_content(body_html, subtype="html", charset="utf-8")

    for attachment in attachments:
        main, _, rest = attachment.content_type.partition("/")
        subtype = rest.split(";", 1)[0].strip()
        message.add_attachment(attachment.content, maintype=main, subtype=subtype, filename=attachment.filename)
    return message


def mime_size(message: EmailMessage) -> int:
    """Bytes que se transmitirán (CRLF y adjuntos ya codificados en base64)."""
    return len(message.as_bytes(policy=SMTP))


def check_size(size_bytes: int, *, message_index: int) -> None:
    """422 message_too_large si el mensaje supera MESSAGE_MAX_BYTES. No se divide (acuerdo)."""
    if size_bytes > settings.MESSAGE_MAX_BYTES:
        raise InvalidDataError(
            f"El mensaje {message_index} pesa {size_bytes} bytes y el máximo es {settings.MESSAGE_MAX_BYTES}.",
            code="message_too_large",
            extra={"message_index": message_index, "size_bytes": size_bytes, "limit_bytes": settings.MESSAGE_MAX_BYTES},
        )
