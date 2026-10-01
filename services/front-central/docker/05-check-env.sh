#!/bin/sh
# Lo ejecuta la imagen oficial de nginx antes de arrancar (/docker-entrypoint.d/).
# Sin API_ORIGIN, la política CSP bloquearía todas las llamadas a la central.
set -e
if [ -z "$API_ORIGIN" ]; then
  echo "front-central: falta API_ORIGIN (origen de la central, p. ej. http://localhost:8001)" >&2
  exit 1
fi
