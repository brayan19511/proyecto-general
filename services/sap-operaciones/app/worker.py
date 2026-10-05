"""Worker de trabajos SAP: proceso separado de la API (misma imagen, otro comando).

    python -m app.worker          # queda corriendo; busca trabajos cada WORKER_POLL_SECONDS
    python -m app.worker --once   # procesa lo que esté en cola y termina (pruebas)

En cada vuelta: retoma los trabajos de workers caídos (bloqueo vencido) y
luego toma y ejecuta trabajos de a uno (app/services/job_runner.py). Varios
workers pueden correr a la vez: cada uno toma un trabajo distinto (SKIP LOCKED).

Al recibir SIGTERM/Ctrl+C termina el ítem en curso, devuelve el trabajo a la cola
con sus pendientes y sale (lo sigue otro worker o el próximo arranque). Sus mensajes van a la salida estándar, solo con ids.
"""

import argparse
import logging
import os
import signal
import socket
import time

from app.core.config import settings
from app.core.db.connection import SessionLocal
from app.services import job_runner

logger = logging.getLogger("sap-operaciones.worker")
_stop = False


def _request_stop(signum, _frame):
    global _stop
    _stop = True
    logger.info("Señal %s recibida: se sale al terminar la vuelta en curso.", signum)


def run(once: bool = False) -> None:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"[:100]
    logger.info("Worker %s iniciado (poll %ss, bloqueo %ss).", worker_id, settings.WORKER_POLL_SECONDS,
                settings.WORKER_LOCK_SECONDS)
    while not _stop:
        try:
            with SessionLocal() as db:
                job_runner.recover_stale(db)
                job_id = job_runner.claim(db, worker_id)
                if job_id is not None:
                    logger.info("Trabajo %s tomado.", job_id)
                    job_runner.run(db, job_id, worker_id, should_stop=lambda: _stop)
                    continue  # Puede haber más en cola: sin esperar.
        except Exception:  # noqa: BLE001 - el worker no se cae por un trabajo; lo retoma otro al vencer el bloqueo.
            logger.exception("Error en la vuelta del worker")
        if once:
            break
        time.sleep(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Procesa lo que esté en cola y termina.")
    run(once=parser.parse_args().once)
