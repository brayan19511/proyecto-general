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
"""

import re

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

    def __enter__(self) -> "ServiceLayerClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def login(self) -> None:
        try:
            response = self._http.post("Login", json=self._login_body)
        except httpx.HTTPError as exc:
            # El login no modifica nada: cualquier fallo de red es "no disponible".
            raise SapUnavailableError(_network_message(exc)) from exc
        if response.status_code in (400, 401):
            raise SapAuthError(f"SAP rechazó el inicio de sesión: {sap_message(response, 300)}", response.status_code)
        if response.status_code >= 400:
            raise SapAuthError(f"SAP no permitió iniciar sesión: {sap_message(response, 300)}", response.status_code)
        self._logged_in = True

    def post(self, path: str, body: dict | None = None) -> tuple[int, object]:
        """POST que modifica SAP. Devuelve (status HTTP, cuerpo de la respuesta) si fue exitoso."""
        if not self._logged_in:
            self.login()
        response = self._send(path, body)
        if response.status_code == 401:
            # Sesión vencida: SAP no ejecutó la solicitud. Nuevo login y un único reintento.
            self._logged_in = False
            self.login()
            response = self._send(path, body)
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
