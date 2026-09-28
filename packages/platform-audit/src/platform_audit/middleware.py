"""Middleware ASGI: registra cada solicitud HTTP en audit.logs y audit.logs_detail.

Por solicitud:
  1. Al empezar: crea la cabecera (trace_id, método, ruta, IP, inicio) para
     que los pasos manuales puedan colgarse de ella mientras avanza.
  2. Durante: deja pasar el body hacia la aplicación y guarda una copia hasta
     max_body_bytes (sin consumirlo ni retrasarlo).
  3. Al terminar: cierra la cabecera (estado, resultado, fin, duración,
     usuario) y agrega los detalles: request (parámetros, headers permitidos,
     body enmascarado), response si hubo error (el mensaje) y la excepción si
     la hubo.

Devuelve X-Trace-Id en la respuesta, para citarlo al reportar un problema.
Escribe en un hilo aparte (las escrituras son síncronas) para no bloquear el
servidor, y nunca interrumpe la solicitud si el log falla.
"""

import time

import anyio

from platform_audit import writer
from platform_audit.config import AuditConfig
from platform_audit.context import Operation, _current
from platform_audit.models import Log, LogDetail
from platform_audit.proxies import client_ip, is_trusted
from platform_audit.redact import safe_body, safe_headers, safe_query


def _outcome(status: int) -> str:
    if status >= 500:
        return "error"
    if status >= 400:
        return "warning"
    return "success"


def _valid_id(value: str | None) -> str | None:
    # Identificadores entrantes: solo formato simple y largo acotado.
    if value and len(value) <= 36 and all(ch.isalnum() or ch == "-" for ch in value):
        return value
    return None


class AuditMiddleware:
    def __init__(self, app, config: AuditConfig):
        self.app = app
        self.config = config
        writer.configure(config)

    async def __call__(self, scope, receive, send):
        # Una sola fuente de configuración (writer): se puede ajustar en ejecución.
        config = writer.get_config() or self.config
        if (
            scope["type"] != "http"
            or not config.enabled
            or scope["method"] == "OPTIONS"
            or scope["path"] in config.exclude_paths
        ):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        peer = scope["client"][0] if scope.get("client") else None
        from_trusted = is_trusted(peer, config.trusted_networks)

        # Solo se continúa una traza entrante si viene de un proxy/servicio confiable.
        trace_id = (_valid_id(headers.get("x-trace-id")) if from_trusted else None) or writer.new_id()
        parent_id = _valid_id(headers.get("x-parent-operation-id")) if from_trusted else None

        operation = Operation(log_id=writer.new_id(), trace_id=trace_id)
        token = _current.set(operation)

        await anyio.to_thread.run_sync(
            writer.start_log,
            Log(
                id=operation.log_id,
                trace_id=trace_id,
                parent_operation_id=parent_id,
                service=config.service,
                service_version=config.service_version,
                method=scope["method"],
                path=scope["path"][:300],
                ip_address=client_ip(peer, headers.get("x-forwarded-for", ""), config.trusted_networks),
                user_agent=headers.get("user-agent", "")[:256] or None,
                started_at=writer.now(),
            ),
        )

        request_body = bytearray()
        request_truncated = False
        response_status = 500
        response_body = bytearray()

        async def receive_wrapper():
            nonlocal request_truncated
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if len(request_body) + len(chunk) <= config.max_body_bytes:
                    request_body.extend(chunk)
                else:
                    request_truncated = True
            return message

        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-trace-id", trace_id.encode())]
            elif message["type"] == "http.response.body" and response_status >= 400:
                # Del cuerpo de la respuesta solo interesa el mensaje de error.
                if len(response_body) < config.max_body_bytes:
                    response_body.extend(message.get("body", b"")[: config.max_body_bytes - len(response_body)])
            await send(message)

        error: Exception | None = None
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception as exc:
            error = exc
            response_status = 500
            raise
        finally:
            duration_ms = (time.monotonic() - operation.started_monotonic) * 1000
            finished = writer.now()
            outcome = _outcome(response_status)
            content_type = headers.get("content-type", "")

            details = [
                LogDetail(
                    id=writer.new_id(), log_id=operation.log_id, level="info", kind="request",
                    created_at=finished,
                    data={
                        "query": safe_query(scope.get("query_string", b""), config.masker),
                        "headers": safe_headers(headers, config.allowed_headers, config.masker),
                        "body": safe_body(
                            bytes(request_body), content_type, request_truncated,
                            config.max_body_bytes, config.masker,
                        ),
                    },
                )
            ]
            if response_status >= 400 and error is None:
                details.append(
                    LogDetail(
                        id=writer.new_id(), log_id=operation.log_id, level=outcome, kind="response",
                        created_at=finished,
                        data={"body": safe_body(bytes(response_body), "application/json", False,
                                                config.max_body_bytes, config.masker)},
                    )
                )
            if error is not None:
                # Tipo de la excepción, sin mensaje ni traza: pueden contener datos sensibles.
                details.append(
                    LogDetail(
                        id=writer.new_id(), log_id=operation.log_id, level="error", kind="error",
                        message=type(error).__name__, created_at=finished,
                    )
                )

            await anyio.to_thread.run_sync(
                writer.finish_log,
                operation.log_id,
                {
                    "status_code": response_status,
                    "outcome": outcome,
                    "finished_at": finished,
                    "duration_ms": duration_ms,
                    "user_id": operation.user_id,
                    "company_id": operation.company_id,
                },
                details,
            )
            _current.reset(token)
