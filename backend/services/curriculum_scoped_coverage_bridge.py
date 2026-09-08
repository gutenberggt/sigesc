"""Ponte de compatibilidade da Cobertura F5 para versões curriculares escopadas.

A F5 original foi desenhada quando havia uma única ``curriculum_version``
publicada por mantenedora/ano. A evolução por componente+série+bimestre permite
várias versões publicadas simultaneamente.

Regra de transição:
- se ainda não existe versão escopada aplicável, F5 permanece byte a byte no
  comportamento anual;
- quando existe versão escopada publicada, seus Planos de Ensino têm precedência
  SOMENTE no mesmo componente + bimestre + série;
- o plano anual continua elegível nos demais escopos ainda não migrados.

Assim não há denominador duplicado durante a migração gradual.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Mapping, Optional

from tenant_scope import get_mantenedora_scope


VIRTUAL_VERSION_ID = "__SCOPED_CURRICULUM_VIRTUAL__"
SCOPED_KIND = "component_grade_bimester"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _ids(docs: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(_norm(doc.get("id")) for doc in docs if _norm(doc.get("id"))))


def _scoped_scope_matchers(scoped_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Escopos nos quais o plano anual deve ceder lugar ao escopado."""
    matchers: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for doc in scoped_docs:
        component_id = _norm(doc.get("component_id"))
        try:
            bimestre = int(doc.get("bimestre") or 0)
        except (TypeError, ValueError):
            bimestre = 0
        grades = [_norm(item) for item in (doc.get("grade_scope") or []) if _norm(item)]
        if not component_id or bimestre not in (1, 2, 3, 4):
            continue
        if not grades:
            key = (component_id, bimestre, "")
            if key not in seen:
                seen.add(key)
                matchers.append({"component_id": component_id, "bimestre": bimestre})
            continue
        for grade in grades:
            key = (component_id, bimestre, grade)
            if key in seen:
                continue
            seen.add(key)
            # Mongo casa igualdade escalar contra elemento de array em grade_scope.
            matchers.append(
                {"component_id": component_id, "bimestre": bimestre, "grade_scope": grade}
            )
    return matchers


def _rewrite_virtual_plan_query(
    query: Mapping[str, Any],
    *,
    scoped_docs: list[dict[str, Any]],
    annual_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reescreve apenas a seleção da versão, preservando os demais filtros F5."""
    q = dict(query or {})
    if q.get("curriculum_version_id") != VIRTUAL_VERSION_ID:
        return q

    q.pop("curriculum_version_id", None)
    scoped_ids = _ids(scoped_docs)
    annual_ids = _ids(annual_docs)
    branches: list[dict[str, Any]] = []

    if scoped_ids:
        branches.append({"curriculum_version_id": {"$in": scoped_ids}})

    if annual_ids:
        annual_clause: dict[str, Any] = {"curriculum_version_id": {"$in": annual_ids}}
        matchers = _scoped_scope_matchers(scoped_docs)
        if matchers:
            branches.append({"$and": [annual_clause, {"$nor": matchers}]})
        else:
            branches.append(annual_clause)

    if not branches:
        version_clause: dict[str, Any] = {"curriculum_version_id": {"$in": []}}
    elif len(branches) == 1:
        version_clause = branches[0]
    else:
        version_clause = {"$or": branches}

    return {"$and": [q, version_clause]}


class _VersionCollectionProxy:
    def __init__(self, inner, *, tenant_id: str, academic_year: int, version_docs: list[dict[str, Any]]):
        self._inner = inner
        self._tenant_id = tenant_id
        self._academic_year = academic_year
        self._version_docs = version_docs

    async def find_one(self, query, projection=None, *args, **kwargs):
        q = dict(query or {})
        if (
            q.get("mantenedora_id") == self._tenant_id
            and int(q.get("academic_year") or 0) == self._academic_year
            and q.get("status") == "published"
            and "id" not in q
        ):
            return {
                "id": VIRTUAL_VERSION_ID,
                "mantenedora_id": self._tenant_id,
                "academic_year": self._academic_year,
                "status": "published",
                "revision": max(int(doc.get("revision") or 0) for doc in self._version_docs),
                "scope_kind": "virtual_multi_scope",
                "source_version_ids": _ids(self._version_docs),
            }
        return await self._inner.find_one(query, projection, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _TeachingPlanCollectionProxy:
    def __init__(self, inner, *, scoped_docs: list[dict[str, Any]], annual_docs: list[dict[str, Any]]):
        self._inner = inner
        self._scoped_docs = scoped_docs
        self._annual_docs = annual_docs

    def find(self, query, projection=None, *args, **kwargs):
        rewritten = _rewrite_virtual_plan_query(
            query,
            scoped_docs=self._scoped_docs,
            annual_docs=self._annual_docs,
        )
        return self._inner.find(rewritten, projection, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CoverageDbProxy:
    def __init__(
        self,
        inner,
        *,
        tenant_id: str,
        academic_year: int,
        scoped_docs: list[dict[str, Any]],
        annual_docs: list[dict[str, Any]],
    ):
        self._inner = inner
        version_docs = [*scoped_docs, *annual_docs]
        self.curriculum_versions = _VersionCollectionProxy(
            inner.curriculum_versions,
            tenant_id=tenant_id,
            academic_year=academic_year,
            version_docs=version_docs,
        )
        self.teaching_plans = _TeachingPlanCollectionProxy(
            inner.teaching_plans,
            scoped_docs=scoped_docs,
            annual_docs=annual_docs,
        )

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


async def _year_for_request(db, *, class_id: Optional[str], academic_year: Optional[int]) -> int:
    if academic_year is not None:
        return int(academic_year)
    if class_id:
        doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "academic_year": 1})
        if doc and doc.get("academic_year") is not None:
            return int(doc["academic_year"])
    from datetime import date

    return date.today().year


async def _published_version_sets(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    component_id: Optional[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scoped_query: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "academic_year": academic_year,
        "status": "published",
        "scope_kind": SCOPED_KIND,
    }
    if component_id:
        scoped_query["component_id"] = component_id
    scoped = await db.curriculum_versions.find(
        scoped_query,
        {
            "_id": 0,
            "id": 1,
            "revision": 1,
            "component_id": 1,
            "bimestre": 1,
            "grade_scope": 1,
            "scope_kind": 1,
        },
    ).to_list(length=5000)
    if not scoped:
        return [], []

    annual = await db.curriculum_versions.find(
        {
            "mantenedora_id": tenant_id,
            "academic_year": academic_year,
            "status": "published",
            "$or": [
                {"scope_kind": {"$exists": False}},
                {"scope_kind": None},
                {"scope_kind": "annual"},
            ],
        },
        {"_id": 0, "id": 1, "revision": 1, "scope_kind": 1},
    ).to_list(length=100)
    return scoped, annual


async def _restore_actual_version_ids(
    db,
    result: dict[str, Any],
    version_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = list(result.get("rows") or [])
    plan_ids = [_norm(row.get("teaching_plan_id")) for row in rows if _norm(row.get("teaching_plan_id"))]
    plan_map: dict[str, dict[str, Any]] = {}
    if plan_ids:
        plans = await db.teaching_plans.find(
            {"id": {"$in": list(dict.fromkeys(plan_ids))}},
            {"_id": 0, "id": 1, "curriculum_version_id": 1},
        ).to_list(length=len(plan_ids))
        plan_map = {doc["id"]: doc for doc in plans}

    actual_ids: list[str] = []
    for row in rows:
        plan = plan_map.get(_norm(row.get("teaching_plan_id"))) or {}
        version_id = _norm(plan.get("curriculum_version_id"))
        row["curriculum_version_id"] = version_id or None
        if version_id:
            actual_ids.append(version_id)
    result["rows"] = rows

    if not actual_ids and result.get("coverage_state") == "plano_inexistente":
        actual_ids = _ids(version_docs)
    unique_ids = list(dict.fromkeys(actual_ids))
    result["curriculum_version_ids"] = unique_ids
    result["curriculum_version_id"] = unique_ids[0] if len(unique_ids) == 1 else None
    if result.get("curriculum_version_id") is None:
        result.pop("curriculum_version_revision", None)
    elif len(unique_ids) == 1:
        version = next((doc for doc in version_docs if doc.get("id") == unique_ids[0]), None)
        if version:
            result["curriculum_version_revision"] = version.get("revision")
    return result


def install_scoped_curriculum_coverage_bridge(coverage_mod: Any) -> None:
    # O servidor monta curriculum_import antes de curriculum_v2. Aproveitamos
    # essa ordem homologada para proteger também a publicação anual legada antes
    # de o router curricular canônico capturar o DB.
    from routers import curriculum_v2 as curriculum_v2_mod
    from services.curriculum_scoped_annual_guard import install_scoped_annual_publish_guard

    install_scoped_annual_publish_guard(curriculum_v2_mod)

    if getattr(coverage_mod, "_scoped_curriculum_versions_bridge_installed", False):
        return
    original = coverage_mod.calculate_curriculum_coverage_v2

    @wraps(original)
    async def calculate_curriculum_coverage_v2(
        db,
        current_user: Mapping[str, Any],
        request,
        *,
        class_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        component_id: Optional[str] = None,
        today_ymd: Optional[str] = None,
    ):
        tenant_id = _norm(get_mantenedora_scope(current_user, request))
        year = await _year_for_request(db, class_id=class_id, academic_year=academic_year)
        scoped_docs, annual_docs = await _published_version_sets(
            db,
            tenant_id=tenant_id,
            academic_year=year,
            component_id=component_id,
        )
        if not scoped_docs:
            return await original(
                db,
                current_user,
                request,
                class_id=class_id,
                academic_year=academic_year,
                component_id=component_id,
                today_ymd=today_ymd,
            )

        version_docs = [*scoped_docs, *annual_docs]
        proxy = _CoverageDbProxy(
            db,
            tenant_id=tenant_id,
            academic_year=year,
            scoped_docs=scoped_docs,
            annual_docs=annual_docs,
        )
        result = await original(
            proxy,
            current_user,
            request,
            class_id=class_id,
            academic_year=academic_year,
            component_id=component_id,
            today_ymd=today_ymd,
        )
        return await _restore_actual_version_ids(db, result, version_docs)

    coverage_mod.calculate_curriculum_coverage_v2 = calculate_curriculum_coverage_v2
    coverage_mod._scoped_curriculum_versions_bridge_installed = True
