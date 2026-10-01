# edge (proxy de borde)

Caddy como única entrada desde la red: HTTP en la red local o HTTPS con
dominio, límite de 100 MB por solicitud y reenvío por prefijo (`/auth`, `/libro-mayor`, `/gateway` → la central; el resto
→ el front; `:8443` → pgAdmin). No es un API Gateway: no tiene reglas,
autorización ni coordinación (ver `docs/arquitectura.md`).

| Archivo | Para qué |
|---|---|
| `Dockerfile` | Caddy 2.10 compilado con el módulo DNS del proveedor (Cloudflare por defecto) |
| `sites.caddy` | Rutas comunes a los tres modos (snippets) |
| `Caddyfile.http` | Sin certificado: red local mientras no haya dominio (default en desarrollo) |
| `Caddyfile.internal` | Certificados de la CA propia de Caddy (solo pruebas en esta máquina) |
| `Caddyfile.dns` | Dominio propio + Let's Encrypt por desafío DNS-01 |
| `.env.example` | `ACME_EMAIL` y `CLOUDFLARE_API_TOKEN` (solo modo dns) |

## Modos de certificado (`CADDY_TLS`)

| Modo | Cuándo | En los equipos |
|---|---|---|
| `http` (default en desarrollo) | Una PC compartida en la red, sin dominio: `http://<IP de la PC>/` | Nada. **Sin cifrado** dentro de la red: usar solo en una red de confianza |
| `internal` | Probar HTTPS en esta máquina con `https://localhost` | Otros equipos verían una advertencia (habría que instalar la CA) |
| `dns` (default en producción) | Red local, servidor interno o nube con un dominio propio | Nada: el certificado es público y válido |

### Modo http (red local, sin dominio)

En el `.env` del compose: `CADDY_TLS=http` y `EDGE_BIND=0.0.0.0`; abrir el
puerto 80 (y 8443 si se usa pgAdmin) en el firewall de Windows. Se entra con
`http://<IP de la PC>/` y pgAdmin con `http://<IP>:8443/`. Acepta cualquier
nombre o IP con que se llegue (`:80`).

Sin HTTPS el navegador desactiva algunas funciones; el front ya usa
alternativas: copiar al portapapeles (método anterior con un clic), ids de
avisos (contador) y el candado entre pestañas para renovar la sesión (en
`localStorage` solo el candado, nunca tokens). Al pasar a `dns` vuelven las
funciones nativas sin cambiar nada.

Si antes se entró por `https://localhost`, el navegador pudo guardar HSTS para
localhost y forzar HTTPS: entrar por la IP o borrar HSTS de ese sitio.

### Activar el modo dns (dominio propio)

1. Elegir un nombre del dominio de la empresa, p. ej. `plataforma.rashperu.com`.
2. En el DNS del dominio (Cloudflare), crear un registro **A** de ese nombre a la
   IP del servidor. Puede ser privada (`192.168.1.50`): Let's Encrypt no se
   conecta al servidor, solo verifica un registro TXT que Caddy crea y borra.
   Si el router de la oficina bloquea nombres públicos que apuntan a IPs
   privadas (protección "DNS rebinding"), agregar una excepción para el dominio
   o crear el mismo registro en el DNS interno.
3. Crear en Cloudflare un token de API con permiso **Zone > DNS > Edit** solo
   para esa zona. Copiar `services/edge/.env.example` a `services/edge/.env`
   (ignorado por git) y completar `ACME_EMAIL` y `CLOUDFLARE_API_TOKEN`.
4. En el `.env` del compose: `CADDY_TLS=dns`, `SITE_ADDRESS=plataforma.rashperu.com`
   y `EDGE_BIND=0.0.0.0` (para que otros equipos lleguen).
5. `docker compose up -d --build caddy` y abrir `https://plataforma.rashperu.com`.
   El primer certificado tarda unos segundos (`docker compose logs caddy`).

Otro proveedor DNS: construir con `--build-arg DNS_MODULE=github.com/caddy-dns/<proveedor>`
(lista en https://github.com/caddy-dns), cambiar la línea `acme_dns` de
`Caddyfile.dns` y el nombre de la variable del token.

Los certificados viven en el volumen `caddy_data`: no borrarlo (Let's Encrypt
limita cuántos certificados se emiten por semana para un mismo dominio).

## IP real del cliente

Caddy reemplaza el `X-Forwarded-For` que envíe el cliente por la IP real de la
conexión. La central solo confía en él porque Caddy le llega por la red interna
`proxy-net` (subred fija en su `TRUSTED_PROXIES`). Si delante de Caddy hay un
balanceador de la nube, agregar su rango en `trusted_proxies` de Caddy.
