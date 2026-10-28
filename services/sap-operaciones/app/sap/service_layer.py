"""Cliente del Service Layer de SAP Business One (una sesión por trabajo).

- Login con el usuario y la clave del operador sobre la base (CompanyDB) del
  trabajo. La cookie de sesión (B1SESSION, ROUTEID) la guarda httpx.
- Sin reintentos automáticos (acuerdo del usuario, 2026-10-04): un POST que se
  corta después de enviarse pudo haberse aplicado en SAP (SapConnectionError:
  el worker lo marca "uncertain"); si ni siquiera conectó, no llegó
  (SapUnavailableError: el ítem sigue pendiente). Única excepción: si SAP responde 401 (sesión vencida), la
  solicitud no se ejecutó; se vuelve a iniciar sesión y se repite una vez.
- Los errores salen con un mensaje saneado (código y texto de SAP, acotado);
  nunca con la clave ni el cuerpo enviado.
- Entidad y acción se arman como segmentos validados ({Entidad}({DocEntry})/{Acción}),
  nunca como una URL libre.
- Lecturas (get_json, stream): no modifican SAP, así que un corte de red es
  "no disponible" y no "incierto". Tampoco se reintentan (salvo el 401).
- Sesión: dura lo que SAP indica en el login (SessionTimeout, en minutos) y se
  renueva con cada uso. Un cliente puede compartirse entre solicitudes
  (app/sap/session_pool.py): el login va con candado y, si varias reciben 401 a
  la vez, solo una vuelve a iniciar sesión.
"""

import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from app.core.config import settings

# Entidad y acción del Service Layer: segmentos de ruta, no URLs libres.
RESOURCE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,99}$")
# Base SAP (CompanyDB): letras, números y _ (decisión del usuario: lista o texto libre validado).
COMPANY_DB_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,100}$")


class SapError(Exception):
    """Base de los errores del Service Layer. message es seguro de mostrar."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


class SapAuthError(SapError):
    """Credenciales o base inválidas: no se puede seguir con el trabajo."""


class SapRequestError(SapError):
    """SAP respondió con error a esta solicitud (el ítem falla; los demás siguen)."""

    def __init__(self, message: str, http_status: int | None = None, body=None):
        super().__init__(message, http_status)
        self.body = body  # Cuerpo de la respuesta de SAP (acotado), para el detalle del ítem.


class SapNotFoundError(SapError):
    """Lectura de algo que no existe en SAP (404)."""


class SapUnavailableError(SapError):
    """No se pudo conectar: la solicitud no llegó a SAP (el ítem sigue pendiente)."""


class SapConnectionError(SapError):
    """La solicitud salió pero no hubo respuesta (timeout, corte): resultado incierto."""


def _network_message(exc: httpx.HTTPError) -> str:
    if "CERTIFICATE_VERIFY_FAILED" in str(exc):
        # Configuración del despliegue, no una caída de SAP.
        return "No se pudo validar el certificado TLS del Service Layer (revisar SAP_CA_FILE o SAP_VERIFY_TLS)."
    return "SAP no responde."


MAX_BODY_BYTES = 20_000  # Cuerpo de respuesta que se guarda por ítem.


def response_body(response: httpx.Response):
    """Cuerpo de la respuesta para guardarlo: JSON si lo es; si no, texto. Acotado."""
    if not response.content:
        return None
    if len(response.content) > MAX_BODY_BYTES:
        return {"omitted": "too_large", "size_bytes": len(response.content)}
    try:
        return response.json()
    except ValueError:
        return response.text


def sap_message(response: httpx.Response, limit: int = 1000) -> str:
    """Código y mensaje del error de SAP, sin el resto del cuerpo."""
    try:
        error = response.json().get("error", {})
        code = error.get("code")
        message = error.get("message")
        if isinstance(message, dict):  # Service Layer v1: {"lang": ..., "value": ...}
            message = message.get("value")
        text = f"{code}: {message}" if code is not None and message else str(message or code or "")
    except (ValueError, AttributeError):
        text = response.text
    return (text or f"HTTP {response.status_code}")[:limit]


DEFAULT_SESSION_SECONDS = 30 * 60  # Si SAP no informa SessionTimeout (su default es 30 min).
SESSION_MARGIN_SECONDS = 60  # Se renueva un poco antes de que SAP la dé por vencida.


class ServiceLayerClient:
    def __init__(self, base_url: str | None, company_db: str, user: str, password: str):
        """base_url: la del trabajo o la configurada para la empresa (job_service.service_layer_url)."""
        if not base_url:
            raise SapAuthError("El Service Layer de SAP no está configurado para esta empresa.")
        if not COMPANY_DB_PATTERN.fullmatch(company_db):
            raise SapAuthError("La base SAP tiene caracteres no permitidos.")
        self._login_body = {"CompanyDB": company_db, "UserName": user, "Password": password}
        # Con verificación: la CA propia si hay una; si no, las del sistema.
        verify: bool | str = (settings.SAP_CA_FILE or True) if settings.SAP_VERIFY_TLS else False
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            verify=verify,
            timeout=httpx.Timeout(settings.SAP_REQUEST_TIMEOUT_SECONDS, connect=settings.SAP_CONNECT_TIMEOUT_SECONDS),
            follow_redirects=False,
            # El tráfico a SAP no pasa por proxies del sistema.
            trust_env=False,
        )
        self._logged_in = False
        self._lock = threading.RLock()  # Login y renovación, de a uno por cliente.
        self._generation = 0  # Sube en cada login: evita renovar dos veces la misma sesión.
        self._session_seconds = DEFAULT_SESSION_SECONDS
        self._last_used = 0.0  # time.monotonic() del último uso con respuesta de SAP.

    def __enter__(self) -> "ServiceLayerClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def login(self) -> None:
        with self._lock:
            self._login()

    def _login(self) -> None:
        try:
            response = self._http.post("Login", json=self._login_body)
        except httpx.HTTPError as exc:
            # El login no modifica nada: cualquier fallo de red es "no disponible".
            raise SapUnavailableError(_network_message(exc)) from exc
        if response.status_code in (400, 401):
            raise SapAuthError(f"SAP rechazó el inicio de sesión: {sap_message(response, 300)}", response.status_code)
        if response.status_code >= 400:
            raise SapAuthError(f"SAP no permitió iniciar sesión: {sap_message(response, 300)}", response.status_code)
        try:
            minutes = int(response.json().get("SessionTimeout"))
        except (ValueError, TypeError, AttributeError):
            minutes = 0
        self._session_seconds = minutes * 60 if minutes > 0 else DEFAULT_SESSION_SECONDS
        self._logged_in = True
        self._generation += 1
        self._last_used = time.monotonic()

    def _session(self) -> int:
        """Inicia sesión si no hay una vigente. Devuelve la generación de la sesión usada."""
        with self._lock:
            idle = time.monotonic() - self._last_used
            if not self._logged_in or idle > max(self._session_seconds - SESSION_MARGIN_SECONDS, 60):
                self._login()
            return self._generation

    def _renew(self, generation: int) -> None:
        """SAP respondió 401: nuevo login, salvo que otra solicitud ya lo haya hecho."""
        with self._lock:
            if self._generation == generation:
                self._logged_in = False
                self._login()

    def _touch(self) -> None:
        self._last_used = time.monotonic()

    def post(self, path: str, body: dict | None = None) -> tuple[int, object]:
        """POST que modifica SAP. Devuelve (status HTTP, cuerpo de la respuesta) si fue exitoso."""
        generation = self._session()
        response = self._send(path, body)
        if response.status_code == 401:
            # Sesión vencida: SAP no ejecutó la solicitud. Nuevo login y un único reintento.
            self._renew(generation)
            response = self._send(path, body)
        self._touch()
        if response.status_code >= 400:
            raise SapRequestError(sap_message(response), response.status_code, response_body(response))
        return response.status_code, response_body(response)

    def _send(self, path: str, body: dict | None) -> httpx.Response:
        try:
            return self._http.post(path, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Sin conexión establecida: SAP no recibió nada.
            raise SapUnavailableError(_network_message(exc)) from exc
        except httpx.TimeoutException as exc:
            raise SapConnectionError("SAP no respondió a tiempo: el resultado es incierto.") from exc
        except httpx.HTTPError as exc:
            raise SapConnectionError("Se perdió la conexión con SAP: el resultado es incierto.") from exc

    def get_json(self, path: str, params: dict | None = None, headers: dict | None = None) -> object:
        """GET de lectura que devuelve JSON. SapNotFoundError si SAP responde 404."""
        response = self._read(lambda: self._http.get(path, params=params, headers=headers))
        try:
            return response.json()
        except ValueError as exc:
            raise SapRequestError("SAP devolvió una respuesta que no es JSON.", response.status_code) from exc

    @contextmanager
    def stream(self, path: str, params: dict | None = None) -> Iterator[httpx.Response]:
        """GET de un archivo sin cargarlo entero en memoria. Úsalo con with: al salir se cierra."""
        response = self._read(lambda: self._http.send(self._http.build_request("GET", path, params=params), stream=True))
        try:
            yield response
        except httpx.HTTPError as exc:
            # Corte mientras se leía el archivo.
            raise SapUnavailableError("Se perdió la conexión con SAP durante la descarga.") from exc
        finally:
            response.close()

    def _read(self, send) -> httpx.Response:
        """Lectura con login perezoso y un único reintento si la sesión venció (401)."""
        generation = self._session()
        response = self._send_read(send)
        if response.status_code == 401:
            response.close()
            self._renew(generation)
            response = self._send_read(send)
        self._touch()
        if response.status_code >= 400:
            response.read()  # En streaming el cuerpo del error aún no se leyó.
            response.close()
            error_class = SapNotFoundError if response.status_code == 404 else SapRequestError
            raise error_class(sap_message(response, 300), response.status_code)
        return response

    @staticmethod
    def _send_read(send) -> httpx.Response:
        try:
            return send()
        except httpx.TimeoutException as exc:
            raise SapUnavailableError("SAP no respondió a tiempo.") from exc
        except httpx.HTTPError as exc:
            raise SapUnavailableError(_network_message(exc)) from exc

    def close(self) -> None:
        if self._logged_in:
            try:
                self._http.post("Logout")
            except httpx.HTTPError:
                pass  # La sesión vence sola en SAP.
            self._logged_in = False
        self._http.close()


def document_action_path(entity: str, action: str, doc_entry: str) -> str:
    """{Entidad}({DocEntry})/{Acción}, con cada parte validada."""
    if not RESOURCE_PATTERN.fullmatch(entity) or not RESOURCE_PATTERN.fullmatch(action):
        raise SapRequestError("Entidad o acción con caracteres no permitidos.")
    if not doc_entry.isdigit():
        raise SapRequestError("El documento debe ser numérico.")
    return f"{entity}({doc_entry})/{action}"
