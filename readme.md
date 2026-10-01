# Plataforma de servicios multiempresa

## Forma de trabajo

El usuario escribe el código. El asistente explica, revisa y propone un paso pequeño por vez. No se implementan funcionalidades ni se cambia el diseño sin una petición explícita para ese paso. Esta regla vive en AGENTS.md y se aplica también en otros chats abiertos en este proyecto.

## Estado real

services/auth es funcional: registro, login con JWT RS256 y refresh rotativo, sesiones, seed idempotente, empresas, áreas, puestos, roles, permisos con alcance, miembros, API keys, documentos de identidad, historial y logs (schema `audit`, vía packages/platform-audit). Ver [services/auth/readme.md](services/auth/readme.md). Tiene health/ready y Dockerfile; faltan pruebas automatizadas y despliegue. services/apigateway (API central) tiene configuración, health/ready, logs, reenvío a auth (timeout, sin reintentos, IP real y trace_id) `AUTH_ENABLED`, estado de servicios en su schema `gateway` (sin reinicio, releído cada 5 s, con historial) y administración para el administrador de plataforma (`/gateway/admin/...`, validado con `GET /auth/me`). El Compose de desarrollo completo está en `desarrollo/plataforma-completa` (uno por servicio en `desarrollo/<servicio>`) y las plantillas de producción en `produccion/` (ver sus README). services/edge es el proxy de borde (Caddy, HTTPS con dominio propio). Lista negra de IPs/rangos con vencimiento opcional (`gateway.ip_blocks`, 403 antes de enrutar). Pendiente: límites por IP en la central. services/front-central es la aplicación web de administración (React + TypeScript + Vite, Bootstrap): consume todo a través de la central y tiene su propio contenedor nginx en el Compose (ver [services/front-central/README.md](services/front-central/README.md)). services/notificaciones envía correos por SMTP (cuentas por empresa, plantillas Jinja2 en sandbox, worker con reintentos, retención y seguimiento) y services/pagos-proveedores lee constancias de pago en PDF y las envía a cada proveedor a través de notificaciones; ambos están publicados en la central y en el Compose completo. services/base-fastapi es la plantilla para nuevos servicios FastAPI. Las reglas de negocio descritas son objetivos, no capacidades ya disponibles.

general.txt es un antecedente descartado.

## Documentación

- [Arquitectura](docs/arquitectura.md)
- [Auth](services/auth/readme.md)
- [platform-audit: logs compartidos (schema audit)](packages/platform-audit/README.md)
- [Plan de seguimiento propio (logs)](docs/plan-observabilidad.md)
- [API central](services/apigateway/readme.md) y [módulos y administración](services/apigateway/docs/modulos-y-administracion.md)
- [Guía y explicación del código](services/auth/docs/desarrollo-guiado.md)
- [Requisitos de auth](services/auth/docs/requisitos.md)
- [Modelo de datos](services/auth/docs/modelo-datos.md)
- [Libro mayor / gastos: sincronización SAP, reglas, consultas por área](services/libro-mayor/readme.md) (publicado en la central, apagado por defecto; falta probar contra HANA real)
- [Notificaciones: correos por SMTP, plantillas, reintentos y seguimiento](services/notificaciones/readme.md) (publicado en la central)
- [Pagos a proveedores: maestro, lectura de constancias y envío por notificaciones](services/pagos-proveedores/readme.md) (publicado en la central; falta validar con constancias reales)
- [Instrucciones de colaboración](AGENTS.md)

## Dirección acordada

Servicios independientes bajo services/, cada uno con sus datos, dependencias y futuro contenedor. Código compartido entre servicios Python bajo packages/ (hoy: platform-audit para logs). API central para enrutamiento y coordinación. Seguimiento propio con logs, logs_detail y logs_steps; historial de negocio separado. Sin OpenTelemetry.

PostgreSQL será el primer motor, en un contenedor separado. SQL Server es un objetivo de portabilidad por confirmar y probar; SQLite está excluido. La central se construye paso a paso; los servicios futuros no se construyen ahora.

