"""Permisos que exige sap-operaciones (acuerdo del usuario, 2026-10-04).

Viven en el catálogo de auth (services/auth/app/core/permissions.py) y se
heredan por puestos. Este servicio solo los lee en GET /auth/me/permissions.
Acumulativos, alcance company:

| Permiso                | Puede                                                      |
| ---------------------- | ---------------------------------------------------------- |
| sap_operations.view    | Ver trabajos, sus ítems y resultados; ver bases SAP          |
| sap_operations.execute | Además crear, ejecutar, cancelar y reanudar trabajos;       |
|                        | administrar la lista de bases SAP de la empresa             |

Ver las credenciales guardadas: solo el administrador de plataforma.
"""

VIEW = "sap_operations.view"
EXECUTE = "sap_operations.execute"

CAN_VIEW = (VIEW, EXECUTE)
CAN_EXECUTE = (EXECUTE,)
