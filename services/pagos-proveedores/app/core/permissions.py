"""Permisos que exige pagos-proveedores (acuerdo del usuario, 2026-10-01).

Viven en el catálogo de auth y se heredan por puestos; todos con alcance company.
Dos ramas sobre view que no se incluyen entre sí:

                     payments.view
                    /             \\
    payments.providers.manage    payments.send
                    \\             /
                     payments.admin

| Permiso                    | Puede                                                   |
| -------------------------- | ------------------------------------------------------- |
| payments.view              | Ver proveedores, lotes y su estado                      |
| payments.providers.manage  | Además crear, editar, dar de baja y restaurar proveedores |
| payments.send              | Además crear lotes, descargar el ZIP y enviar           |
| payments.admin             | Todo                                                    |
"""

VIEW = "payments.view"
MANAGE_PROVIDERS = "payments.providers.manage"
SEND = "payments.send"
ADMIN = "payments.admin"

# Lo que acepta cada acción.
CAN_VIEW = (VIEW, MANAGE_PROVIDERS, SEND, ADMIN)
CAN_MANAGE_PROVIDERS = (MANAGE_PROVIDERS, ADMIN)
CAN_SEND = (SEND, ADMIN)
