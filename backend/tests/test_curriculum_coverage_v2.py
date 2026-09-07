from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from routers import curriculum_coverage_v2 as coverage


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend" / "routers" / "curriculum_coverage_v2.py"
ROUTERS_INIT = ROOT / "backend" / "routers" / "__init__.py"


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs if length is None else self.docs[:length])


class FakeCollection:
    def __init__(self, docs=None, *, count_override=None):
        self.docs = list(docs or [])
        self.count_override = count_override

    async def find_one(self, query, projection=None, sort=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return FakeCursor([dict(doc) for doc in self.docs if _matches(doc, query)])

    async def count_documents(self, query):
        if self.count_override is not None:
            return self.count_override
        return len([doc for doc in self.docs if _matches(doc, query)])


def _matches(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


def _db(*, plans, entries, legacy_count=0):
    return SimpleNamespace(
        permission_overrides=FakeCollection([]),
        calendario_letivo=FakeCollection([
            {
                "ano_letivo": 2026,
                "mantenedora_id": "tenant-1",
                "bimestre_1_inicio": "2026-02-01",
                "bimestre_1_fim": "2026-04-15",
                "bimestre_2_inicio": "2026-04-16",
                "bimestre_2_fim": "2026-06-30",
                "bimestre_3_inicio": "2026-08-01",
                "bimestre_3_fim": "2026-10-15",
                "bimestre_4_inicio": "2026-10-16",
                "bimestre_4_fim": "2026-12-20",
            }
        ]),
        curriculum_versions=FakeCollection([
            {
                "id": "version-1",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "revision": 2,
                "status": "published",
            }
        ]),
        classes=FakeCollection([
            {
                "id": "class-1",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "grade_level": "6º ANO",
            }
        ]),
        teaching_plans=FakeCollection(plans),
        content_entries=FakeCollection(entries),
        learning_objects=FakeCollection([], count_override=legacy_count),
        curriculum_components=FakeCollection([
            {"id": "component-1", "codigo": "ING", "nome": "Língua Inglesa"}
        ]),
    )


def _plan():
    return {
        "id": "plan-1",
        "mantenedora_id": "tenant-1",
        "curriculum_version_id": "version-1",
        "academic_year": 2026,
        "component_id": "component-1",
        "bimestre": 3,
        "grade_scope": ["6º ANO"],
        "revision": 4,
        "status": "published",
        "items": [
            {
                "id": "item-1",
                "adaptation_id": "adapt-1",
                "skill_code_snapshot": "EF06LI01",
                "skill_description_snapshot": "Habilidade 1",
            },
            {
                "id": "item-2",
                "adaptation_id": "adapt-2",
                "skill_code_snapshot": "EF06LI02",
                "skill_description_snapshot": "Habilidade 2",
            },
        ],
    }


def _request():
    return SimpleNamespace(headers={}, state=SimpleNamespace())


def test_source_contract_uses_plan_as_denominator_and_content_entries_as_numerator():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'db.teaching_plans.find(' in source
    assert 'db.content_entries.find(' in source
    assert 'db.learning_objects.count_documents' in source
    assert 'db.learning_objects.find(' not in source
    assert '"pct": None' in source
    assert '"coverage_state": "plano_inexistente"' in source
    assert '"trabalhado_fora_plano"' in source
    assert '"historico_nao_estruturado"' in source


def test_bootstrap_installs_f5_without_replacing_legacy_coverage():
    source = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "from .curriculum_coverage_v2 import install_curriculum_coverage_v2_setup" in source
    assert "install_curriculum_core_setup(_curriculum_v2_mod)" in source
    assert "install_curriculum_coverage_v2_setup(_curriculum_v2_mod)" in source
    service = SERVICE.read_text(encoding="utf-8")
    assert '@router.get("/coverage-v2")' in service
    assert 'original_setup = curriculum_v2_mod.setup_router' in service


@pytest.mark.asyncio
async def test_class_coverage_counts_only_structured_links_and_keeps_history_separate(monkeypatch):
    monkeypatch.setattr(coverage, "get_mantenedora_scope", lambda user, request: "tenant-1")
    monkeypatch.setattr(coverage, "assert_same_tenant", lambda doc, user, request: None)
    db = _db(
        plans=[_plan()],
        entries=[
            {
                "id": "entry-covered",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "class_id": "class-1",
                "component_id": "component-1",
                "date": "2026-09-07",
                "deleted": False,
                "curriculum_binding": {"bimestre": 3},
                "curriculum_links": {
                    "adaptation_ids": ["adapt-1"],
                    "teaching_plan_item_ids": ["item-1"],
                },
            },
            {
                "id": "entry-outside",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "class_id": "class-1",
                "component_id": "component-1",
                "date": "2026-09-08",
                "deleted": False,
                "curriculum_binding": {"bimestre": 3},
                "curriculum_links": {"adaptation_ids": ["adapt-outside"]},
            },
            {
                "id": "entry-history",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "class_id": "class-1",
                "component_id": "component-1",
                "date": "2026-09-09",
                "deleted": False,
            },
        ],
        legacy_count=2,
    )

    result = await coverage.calculate_curriculum_coverage_v2(
        db,
        {"id": "user-1", "role": "coordenador", "mantenedora_id": "tenant-1"},
        _request(),
        class_id="class-1",
        academic_year=2026,
        component_id="component-1",
        today_ymd="2026-09-07",
    )

    assert result["version"] == "coverage_v2"
    assert result["coverage_state"] == "ok"
    assert result["curriculum_version_id"] == "version-1"
    assert result["totals"]["total"] == 2
    assert result["totals"]["covered"] == 1
    assert result["totals"]["pct"] == 50.0
    assert result["totals"]["pending_count"] == 1
    assert result["totals"]["worked_outside_plan_count"] == 1
    assert result["totals"]["historical_unstructured_count"] == 3
    assert result["classification_counts"]["previsto_trabalhado"] == 1
    assert result["classification_counts"]["previsto_pendente"] == 1
    row = result["rows"][0]
    assert row["teaching_plan_id"] == "plan-1"
    assert row["pending"][0]["plan_item_id"] == "item-2"
    assert row["worked_outside_plan"] == ["adapt-outside"]


@pytest.mark.asyncio
async def test_missing_plan_never_fabricates_percentage(monkeypatch):
    monkeypatch.setattr(coverage, "get_mantenedora_scope", lambda user, request: "tenant-1")
    monkeypatch.setattr(coverage, "assert_same_tenant", lambda doc, user, request: None)
    db = _db(
        plans=[],
        entries=[
            {
                "id": "entry-structured",
                "mantenedora_id": "tenant-1",
                "academic_year": 2026,
                "class_id": "class-1",
                "component_id": "component-1",
                "date": "2026-09-07",
                "deleted": False,
                "curriculum_binding": {"bimestre": 3},
                "curriculum_links": {"adaptation_ids": ["adapt-1"]},
            }
        ],
        legacy_count=1,
    )

    result = await coverage.calculate_curriculum_coverage_v2(
        db,
        {"id": "user-1", "role": "coordenador", "mantenedora_id": "tenant-1"},
        _request(),
        class_id="class-1",
        academic_year=2026,
        component_id="component-1",
        today_ymd="2026-09-07",
    )

    assert result["coverage_state"] == "plano_inexistente"
    assert result["totals"]["pct"] is None
    assert result["totals"]["percentage_available"] is False
    assert result["totals"]["plan_missing"] is True
    assert result["classification_counts"]["plano_inexistente"] == 1
    assert result["classification_counts"]["trabalhado_fora_plano"] == 1
