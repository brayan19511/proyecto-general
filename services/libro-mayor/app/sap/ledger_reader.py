"""Lector de la vista de libro mayor en SAP HANA (repositorio SAP).

Todo el SQL hacia SAP vive aquí. Contrato con la vista (acordado con el equipo
SAP; proviene de proyecto-05): las columnas de SAP_COLUMNS. El lector las pide
explícitamente, nunca SELECT *: si la vista cambia, falla de forma visible en
lugar de traer columnas nuevas sin revisar.

Seguridad del SQL:
- schema y vista son identificadores (no admiten parámetros): se revalidan
  con la lista cerrada de sap_company_service y se escriben entre comillas.
- Cuentas y fechas siempre como parámetros (:a0, :date_from, …).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

from app.sap.connection import sap_engine
from app.services.sap_company_service import validate_identifier

# Columnas de la vista que usa este servicio. No se piden usuario_id ni autor
# (datos del usuario SAP que no hacen falta).
SAP_COLUMNS = (
    "transaccion_id",
    "linea",
    "fecha_contabilizacion",
    "fecha_documento",
    "numero_documento",
    "transaccion_tipo",
    "folio",
    "tipo_documento",
    "cuenta_asociada",
    "nombre_cuenta_asociada",
    "proveedor",
    "descripcion",
    "comentario_linea",
    "cuenta_contrapartida",
    "nombre_contrapartida",
    "referencia_1",
    "referencia_2",
    "referencia_3",
    "cargo_abono_ml",
    "cargo_abono_me",
    "centro_costo",
    "centro_area",
    "nombre_area",
    "fecha_creacion",
    "fecha_actualizacion",
)


@dataclass(frozen=True)
class AccountFilter:
    """Una cuenta registrada: exact = igual al código; prefix = empieza por él."""

    code: str
    match_mode: str


class SapLedgerReader:
    def __init__(self, sap_schema: str, source_view: str):
        schema = validate_identifier("sap_schema", sap_schema)
        view = validate_identifier("source_view", source_view)
        self.source = f'"{schema}"."{view}"'

    def lines_by_posting_date(
        self, accounts: list[AccountFilter], date_from: date, date_to: date
    ) -> list[dict]:
        """Líneas de las cuentas dadas con fecha de contabilización en [date_from, date_to]."""
        if not accounts:
            return []
        where_accounts, params = _accounts_condition(accounts)
        columns = ", ".join(f'"{c}"' for c in SAP_COLUMNS)
        sql = text(
            f'SELECT {columns} FROM {self.source} '
            f'WHERE "fecha_contabilizacion" BETWEEN :date_from AND :date_to AND ({where_accounts}) '
            f'ORDER BY "transaccion_id", "linea"'
        )
        with sap_engine().connect() as connection:
            result = connection.execute(sql, {**params, "date_from": date_from, "date_to": date_to})
            return [dict(row) for row in result.mappings()]

    def lines_changed_since(self, accounts: list[AccountFilter], since: date) -> list[dict]:
        """Líneas de las cuentas dadas creadas o actualizadas en SAP desde el día `since` (inclusive).

        Es el delta: incluye líneas de cualquier fecha de contabilización que SAP
        haya modificado. Se compara por día completo porque SAP puede guardar
        solo la fecha (sin hora) de creación y actualización.
        """
        if not accounts:
            return []
        where_accounts, params = _accounts_condition(accounts)
        columns = ", ".join(f'"{c}"' for c in SAP_COLUMNS)
        sql = text(
            f'SELECT {columns} FROM {self.source} '
            f'WHERE ("fecha_creacion" >= :since OR "fecha_actualizacion" >= :since) AND ({where_accounts}) '
            f'ORDER BY "transaccion_id", "linea"'
        )
        with sap_engine().connect() as connection:
            result = connection.execute(sql, {**params, "since": since})
            return [dict(row) for row in result.mappings()]

    def describe(self) -> list[str]:
        """Columnas que expone la vista (sin traer filas). Para comprobar el contrato."""
        with sap_engine().connect() as connection:
            result = connection.execute(text(f"SELECT * FROM {self.source} WHERE 1 = 0"))
            return list(result.keys())


def _accounts_condition(accounts: list[AccountFilter]) -> tuple[str, dict]:
    """ "cuenta_asociada" = :a0 OR "cuenta_asociada" LIKE :a1 … con sus parámetros.

    Los códigos son solo dígitos (validados al registrar), así que un prefijo no
    puede contener comodines de LIKE.
    """
    parts, params = [], {}
    for i, account in enumerate(accounts):
        name = f"a{i}"
        if account.match_mode == "prefix":
            parts.append(f'"cuenta_asociada" LIKE :{name}')
            params[name] = f"{account.code}%"
        else:
            parts.append(f'"cuenta_asociada" = :{name}')
            params[name] = account.code
    return " OR ".join(parts), params
