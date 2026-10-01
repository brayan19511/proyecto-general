"""Consultas en vivo a SAP: una sola llamada que extrae, clasifica y responde.

1. Parte el rango en tramos: por mes (default) o por día.
2. Consulta SAP cada tramo en paralelo, en hilos de este proceso, y clasifica
   cada línea con las reglas activas de la empresa (classifier.py).
3. Une los tramos en orden y devuelve lo pedido en view: full (líneas +
   resumen), lines (solo líneas) o summary (solo resumen).

No guarda nada en la base: la memoria se libera al responder. Controles:
- Pool de hilos COMPARTIDO por todas las solicitudes (LIVE_QUERY_PARALLEL):
  aunque lleguen muchas consultas a la vez, este proceso nunca tiene más de N
  consultas abiertas contra SAP; las demás esperan turno.
- view=full / lines: como máximo LIVE_QUERY_MAX_LINES líneas (si no, 422).
- view=summary: cada tramo se resume al llegar y sus líneas se descartan; el
  resumen de un año entero pesa unos pocos KB y no tiene límite de líneas.
- LIVE_QUERY_TIMEOUT_SECONDS para toda la consulta (si no, 504).

Cuentas: "95*" = todas las que empiezan por 95; "979005400" = exacta. No hace
falta que estén registradas. No toca ledger_lines.

Visibilidad: con ledger.view de alcance area solo quedan las líneas cuyos
centros de costo están homologados a esas áreas (se filtran al llegar de SAP).
Cada línea trae area_id / area_name de su homologación.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date

from platform_audit import step
from sqlalchemy.orm import Session

from app.core.config import settings
from app.sap.connection import sap_enabled
from app.sap.ledger_reader import AccountFilter, SapLedgerReader
from app.services.classifier import CompiledRule, classify, load_rules
from app.services.cost_center_service import CenterMap, load_center_map
from app.services.errors import ConflictError, DeadlineExceededError, InvalidDataError, ServiceError, UpstreamError
from app.services.reporting import UNCLASSIFIED, add_to_partial, build_summary, describe_rules, merge_partials
from app.services.sap_company_service import active_sap_company
from app.services.sync_service import SapDataError, safe_message, sap_today, split_range, to_line_values

ACCOUNT_PATTERN = re.compile(r"^(\d{1,20})(\*?)$")

# Un solo pool por proceso para todas las solicitudes: es el límite de carga sobre SAP.
_pool = ThreadPoolExecutor(max_workers=settings.LIVE_QUERY_PARALLEL, thread_name_prefix="live-sap")


def parse_accounts(accounts: list[str]) -> list[AccountFilter]:
    """["95*", "979005400"] → filtros de SAP. Sin repetidos, en el orden recibido."""
    filters = []
    for raw in accounts:
        match = ACCOUNT_PATTERN.fullmatch(raw.strip())
        if match is None:
            raise InvalidDataError(f"Cuenta inválida: {raw!r}. Use dígitos (exacta) o dígitos y * (prefijo), p. ej. 95*.")
        account = AccountFilter(match[1], "prefix" if match[2] else "exact")
        if account not in filters:
            filters.append(account)
    return filters


def _fetch(
    reader: SapLedgerReader, filters, start: date, end: date, rules: list[CompiledRule], summary_only: bool,
    centers: CenterMap, area_ids: frozenset[str] | None,
):
    """Un tramo (corre en un hilo del pool): consulta SAP, convierte y clasifica.

    Devuelve las líneas, o solo su total parcial si summary_only (las líneas
    se descartan en el acto y no ocupan memoria).
    """
    rows = reader.lines_by_posting_date(filters, start, end)
    lines, partial = [], {}
    for row in rows:
        line = to_line_values(row)
        if not centers.visible(line["cost_center_code"], area_ids):
            continue  # Alcance area: centro no homologado a sus áreas.
        line["rule_id"] = classify(line, rules)
        if summary_only:
            add_to_partial(partial, line)
        else:
            lines.append(line)
    return partial if summary_only else lines


class LiveQueryService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self, *, company_id: str, accounts: list[str], date_from: date, date_to: date, split: str, view: str,
        area_ids: frozenset[str] | None = None,
    ) -> dict:
        filters = parse_accounts(accounts)
        if not filters:
            raise InvalidDataError("Indique al menos una cuenta.")
        if len(filters) > settings.LIVE_QUERY_MAX_ACCOUNTS:
            raise InvalidDataError(f"Máximo {settings.LIVE_QUERY_MAX_ACCOUNTS} cuentas por consulta.")
        days = (date_to - date_from).days + 1
        if days < 1:
            raise InvalidDataError("date_to no puede ser anterior a date_from.")
        if days > settings.LIVE_QUERY_MAX_DAYS:
            raise InvalidDataError(f"El rango no puede superar {settings.LIVE_QUERY_MAX_DAYS} días.")
        if date_to > sap_today():
            raise InvalidDataError("date_to no puede ser una fecha futura (día de SAP).")
        if not sap_enabled():
            raise ConflictError("SAP no está configurado en este servicio (SAP_HOST).")

        with self.db.begin():
            sap_company = active_sap_company(self.db, company_id)
            if sap_company is None:
                raise ConflictError("La empresa no tiene compañía SAP configurada.")
            rules = load_rules(self.db, company_id)  # Mismas reglas para todos los tramos.
            centers = load_center_map(self.db, company_id)
        reader = SapLedgerReader(sap_company.sap_schema, sap_company.source_view)
        chunks = split_range(date_from, date_to, split)
        summary_only = view == "summary"

        started = time.monotonic()
        deadline = started + settings.LIVE_QUERY_TIMEOUT_SECONDS
        with step("live_query", f"{len(chunks)} tramos por {split}, vista {view}"):
            futures = [_pool.submit(_fetch, reader, filters, a, b, rules, summary_only, centers, area_ids) for a, b in chunks]
            results, lines_total = [], 0
            try:
                for future in futures:  # En orden de tramo: el resultado sale ordenado por fecha.
                    part = future.result(timeout=max(deadline - time.monotonic(), 0))
                    if not summary_only:
                        lines_total += len(part)
                        if lines_total > settings.LIVE_QUERY_MAX_LINES:
                            raise InvalidDataError(
                                f"La consulta supera {settings.LIVE_QUERY_MAX_LINES} líneas: acote el rango o las "
                                "cuentas, o pida view=summary."
                            )
                    results.append(part)
            except FutureTimeout:
                raise DeadlineExceededError(
                    f"La consulta superó {settings.LIVE_QUERY_TIMEOUT_SECONDS} s: acote el rango o pida view=summary."
                ) from None
            except ServiceError:
                raise  # Errores propios (p. ej. demasiadas líneas): tal cual.
            except SapDataError as exc:
                raise UpstreamError(str(exc)) from None
            except Exception as exc:  # noqa: BLE001 - cualquier fallo de SAP (driver, red…) = 502.
                raise UpstreamError(safe_message(exc)) from None  # Solo tipo/código: nunca el texto crudo.
            finally:
                for future in futures:
                    future.cancel()  # Tramos que aún no empezaron; los que ya corren terminan solos.

        if summary_only:
            partial = merge_partials(results)
            lines = None
            lines_total = sum(count for count, _, _ in partial.values())
            rule_ids = {key[2] for key in partial}
        else:
            lines = sorted(
                (line for part in results for line in part),
                key=lambda l: (l["posting_date"], l["sap_transaction_id"], l["sap_line"]),
            )
            partial = {}
            if view == "full":  # view=lines no arma resumen.
                for line in lines:
                    add_to_partial(partial, line)
            rule_ids = {line["rule_id"] for line in lines}

        with self.db.begin():
            described = describe_rules(self.db, rule_ids)
        if lines is not None:
            for line in lines:
                info = described.get(line["rule_id"], UNCLASSIFIED)
                line.update(info)
                line["nombre_cuenta"] = info["nombre_cuenta"] or line["account_name"]
                line.update(centers.area(line["cost_center_code"]))
        return {
            "accounts": [f.code + ("*" if f.match_mode == "prefix" else "") for f in filters],
            "date_from": date_from,
            "date_to": date_to,
            "split": split,
            "chunks": len(chunks),
            "lines_total": lines_total,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "summary": None if view == "lines" else build_summary(partial, described),
            "lines": lines,
        }
