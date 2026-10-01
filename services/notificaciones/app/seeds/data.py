"""Datos iniciales de notificaciones por empresa. Solo estructura: ningún secreto.

Se usan en POST /notificaciones/admin/seed (app/services/seed_service.py), que
busca la empresa de X-Company-Id por su código en auth (p. ej. RASH). Para
preconfigurar otra empresa, agrega su código aquí.

No se siembran cuentas SMTP (llevan contraseña: la plataforma prohíbe
contraseñas fijas en seeds) ni datos de negocio.

body_html_file: archivo en app/seeds/templates/ (más legible que un string largo).
"""

SEED_COMPANIES: dict[str, dict] = {
    "RASH": {
        "templates": [
            {
                # La de mailing_parameters "payment_provider_summary" de proyecto-05,
                # con "asunto" y "mensaje" opcionales que manda pagos-proveedores.
                "code": "payment_provider_summary",
                "name": "Constancia de pago a proveedores",
                "description": "Correo por proveedor con sus constancias de pago (pagos-proveedores).",
                "subject_template": "{{ asunto or 'CONSTANCIA DE PAGO ' ~ proveedor ~ ' || RASH PERU' }}",
                "body_html_file": "payment_provider_summary.html",
                "body_text_template": None,
                "to": [],
                "cc": [],
                "bcc": [],
                "reply_to": None,
            },
        ],
    },
}
