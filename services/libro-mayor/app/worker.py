"""Worker de sincronización: proceso separado de la API (misma imagen, otro comando).

    python -m app.worker          # queda corriendo; busca pendientes cada SYNC_POLL_SECONDS
    python -m app.worker --once   # procesa las pendientes que haya y termina (pruebas)

Toma trabajo pendiente, una unidad por vez, en este orden de prioridad:
1. Reclasificaciones (classification_runs): no consultan SAP.
2. Sincronizaciones (sync_runs).
Varios workers pueden correr a la vez: cada uno toma una unidad distinta
(SKIP LOCKED). Las consultas en vivo no pasan por aquí: responden en la misma
solicitud HTTP (app/services/live_query_service.py). Al recibir SIGTERM/Ctrl+C termina la
ejecución en curso y sale; si lo matan antes, esa ejecución queda "running"
sin avance y se marca interrumpida pasado SYNC_STALE_MINUTES.

Horario (SYNC_SCHEDULE en SAP_TIMEZONE): en cada vuelta crea, si faltan, las
ejecuciones del turno actual (carga inicial o delta por cuenta); luego las
procesa como cualquier otra. Con SYNC_SCHEDULE=off solo procesa las manuales.
Sus mensajes van a la salida estándar (no pasa por el middleware de logs HTTP);
el estado definitivo de cada trabajo está en sync_runs.
"""

import argparse
import logging
import signal
import time

from app.core.config import settings
from app.core.db.connection import SessionLocal
from app.services import classification_service, sync_service

logger = logging.getLogger("libro_mayor.worker")
_stop = False


def _request_stop(signum, _frame):
    global _stop
    _stop = True
    logger.info("Señal %s recibida: se termina la ejecución en curso y se sale.", signum)


def run(once: bool = False) -> None:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    logger.info(
        "Worker iniciado (poll %ss, horario %s %s).",
        settings.SYNC_POLL_SECONDS, settings.SYNC_SCHEDULE, settings.SAP_TIMEZONE,
    )
    while not _stop:
        with SessionLocal() as db:
            if _work_once(db):
                continue  # Puede haber más pendientes: buscar sin esperar.
        if once:
            break
        # Espera en pasos cortos para reaccionar pronto a SIGTERM.
        for _ in range(settings.SYNC_POLL_SECONDS):
            if _stop:
                break
            time.sleep(1)
    logger.info("Worker detenido.")


def _work_once(db) -> bool:
    """Marca interrumpidos, programa el turno y procesa UNA unidad. True si hubo trabajo."""
    sync_service.mark_stale_runs(db)
    classification_service.mark_stale(db)
    sync_service.enqueue_scheduled(db)  # Crea las del turno actual que falten (no hace nada si ya existen).

    run_id = classification_service.claim_next(db)
    if run_id is not None:
        logger.info("Procesando reclasificación %s", run_id)
        classification_service.process(db, run_id)
        return True
    run_id = sync_service.claim_next(db)
    if run_id is not None:
        logger.info("Procesando sincronización %s", run_id)
        sync_service.process(db, run_id)
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de sincronización de libro-mayor.")
    parser.add_argument("--once", action="store_true", help="Procesar las pendientes y terminar.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(once=args.once)


if __name__ == "__main__":
    main()
