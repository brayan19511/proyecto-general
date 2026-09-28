from pwdlib import PasswordHash


# Una instancia reutilizable con la configuración recomendada de Argon2.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Genera el hash que guardaremos en users.password_hash."""
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Comprueba una contraseña contra el hash almacenado."""
    return password_hasher.verify(password, stored_hash)


# Hash de una contraseña que nadie conoce. El login lo verifica cuando el email
# no existe, para tardar lo mismo que con un email real: así el tiempo de
# respuesta no revela qué cuentas están registradas.
DUMMY_PASSWORD_HASH = hash_password("cuenta-inexistente")