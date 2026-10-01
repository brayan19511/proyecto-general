# produccion

Plantillas para desplegar la plataforma en un servidor Linux. **Solo imágenes
del registro** (`image:`, nunca `build:`), con la versión fijada; variables y
secretos fuera de git (aquí solo hay `*.example`). Los Dockerfiles siguen en
`services/*`; desarrollo está en `../desarrollo`.

## 1. Publicar las imágenes (CI de cada servicio)

Desde la raíz del repo (contexto de build = raíz, por `packages/platform-audit`):

```bash
docker build -f services/auth/Dockerfile        -t ghcr.io/empresa/plataforma/auth:0.1.0 .
docker build -f services/libro-mayor/Dockerfile -t ghcr.io/empresa/plataforma/libro-mayor:0.1.0 .
docker build -f services/apigateway/Dockerfile  -t ghcr.io/empresa/plataforma/apigateway:0.1.0 .
docker build -f services/notificaciones/Dockerfile    -t ghcr.io/empresa/plataforma/notificaciones:0.1.0 .
docker build -f services/pagos-proveedores/Dockerfile -t ghcr.io/empresa/plataforma/pagos-proveedores:0.1.0 .
docker build --build-arg VITE_API_URL=/ -t ghcr.io/empresa/plataforma/front-central:0.1.0 services/front-central
docker build -t ghcr.io/empresa/plataforma/edge-caddy:0.1.0 services/edge
docker push ghcr.io/empresa/plataforma/auth:0.1.0     # y así cada una
```

- Versionar cada imagen por separado (`0.1.0`, `0.1.1`…), nunca `latest`:
  volver atrás es cambiar un número.
- El front se construye con `VITE_API_URL=/` (mismo origen detrás de caddy): la
  misma imagen sirve en cualquier dominio.
- En CI (p. ej. GitHub Actions) cada pipeline se dispara solo cuando cambia su
  carpeta (`services/auth/**`) y publica solo su imagen.

## 2. Elegir escenario

| | A: un compose (`escenario-a-un-compose/`) | B: un compose por servicio (`escenario-b-por-servicio/`) |
|---|---|---|
| Para | Un servidor, un equipo que despliega todo | Equipos que despliegan su servicio por separado |
| Variables | `.env` (registro, versiones, dominio) + `env/<servicio>.env` | Por carpeta: `.env` (su versión) + `<servicio>.env` |
| Redes | Las crea el compose | Compartidas, creadas una vez con `crear-redes.sh` |
| Actualizar un servicio | Cambiar su `*_VERSION` y `docker compose up -d <servicio>` | En su carpeta: cambiar su versión y `docker compose up -d` |

En los dos, cada contenedor recibe solo sus variables: no se comparte un `.env`
con todos los secretos (auth no ve la clave de SAP, libro-mayor no ve las llaves JWT,
solo notificaciones ve `SMTP_ENCRYPTION_KEYS`).

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
sh crear-redes.sh                                     # una vez por servidor
# En cada carpeta: cp .env.example .env y cp <servicio>.env.example <servicio>.env
(cd base && docker compose up -d)                     # o una base gestionada
(cd auth && docker compose up -d)                     # auth: además ./secrets con las llaves JWT
(cd libro-mayor && docker compose up -d)
(cd notificaciones && docker compose up -d)          # API + worker
(cd pagos-proveedores && docker compose up -d)       # necesita notificaciones
(cd apigateway && docker compose up -d)
(cd borde && docker compose up -d)
```

El orden importa la primera vez (cada *-migrate necesita la base y también
migra el schema `audit`, así que no deben correr a la vez): entre composes no
hay `depends_on`. En el escenario A el compose ya los encadena (auth →
apigateway → libro-mayor → notificaciones → pagos-proveedores). Las redes usan
las mismas subredes fijas que desarrollo (172.30–172.34): no crearlas en la
misma máquina que `desarrollo/plataforma-completa`.

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
- **Migraciones**: los `*-migrate` corren antes de cada versión nueva; revisar
  sus logs (`docker compose logs auth-migrate`) antes de dar por hecho el despliegue.
- **Seed de auth**: solo para el primer administrador (`SEED_ENABLED=true`,
  `POST /auth/seed` con `X-Seed-Token`) y volver a `false`.
- **Firewall del servidor**: abrir solo 80 y 443 (y 8443 si se usa pgAdmin).
- **Recomendado**: un usuario de base por servicio con permisos solo sobre su
  schema (hoy los ejemplos usan uno común).

## 4. Notificaciones y pagos a proveedores

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
- **Permisos:** ejecutar el seed de auth tras actualizarlo para cargar
  `notifications.*` y `payments.*`.
