"""Permisos que exige libro-mayor (acuerdo del usuario, 2026-09-30).

Viven en el catálogo de auth (services/auth/app/core/permissions.py) y se
heredan por puestos. Este servicio solo los lee en GET /auth/me/permissions.
Tres niveles; cada uno incluye al anterior:

| Permiso        | Puede                                                                 |
| -------------- | --------------------------------------------------------------------- |
| ledger.view    | Consultar líneas, resumen, CSV y en vivo; ver reglas, categorías,    |
|                | cuentas, sincronizaciones y su estado                                 |
| ledger.update  | Además crear, editar y dar de baja reglas y categorías, importarlas   |
|                | y reclasificar                                                        |
| ledger.admin   | Además cuentas a sincronizar y sincronización manual                 |

Alcance company (el alcance area llegará con la homologación de centros de
costo). Compañía SAP, seed y logs: solo el administrador de plataforma.
"""

VIEW = "ledger.view"
UPDATE = "ledger.update"
ADMIN = "ledger.admin"

# Lo que acepta cada nivel (un permiso mayor incluye a los menores).
CAN_VIEW = (VIEW, UPDATE, ADMIN)
CAN_UPDATE = (UPDATE, ADMIN)
CAN_ADMIN = (ADMIN,)
