"""Guard de convivência entre versões anuais legadas e versões escopadas.

O publicador anual histórico supersede versões publicadas do mesmo ano. Após a
introdução de ``component_grade_bimester``, esse update não pode atingir as
versões escopadas. Em vez de duplicar o endpoint, este proxy estreito endurece
somente o ``update_many`` com a assinatura exata da supersessão anual.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Mapping


ANNUAL_SCOPE_CLAUSE = {
    "$or": [
        {"scope_kind": {"$exists": False}},
        {"scope_kind": None},
        {"scope_kind": "annual"},
    ]
}


def _is_annual_supersession_query(query: Mapping[str, Any]) -> bool:
    q = dict(query or {})
    return bool(
        q.get("mantenedora_id")
        and q.get("academic_year") is not None
        and q.get("status") == "published"
        and isinstance(q.get("id"), Mapping)
        and "$ne" in q["id"]
        and "scope_kind" not in q
    )


def _guard_annual_supersession_query(query: Mapping[str, Any]) -> dict[str, Any]:
    q = dict(query or {})
    if not _is_annual_supersession_query(q):
        return q
    return {"$and": [q, ANNUAL_SCOPE_CLAUSE]}


class _CurriculumVersionsGuardCollection:
    def __init__(self, inner):
        self._inner = inner

    async def update_many(self, query, update, *args, **kwargs):
        return await self._inner.update_many(
            _guard_annual_supersession_query(query), update, *args, **kwargs
        )

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _CurriculumAnnualGuardDb:
    def __init__(self, inner):
        self._inner = inner
        self.curriculum_versions = _CurriculumVersionsGuardCollection(inner.curriculum_versions)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def install_scoped_annual_publish_guard(curriculum_v2_mod: Any) -> None:
    if getattr(curriculum_v2_mod, "_scoped_annual_publish_guard_installed", False):
        return
    original_setup = curriculum_v2_mod.setup_router

    @wraps(original_setup)
    def setup_router(db):
        return original_setup(_CurriculumAnnualGuardDb(db))

    curriculum_v2_mod.setup_router = setup_router
    curriculum_v2_mod._scoped_annual_publish_guard_installed = True
