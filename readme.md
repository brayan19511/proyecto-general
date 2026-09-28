# Plataforma de servicios multiempresa

## Forma de trabajo

El usuario escribe el código. El asistente explica, revisa y propone un paso pequeño por vez. No se implementan funcionalidades ni se cambia el diseño sin una petición explícita para ese paso. Esta regla vive en AGENTS.md y se aplica también en otros chats abiertos en este proyecto.

## Estado real

services/auth es funcional: registro, login con JWT RS256 y refresh rotativo, sesiones, seed idempotente, empresas, áreas, puestos, roles, permisos con alcance, miembros, API keys, documentos de identidad, historial y logs (schema `audit`, vía packages/platform-audit). Ver [services/auth/readme.md](services/auth/readme.md). Tiene health/ready y Dockerfile; faltan pruebas automatizadas y despliegue. services/apigateway (API central) tiene configuración, health/ready y logs; el reenvío a auth está pendiente. Su carpeta también contiene el Compose local de PostgreSQL y pgAdmin. services/base es la plantilla para nuevos servicios FastAPI. Las reglas de negocio descritas son objetivos, no capacidades ya disponibles.

general.txt es un antecedente descartado.

## Documentación

- [Arquitectura](docs/arquitectura.md)
- [Auth](services/auth/readme.md)
- [platform-audit: logs compartidos (schema audit)](packages/platform-audit/README.md)
- [Plan de seguimiento propio (logs)](docs/plan-observabilidad.md)
- [Guía y explicación del código](services/auth/docs/desarrollo-guiado.md)
- [Requisitos de auth](services/auth/docs/requisitos.md)
- [Modelo de datos](services/auth/docs/modelo-datos.md)
- [Instrucciones de colaboración](AGENTS.md)

## Dirección acordada

Servicios independientes bajo services/, cada uno con sus datos, dependencias y futuro contenedor. Código compartido entre servicios Python bajo packages/ (hoy: platform-audit para logs). API central para enrutamiento y coordinación. Seguimiento propio con logs, logs_detail y logs_steps; historial de negocio separado. Sin OpenTelemetry.

PostgreSQL será el primer motor, en un contenedor separado. SQL Server es un objetivo de portabilidad por confirmar y probar; SQLite está excluido. La central se construye paso a paso; los servicios futuros no se construyen ahora.

