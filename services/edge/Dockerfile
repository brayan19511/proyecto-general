# Proxy de borde (Caddy) con el módulo DNS del proveedor del dominio, para que
# Let's Encrypt emita el certificado por desafío DNS-01: no hace falta abrir el
# servidor a internet ni instalar una CA en cada equipo.
#
# Proveedor distinto de Cloudflare: --build-arg DNS_MODULE=github.com/caddy-dns/<proveedor>
# (lista en https://github.com/caddy-dns) y ajustar "acme_dns" en Caddyfile.dns.

ARG CADDY_VERSION=2.10

FROM caddy:${CADDY_VERSION}-builder-alpine AS build
ARG DNS_MODULE=github.com/caddy-dns/cloudflare
RUN xcaddy build --with ${DNS_MODULE}

FROM caddy:${CADDY_VERSION}-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
# Configuraciones: "http" (red local sin dominio), "internal" (CA propia, solo esta
# máquina) o "dns" (dominio propio + Let's Encrypt). Se elige con CADDY_TLS al
# arrancar (ver README).
COPY Caddyfile.http Caddyfile.internal Caddyfile.dns sites.caddy /etc/caddy/
