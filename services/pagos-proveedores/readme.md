# Servicio pagos-proveedores

Estado (2026-10-01): **implementado**, dockerizado y publicado en la central
(`PAGOS_PROVEEDORES_ENABLED`). Reemplaza a `app/api/finance/payment_provider`
de proyecto-05; los correos los envía `services/notificaciones`.

## Qué hace

- **Maestro de proveedores** por empresa: RUC/DNI normalizado, razón social,
  nombres comerciales (para reconocerlos por nombre) y correos de pago. Un
  mismo nombre no puede identificar a dos proveedores.
- **Lotes de constancias**: se suben los PDF una vez (hasta 100, 25 MB cada
  uno), se leen con el lector portado de proyecto-05 (pdfplumber y OCR con
  tesseract si son escaneados) y se agrupan por proveedor (RUC y luego
  nombre). Un borrador se agrupa al consultarlo con el maestro actual.
- **ZIP** con las constancias renombradas (titular + fecha).
- **Envío** por notificaciones con la plantilla `payment_provider_summary`
  (un correo por proveedor, sus constancias adjuntas, asunto y mensaje
  opcionales). En dos fases e idempotente: reintentar nunca duplica correos.
  El lote enviado conserva la copia de a quién se envió y sus PDF (retención
  indefinida).

## Ejecutar en local

Desde `services/pagos-proveedores`, con Python 3.14:

```powershell
py -3.14 -m venv enviroment
.\enviroment\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # DB_*, AUTH_URL, NOTIFICACIONES_URL (ver comentarios)
alembic upgrade head
python -m uvicorn app.main:app --port 8012
```

El OCR necesita tesseract (idioma `spa`) y poppler instalados; la imagen de
Docker los trae. Sin ellos solo falla la lectura de PDF escaneados. En Docker:
`desarrollo/plataforma-completa` (`pagos-proveedores` y
`pagos-proveedores-migrate`).

## Permisos (catálogo de auth)

Alcance company. `payments.view`; dos ramas que no se incluyen entre sí:
`payments.providers.manage` (editar el maestro) y `payments.send` (lotes y
envío); `payments.admin` incluye todo. Enviar exige además `notifications.send`.
`ADMIN_EMPRESA` recibe `payments.admin` por el seed de auth.

## Documentos

- [Alcance y acuerdos](docs/alcance.md)
- [Modelo de datos y cobertura de proyecto-05](docs/modelo-datos.md)

## Pendientes

- Validar el lector con constancias reales (`muestras/`, fuera de git) y el OCR.
- Si leer un lote grande con OCR se acerca a los 300 s de la central, pasar la
  lectura a un worker.
- Importación del maestro de proveedores desde proyecto-05 (no hecha).
