"""Rutas que la central publica de cada servicio (lista positiva, en código).

Solo se reenvía lo que está aquí; lo demás responde 404 sin llegar al servicio.
Un prefijo incluye todo lo que cuelga de él ("/auth/me" cubre
"/auth/me/sessions/..."). Para dejar de publicar algo: borra o comenta su
línea, o quita un método. Para ser más fino, agrega una línea más específica
y quita la general. Cada cambio requiere redesplegar la central.

timeout: segundos para esa ruta; None = el del servicio (<SERVICIO>_TIMEOUT_SECONDS).
Con streaming, es la espera máxima para conectar y entre dos trozos de la
respuesta, no la duración total de una descarga.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    prefix: str
    methods: frozenset[str]
    timeout: float | None = None


READ = frozenset({"GET"})
WRITE = frozenset({"GET", "POST", "PATCH", "DELETE"})
POST = frozenset({"POST"})


AUTH_ROUTES: tuple[Route, ...] = (
    # Comprobaciones y documentación de auth.
    Route("/auth/health", READ),
    Route("/auth/ready", READ),
    Route("/auth/docs", READ),
    Route("/auth/redoc", READ),
    Route("/auth/openapi.json", READ),
    # Registro, login y sesión.
    Route("/auth/users", POST),
    Route("/auth/login", POST),
    Route("/auth/refresh", POST),
    Route("/auth/logout", POST),
    # Cuenta propia: perfil, documentos, sesiones, permisos y contraseña.
    Route("/auth/me", WRITE),
    Route("/auth/catalog", READ),
    # Organización de la empresa activa.
    Route("/auth/areas", WRITE),
    Route("/auth/positions", WRITE),
    Route("/auth/roles", WRITE),
    Route("/auth/members", WRITE),
    Route("/auth/history", READ),
    Route("/auth/api-keys", WRITE),
    # Administración de plataforma (incluye /auth/admin/logs).
    Route("/auth/admin", WRITE),
    # Bootstrap: auth solo registra la ruta con SEED_ENABLED=true y exige X-Seed-Token.
    Route("/auth/seed", POST),
)

LIBRO_MAYOR_ROUTES: tuple[Route, ...] = (
    # Comprobaciones y documentación.
    Route("/libro-mayor/health", READ),
    Route("/libro-mayor/ready", READ),
    Route("/libro-mayor/docs", READ),
    Route("/libro-mayor/redoc", READ),
    Route("/libro-mayor/openapi.json", READ),
    # Configuración: cuentas, categorías, reglas (incluye /rules/import) y homologación.
    Route("/libro-mayor/accounts", WRITE),
    Route("/libro-mayor/categories", WRITE),
    Route("/libro-mayor/rules", WRITE),
    Route("/libro-mayor/cost-centers", READ),
    Route("/libro-mayor/cost-center-mappings", WRITE),
    # Trabajos: sincronización y reclasificación (el worker los procesa).
    Route("/libro-mayor/sync-runs", WRITE),
    Route("/libro-mayor/sync-status", READ),
    Route("/libro-mayor/classification-runs", WRITE),
    # Consultas sobre lo sincronizado: lines, lines.csv (streaming) y summary.
    Route("/libro-mayor/ledger", READ),
    # Consulta a SAP en la misma solicitud: libro-mayor corta a los 120 s
    # (LIVE_QUERY_TIMEOUT_SECONDS); la central espera un poco más para
    # devolver su respuesta (504 propio) y no cortarla antes.
    Route("/libro-mayor/live-queries", POST, timeout=130),
    # Administración de plataforma: compañía SAP y logs (los valida el servicio).
    Route("/libro-mayor/admin/sap-company", WRITE),
    Route("/libro-mayor/admin/logs", READ),
    # Carga inicial: libro-mayor solo registra la ruta con SEED_ENABLED=true.
    Route("/libro-mayor/admin/seed", POST),
)

# Acuerdo (2026-10-01): todo salvo health y ready. Los permisos los valida
# notificaciones con auth (notifications.view/send/retry/admin).
NOTIFICACIONES_ROUTES: tuple[Route, ...] = (
    # Documentación.
    Route("/notificaciones/docs", READ),
    Route("/notificaciones/redoc", READ),
    Route("/notificaciones/openapi.json", READ),
    # Cuentas SMTP de la empresa (incluye /restore y /test). POST /{id}/test espera
    # al servidor SMTP hasta timeout_seconds de la cuenta (máx. 120): la central
    # espera un poco más para no cortarlo antes.
    Route("/notificaciones/smtp-accounts", POST, timeout=130),
    Route("/notificaciones/smtp-accounts", WRITE),
    # Crear envíos: multipart con adjuntos (hasta 100 MB por el borde) y 500
    # mensajes que se validan y arman antes de responder. Más que los 30 s por
    # defecto; si se corta, el consumidor reintenta con la misma Idempotency-Key.
    Route("/notificaciones/dispatches", POST, timeout=120),
    # Consultas de envíos y mensajes; reproceso y cancelación (paso posterior).
    Route("/notificaciones/dispatches", WRITE),
    Route("/notificaciones/messages", WRITE),
    # Plantillas generales (incluye /restore y /preview).
    Route("/notificaciones/templates", WRITE),
    # Carga inicial: notificaciones solo registra la ruta con SEED_ENABLED=true.
    Route("/notificaciones/admin/seed", POST),
)

# Todo salvo health y ready (mismo criterio que notificaciones). Los permisos
# los valida pagos-proveedores con auth (payments.view/providers.manage/send/admin).
PAGOS_PROVEEDORES_ROUTES: tuple[Route, ...] = (
    # Documentación.
    Route("/pagos-proveedores/docs", READ),
    Route("/pagos-proveedores/redoc", READ),
    Route("/pagos-proveedores/openapi.json", READ),
    # Maestro de proveedores (incluye /restore).
    Route("/pagos-proveedores/providers", WRITE),
    # Crear un lote lee hasta 100 PDFs (con OCR si son escaneados, varios segundos
    # cada uno) y enviarlo espera a notificaciones (hasta 120 s): el máximo
    # admitido. Si se corta, el lote sigue en la base (se consulta o se reenvía).
    Route("/pagos-proveedores/batches", POST, timeout=300),
    # Consultas, descargas (constancia y ZIP), quitar archivos y descartar.
    Route("/pagos-proveedores/batches", WRITE),
    # Configuración de la empresa (plantilla por defecto; cambiarla: payments.admin).
    Route("/pagos-proveedores/settings", WRITE),
)
