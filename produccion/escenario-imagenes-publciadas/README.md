# escenario-imagenes-publciadas

Despliegue en un servidor que **no tiene el repositorio**: solo esta carpeta y
las imágenes publicadas en Docker Hub (`brayan1951/*`). El compose es el mismo
del escenario A (sin `build:`); la imagen y la versión de cada servicio se eligen
en `.env`.

Servicios: auth, apigateway, libro-mayor (API + worker), notificaciones (API +
worker), pagos-proveedores, canales-venta, sap-operaciones (API + worker),
front-central, caddy (edge), la base y pgAdmin (opcional).

## 1. Construir y publicar (en tu PC, desde la raíz del repo)

El último argumento es el **contexto de build**, y no es el mismo para todos:

- Servicios Python: contexto = **raíz del repo** (`.`), porque copian
  `packages/platform-audit`. Por eso llevan `-f services/<servicio>/Dockerfile`.
- `front-central` y `edge`: contexto = **su propia carpeta**; sus `COPY`
  (`nginx/`, `docker/`, `Caddyfile.*`, `sites.caddy`) son relativos a ella.

```bash
docker login

# Versiones de esta entrega (2026-10-04). Una versión publicada no se reutiliza:
# cada cambio de código = versión nueva. (Las 0.1.0 de libro-mayor, notificaciones
# y pagos-proveedores se construyeron con el Dockerfile de auth: no usarlas.)

# auth: permisos lastmiller.* y sap_operations.*, carga de permisos sin seed
docker build -f services/auth/Dockerfile -t brayan1951/auth:0.1.1 .
docker push brayan1951/auth:0.1.1
# apigateway: rutas de canales-venta y sap-operaciones
docker build -f services/apigateway/Dockerfile -t brayan1951/apigateway:0.1.1 .
docker push brayan1951/apigateway:0.1.1
# libro-mayor: sin cambios propios; se reconstruye por platform-audit (logs con respuestas)
docker build -f services/libro-mayor/Dockerfile -t brayan1951/libro-mayor:0.1.3 .
docker push brayan1951/libro-mayor:0.1.3
# notificaciones: logs en Monitoreo
docker build -f services/notificaciones/Dockerfile -t brayan1951/notificaciones:0.1.2 .
docker push brayan1951/notificaciones:0.1.2
# pagos-proveedores: logs en Monitoreo y mensaje claro de permisos de correos
docker build -f services/pagos-proveedores/Dockerfile -t brayan1951/pagos-proveedores:0.1.2 .
docker push brayan1951/pagos-proveedores:0.1.2
# canales-venta (nuevo): lastmiller sobre Ofisis
docker build -f services/canales-venta/Dockerfile -t brayan1951/canales-venta:0.1.0 .
docker push brayan1951/canales-venta:0.1.0
# sap-operaciones (nuevo): API y worker en la misma imagen
docker build -f services/sap-operaciones/Dockerfile -t brayan1951/sap-operaciones:0.1.0 .
docker push brayan1951/sap-operaciones:0.1.0

# front-central: VITE_API_URL=/ (mismo origen que caddy) para que la imagen sirva en cualquier dominio
docker build --build-arg VITE_API_URL=/ -t brayan1951/front-central:0.1.3 services/front-central
docker push brayan1951/front-central:0.1.3
# edge: prefijos /canales-venta y /sap-operaciones. El nombre debe ser edge-caddy (así lo busca el compose)
docker build -t brayan1951/edge-caddy:0.1.2 services/edge
docker push brayan1951/edge-caddy:0.1.2
```

- Cada imagen se versiona por separado y nunca con `latest`: volver atrás es
  cambiar un número en `.env`.
- Una versión ya publicada no se reutiliza para otro código: un cambio = versión nueva.
- Las imágenes llevan el código. Si los repositorios de Docker Hub son públicos,
  cualquiera puede descargarlas; marcarlos como privados si el código es de la empresa.

## 2. Qué necesita el servidor

```
escenario-imagenes-publciadas/
├── docker-compose.yml
├── .env                  # del compose: REGISTRY, *_VERSION, dominio, DB_*
├── env/                  # uno por contenedor; cada uno ve solo sus secretos
│   ├── auth.env
│   ├── apigateway.env
│   ├── libro-mayor.env
│   ├── notificaciones.env
│   ├── pagos-proveedores.env
│   ├── canales-venta.env     # Ofisis
│   ├── sap-operaciones.env   # Service Layer y clave de cifrado de credenciales
│   ├── edge.env          # solo con CADDY_TLS=dns
│   └── pgadmin.env       # solo con COMPOSE_PROFILES=admin (pgAdmin)
└── secrets/auth/         # jwt_private.pem y jwt_public.pem
```

Los `env/*.env.example` están en esta carpeta; en el servidor se copian a `env/*.env`.
Ningún `.env` real va a git.

En `.env` es donde se indica que las imágenes vienen de Docker Hub:

```env
REGISTRY=brayan1951
AUTH_VERSION=0.1.1
APIGATEWAY_VERSION=0.1.1
LIBRO_MAYOR_VERSION=0.1.3
NOTIFICACIONES_VERSION=0.1.2
PAGOS_PROVEEDORES_VERSION=0.1.2
CANALES_VENTA_VERSION=0.1.0
SAP_OPERACIONES_VERSION=0.1.0
FRONT_VERSION=0.1.3
EDGE_VERSION=0.1.2
```

Los `env/*.env` no cambian por usar Docker Hub: contienen la configuración de
cada servicio (base, SAP, Ofisis, SMTP, seed…), no el nombre de la imagen.

**Red del servidor:** canales-venta debe llegar a Ofisis (SQL Server, puerto 1433)
y sap-operaciones al Service Layer (`https://10.0.0.14:50000`). Salen por las redes
`ofisis-egress` y `sap-egress` del compose: el servidor necesita ruta a esas IPs.

## 3. Primer despliegue (en el servidor)

```bash
cp .env.example .env                                           # completar REGISTRY, versiones, SITE_ADDRESS, DB_PASSWORD
for f in env/*.env.example; do cp "$f" "${f%.example}"; done   # completar cada uno (mismo DB_PASSWORD)

# Llaves JWT, con el script que trae la imagen de auth (una sola vez; respaldarlas)
mkdir -p secrets/auth
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/secrets/auth:/app/services/auth/secrets" \
  brayan1951/auth:0.1.1 python scripts/generate_jwt_keys.py

# Claves Fernet (una distinta para cada uno, como lista JSON ["..."]):
#   SMTP_ENCRYPTION_KEYS        en env/notificaciones.env
#   CREDENTIALS_ENCRYPTION_KEYS en env/sap-operaciones.env
docker run --rm brayan1951/sap-operaciones:0.1.0 \
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker login                  # solo si los repositorios son privados
docker compose pull
docker compose up -d
docker compose ps
docker compose logs auth-migrate   # revisar cada *-migrate
```

Primer administrador: `SEED_ENABLED=true` y `SEED_TOKEN` en `env/auth.env`,
`docker compose up -d auth`, `POST /auth/seed` con `X-Seed-Token`, y volver a `false`.
Ese seed crea también los permisos y las empresas de su `data.py`.

Carga inicial por empresa (libro-mayor: compañía SAP y cuentas; notificaciones:
plantillas): `SEED_ENABLED=true` en su `env/*.env`, `docker compose up -d`, y en el
front **Plataforma › Empresas › Carga inicial** (front-central 0.1.2 o posterior).
Es idempotente; al terminar, volver a `false`. Ahí mismo se ve y copia el id de
cada empresa (`X-Company-Id` para llamadas por API).

## 4. Pasar a esta versión desde la anterior (2026-10-04)

Si el servidor ya corre la versión anterior (auth 0.1.0, libro-mayor 0.1.2,
notificaciones 0.1.1, pagos-proveedores 0.1.1, front 0.1.2, edge 0.1.1):

1. En tu PC: construir y publicar todas las imágenes de la sección 1.
2. En el servidor, copiar desde tu PC el `docker-compose.yml` nuevo y los
   `env/canales-venta.env.example` y `env/sap-operaciones.env.example`.
3. Crear y completar los dos `env` nuevos (sin secretos en git):
   - `env/canales-venta.env`: `DB_*` (los mismos), `OFISIS_HOST/USER/PASSWORD`,
     `LASTMILLER_COMPANY_CODE=RASH`.
   - `env/sap-operaciones.env`: `DB_*`, `SAP_SERVICE_LAYER_URL`, `SAP_VERIFY_TLS=false`
     y una clave nueva en `CREDENTIALS_ENCRYPTION_KEYS` (respaldarla).
4. En `env/apigateway.env` agregar `CANALES_VENTA_ENABLED=true` y
   `SAP_OPERACIONES_ENABLED=true`. Opcional: actualizar `SERVICE_VERSION` de cada
   `env/*.env` a la versión de su imagen (solo identifica la versión en los logs).
5. En `.env`, las versiones nuevas (bloque de la sección 2), incluidas
   `CANALES_VENTA_VERSION` y `SAP_OPERACIONES_VERSION`.
6. Desplegar y revisar las migraciones:

   ```bash
   docker compose pull
   docker compose up -d
   docker compose ps
   docker compose logs canales-venta-migrate sap-operaciones-migrate
   ```

7. Permisos nuevos: entrar como administrador de plataforma a
   **Empresa › Roles y permisos › Permisos** y pulsar **Cargar permisos pendientes**
   (crea `lastmiller.*` y `sap_operations.*`; ya no hace falta el seed). Luego
   asignarlos a los roles que corresponda.
8. Comprobar: Canales de venta (listado de SKU), SAP › Configuración (Service
   Layer), y Monitoreo › Actividad y logs (pestañas nuevas; ahora se guardan
   también las respuestas).

Volver atrás: poner las versiones anteriores en `.env` y `docker compose up -d`.
Las migraciones nuevas solo agregan tablas, columnas y un estado: las versiones
anteriores siguen funcionando con ellas.

## pgAdmin

No se levanta por defecto. `COMPOSE_PROFILES=admin` en `.env` y `docker compose up -d`
(o una vez: `docker compose --profile admin up -d pgadmin`). Se entra por caddy en el
puerto 8443 (`http://<IP>:8443/` con `CADDY_TLS=http`, `https://SITE_ADDRESS:8443`
con `dns`) con `PGADMIN_DEFAULT_EMAIL`/`PGADMIN_DEFAULT_PASSWORD` de `env/pgadmin.env`.
Servidor a registrar: host `db`, puerto `5432`, usuario y contraseña de `DB_USER`/`DB_PASSWORD`.
Para apagarlo: vaciar `COMPOSE_PROFILES` y `docker compose stop pgadmin`.

## 5. Actualizar un servicio

1. En tu PC: build y push con versión nueva (p. ej. `brayan1951/auth:0.1.2`).
2. En el servidor: `AUTH_VERSION=0.1.2` en `.env`, luego
   `docker compose pull auth && docker compose up -d auth` (su `auth-migrate` corre antes).

Servicios con worker (libro-mayor, notificaciones, sap-operaciones): actualizar
API y worker juntos, p. ej. `docker compose up -d sap-operaciones sap-operaciones-worker`.
