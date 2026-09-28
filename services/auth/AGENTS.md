# Identidad y acceso

Lee las instrucciones raíz, `docs/requisitos.md` y `docs/modelo-datos.md` de este servicio.

## Tecnología

Python + FastAPI y modelos SQLAlchemy. Dependencias mínimas explícitas en requirements.txt; consultar antes de agregar otras.

Estado actual: configuración, conexión PostgreSQL, modelos, migraciones Alembic aplicadas, hash Argon2 y service de registro sin ruta. Ver readme.md. El usuario codifica; el asistente guía según AGENTS.md raíz. Lee docs/desarrollo-guiado.md antes de proponer el siguiente paso. No crear automáticamente migraciones, rutas, seed, Docker ni pruebas de integración.

PostgreSQL primero, SQL Server como objetivo; SQLite excluido. Evitar SQL específico del proveedor salvo necesidad explicada y acordada. No afirmar compatibilidad hasta validar ambos motores. El seed será una ruta API `/seed` idempotente (decisión del usuario); su autorización, habilitación y cierre se acuerdan antes de implementarla. Nunca ejecutarlo como efecto de importar la aplicación.

Atribución: created_by/updated_by/deleted_by referencian users.id. Toda operación registra al usuario responsable; el autorregistro se atribuye al propio usuario creado. NULL solo se admite en los registros creados por el seed y en los contadores anónimos de login (rate_buckets).

## Reglas

- Registro y login públicos; sin invitaciones ni verificación de correo en esta entrega.
- Una cuenta nueva no tiene membresías ni privilegios empresariales automáticos.
- Solo administradores autorizados asignan empresas, puestos y roles de puestos.
- Excepción acordada a la herencia por puestos: `users.is_platform_admin` (master admin). Solo el seed lo activa; ningún schema de la API debe aceptarlo ni exponer su modificación sin una decisión explícita.
- Documentos mediante país emisor y catálogo de tipos; no asumas Perú ni DNI como obligatorios.
- Política de sesiones configurable; API keys con vencimiento opcional (null significa sin fecha límite).
- Conserva expiración finita de JWT y sesiones según política, distinta de la duración de API keys.
- Implementa límites locales de auth; no dependas de la futura API central para proteger login.
- Todas las entidades y relaciones conservan atribución y baja lógica según el modelo común.
- Eventos históricos de solo anexado; ninguna operación DELETE debe eliminar físicamente filas.
- El backend asigna actores y fechas. Nunca confíes en created_by/updated_by enviados por el cliente.
- Registra cambios de negocio anteriores/nuevos permitidos de forma transaccional, excluyendo secretos.
- Seguimiento propio mediante logs/logs_detail/logs_steps locales, con lista positiva de metadatos y duración monotónica. Nunca capturar bodies de auth.
- Acuerdos: cliente web, sesiones de cinco horas, tres simultáneas configurables por usuario y bloqueo tras cinco fallos. Duración absoluta/inactividad, respuesta al exceso, ventana y duración del bloqueo, y transporte de tokens siguen como propuestas a confirmar antes de implementarse.

## Verificación

Prueba aislamiento entre empresas, cuentas sin membresía, alcance de delegación administrativa, herencia de permisos, revocación, rotación y concurrencia de sesiones/claves. Verifica que las bajas no permiten recuperar acceso, que las relaciones siguen disponibles para historial y que catálogos internacionales no dependen de un único país.
