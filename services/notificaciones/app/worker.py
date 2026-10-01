"""Worker de envío: proceso separado de la API (misma imagen, otro comando).

    python -m app.worker          # queda corriendo; busca pendientes cada WORKER_POLL_SECONDS
    python -m app.worker --once   # procesa lo que esté listo y termina (pruebas)

En cada vuelta: marca uncertain los mensajes con el bloqueo vencido y luego
toma y envía mensajes de a uno (app/services/delivery_service.py). Varios
workers pueden correr a la vez: cada uno toma un mensaje distinto (SKIP LOCKED).
Cada RETENTION_INTERVAL_SECONDS (y al arrancar) ejecuta la retención: cancela
por plazo y crea los avisos previos (app/services/retention_service.py).

Al recibir SIGTERM/Ctrl+C termina el mensaje en curso y sale. Si lo matan a
mitad de un envío, ese mensaje queda en sending y, al vencer su bloqueo, pasa a
uncertain (no se reenvía solo: pudo haberse entregado).

Sus mensajes van a la salida estándar, solo con ids (sin destinatarios ni
contenido); el estado definitivo de cada mensaje está en la base.
"""

import argparse
import logging
import os
import signal
import socket
import time

from app.core.config import settings
from app.core.db.connection import SessionLocal
from app.services import delivery_service, retention_service

logger = logging.getLogger("notificaciones.worker")
_stop = False


def _request_stop(signum, _frame):
    global _stop
    _stop = True
    logger.info("Señal %s recibida: se termina el mensaje en curso y se sale.", signum)


def run(once: bool = False) -> None:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    # Identifica a este proceso en messages.locked_by (varias réplicas, varios procesos).
    worker_id = f"{socket.gethostname()}:{os.getpid()}"[:100]
    logger.info(
        "Worker %s iniciado (poll %ss, bloqueo %ss, reintentos %s).",
        worker_id, settings.WORKER_POLL_SECONDS, settings.WORKER_LOCK_SECONDS, settings.RETRY_DELAYS_SECONDS,
    )
    last_retention = None  # Monotónico: no le afectan los cambios de hora del sistema.
    while not _stop:
        now = time.monotonic()
        if last_retention is None or now - last_retention >= settings.RETENTION_INTERVAL_SECONDS:
            with SessionLocal() as db:
                cancelled, notices = retention_service.run(db)
            if cancelled or notices:
                logger.info("Retención: %s cancelado(s), %s aviso(s).", cancelled, notices)
            last_retention = now
        with SessionLocal() as db:
            if _work_once(db, worker_id):
                continue  # Puede haber más listos: buscar sin esperar.
        if once:
            break
        # Espera en pasos cortos para reaccionar pronto a SIGTERM.
        for _ in range(settings.WORKER_POLL_SECONDS):
            if _stop:
                break
            time.sleep(1)
    logger.info("Worker detenido.")


def _work_once(db, worker_id: str) -> bool:
    """Marca bloqueos vencidos y envía UN mensaje. True si hubo trabajo."""
    delivery_service.mark_expired_locks(db)
    message_id = delivery_service.claim_next(db, worker_id)
    if message_id is None:
        return False
    delivery_service.process(db, message_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de envío de notificaciones.")
    parser.add_argument("--once", action="store_true", help="Procesar lo que esté listo y terminar.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(once=args.once)


if __name__ == "__main__":
    main()
