"""Datos de la carga inicial (POST /libro-mayor/admin/seed), por código de empresa de auth.

El seed aplica los datos de la empresa de X-Company-Id. Lo que ya existe no se
modifica y lo que fue dado de baja no se reactiva: para agregar una cuenta,
se agrega aquí y se vuelve a ejecutar (o se usa POST /accounts).

Cuentas iniciales de RASH (definidas por el usuario, 2026-09-28): 95 y 97 por
prefijo y dos cuentas de ventas 701 exactas. No agregar aquí cuentas 95… o
97… exactas: se superpondrían con los prefijos (el seed respondería 409).
"""

from datetime import date

SEED_COMPANIES = {
    "RASH": {
        "sap_company": {
            "sap_schema": "SBO_RASH_PRODUCCION",
            "source_view": "VW_LIBRO_MAYOR_PERSONALIZADO_2",
            "sync_start_date": date(2026, 1, 1),
        },
        "accounts": [
            ("95", "prefix", "GASTOS (TODAS LAS 95)"),
            ("97", "prefix", "GASTOS (TODAS LAS 97)"),
            ("701110002", "exact", "VENTAS POWERZONE"),
            ("701110003", "exact", "VENTAS ACCESORIOS DE CELULARES"),
       
        ],
    },
}
