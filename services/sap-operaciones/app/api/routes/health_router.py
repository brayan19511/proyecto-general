from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.db.connection import engine

# Comprobaciones para el gateway, Docker y orquestadores. Públicas y sin datos:
# no revelan versión, configuración ni detalles de errores. No se registran en
# los logs (exclude_paths en main.py).
router = APIRouter(tags=["health"])


@router.get("/health", operation_id="health")
def health():
    """El proceso está vivo. No consulta dependencias: si falla la base, el
    servicio sigue "vivo" (reiniciarlo no lo arreglaría)."""
    return {"status": "ok"}


@router.get("/ready", operation_id="ready")
def ready(response: Response):
    """Puede atender solicitudes: la base responde. El gateway solo le envía
    tráfico si da 200; con 503 lo saca de rotación hasta que se recupere."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - cualquier fallo de la base = no listo.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}
