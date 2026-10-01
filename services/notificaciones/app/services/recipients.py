"""Destinatarios de un mensaje (acuerdo 2026-10-01).

- Cada dirección se valida y normaliza con email-validator (sin consultar DNS):
  el dominio queda en minúsculas. Solo direcciones simples ("x@y.com"), sin
  nombre visible ("Juan <x@y.com>").
- Duplicados entre to, cc y bcc se quitan sin distinguir mayúsculas; se
  conserva la primera aparición (to tiene prioridad sobre cc y cc sobre bcc).
- Al menos un to y como máximo MAX_RECIPIENTS entre los tres, ya sin duplicados.
"""

from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email

from app.services.errors import InvalidDataError

MAX_RECIPIENTS = 50


@dataclass(frozen=True)
class Recipients:
    to: list[str]
    cc: list[str]
    bcc: list[str]

    @property
    def all(self) -> list[str]:
        """Destino real de la entrega (sobre SMTP), bcc incluido."""
        return self.to + self.cc + self.bcc


def normalize_address(address: str) -> str:
    try:
        return validate_email(address.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        raise InvalidDataError(f"Dirección de correo no válida: {address!r}.") from None


def normalize_fixed(to: list[str], cc: list[str], bcc: list[str]) -> Recipients:
    """Destinatarios fijos de una plantilla: mismas reglas, pero to puede ir vacío
    (lo completa el consumidor al enviar)."""
    seen: set[str] = set()
    lists = []
    for addresses in (to, cc, bcc):
        unique = []
        for address in addresses:
            normalized = normalize_address(address)
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
                unique.append(normalized)
        lists.append(unique)
    fixed = Recipients(*lists)
    if len(fixed.all) > MAX_RECIPIENTS:
        raise InvalidDataError(f"Máximo {MAX_RECIPIENTS} destinatarios fijos entre to, cc y bcc.")
    return fixed


def normalize_recipients(to: list[str], cc: list[str], bcc: list[str]) -> Recipients:
    seen: set[str] = set()

    def unique(addresses: list[str]) -> list[str]:
        result = []
        for address in addresses:
            normalized = normalize_address(address)
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
                result.append(normalized)
        return result

    recipients = Recipients(to=unique(to), cc=unique(cc), bcc=unique(bcc))
    if not recipients.to:
        raise InvalidDataError("Cada mensaje necesita al menos un destinatario en to.")
    if len(recipients.all) > MAX_RECIPIENTS:
        raise InvalidDataError(f"Máximo {MAX_RECIPIENTS} destinatarios por mensaje entre to, cc y bcc.")
    return recipients
