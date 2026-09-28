"""Permisos que exige libro-mayor.

Los permisos viven en el catálogo de auth (services/auth/app/core/permissions.py)
y se heredan por puestos. Este servicio solo los lee en la respuesta de
GET /auth/me/permissions. Mientras un código no esté en ese catálogo nadie lo
tiene, y solo el administrador de plataforma puede usar la ruta.
"""

# Registrar, editar y dar de baja las cuentas SAP que se sincronizan (alcance company).
ACCOUNTS_MANAGE = "ledger.accounts.manage"
# Lanzar sincronizaciones manuales y consultar su estado (alcance company).
SYNC = "ledger.sync"
