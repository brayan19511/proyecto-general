"""Convierte reglas de proyecto-05 (INSERT INTO finance.reglas_gastos …) al JSON de POST /rules/import.

No se conecta a ninguna base: lee un archivo .sql y escribe un .json.

    python scripts/convert_legacy_rules.py reglas.sql reglas.json            # mode=replace
    python scripts/convert_legacy_rules.py reglas.sql reglas.json --append   # mode=append

Correspondencia de columnas:
    cuenta → account_code, cuenta_contrapartida → counter_account_code,
    centro_costo → cost_center_code, filtro_texto → include_text,
    texto_excluido → exclude_text, monto_min / monto_max → amount_min / amount_max,
    nombre_cuenta, codigo y subcodigo se mantienen con su nombre,
    prioridad → priority. tipo_regla se ignora (acuerdo: sin tipo_regla).
    Las filas con activo = False no se incluyen.
Los textos se copian tal cual (solo sin espacios al inicio y al final).
"""

import argparse
import json
import re
import sys
from pathlib import Path

COLUMNS = {
    "cuenta": "account_code",
    "cuenta_contrapartida": "counter_account_code",
    "centro_costo": "cost_center_code",
    "filtro_texto": "include_text",
    "texto_excluido": "exclude_text",
    "monto_min": "amount_min",
    "monto_max": "amount_max",
    "nombre_cuenta": "nombre_cuenta",
    "codigo": "codigo",
    "subcodigo": "subcodigo",
    "prioridad": "priority",
}
IGNORED = {"tipo_regla", "activo", "id_regla", "created_at", "created_by", "updated_at", "updated_by"}
TOKEN = re.compile(r"\s*(?:'((?:[^']|'')*)'|(NULL|TRUE|FALSE)|(-?\d+(?:\.\d+)?)|([(),;]))", re.IGNORECASE)


def parse_insert(sql: str) -> tuple[list[str], list[list]]:
    """Columnas y filas de un INSERT INTO … (cols) VALUES (…), (…);"""
    header = re.search(r"INSERT\s+INTO\s+[\w.\"]+\s*\(([^)]*)\)\s*VALUES", sql, re.IGNORECASE)
    if header is None:
        raise ValueError("No se encontró INSERT INTO … (columnas) VALUES")
    columns = [c.strip().strip('"').lower() for c in header[1].split(",")]
    position, rows, row, depth = header.end(), [], None, 0
    while position < len(sql):
        match = TOKEN.match(sql, position)
        if match is None:
            if sql[position:].strip().upper().startswith(("COMMIT", "--")) or not sql[position:].strip():
                break
            raise ValueError(f"No se entiende el SQL cerca de: {sql[position:position + 40]!r}")
        position = match.end()
        text, keyword, number, symbol = match.groups()
        if symbol == "(":
            row, depth = [], depth + 1
        elif symbol == ")":
            rows.append(row)
            row, depth = None, depth - 1
        elif symbol == ";":
            break
        elif symbol == ",":
            continue
        elif row is not None:
            if text is not None:
                row.append(text.replace("''", "'"))
            elif keyword is not None:
                row.append({"NULL": None, "TRUE": True, "FALSE": False}[keyword.upper()])
            else:
                row.append(number)
    for index, values in enumerate(rows, start=1):
        if len(values) != len(columns):
            raise ValueError(f"La fila {index} tiene {len(values)} valores y hay {len(columns)} columnas")
    return columns, rows


def convert(columns: list[str], rows: list[list]) -> list[dict]:
    unknown = set(columns) - COLUMNS.keys() - IGNORED
    if unknown:
        raise ValueError(f"Columnas sin correspondencia: {', '.join(sorted(unknown))}")
    rules = []
    for values in rows:
        record = dict(zip(columns, values))
        if record.get("activo") is False:
            continue
        rule = {}
        for legacy, field in COLUMNS.items():
            value = record.get(legacy)
            if isinstance(value, str):
                value = value.strip() or None
            if field == "priority":
                value = int(value)
            rule[field] = value
        rules.append(rule)
    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sql", type=Path)
    parser.add_argument("json", type=Path)
    parser.add_argument("--append", action="store_true", help="mode=append (agrega sin dar de baja las activas)")
    args = parser.parse_args()

    columns, rows = parse_insert(args.sql.read_text(encoding="utf-8"))
    rules = convert(columns, rows)
    body = {"mode": "append" if args.append else "replace", "dry_run": True, "rules": rules}
    args.json.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    categories = {r["codigo"] for r in rules}
    print(f"{len(rows)} filas leídas, {len(rules)} reglas activas, {len(categories)} categorías distintas.")
    print(f"Escrito {args.json} con dry_run=true: revisar la respuesta y luego enviarlo con dry_run=false.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        sys.exit(f"Error: {exc}")
