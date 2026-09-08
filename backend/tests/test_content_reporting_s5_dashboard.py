"""Gate S5.1 — Dashboard de Diários consome o read model institucional."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.content_reporting_dashboard_s5 import (
    _format_dashboard_stats,
    _reference_date_for_year,
    get_diary_dashboard_content_stats,
)
from services.content_reporting_projection import ContentReportingCutoverScope


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


class FakeClasses:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.calls = []

    def find(self, query, projection=None):
        self.calls.append((query, projection))
        docs = self.docs
        for key, expected in query.items():
            if isinstance(expected, dict) and "$in" in expected:
                docs = [doc for doc in docs if doc.get(key) in expected["$in"]]
            else:
                docs = [doc for doc in docs if doc.get(key) == expected]
        if projection:
            include = [key for key, enabled in projection.items() if enabled and key != "_id"]
            if include:
                docs = [{key: doc.get(key) for key in include} for doc in docs]
        return FakeCursor(docs)


def test_formatacao_preserva_payload_historico_do_dashboard():
    payload = _format_dashboard_stats(
        {
            "record_count": 9,
            "monthly_record_count": {"2026-02": 3, "2026-09": 6},
            "monthly_number_of_classes_sum": {"2026-02": 4, "2026-09": 8},
        }
    )
    assert payload == {
        "completion_rate": 4,
        "total_records": 9,
        "by_month": [
            {"month": "Fev", "registros": 3, "aulas": 4},
            {"month": "Set", "registros": 6, "aulas": 8},
        ],
    }


def test_reference_date_nao_projeta_cutover_futuro_no_ano_corrente():
    today = date(2026, 9, 7)
    assert _reference_date_for_year(2025, today) == "2025-12-31"
    assert _reference_date_for_year(2026, today) == "2026-09-07"
    assert _reference_date_for_year(2027, today) == "2027-01-01"


@pytest.mark.asyncio
async def test_dashboard_usa_resolver_s2_e_projecao_s1(monkeypatch):
    calls = {}

    async def fake_resolver(db, **kwargs):
        calls["resolver"] = kwargs
        return SimpleNamespace(
            scopes=[ContentReportingCutoverScope("class-a", "2026-08-18", "comp-a")]
        )

    async def fake_projection(db, **kwargs):
        calls["projection"] = kwargs
        return {
            "source_metrics": {
                "projected": {
                    "record_count": 2,
                    "monthly_record_count": {"2026-09": 2},
                    "monthly_number_of_classes_sum": {"2026-09": 3},
                }
            }
        }

    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.resolve_content_reporting_cutover_scopes",
        fake_resolver,
    )
    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.list_reporting_content_shadow",
        fake_projection,
    )

    db = SimpleNamespace(classes=FakeClasses([]))
    result = await get_diary_dashboard_content_stats(
        db,
        tenant_id="tenant-a",
        academic_year=2026,
        course_id="comp-a",
        reference_date="2026-09-07",
    )

    assert result["total_records"] == 2
    assert result["by_month"] == [{"month": "Set", "registros": 2, "aulas": 3}]
    assert calls["resolver"]["mantenedora_id"] == "tenant-a"
    assert calls["resolver"]["reference_date"] == "2026-09-07"
    assert calls["projection"]["mantenedora_id"] == "tenant-a"
    assert calls["projection"]["component_ids"] == ["comp-a"]
    assert calls["projection"]["start_date"] == "2026-01-01"
    assert calls["projection"]["end_date"] == "2026-12-31"
    assert len(calls["projection"]["cutover_scopes"]) == 1


@pytest.mark.asyncio
async def test_filtro_escola_turma_e_ancorado_no_tenant(monkeypatch):
    calls = {}

    async def fake_resolver(db, **kwargs):
        calls["resolver"] = kwargs
        return SimpleNamespace(scopes=[])

    async def fake_projection(db, **kwargs):
        calls["projection"] = kwargs
        return {
            "source_metrics": {
                "projected": {
                    "record_count": 1,
                    "monthly_record_count": {"2026-03": 1},
                    "monthly_number_of_classes_sum": {"2026-03": 1},
                }
            }
        }

    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.resolve_content_reporting_cutover_scopes",
        fake_resolver,
    )
    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.list_reporting_content_shadow",
        fake_projection,
    )

    classes = FakeClasses(
        [
            {"id": "class-a", "school_id": "school-a", "mantenedora_id": "tenant-a", "academic_year": 2026},
            {"id": "class-b", "school_id": "school-b", "mantenedora_id": "tenant-a", "academic_year": 2026},
            {"id": "class-x", "school_id": "school-a", "mantenedora_id": "tenant-x", "academic_year": 2026},
        ]
    )
    db = SimpleNamespace(classes=classes)
    result = await get_diary_dashboard_content_stats(
        db,
        tenant_id="tenant-a",
        academic_year=2026,
        school_id="school-a",
        class_id="class-a",
        reference_date="2026-09-07",
    )

    assert result["total_records"] == 1
    query, _projection = classes.calls[0]
    assert query["mantenedora_id"] == "tenant-a"
    assert query["school_id"] == "school-a"
    assert query["id"] == "class-a"
    assert calls["resolver"]["class_ids"] == ["class-a"]
    assert calls["projection"]["class_ids"] == ["class-a"]


@pytest.mark.asyncio
async def test_escopo_filtrado_sem_turma_retorna_zero_sem_expandir_para_tenant(monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("resolver/projection não deve executar com filtro vazio")

    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.resolve_content_reporting_cutover_scopes",
        must_not_run,
    )
    monkeypatch.setattr(
        "services.content_reporting_dashboard_s5.list_reporting_content_shadow",
        must_not_run,
    )

    db = SimpleNamespace(classes=FakeClasses([]))
    result = await get_diary_dashboard_content_stats(
        db,
        tenant_id="tenant-a",
        academic_year=2026,
        school_id="school-sem-turma",
        reference_date="2026-09-07",
    )
    assert result == {"completion_rate": 0, "total_records": 0, "by_month": []}


def test_router_content_nao_le_learning_objects_diretamente():
    source = Path("routers/diary_dashboard.py").read_text(encoding="utf-8")
    start = source.index('@router.get("/content")')
    end = source.index('@router.get("/courses-by-class/{class_id}")')
    block = source[start:end]

    assert "db.learning_objects" not in block
    assert "get_diary_dashboard_content_stats" in block
    assert "get_mantenedora_scope" in block
    assert 'status_code=403' in block


def test_s5_1_nao_remove_compatibilidade_legada_do_read_model():
    projection = Path("services/content_reporting_projection.py").read_text(encoding="utf-8")
    assert "db.learning_objects.find" in projection
    assert "legacy_excluded_post_cutover" in projection
