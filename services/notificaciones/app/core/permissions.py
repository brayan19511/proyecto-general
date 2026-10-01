"""Permisos que exige notificaciones (acuerdo del usuario, 2026-10-01).

Viven en el catálogo de auth y se heredan por puestos. Este servicio solo los
lee en GET /auth/me/permissions. Cuatro niveles; cada uno incluye al anterior:

| Permiso              | Alcances     | Puede                                                    |
| -------------------- | ------------ | -------------------------------------------------------- |
| notifications.view   | company, own | Listar envíos y mensajes; ver destinatarios, asunto,     |
|                      |              | cuerpo, adjuntos y estado                                |
| notifications.send   | company, own | Además crear envíos                                      |
| notifications.retry  | company, own | Además reprocesar y cancelar mensajes                    |
| notifications.admin  | company      | Además cuentas SMTP y detalle técnico (intentos, cuenta  |
|                      |              | usada, códigos SMTP)                                     |

own: solo los envíos que solicitó el usuario. company: todos los de la empresa.
"""

VIEW = "notifications.view"
SEND = "notifications.send"
RETRY = "notifications.retry"
ADMIN = "notifications.admin"

# Lo que acepta cada nivel (un permiso mayor incluye a los menores).
CAN_VIEW = (VIEW, SEND, RETRY, ADMIN)
CAN_SEND = (SEND, RETRY, ADMIN)
CAN_RETRY = (RETRY, ADMIN)
CAN_ADMIN = (ADMIN,)
