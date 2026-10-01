"""Homologación de centros de costo a áreas de auth (libro_mayor.cost_center_mappings).

Decide quién ve cada línea (ledger.view de alcance area), no su clasificación.
- Un centro de costo pertenece a una sola área (acuerdo). Coincidencia exact
  (código completo) o prefix (V114 → todas las tiendas V114…). Si varias
  coinciden: exacto > prefijo más largo (acuerdo), así un centro puede
  exceptuarse de su prefijo.
- El área llega ya validada contra auth (la ruta consulta GET /auth/areas con
  las credenciales del usuario) como {"id", "code", "name"}.
- Se resuelve al consultar: cambiar una homologación no reprocesa líneas.
- Líneas sin centro o con centro sin homologar: solo alcance company.
"""

from platform_audit import step
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import CostCenterMapping, LedgerLine
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.history import record_change

DUPLICATE = "Ese centro de costo (o prefijo) ya está homologado a un área; use PATCH para cambiarla."


def _snapshot(mapping: CostCenterMapping) -> dict:
    return {
        "cost_center_code": mapping.cost_center_code, "match_mode": mapping.match_mode,
        "auth_area_id": mapping.auth_area_id, "area_code": mapping.area_code, "area_name": mapping.area_name,
    }


def _code(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        raise InvalidDataError("cost_center_code no puede estar vacío.")
    return value


# --- Lecturas que usan las consultas ---------------------------------------


NO_AREA = {"area_id": None, "area_name": None}


class CenterMap:
    """Homologaciones activas de una empresa, listas para resolver centros."""

    def __init__(self, mappings):
        self.exact: dict[str, dict] = {}
        prefixes = []
        for m in mappings:
            info = {"area_id": m.auth_area_id, "area_name": m.area_name,
                    "match_mode": m.match_mode, "mapping_code": m.cost_center_code}
            if m.match_mode == "prefix":
                prefixes.append((m.cost_center_code, info))
            else:
                self.exact[m.cost_center_code] = info
        self.prefixes = sorted(prefixes, key=lambda p: len(p[0]), reverse=True)  # Más largo primero.

    def resolve(self, code: str | None) -> dict | None:
        """Homologación que aplica al centro (exacto > prefijo más largo); None = sin homologar."""
        if not code:
            return None
        found = self.exact.get(code)
        if found is None:
            found = next((info for prefix, info in self.prefixes if code.startswith(prefix)), None)
        return found

    def area(self, code: str | None) -> dict:
        found = self.resolve(code)
        return {"area_id": found["area_id"], "area_name": found["area_name"]} if found else NO_AREA

    def visible(self, code: str | None, area_ids: frozenset[str] | None) -> bool:
        """None = alcance company (todo). Con áreas: solo centros resueltos a una de ellas."""
        if area_ids is None:
            return True
        found = self.resolve(code)
        return found is not None and found["area_id"] in area_ids


def load_center_map(db: Session, company_id: str) -> CenterMap:
    return CenterMap(db.scalars(
        select(CostCenterMapping).where(CostCenterMapping.company_id == company_id, CostCenterMapping.is_active.is_(True))
    ))


def visible_codes(db: Session, company_id: str, area_ids: frozenset[str] | None, centers: CenterMap) -> set[str] | None:
    """Centros sincronizados que puede ver quien tiene esas áreas; None = sin restricción (company).

    Con prefijos no basta un IN de los códigos homologados: se resuelven los
    centros distintos de las líneas (unos cientos, índice company+centro).
    """
    if area_ids is None:
        return None
    codes = db.scalars(
        select(LedgerLine.cost_center_code).where(
            LedgerLine.company_id == company_id, LedgerLine.cost_center_code.is_not(None)
        ).distinct()
    )
    return {code for code in codes if centers.visible(code, area_ids)}


# --- Administración ----------------------------------------------------------


class CostCenterService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool = False) -> list[CostCenterMapping]:
        with self.db.begin():
            query = select(CostCenterMapping).where(CostCenterMapping.company_id == company_id)
            if not include_inactive:
                query = query.where(CostCenterMapping.is_active.is_(True))
            return list(self.db.scalars(query.order_by(CostCenterMapping.cost_center_code)))

    def centers(self, company_id: str, *, unmapped_only: bool) -> list[dict]:
        """Centros de costo que aparecen en las líneas sincronizadas, con su homologación.

        Sirve para ver qué falta homologar (unmapped_only). Las líneas sin centro
        de costo se cuentan aparte en una fila con cost_center_code null.
        """
        with self.db.begin():
            rows = self.db.execute(
                select(
                    LedgerLine.cost_center_code,
                    func.max(LedgerLine.cost_center_name),
                    func.count(),
                    func.max(LedgerLine.posting_date),
                )
                .where(LedgerLine.company_id == company_id)
                .group_by(LedgerLine.cost_center_code)
                .order_by(LedgerLine.cost_center_code)
            ).all()
            centers = load_center_map(self.db, company_id)
        result = []
        for code, name, lines, last in rows:
            mapped = centers.resolve(code)
            if unmapped_only and mapped is not None:
                continue
            result.append({
                "cost_center_code": code, "sap_name": name, "lines": lines, "last_posting_date": last,
                **(mapped or {"area_id": None, "area_name": None, "match_mode": None, "mapping_code": None}),
            })
        return result

    def create(
        self, *, company_id: str, user_id: str, cost_center_code: str, match_mode: str, area: dict
    ) -> CostCenterMapping:
        code = _code(cost_center_code)
        try:
            with step("cost_center_mapping.create"), self.db.begin():
                if self._active(company_id, code, match_mode) is not None:
                    raise ConflictError(DUPLICATE)
                mapping = self._add(company_id, user_id, code, match_mode, area, utcnow())
        except IntegrityError:
            raise ConflictError(DUPLICATE) from None
        return mapping

    def update(self, *, company_id: str, user_id: str, mapping_id: str, area: dict) -> CostCenterMapping:
        """Cambia el área (y refresca su código y nombre)."""
        with step("cost_center_mapping.update"), self.db.begin():
            mapping = self._find(company_id, mapping_id)
            before = _snapshot(mapping)
            mapping.auth_area_id, mapping.area_code, mapping.area_name = area["id"], area["code"], area["name"]
            after = _snapshot(mapping)
            if after == before:
                return mapping
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            mapping.updated_at, mapping.updated_by = now, actor_id
            record_change(
                self.db, action="cost_center_mapping.update", resource_type="cost_center_mapping",
                resource_id=mapping.id, company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
        return mapping

    def deactivate(self, *, company_id: str, user_id: str, mapping_id: str) -> None:
        """Baja lógica: sus líneas vuelven a verse solo con alcance company."""
        with step("cost_center_mapping.delete"), self.db.begin():
            mapping = self._find(company_id, mapping_id)
            actor_id = user_actor_id(self.db, user_id)
            self._retire(mapping, actor_id, utcnow())

    def import_(self, *, company_id: str, user_id: str, mode: str, dry_run: bool, items: list[tuple[str, dict]]) -> dict:
        """Carga masiva en una transacción (todo o nada).

        items: [(cost_center_code, match_mode, área validada)]. mode=replace da
        de baja las homologaciones activas que no vengan en la carga; append
        solo agrega. Clave: código + match_mode. Si ya existe con la misma área
        queda igual; con otra área se actualiza (con historial).
        """
        keys = [(_code(code), match_mode) for code, match_mode, _ in items]
        repeated = sorted({code + ("*" if m == "prefix" else "") for code, m in keys if keys.count((code, m)) > 1})
        if repeated:
            raise InvalidDataError(f"Centros de costo repetidos en la carga: {', '.join(repeated[:20])}.")
        transaction = self.db.begin()
        try:
            with step("cost_center_mapping.import", f"{len(items)} homologaciones, mode={mode}, dry_run={dry_run}"):
                actor_id = user_actor_id(self.db, user_id)
                now = utcnow()
                active = {
                    (m.cost_center_code, m.match_mode): m
                    for m in self.db.scalars(
                        select(CostCenterMapping)
                        .where(CostCenterMapping.company_id == company_id, CostCenterMapping.is_active.is_(True))
                        .with_for_update()
                    )
                }
                created = updated = unchanged = deactivated = 0
                for (code, match_mode), (_, _, area) in zip(keys, items):
                    current = active.get((code, match_mode))
                    if current is None:
                        self._add(company_id, user_id, code, match_mode, area, now, actor_id=actor_id)
                        created += 1
                    elif current.auth_area_id == area["id"]:
                        unchanged += 1
                    else:
                        before = _snapshot(current)
                        current.auth_area_id, current.area_code, current.area_name = area["id"], area["code"], area["name"]
                        current.updated_at, current.updated_by = now, actor_id
                        record_change(
                            self.db, action="cost_center_mapping.update", resource_type="cost_center_mapping",
                            resource_id=current.id, company_id=company_id, actor_id=actor_id, now=now,
                            before=before, after=_snapshot(current),
                        )
                        updated += 1
                if mode == "replace":
                    wanted = set(keys)
                    for key, mapping in active.items():
                        if key not in wanted:
                            self._retire(mapping, actor_id, now)
                            deactivated += 1
            result = {"mode": mode, "dry_run": dry_run, "created": created, "updated": updated,
                      "unchanged": unchanged, "deactivated": deactivated}
            if dry_run:
                transaction.rollback()
            else:
                transaction.commit()
        except BaseException:
            transaction.rollback()
            raise
        return result

    def _add(self, company_id: str, user_id: str, code: str, match_mode: str, area: dict, now, actor_id: str | None = None):
        actor_id = actor_id or user_actor_id(self.db, user_id)
        mapping = CostCenterMapping(
            company_id=company_id, cost_center_code=code, match_mode=match_mode, auth_area_id=area["id"],
            area_code=area["code"], area_name=area["name"], created_at=now, created_by=actor_id,
        )
        self.db.add(mapping)
        self.db.flush()
        record_change(
            self.db, action="cost_center_mapping.create", resource_type="cost_center_mapping", resource_id=mapping.id,
            company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(mapping),
        )
        return mapping

    def _retire(self, mapping: CostCenterMapping, actor_id: str, now) -> None:
        mapping.is_active = False
        mapping.deleted_at = mapping.updated_at = now
        mapping.deleted_by = mapping.updated_by = actor_id
        record_change(
            self.db, action="cost_center_mapping.delete", resource_type="cost_center_mapping", resource_id=mapping.id,
            company_id=mapping.company_id, actor_id=actor_id, now=now, before=_snapshot(mapping), after={},
        )

    def _active(self, company_id: str, code: str, match_mode: str) -> CostCenterMapping | None:
        return self.db.scalar(
            select(CostCenterMapping).where(
                CostCenterMapping.company_id == company_id, CostCenterMapping.cost_center_code == code,
                CostCenterMapping.match_mode == match_mode,
                CostCenterMapping.is_active.is_(True),
            )
        )

    def _find(self, company_id: str, mapping_id: str) -> CostCenterMapping:
        mapping = self.db.scalar(
            select(CostCenterMapping)
            .where(CostCenterMapping.id == mapping_id, CostCenterMapping.company_id == company_id,
                   CostCenterMapping.is_active.is_(True))
            .with_for_update()
        )
        if mapping is None:
            raise NotFoundError("Homologación no encontrada.")
        return mapping
