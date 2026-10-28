"""Sesiones del Service Layer reutilizadas entre solicitudes (/documents).

Pedido del usuario (2026-10-28): no hacer login y logout en cada búsqueda. Se
guarda un ServiceLayerClient por (URL, base, usuario) en la memoria del proceso;
su sesión dura lo que SAP indica en el login (SessionTimeout) y se renueva con
cada uso (ver ServiceLayerClient). Nada va a disco ni a la base: al reiniciar el
servicio se vuelve a iniciar sesión.

- La clave lleva un hash de la clave SAP: si cambia la configuración, se abre
  una sesión nueva y la anterior se cierra.
- Los trabajos masivos no usan esto: cada trabajo tiene su sesión con las
  credenciales del operador y la cierra al terminar.
- La cookie de sesión de SAP equivale a una credencial: solo vive aquí, nunca en
  logs ni respuestas.
"""

import hashlib
import threading

from app.sap.service_layer import ServiceLayerClient

_clients: dict[tuple[str, str, str, str], ServiceLayerClient] = {}
_lock = threading.Lock()


def shared_client(base_url: str | None, company_db: str, user: str, password: str) -> ServiceLayerClient:
    """Cliente compartido; inicia sesión al primer uso (no aquí)."""
    url = (base_url or "").rstrip("/")
    key = (url, company_db, user, hashlib.sha256(password.encode("utf-8")).hexdigest())
    with _lock:
        client = _clients.get(key)
        if client is None:
            client = ServiceLayerClient(base_url, company_db, user, password)
            # Misma URL, base y usuario con otra clave: la sesión vieja ya no sirve.
            for old_key in [k for k in _clients if k[:3] == key[:3]]:
                _clients.pop(old_key).close()
            _clients[key] = client
    return client


def close_all() -> None:
    """Cierra todas las sesiones (al apagar el servicio)."""
    with _lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        client.close()
