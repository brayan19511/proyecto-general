"""Permisos que exige canales-venta, módulo lastmiller (acuerdo del usuario, 2026-10-03).

Viven en el catálogo de auth (services/auth/app/core/permissions.py) y se
heredan por puestos. Este servicio solo los lee en GET /auth/me/permissions.
Compartidos por SKU y promociones; cada nivel incluye al anterior:

| Permiso           | Puede                                                     |
| ----------------- | --------------------------------------------------------- |
| lastmiller.view   | Consultar SKU y cuáles tienen promoción                    |
| lastmiller.edit   | Además on/off y alta/baja de promociones una por una       |
| lastmiller.import | Además cargas masivas (on/off y snapshot de promociones)   |

Alcance company.
"""

VIEW = "lastmiller.view"
EDIT = "lastmiller.edit"
IMPORT = "lastmiller.import"

# Lo que acepta cada nivel (un permiso mayor incluye a los menores).
CAN_VIEW = (VIEW, EDIT, IMPORT)
CAN_EDIT = (EDIT, IMPORT)
CAN_IMPORT = (IMPORT,)
