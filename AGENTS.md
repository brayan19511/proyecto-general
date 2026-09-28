# Instrucciones generales

## Forma de colaboración: desarrollo guiado

- El usuario quiere escribir y comprender el código. Por defecto actúa como guía y revisor, no como implementador autónomo.
- Avanza en un solo paso pequeño por vez: explica su objetivo, archivos implicados y conceptos necesarios; espera a que el usuario escriba el código o solicite expresamente implementarlo.
- Una consulta o una propuesta de diseño no autoriza a implementarla. No generes módulos, endpoints, infraestructura ni dependencias anticipadamente.
- Consulta antes de modificar reglas de negocio, modelos, arquitectura o decisiones técnicas. Distingue acuerdos del usuario de recomendaciones pendientes.
- Si se autoriza editar, limita el cambio al paso acordado y explica cada parte. Documenta las nuevas configuraciones: propósito, necesidad, default y momento de uso.
- No convertir recomendaciones en requisitos definitivos sin confirmación. Simplicidad y aprendizaje prevalecen sobre completar de golpe el servicio.
- No usar SQLite, ni siquiera para pruebas. PostgreSQL es el primer motor previsto; SQL Server es un objetivo de portabilidad que requiere revisión y pruebas reales, no una compatibilidad asumida.

## Contexto y alcance

- Lee `docs/arquitectura.md` y los requisitos e instrucciones del servicio antes de modificarlo.
- `general.txt` es un antecedente descartado: no usarlo como requisito ni modificarlo.
- Prioriza código sencillo, explícito y eficiente. No agregues frameworks de infraestructura ni abstracciones para necesidades futuras. Usa librerías mantenidas para criptografía, HTTP y acceso a datos; no implementes primitivas criptográficas propias.
- Cada servicio conserva lenguaje, dependencias, contratos y despliegue propios.
- Implementa el alcance solicitado; los servicios futuros son contexto.
- No accedas a tablas de otro servicio ni compartas entidades internas del ORM entre servicios.
- Documenta contratos HTTP con OpenAPI y planifica cambios incompatibles antes de desplegarlos.

## Identidad y autorización

- Valida usuario, empresa y permisos sobre el recurso en el backend.
- Nunca aceptes campos de actor o empresa sin comprobar su origen y autorización.
- El registro público de una cuenta no concede acceso empresarial.
- Los roles se heredan mediante los puestos activos de una membresía.

## Persistencia e historial

- No implementes borrados físicos ni cascadas destructivas sobre datos persistentes de la aplicación.
- DELETE realiza una baja lógica: is_active=false y atribución de baja.
- Las tablas, incluidas las relaciones, incorporan created_at, created_by, updated_at, updated_by e is_active. Usa deleted_at y deleted_by para distinguir baja lógica de suspensión.
- Los actores pueden ser usuarios, servicios o procesos de sistema; deben identificarse explícitamente. No inventes un usuario para tareas automáticas.
- No aceptes campos de auditoría desde el body: los asigna el servidor.
- Conserva historial de cambios de negocio con actor, fecha, recurso, acción y valores anteriores/nuevos permitidos. updated_by no sustituye ese historial.
- Guarda el cambio y su evento en una misma transacción cuando comparten base de datos.
- Los eventos históricos son de solo anexado: no se editan ni se desactivan para ocultarlos. Las correcciones generan nuevos eventos.
- No guardes contraseñas, hashes de credenciales ni tokens en snapshots de historial o telemetría.
- Los contadores de Redis, cachés y telemetría tienen ciclo de vida propio; no son tablas históricas de negocio.
- Cualquier futura purga o anonimización de datos persistentes requiere una decisión explícita, fuera del DELETE ordinario.

## Observabilidad y límites

- No utilizar OpenTelemetry. Implementa seguimiento propio con logs, logs_detail y logs_steps, correlacionados por trace_id y operación padre.
- Los servicios Python usan el paquete compartido `packages/platform-audit` (schema `audit`, propiedad del paquete); no reimplementar middleware ni tablas por servicio. Servicios en otro lenguaje implementan el mismo contrato.
- Cada servicio escribe y consulta únicamente sus filas (columna service); la central no puede observar pasos internos sin instrumentación del servicio. No crear ahora un servidor central de logs.
- Se guardan parámetros, headers y bodies solo enmascarados (contraseñas, tokens, keys, cookies, emails, documentos) y con límite de tamaño; headers por lista positiva; de excepciones, solo el tipo (decisión del usuario, 2026-09-27). Un fallo técnico de logging no anula una operación de negocio confirmada; el historial de negocio sí es transaccional.
- Registra identidad validada (set_actor), recurso y resultado.
- La API central aplica límites generales; cada servicio conserva protecciones específicas. Evita contar dos veces en el mismo bucket al atravesar ambos.
- No uses trazas para calcular consumo exacto ni para almacenar el estado definitivo de trabajos.
- Mantén persistencia e idempotencia en trabajos largos; diferencia final HTTP y final de trabajo.

## Entrega

- Incluye migraciones y documentación cuando correspondan.
- Verifica aislamiento entre empresas, autorización, bajas lógicas y consistencia histórica.
- Reporta cambios, comprobaciones y decisiones aún pendientes.

## Integración configurable

- Sigue el diseño de integración descrito en docs/arquitectura.md.
- No fijes URLs de otros servicios dentro del código.
- Separa versiones de imágenes, contratos y clientes generados.
- Conserva contratos compatibles cuando actualices un servicio.
- No interpretes una imagen configurada como una integración completa.
- No expongas endpoints internos automáticamente.
- Prepara únicamente la integración requerida por la entrega actual.
- Timeout HTTP predeterminado de 30 segundos configurable por operación; sin reintentos automáticos por defecto. No reintentar mutaciones sin idempotencia.
- Seeds explícitos e idempotentes por servicio; nunca contraseñas fijas ni reactivación silenciosa de usuarios o privilegios en sucesivas ejecuciones.

## API central

- La central cumple funciones de API Gateway y coordinación de operaciones.
- Separa internamente enrutamiento, clientes HTTP y coordinación.
- Cada servicio conserva sus reglas de negocio, datos y autorización.
- No concedas acceso solo porque una solicitud proviene de la central.
- Configura explícitamente rutas públicas; no expongas endpoints internos automáticamente.
- El enrutamiento simple puede resolverse por configuración.
- Combinar operaciones de varios servicios requiere coordinación explícita.
- No crear inicialmente otro contenedor de gateway ni un sistema de plugins.
- Implementar la central después de disponer de auth funcional e independiente.