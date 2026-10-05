# produccion

Plantillas para desplegar la plataforma en un servidor Linux. **Solo imágenes
del registro** (`image:`, nunca `build:`), con la versión fijada; variables y
secretos fuera de git (aquí solo hay `*.example`). Los Dockerfiles siguen en
`services/*`; desarrollo está en `../desarrollo`.

Servicios: auth, apigateway (la central), libro-mayor (API + worker),
notificaciones (API + worker), pagos-proveedores, canales-venta, sap-operaciones
(API + worker), front-central, edge (caddy) y la base.

## 1. Publicar las imágenes (CI de cada servicio)

Desde la raíz del repo (contexto de build = raíz, por `packages/platform-audit`):

```bash
docker build -f services/auth/Dockerfile              -t ghcr.io/empresa/plataforma/auth:0.1.1 .
docker build -f services/apigateway/Dockerfile        -t ghcr.io/empresa/plataforma/apigateway:0.1.1 .
docker build -f services/libro-mayor/Dockerfile       -t ghcr.io/empresa/plataforma/libro-mayor:0.1.3 .
docker build -f services/notificaciones/Dockerfile    -t ghcr.io/empresa/plataforma/notificaciones:0.1.2 .
docker build -f services/pagos-proveedores/Dockerfile -t ghcr.io/empresa/plataforma/pagos-proveedores:0.1.2 .
docker build -f services/canales-venta/Dockerfile     -t ghcr.io/empresa/plataforma/canales-venta:0.1.0 .
docker build -f services/sap-operaciones/Dockerfile   -t ghcr.io/empresa/plataforma/sap-operaciones:0.1.0 .
docker build --build-arg VITE_API_URL=/ -t ghcr.io/empresa/plataforma/front-central:0.1.3 services/front-central
docker build -t ghcr.io/empresa/plataforma/edge-caddy:0.1.2 services/edge
docker push ghcr.io/empresa/plataforma/auth:0.1.1     # y así cada una
```
```bash
docker build -f services/auth/Dockerfile              -t brayan1951/auth:0.2.0 .
docker build -f services/apigateway/Dockerfile        -t brayan1951/apigateway:0.2.0 .
docker build -f services/libro-mayor/Dockerfile       -t brayan1951/libro-mayor:0.2.0 .
docker build -f services/notificaciones/Dockerfile    -t brayan1951/notificaciones:0.2.0 .
docker build -f services/pagos-proveedores/Dockerfile -t brayan1951/pagos-proveedores:0.2.0 .
docker build -f services/canales-venta/Dockerfile     -t brayan1951/canales-venta:0.2.0 .
docker build -f services/sap-operaciones/Dockerfile   -t brayan1951/sap-operaciones:0.2.0 .
docker build --build-arg VITE_API_URL=/ -t brayan1951/front-central:0.2.0 services/front-central
docker build -t brayan1951/edge-caddy:0.2.0 services/edge
docker push brayan1951/auth:0.2.0     # y así cada una
```

- Versionar cada imagen por separado (`0.1.0`, `0.1.1`…), nunca `latest`:
  volver atrás es cambiar un número.
- El front se construye con `VITE_API_URL=/` (mismo origen detrás de caddy): la
  misma imagen sirve en cualquier dominio.
- En CI (p. ej. GitHub Actions) cada pipeline se dispara solo cuando cambia su
  carpeta (`services/auth/**`) y publica solo su imagen. Un cambio en
  `packages/platform-audit` obliga a reconstruir todos los servicios Python.
- Con imágenes en Docker Hub y un servidor sin el repositorio: ver
  `escenario-imagenes-publciadas/README.md` (comandos y paso a esta versión).

## 2. Elegir escenario

| | A: un compose (`escenario-a-un-compose/`) | B: un compose por servicio (`escenario-b-por-servicio/`) |
|---|---|---|
| Para | Un servidor, un equipo que despliega todo | Equipos que despliegan su servicio por separado |
| Variables | `.env` (registro, versiones, dominio) + `env/<servicio>.env` | Por carpeta: `.env` (su versión) + `<servicio>.env` |
| Redes | Las crea el compose | Compartidas, creadas una vez con `crear-redes.sh` |
| Actualizar un servicio | Cambiar su `*_VERSION` y `docker compose up -d <servicio>` | En su carpeta: cambiar su versión y `docker compose up -d` |

`escenario-imagenes-publciadas/` es el escenario A con imágenes de Docker Hub,
para copiar solo esa carpeta al servidor.

En todos, cada contenedor recibe solo sus variables: no se comparte un `.env`
con todos los secretos (auth no ve la clave de SAP, libro-mayor no ve las llaves
JWT, solo notificaciones ve `SMTP_ENCRYPTION_KEYS`, solo sap-operaciones ve
`CREDENTIALS_ENCRYPTION_KEYS` y solo canales-venta ve la clave de Ofisis).

### Escenario A

```bash
cd escenario-a-un-compose
cp .env.example .env                                  # registro, versiones, dominio
for f in env/*.env.example; do cp "$f" "${f%.example}"; done   # y completarlos
mkdir -p secrets/auth                                 # jwt_private.pem / jwt_public.pem de auth
docker compose pull && docker compose up -d
docker compose --profile admin up -d pgadmin          # opcional: https://SITE_ADDRESS:8443
```

### Escenario B

```bash
cd escenario-b-por-servicio
sh crear-redes.sh                                     # una vez por servidor (también al agregar servicios)
# En cada carpeta: cp .env.example .env y cp <servicio>.env.example <servicio>.env
(cd base && docker compose up -d)                     # o una base gestionada
(cd auth && docker compose up -d)                     # auth: además ./secrets con las llaves JWT
(cd libro-mayor && docker compose up -d)
(cd notificaciones && docker compose up -d)           # API + worker
(cd pagos-proveedores && docker compose up -d)        # necesita notificaciones
(cd canales-venta && docker compose up -d)            # sale a Ofisis
(cd sap-operaciones && docker compose up -d)          # API + worker; sale al Service Layer
(cd apigateway && docker compose up -d)
(cd borde && docker compose up -d)
```

El orden importa la primera vez (cada *-migrate necesita la base y también
migra el schema `audit`, así que no deben correr a la vez): entre composes no
hay `depends_on`. En el escenario A el compose ya los encadena (auth →
apigateway → libro-mayor → notificaciones → pagos-proveedores → canales-venta →
sap-operaciones). Las redes usan las mismas subredes fijas que desarrollo
(172.30–172.36): no crearlas en la misma máquina que `desarrollo/plataforma-completa`.

**En servidores distintos** ya no sirve la red de Docker: cada servicio se
llama por URL (p. ej. `AUTH_URL=https://auth.interna.empresa.com`) por una red
privada o VPN y con TLS, y el `TRUSTED_PROXIES` de cada uno se cambia a las IPs
reales de quien lo llama.

## 3. Certificado y acceso

Por defecto `CADDY_TLS=dns`: dominio propio con certificado de Let's Encrypt
por DNS (Cloudflare), sin abrir el servidor a internet ni instalar nada en los
equipos. Pasos en `services/edge/README.md`. Solo caddy publica puertos
(80, 443 y 8443 para pgAdmin); la base y los servicios no son accesibles desde fuera.

## 4. Antes de abrirlo a usuarios

- **Respaldos de la base**: si es un contenedor, programar `pg_dump` diario
  fuera del compose (cron del servidor) y guardar las copias en otro lugar.
  Una base gestionada los trae.
- **Llaves JWT de auth** (`secrets/auth`): generarlas una vez, guardarlas con
  respaldo; cambiarlas invalida todas las sesiones.
- **Claves de cifrado** (`SMTP_ENCRYPTION_KEYS`, `CREDENTIALS_ENCRYPTION_KEYS`):
  una distinta por servicio, con respaldo. Si se pierden, lo cifrado queda ilegible.
- **Migraciones**: los `*-migrate` corren antes de cada versión nueva; revisar
  sus logs (`docker compose logs auth-migrate`) antes de dar por hecho el despliegue.
- **Seed de auth**: solo para el primer administrador (`SEED_ENABLED=true`,
  `POST /auth/seed` con `X-Seed-Token`) y volver a `false`.
- **Permisos nuevos de una versión**: ya no hace falta el seed. El administrador
  de plataforma los carga en Empresa › Roles y permisos › Permisos › **Cargar
  permisos pendientes** y luego los asigna a los roles.
- **Firewall del servidor**: abrir solo 80 y 443 (y 8443 si se usa pgAdmin).
- **Recomendado**: un usuario de base por servicio con permisos solo sobre su
  schema (hoy los ejemplos usan uno común).

## 5. Notificaciones y pagos a proveedores

- **Claves SMTP:** `SMTP_ENCRYPTION_KEYS` en `notificaciones.env` (lista JSON de
  claves Fernet; la primera cifra). Guardarlas como cualquier secreto: si se
  pierden, hay que volver a escribir las contraseñas de las cuentas SMTP.
- **Salida SMTP:** notificaciones (API y worker) usa su propia red de salida
  (`smtp-egress`). Un relay interno se permite con `SMTP_ALLOWED_PRIVATE_NETWORKS`.
- **Worker siempre levantado:** sin `notificaciones-worker` los correos quedan
  pendientes. Al actualizar, `stop_grace_period: 2m` deja terminar el envío en curso.
- **Publicarlos:** `NOTIFICACIONES_ENABLED=true` y `PAGOS_PROVEEDORES_ENABLED=true`
  en `apigateway.env` (también se apagan desde Plataforma › Servicios).
- **Primera vez por empresa:** en el front, Plataforma › Cuentas SMTP y
  Plantillas de correo (la de los avisos de pago: `payment_provider_summary`, o
  la que elija el administrador en Tesorería › Plantilla por defecto).
- **Ver el estado de los correos de un lote:** quien lo mira necesita
  `notifications.view` con alcance de toda la empresa (con "solo lo propio", solo
  los lotes que envió él).

## 6. Canales de venta y operaciones SAP

- **Publicarlos:** `CANALES_VENTA_ENABLED=true` y `SAP_OPERACIONES_ENABLED=true`
  en `apigateway.env` (también se apagan desde Plataforma › Servicios).
- **Salida a sistemas externos:** canales-venta llega a Ofisis (SQL Server, 1433)
  por `ofisis-egress`; sap-operaciones (API y worker) llega al Service Layer por
  `sap-egress`. El servidor necesita ruta a esas IPs.
- **canales-venta:** `OFISIS_*` y `LASTMILLER_COMPANY_CODE` (la empresa dueña de
  lastmiller) en `canales-venta.env`. Sin pool de conexiones: cada operación abre
  y cierra la suya. Las cargas masivas escriben por lotes cortos (`LASTMILLER_WRITE_BATCH_SIZE`).
- **sap-operaciones:** `SAP_SERVICE_LAYER_URL` (por defecto; cada empresa puede
  tener la suya en SAP › Configuración, solo la cambia el administrador),
  `SAP_VERIFY_TLS` y `CREDENTIALS_ENCRYPTION_KEYS` en `sap-operaciones.env`.
- **Worker de SAP siempre levantado:** sin `sap-operaciones-worker` los trabajos
  quedan en cola. Al actualizar, `stop_grace_period: 3m` deja terminar el ítem en
  curso y el trabajo vuelve a la cola. Sin reintentos automáticos: un ítem cortado
  queda "incierto" y se revisa en SAP.
- **Certificados autofirmados** (Ofisis y Service Layer de desarrollo): hoy se
  conecta cifrado sin validar el certificado (`OFISIS_TRUST_SERVER_CERTIFICATE=true`,
  `SAP_VERIFY_TLS=false`, decisión del usuario). La alternativa es montar la CA en
  el contenedor (`SAP_CA_FILE`).
