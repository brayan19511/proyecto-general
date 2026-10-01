# Servicio notificaciones

Estado (2026-10-01): **alcance v1 implementado**, dockerizado y publicado en la
central (`NOTIFICACIONES_ENABLED`). Canal email por SMTP.

## Qué hace

- **Cuentas SMTP por empresa** con prioridad y failover, contraseña cifrada
  (`MultiFernet`), prueba de conexión sin enviar, protección SSRF y TLS
  verificado.
- **Envíos** (`POST /dispatches`, multipart): N mensajes con adjuntos,
  idempotencia (`Idempotency-Key`), validación de tipos por contenido,
  destinatarios y tamaño (25 MB por mensaje). Asíncrono: responde 202.
- **Plantillas generales** (Jinja2 en sandbox) con destinatarios fijos; un
  envío usa `template_code` + `parameters` o contenido armado.
- **Worker** (`python -m app.worker`): envía, reintenta 3 veces (1, 5 y 15
  min), deja `uncertain` lo que no sabe si salió y purga adjuntos al enviar.
- **Retención**: aviso al solicitante a las 48 h de un fallo y cancelación a
  las 72 h.
- **Consultas** con alcance own/company, reproceso y cancelación manuales,
  descarga de adjuntos, historial y logs (`packages/platform-audit`).
- **Seed** (`POST /admin/seed`, `SEED_ENABLED`): plantillas por empresa.

Primer consumidor: `services/pagos-proveedores`.

## Ejecutar en local

Desde `services/notificaciones`, con Python 3.14 (uuid7, igual que el Dockerfile):

```powershell
py -3.14 -m venv enviroment
.\enviroment\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # DB_*, AUTH_URL, SMTP_ENCRYPTION_KEYS (ver comentarios)
alembic upgrade head
python -m uvicorn app.main:app --port 8010
python -m app.worker          # en otra terminal; --once procesa y termina
```

En Windows usar `DB_HOST=127.0.0.1` (no `localhost`: intenta IPv6 primero y
tarda). En Docker: `desarrollo/plataforma-completa` (API `notificaciones`,
`notificaciones-worker` y `notificaciones-migrate`).

## Permisos (catálogo de auth)

`notifications.view` · `.send` · `.retry` (alcance own o company) y `.admin`
(company); cada nivel incluye al anterior. `ADMIN_EMPRESA` recibe
`notifications.admin` por el seed de auth.

## Documentos

- [Alcance y acuerdos](docs/alcance.md)
- [Modelo de datos](docs/modelo-datos.md)
- [Contrato de la API y reglas](docs/api.md)

## Pendientes

- Credenciales máquina en auth para envíos sin usuario (procesos programados).
- La central lee el cuerpo entero en memoria antes de reenviarlo (multipart de
  hasta 100 MB).
- Canales futuros (WhatsApp, mapeado en el alcance) y división de mensajes
  grandes `(1/N)`.
- Validar en SQL Server (`SKIP LOCKED`, índices filtrados).
