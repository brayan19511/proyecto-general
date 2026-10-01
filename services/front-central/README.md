# front-central

Aplicación web de administración de la plataforma (React + TypeScript + Vite,
Bootstrap 5). Consume todo a través de la central (API Gateway): nunca llama a
un servicio directo. Reglas y estado en [AGENTS.md](AGENTS.md); módulos y
endpoints en [docs/alcance.md](docs/alcance.md).

## Desarrollo

```bash
cp .env.example .env.local   # VITE_API_URL=http://localhost:8001 (la central)
npm install
npm run dev                  # http://localhost:3000
```

- El puerto 3000 es fijo (`strictPort`): la central solo acepta por CORS los
  orígenes de `CORS_ORIGINS` (por defecto `http://localhost:3000`).
- `npm run lint` y `npm run build` (incluye `tsc`) antes de entregar.
- Si el navegador muestra código viejo tras editar, reiniciar `npm run dev`.

## Docker

Se construye y levanta con el resto de la plataforma, desde `services/apigateway`:

```bash
docker compose up -d --build front-central
```

- Imagen en dos etapas: `node:22-alpine` compila; `nginx:1.27-alpine` sirve
  `dist/` (sin proxy: el navegador llama a la central).
- Configuración (en `services/apigateway/.env`):

  | Variable | Default | Para qué |
  |---|---|---|
  | `FRONT_PORT` | `3000` | Puerto local del front. Su origen debe estar en `CORS_ORIGINS`. Choca con `npm run dev` si es el mismo. |
  | `FRONT_API_URL` | `http://localhost:8001` | URL de la central vista desde el navegador. Se fija al construir (cambiarla exige `docker compose build front-central`) y se permite en la CSP. |

- nginx (`nginx/*.template`): rutas de la SPA a `index.html` sin caché, assets
  con hash en caché un año, gzip, `/healthz` para el healthcheck y cabeceras de
  seguridad (CSP estricta: sin scripts en línea; `connect-src` solo a la central).
- El contenedor no arranca si falta `API_ORIGIN` (`docker/05-check-env.sh`).
