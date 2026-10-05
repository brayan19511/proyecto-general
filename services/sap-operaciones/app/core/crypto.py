"""Cifrado de las claves SAP de los operadores guardadas en los trabajos.

Fernet (cryptography): cifrado autenticado, así un valor alterado en la base
no se descifra en silencio, sino que falla. MultiFernet cifra con la primera
clave de CREDENTIALS_ENCRYPTION_KEYS y descifra con cualquiera de ellas.

Decisión del usuario (2026-10-04): las credenciales se conservan cifradas y
solo el administrador de plataforma puede verlas (acción con historial).
Nunca registrar en logs ni devolver el texto descifrado fuera de esa ruta.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

_cipher = MultiFernet([Fernet(key.get_secret_value()) for key in settings.CREDENTIALS_ENCRYPTION_KEYS])


class SecretDecryptionError(Exception):
    """El valor no se pudo descifrar con ninguna clave configurada."""


def encrypt_secret(plain: str) -> str:
    return _cipher.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _cipher.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Clave retirada o valor alterado. Sin detalles: no ayudan a un atacante.
        raise SecretDecryptionError("No se pudo descifrar la credencial") from None
