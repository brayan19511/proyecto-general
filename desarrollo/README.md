# desarrollo

Composes para trabajar en esta máquina. Construyen las imágenes desde
`services/*/Dockerfile` (no se copian Dockerfiles aquí) y montan el `.env` de
cada servicio. Todo escucha en `127.0.0.1` salvo el proxy de borde, que se abre
a la red solo si se configura (`EDGE_BIND`).

| Carpeta | Proyecto Docker | Qué levanta | Comando (desde la carpeta) |
|---|---|---|---|
| `plataforma-completa/` | `proyecto-central` | Todo: db, pgAdmin, auth, libro-mayor (API + worker), notificaciones (API + worker), pagos-proveedores, central, front y caddy | `docker compose --env-file ../../services/apigateway/.env up -d --build` |
| `auth/` | `dev-auth` | Base propia (5433) + auth (8000) | `docker compose --env-file ../../services/auth/.env up -d --build` |
| `libro-mayor/` | `dev-libro-mayor` | Base propia (5434) + API (8002) + worker; usa el auth de `auth/` | `docker compose --env-file ../../services/libro-mayor/.env up -d --build` |
| `notificaciones/` | `dev-notificaciones` | Base propia (5436) + API (8010) + worker; usa el auth de `auth/` | `docker compose --env-file ../../services/notificaciones/.env up -d --build` |
| `pagos-proveedores/` | `dev-pagos-proveedores` | Base propia (5437) + API (8012); usa `auth/` y `notificaciones/` | `docker compose --env-file ../../services/pagos-proveedores/.env up -d --build` |
| `apigateway/` | `dev-apigateway` | Base propia (5435) + central (8011); reenvía a `auth/`, `libro-mayor/`, `notificaciones/` y `pagos-proveedores/` | `docker compose --env-file ../../services/apigateway/.env up -d --build` |
| `front-central/` | `dev-front-central` | El front en nginx (3001), contra una central ya corriendo | `docker compose up -d --build` |

- **Plataforma completa** es la que se usa a diario: un solo compose, redes
  internas entre servicios y HTTPS por caddy (`https://localhost`). Detalle de
  redes, IP real y acceso desde la red en `services/apigateway/readme.md` y
  `services/edge/README.md`.
- **Un servicio solo** sirve para que cada equipo trabaje en lo suyo sin
  levantar el resto. Son proyectos independientes (su propia base y volumen);
  se comunican por `host.docker.internal` con los otros composes de esta
  carpeta. Cada uno se puede apuntar a otro servidor con `DEV_AUTH_URL`,
  `DEV_LIBRO_MAYOR_URL`, `DEV_NOTIFICACIONES_URL`, `DEV_PAGOS_PROVEEDORES_URL`
  o `DEV_API_URL`.
- Los puertos de un servicio solo (8010, 8012…) son los mismos que usa ese
  servicio con `uvicorn` en local: no levantar los dos a la vez (o cambiar
  `DEV_<SERVICIO>_PORT`).
- **`--env-file`**: el compose toma de ese `.env` las credenciales de su base
  (`DB_NAME`, `DB_USER`, `DB_PASSWORD`), así no se repiten en otro archivo. Para
  no escribirlo cada vez, copiar ese `.env` a la carpeta del compose (`.env`
  está ignorado por git).
- Para editar el front con recarga en caliente es más práctico `npm run dev` en
  `services/front-central` (puerto 3000) que su contenedor.

Comandos útiles (en la carpeta del compose, con el mismo `--env-file`):

```bash
docker compose ps                    # estado
docker compose logs -f auth          # logs de un servicio
docker compose up -d --build auth    # reconstruir y reiniciar uno
docker compose down                  # detener (los datos siguen en el volumen)
```

`docker compose down -v` borra también los volúmenes (la base queda vacía).
En `plataforma-completa` eso incluye la CA y los certificados de caddy.
