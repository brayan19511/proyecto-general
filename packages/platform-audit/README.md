# platform-audit

Seguimiento propio (logs) común a los servicios de la plataforma. Un solo
código, instalado en cada servicio Python: si se cambia aquí, todos lo reciben.

## Qué hace

| Pieza | Qué registra | Cómo se usa |
| --- | --- | --- |
| `AuditMiddleware` | Cada solicitud HTTP: cabecera + detalles | Una línea en `main.py` |
| `step("nombre")` | Inicio/fin/error de un paso, en el momento | `with step(...)` o `@step(...)` |
| `log_message(level, msg, data)` | Un mensaje manual (info, success, warning, error) | Donde haga falta |
| `set_actor(user_id, company_id)` | Quién hace la solicitud | Tras validar la identidad |
| `proxies.client_ip / is_trusted` | IP real del cliente detrás de proxies confiables (IP o CIDR) | Límites por IP, reenvío |
| `queries.list_logs / get_log` | Lectura de las filas del propio servicio | Rutas de consulta del servicio |
| `migrate.upgrade(engine)` | Crea/actualiza el schema `audit` | Una vez por despliegue |

## Dónde se guarda: schema `audit`

| Tabla | Contenido |
| --- | --- |
| `audit.logs` | Cabecera: trace_id, operación padre, servicio y versión, método, ruta, estado HTTP, resultado (success/warning/error), IP, user agent, usuario y empresa, inicio, fin y duración |
| `audit.logs_detail` | Detalles: `request` (parámetros, headers permitidos, body), `response` (mensaje de error si status ≥ 400), `error` (tipo de excepción), `message` (manuales). Con nivel info/success/warning/error |
| `audit.logs_steps` | Pasos manuales: una fila al empezar y otra al terminar o fallar, con duración |

El schema es de este paquete, no de un servicio. Cada servicio escribe solo sus
filas (columna `service`) y consulta solo las suyas. La vista entre servicios
se hará por APIs internas, nunca leyendo filas de otro servicio.

## Qué nunca se guarda

- Campos sensibles en bodies, parámetros y headers (a cualquier profundidad,
  también dentro de listas): se reemplazan por `***`. Ver "Configurar qué es sensible".
- Headers fuera de la lista positiva (`DEFAULT_ALLOWED_HEADERS`): Authorization,
  Cookie o X-API-Key ni siquiera se copian.
- Bodies de más de `max_body_bytes` (4 KB por defecto) o que no son JSON: solo su tipo y tamaño.
- Mensajes y trazas de excepciones: solo el tipo (pueden contener datos sensibles).

## Configurar qué es sensible

Dos listas de constantes en `config.py`:

| Constante | Regla | Ejemplos |
| --- | --- | --- |
| `DEFAULT_SENSITIVE_KEYS` | Nombre **exacto** del campo | `email`, `dni`, `rut`, `api_key`, `authorization` |
| `DEFAULT_SENSITIVE_KEY_PARTS` | El nombre **contiene** el fragmento | `password`, `contrasena`, `clave`, `token`, `secret` |

- Mayúsculas y acentos no importan: `Contraseña`, `CONTRASENA_NUEVA` y
  `contraseñaActual` se ocultan con el fragmento `contrasena`.
- Fragmentos distintivos: uno corto (`pin`) también ocultaría `shipping`. Para
  palabras cortas, usa la lista exacta.

Dónde cambiarlo:

- **Para toda la plataforma**: edita las constantes en `config.py` del paquete.
- **Solo para un servicio**: pásale sus listas a `AuditConfig`, sumando o reemplazando:
  ```python
  from platform_audit.config import DEFAULT_SENSITIVE_KEYS, DEFAULT_SENSITIVE_KEY_PARTS

  AuditConfig(
      ...,
      sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"numero_tarjeta"},   # sumar
      sensitive_key_parts=frozenset({"password", "contrasena"}),     # reemplazar
  )
  ```
  En auth esto vive en `services/auth/app/core/audit.py`.

El límite de tamaño del body es `max_body_bytes` (constante `DEFAULT_MAX_BODY_BYTES`, 4096).

## Garantías

- **Un fallo de logging no rompe la operación**: se emite un aviso con el tipo
  de error y la solicitud sigue.
- **Fuera de la transacción de negocio**: conexiones propias del mismo engine.
- **Trazas entrantes** (`X-Trace-Id`, `X-Parent-Operation-Id`) y `X-Forwarded-For` solo se aceptan
  desde `trusted_proxies`; de cualquier otro origen se genera una traza nueva
  y se usa la IP de la conexión. Correlación nunca equivale a autorización.
- `trusted_proxies` acepta IPs exactas (`"10.0.0.5"`) o rangos CIDR
  (`"172.30.0.0/24"`); un valor inválido falla al arrancar. Un rango confía en
  todo lo que contiene: usarlo solo con redes exclusivas. Los servicios que
  necesiten la IP real (límites) usan la misma regla: `platform_audit.proxies.client_ip`.
- La respuesta incluye `X-Trace-Id`, para citarlo al reportar un problema.
- Duración con reloj monotónico; fechas en UTC.
- Una cabecera sin `outcome` significa que no se registró el cierre (p. ej. el
  proceso cayó), no que siga ejecutándose.

## Integrar un servicio nuevo

1. Instalar (desde la carpeta del servicio):
   ```text
   # requirements.txt
   -e ../../packages/platform-audit
   ```
2. Migrar el schema con el engine del servicio (idempotente):
   ```python
   from platform_audit.migrate import upgrade
   upgrade(engine)
   ```
3. Registrar el middleware:
   ```python
   from platform_audit import AuditConfig, AuditMiddleware

   app.add_middleware(
       AuditMiddleware,
       config=AuditConfig(engine=engine, service="documentos", service_version="0.1.0",
                          trusted_proxies=frozenset({"10.0.0.5"})),
   )
   ```
4. Llamar `set_actor(user_id, company_id)` donde el servicio valida la identidad.
5. Agregar `step(...)` en los pasos que interese seguir.

Servicios en otro lenguaje: implementan el mismo contrato (tablas, headers,
enmascarado). Este README y `models.py` son la referencia.

## Cambiar el paquete

- Solo cambios compatibles en las tablas (columnas nuevas opcionales): varios
  servicios con versiones distintas del paquete pueden escribir a la vez.
- Nueva revisión: `platform_audit.migrate.revision(engine, "descripcion")`, revisar
  el archivo generado en `migrations/versions/` y subir la versión en `pyproject.toml`.
- La versión aplicada vive en `audit.alembic_version`, separada de la de cada servicio.
