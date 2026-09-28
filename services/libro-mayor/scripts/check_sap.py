"""Comprueba la conexión a SAP HANA y el contrato de la vista, sin escribir nada.

Usa SAP_HOST/SAP_USER/SAP_PASSWORD del .env. Ejemplos (desde services/libro-mayor):

    python scripts/check_sap.py --schema SBO_RASH_PRODUCCION --view VW_LIBRO_MAYOR_PERSONALIZADO_2
    python scripts/check_sap.py --schema SBO_RASH_PRODUCCION --view VW_LIBRO_MAYOR_PERSONALIZADO_2 \
        --account 95 --mode prefix --date 2026-09-01

1. Lista las columnas de la vista y compara con SAP_COLUMNS (faltantes / extra).
2. Con --account y --date: cuenta las líneas de ese día y muestra el tipo
   Python de cada columna (para revisar fechas, importes y textos).
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Para importar app.

from app.sap.ledger_reader import SAP_COLUMNS, AccountFilter, SapLedgerReader  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--view", required=True)
    parser.add_argument("--account", help="Código de cuenta, p. ej. 95 o 979005400")
    parser.add_argument("--mode", choices=["exact", "prefix"], default="prefix")
    parser.add_argument("--date", type=date.fromisoformat, help="Fecha de contabilización (AAAA-MM-DD)")
    args = parser.parse_args()

    reader = SapLedgerReader(args.schema, args.view)
    columns = reader.describe()
    missing = [c for c in SAP_COLUMNS if c not in columns]
    extra = [c for c in columns if c not in SAP_COLUMNS]
    print(f"Conexión correcta. La vista tiene {len(columns)} columnas.")
    print("Faltan del contrato:", missing or "ninguna")
    print("Extra (no se usan):", extra or "ninguna")
    if missing:
        sys.exit(1)

    if args.account and args.date:
        rows = reader.lines_by_posting_date([AccountFilter(args.account, args.mode)], args.date, args.date)
        print(f"\n{len(rows)} líneas de {args.account} ({args.mode}) el {args.date}.")
        if rows:
            print("Tipos por columna (tipos distintos entre filas se muestran juntos):")
            for column in SAP_COLUMNS:
                kinds = Counter(type(row[column]).__name__ for row in rows)
                print(f"  {column:<24} {dict(kinds)}")
            keys = Counter((row["transaccion_id"], row["linea"]) for row in rows)
            duplicated = sum(1 for n in keys.values() if n > 1)
            print(f"Claves (transaccion_id, linea) repetidas: {duplicated}")


if __name__ == "__main__":
    main()
