"""Plan de una carga masiva: qué cambiaría en Ofisis. Funciones puras (sin bases).

Tipos de carga (acuerdo del usuario, 2026-10-04):
- sku_full (completa): el archivo es la lista completa del canal. Cada SKU
  listado queda on/off según el archivo; los existentes que NO están en el
  archivo quedan off.
- sku_partial (parcial): solo se tocan los SKU del archivo; el resto no cambia.
- promotions (solo PedidosYa): el archivo es la lista completa de SKU con
  promoción. Todos deben existir en el canal (si falta uno, no se aplica nada).
  El resultado final es exactamente esa lista: se quitan las que no están y se
  agregan las nuevas; las que siguen no se tocan (mismo resultado que borrar
  todo y volver a cargar, con menos escrituras y sin dejar el canal vacío).

En las cargas de SKU, create_missing decide si un SKU del archivo que no existe
se crea (con el estado del archivo) o se informa como "no existe" y se omite.
"""

import json
from hashlib import sha256

from app.lastmiller.sku_repository import normalize


def plan_skus(
    kind: str,
    rows: list[dict],
    current: dict[str, tuple[str, bool]],
    create_missing: bool,
) -> dict:
    create: list[dict] = []
    activate: list[str] = []
    deactivate: list[str] = []
    missing: list[str] = []
    unchanged = 0
    listed: set[str] = set()

    for row in rows:
        key = normalize(row["sku"])
        listed.add(key)
        existing = current.get(key)
        if existing is None:
            if create_missing:
                create.append({"sku": row["sku"], "active": row["active"]})
            else:
                missing.append(row["sku"])
            continue
        sku, active = existing
        if active == row["active"]:
            unchanged += 1
        elif row["active"]:
            activate.append(sku)
        else:
            deactivate.append(sku)

    # Solo en la carga completa: lo que no vino en el archivo y está on, se apaga.
    deactivate_unlisted = (
        [sku for key, (sku, active) in current.items() if key not in listed and active]
        if kind == "sku_full"
        else []
    )
    return {
        "rows": len(rows),
        "create": sorted(create, key=lambda item: item["sku"]),
        "activate": sorted(activate),
        "deactivate": sorted(deactivate),
        "deactivate_unlisted": sorted(deactivate_unlisted),
        "missing": sorted(missing),
        "unchanged": unchanged,
        "blocking": False,
    }


def plan_promotions(rows: list[dict], current: dict[str, tuple[str, bool]], promotions: dict[str, str]) -> dict:
    add: list[str] = []
    missing: list[str] = []
    inactive: list[str] = []
    unchanged = 0
    listed: set[str] = set()

    for row in rows:
        key = normalize(row["sku"])
        listed.add(key)
        existing = current.get(key)
        if existing is None:
            missing.append(row["sku"])
            continue
        sku, active = existing
        if not active:
            inactive.append(sku)  # Aviso: tendrá promoción pero el SKU está off.
        if key in promotions:
            unchanged += 1
        else:
            add.append(sku)

    remove = [sku for key, sku in promotions.items() if key not in listed]
    return {
        "rows": len(rows),
        "add": sorted(add),
        "remove": sorted(remove),
        "missing": sorted(missing),
        "inactive": sorted(inactive),
        "unchanged": unchanged,
        # Un SKU inexistente bloquea toda la carga: no se aplica a medias.
        "blocking": bool(missing),
    }


def steps(plan: dict) -> list[tuple[str, str, bool | None]]:
    """Cambios a ejecutar, en orden: (acción, sku, estado nuevo si aplica)."""
    result: list[tuple[str, str, bool | None]] = []
    result += [("create", item["sku"], item["active"]) for item in plan.get("create", [])]
    result += [("activate", sku, True) for sku in plan.get("activate", [])]
    result += [("deactivate", sku, False) for sku in plan.get("deactivate", []) + plan.get("deactivate_unlisted", [])]
    result += [("promotion_remove", sku, None) for sku in plan.get("remove", [])]
    result += [("promotion_add", sku, None) for sku in plan.get("add", [])]
    return result


def plan_hash(plan: dict) -> str:
    """Huella de los cambios del plan. Si al aplicar no coincide con la de la
    vista previa, el estado de Ofisis cambió y hay que volver a previsualizar."""
    payload = json.dumps({"steps": steps(plan), "blocking": plan.get("blocking", False)}, sort_keys=True)
    return sha256(payload.encode()).hexdigest()
