# Seguimiento propio (logs)

Estado: **implementado en auth (2026-09-27)** con el paquete compartido
[packages/platform-audit](../packages/platform-audit/README.md). Falta la parte
de la API central (logs de borde y vista conjunta), que se hará con ella.

## Decisiones del usuario

| Tema | Decisión |
| --- | --- |
| Enfoque | Contrato común; cada servicio escribe sus propias filas. La central registra la operación de borde y propaga el trace_id |
| Dónde | Schema `audit`, propiedad del paquete compartido (no de un servicio), para que cualquier proyecto sepa dónde están |
| Código | Un paquete Python compartido (`platform_audit`): un cambio se hace una sola vez |
| Cabecera | trace_id, usuario, método, ruta, estado, duración, inicio, fin, IP (más empresa, servicio, versión, resultado) |
| Detalle | Parámetros, headers, bodies, mensajes de error y nivel (info, success, warning, error) |
| Pasos | Manuales, donde el servicio quiera saber en qué parte va |
| Escritura | Síncrona (cabecera al empezar, pasos en el momento, cierre al terminar), en hilo aparte y fuera de la transacción de negocio |
| Retención | Sin purga hasta decidir una política explícita |

### Cambio a una regla anterior

La regla "no capturar bodies ni headers completos" se reemplazó por decisión
del usuario: **se guardan parámetros, headers y bodies, pero siempre
enmascarados y con límite de tamaño**. Contraseñas, tokens, keys, cookies,
emails y números de documento nunca se guardan; los headers siguen una lista
positiva; los bodies de más de 4 KB o no JSON solo registran tipo y tamaño; de
las excepciones solo se guarda el tipo.

## Por qué no todo en la central

| Solo en la central | Problema |
| --- | --- |
| Ve entrada, ruta, estado y duración total | No ve qué pasó dentro del servicio (qué paso tardó o falló) |
| Un solo lugar | Lo que no pasa por la central (llamadas internas, jobs) quedaría sin registro |
| "Qué proceso se ejecuta" | Es estado de trabajo, no log: los trabajos largos tendrán su tabla de estado persistente |

```text
cliente → central [audit.logs: op A, trace T, service=central]
            └→ auth [audit.logs: op B, trace T, padre A, service=auth]
                 ├ paso "verificar contraseña" (start/end)
                 └ paso "crear sesión" (start/end)
```

## Pendiente

1. **API central**: generar el trace_id en el borde, registrar su operación con
   el mismo paquete (si es Python) y propagar `X-Trace-Id` y
   `X-Parent-Operation-Id`. Configurar su IP en `TRUSTED_PROXIES` de cada servicio.
2. **Vista conjunta por trace_id**: la central consulta a cada servicio por
   una API interna autenticada (credenciales entre servicios, aún no diseñadas).
3. **Retención**: definir cuánto se conservan y cómo se purgan (decisión explícita).
4. Si el volumen crece: escritura en segundo plano con buffer, aceptando que
   una caída puede perder los últimos registros.
