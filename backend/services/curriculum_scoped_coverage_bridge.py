"""Ponte de compatibilidade da Cobertura F5 para versões curriculares escopadas.

A F5 original foi desenhada quando havia uma única ``curriculum_version``
publicada por mantenedora/ano. A evolução por componente+série+bimestre permite
várias versões publicadas simultaneamente. Este bridge mantém o algoritmo F5
intacto e altera somente a seleção dos Planos de Ensino elegíveis.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Mapping, Optional

from tenant_scope import get_mantenedora_scope


VIRTUAL_VERSION_ID = "__SCOPED_CURRICULUM_VIRTUAL__"
SCOPED_KIND = "component_grade_bimester"


def _norm(value: Any) -> str:
    return str(value or "").strip()


class _VersionCollectionProxy:
    def __init__(self, inner, *, tenant_id: str, academic_year: int, allowed_version_ids: list[str], max_revision: int):
        self._inner = inner
        self._tenant_id = tenant_id
        self._academic_year = academic_year
        self._allowed_version_ids = allowed_version_ids
        self._max_revision = max_revision

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
                "revision": self._max_revision,
                "scope_kind": "virtual_multi_scope",
                "source_version_ids": list(self._allowed_version_ids),
            }
        return await self._inner.find_one(query, projection, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _TeachingPlanCollectionProxy:
    def __init__(self, inner, *, allowed_version_ids: list[str]):
        self._inner = inner
        self._allowed_version_ids = allowed_version_ids

    def find(self, query, projection=None, *args, **kwargs):
        q = dict(query or {})
        if q.get("curriculum_version_id") == VIRTUAL_VERSION_ID:
            q["curriculum_version_id"] = {"$in": list(self._allowed_version_ids)}
        return self._inner.find(q, projection, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CoverageDbProxy:
    def __init__(self, inner, *, tenant_id: str, academic_year: int, allowed_version_ids: list[str], max_revision: int):
        self._inner = inner
        self.curriculum_versions = _VersionCollectionProxy(
            inner.curriculum_versions,
            tenant_id=tenant_id,
            academic_year=academic_year,
            allowed_version_ids=allowed_version_ids,
            max_revision=max_revision,
        )
        self.teaching_plans = _TeachingPlanCollectionProxy(
            inner.teaching_plans,
            allowed_version_ids=allowed_version_ids,
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


async def _published_version_set(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    component_id: Optional[str],
) -> list[dict[str, Any]]:
    scoped_query: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "academic_year": academic_year,
        "status": "published",
        "scope_kind": SCOPED_KIND,
    }
    if component_id:
        scoped_query["component_id"] = component_id
    scoped = await db.curriculum_versions.find(scoped_query, {"_id": 0, "id": 1, "revision": 1}).to_list(length=5000)
    if not scoped:
        return []

    # Durante a migração, planos ainda ligados à versão anual publicada continuam
    # elegíveis para componentes que ainda não receberam versão escopada.
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
        {"_id": 0, "id": 1, "revision": 1},
    ).to_list(length=100)
    return [*scoped, *annual]


async def _restore_actual_version_ids(db, result: dict[str, Any], version_docs: list[dict[str, Any]]) -> dict[str, Any]:
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
        actual_ids = [_norm(doc.get("id")) for doc in version_docs if _norm(doc.get("id"))]
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
        tenant_id = get_mantenedora_scope(current_user, request)
        year = await _year_for_request(db, class_id=class_id, academic_year=academic_year)
        versions = await _published_version_set(
            db,
            tenant_id=_norm(tenant_id),
            academic_year=year,
            component_id=component_id,
        )
        if not versions:
            return await original(
                db,
                current_user,
                request,
                class_id=class_id,
                academic_year=academic_year,
                component_id=component_id,
                today_ymd=today_ymd,
            )

        allowed_ids = list(dict.fromkeys(_norm(doc.get("id")) for doc in versions if _norm(doc.get("id"))))
        proxy = _CoverageDbProxy(
            db,
            tenant_id=_norm(tenant_id),
            academic_year=year,
            allowed_version_ids=allowed_ids,
            max_revision=max(int(doc.get("revision") or 0) for doc in versions),
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
        return await _restore_actual_version_ids(db, result, versions)

    coverage_mod.calculate_curriculum_coverage_v2 = calculate_curriculum_coverage_v2
    coverage_mod._scoped_curriculum_versions_bridge_installed = True
