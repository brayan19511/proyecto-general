"""Aplica las migraciones del schema audit (paquete platform_audit) con la
misma conexión del servicio. Ejecutar después de `alembic upgrade head`:

    python scripts/migrate_audit.py

Es idempotente: si el schema ya está al día, no hace nada. Si otro servicio
comparte la base y ya lo migró, tampoco.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Para importar app.

from platform_audit.migrate import upgrade  # noqa: E402

from app.core.db.connection import engine  # noqa: E402

if __name__ == "__main__":
    upgrade(engine)
    print("Schema audit al día.")
