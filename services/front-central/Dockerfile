# Front central: build de Vite servido por nginx (solo archivos estáticos).
# El navegador llama directo a la central (API Gateway); este contenedor no hace
# de proxy (la central vería la IP del contenedor y no la del usuario).
#
#   docker compose up -d --build front-central   (desde services/apigateway)

# --- 1. Compilar ---
FROM node:22-alpine AS build
WORKDIR /app

# Dependencias primero: se reutiliza la capa mientras no cambie package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# URL de la central tal como la ve el NAVEGADOR (no la red interna de Docker).
# Vite la fija en el build: cambiarla exige reconstruir la imagen.
ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || (echo "Falta el build arg VITE_API_URL" >&2 && exit 1)
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- 2. Servir ---
FROM nginx:1.27-alpine
# La imagen oficial procesa /etc/nginx/templates/*.template al arrancar
# (sustituye ${VAR} por variables de entorno) y deja el resultado en conf.d/.
COPY nginx/ /etc/nginx/templates/
# Falla al arrancar si falta API_ORIGIN (en lugar de servir un front que no llega a la central).
COPY --chmod=755 docker/05-check-env.sh /docker-entrypoint.d/05-check-env.sh
COPY --from=build /app/dist /usr/share/nginx/html
# Origen de la central para la política CSP (connect-src). Obligatorio.
ENV API_ORIGIN=""
EXPOSE 80
