"""Cifrado de secretos guardados en la base (contraseñas SMTP).

Usa Fernet (cryptography): cifrado autenticado, así un valor alterado en la
base no se descifra en silencio, sino que falla. MultiFernet cifra con la
primera clave de SMTP_ENCRYPTION_KEYS y descifra con cualquiera de ellas.
Nunca registrar en logs ni devolver en la API el texto descifrado.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

_cipher = MultiFernet([Fernet(key.get_secret_value()) for key in settings.SMTP_ENCRYPTION_KEYS])


class SecretDecryptionError(Exception):
    """El valor no se pudo descifrar con ninguna clave configurada."""


def encrypt_secret(plain: str) -> str:
    """Cifra con la clave principal; devuelve texto apto para una columna Text."""
    return _cipher.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Descifra con cualquiera de las claves configuradas."""
    try:
        return _cipher.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Clave retirada o valor alterado. Sin detalles: no ayudan a un atacante.
        raise SecretDecryptionError("No se pudo descifrar el secreto") from None
