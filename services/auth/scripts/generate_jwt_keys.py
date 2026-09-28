"""Genera el par de claves RSA para firmar JWT (RS256).

Uso, desde services/auth:
    python scripts/generate_jwt_keys.py

Crea secrets/jwt_private.pem y secrets/jwt_public.pem. Nunca sobrescribe
claves existentes: regenerarlas invalida todos los tokens emitidos.
La carpeta secrets/ está excluida del repositorio por .gitignore.
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SECRETS_DIR = Path(__file__).resolve().parents[1] / "secrets"
PRIVATE_KEY = SECRETS_DIR / "jwt_private.pem"
PUBLIC_KEY = SECRETS_DIR / "jwt_public.pem"


def main() -> None:
    if PRIVATE_KEY.exists() or PUBLIC_KEY.exists():
        raise SystemExit(f"Ya existen claves en {SECRETS_DIR}; no se sobrescriben.")

    SECRETS_DIR.mkdir(exist_ok=True)

    # 2048 bits es el mínimo recomendado para RSA.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    PRIVATE_KEY.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Claves creadas en {SECRETS_DIR}")


if __name__ == "__main__":
    main()
