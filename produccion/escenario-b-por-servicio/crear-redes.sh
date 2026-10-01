#!/bin/sh
# Redes compartidas entre los composes del escenario B (una vez por servidor).
# Mismas subredes que en desarrollo: auth, libro-mayor y la central confían en
# ellas por TRUSTED_PROXIES. Idempotente: no toca las que ya existen.
set -e

crear() { # nombre [opciones de docker network create]
  name="$1"
  shift
  if docker network inspect "$name" >/dev/null 2>&1; then
    echo "ya existe: $name"
  else
    docker network create "$@" "$name" >/dev/null
    echo "creada:    $name"
  fi
}

crear plataforma-data --internal                                  # la base
crear plataforma-auth --internal --subnet 172.30.0.0/24           # central ↔ auth
crear plataforma-libro-mayor --internal --subnet 172.31.0.0/24    # central ↔ libro-mayor
crear plataforma-proxy --internal --subnet 172.32.0.0/24          # caddy ↔ central, front, pgAdmin
