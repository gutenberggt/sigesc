"""Gate S5.2 — Relatório Mensal corta somente a métrica de conteúdo para S1/S2."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.content_reporting_monthly_s5 import (
    ContentReportingMonthlyError,
    MonthlyReportS5Db,
    _month_bounds,
    _pipeline_school_ids,
    generate_monthly_report_s5,
    get_monthly_content_record_counts_by_school,
    monthly_report_s5_db,
)
from services.content_reporting_projection import ContentReportingCutoverScope


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit=5000, **_kwargs):
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
        return FakeCursor(docs)


def test_month_bounds_exato_inclusive():
    assert _month_bounds(2026, 2) == ("2026-02-01", "2026-02-28")
    assert _month_bounds(2024, 2) == ("2024-02-01", "2024-02-29")
    with pytest.raises(ContentReportingMonthlyError):
        _month_bounds(2026, 13)


@pytest.mark.asyncio
async def test_contagem_mensal_preserva_registros_e_agrupa_por_escola(monkeypatch):
    resolver_calls = []
    projection_calls = []

    async def fake_resolver(db, **kwargs):
        resolver_calls.append(kwargs)
        first = kwargs["class_ids"][0]
        return SimpleNamespace(
            scopes=(ContentReportingCutoverScope(first, "2026-08-18", None),)
        )

    async def fake_projection(db, **kwargs):
        projection_calls.append(kwargs)
        # A métrica é record_count; não number_of_classes_sum.
        n = 3 if kwargs["class_ids"] == ["c1", "c2"] else 1
        return {
            "source_metrics": {
                "projected": {
                    "record_count": n,
                    "number_of_classes_sum": 99,
                }
            }
        }

    monkeypatch.setattr(
        "services.content_reporting_monthly_s5.resolve_content_reporting_cutover_scopes",
        fake_resolver,
    )
    monkeypatch.setattr(
        "services.content_reporting_monthly_s5.list_reporting_content_shadow",
        fake_projection,
    )

    db = SimpleNamespace(
        classes=FakeClasses([
            {"id": "c1", "school_id": "s1", "mantenedora_id": "t1", "academic_year": 2026},
            {"id": "c2", "school_id": "s1", "mantenedora_id": "t1", "academic_year": 2026},
            {"id": "c3", "school_id": "s2", "mantenedora_id": "t1", "academic_year": "2026"},
        ]),
    )

    result = await get_monthly_content_record_counts_by_school(
        db,
        tenant_id="t1",
        academic_year=2026,
        month=9,
        school_ids=["s1", "s2", "s3"],
    )

    assert result == {"s1": 3, "s2": 1, "s3": 0}
    assert len(resolver_calls) == 2
    assert all(call["reference_date"] == "2026-09-30" for call in resolver_calls)
    assert all(call["mantenedora_id"] == "t1" for call in resolver_calls)
    assert all(call["start_date"] == "2026-09-01" for call in projection_calls)
    assert all(call["end_date"] == "2026-09-30" for call in projection_calls)


@pytest.mark.asyncio
async def test_sem_turma_retorna_zero_sem_expandir_escopo(monkeypatch):
    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("S2/S1 não devem executar sem turmas autorizadas")

    monkeypatch.setattr(
        "services.content_reporting_monthly_s5.resolve_content_reporting_cutover_scopes",
        must_not_run,
    )
    monkeypatch.setattr(
        "services.content_reporting_monthly_s5.list_reporting_content_shadow",
        must_not_run,
    )
    db = SimpleNamespace(classes=FakeClasses([]))
    result = await get_monthly_content_record_counts_by_school(
        db,
        tenant_id="t1",
        academic_year=2026,
        month=9,
        school_ids=["s1"],
    )
    assert result == {"s1": 0}


@pytest.mark.asyncio
async def test_tenant_mensal_e_obrigatorio():
    db = SimpleNamespace(classes=FakeClasses([]))
    with pytest.raises(ContentReportingMonthlyError, match="Mantenedora explícita"):
        await get_monthly_content_record_counts_by_school(
            db,
            tenant_id="",
            academic_year=2026,
            month=9,
            school_ids=["s1"],
        )


def _legacy_pipeline():
    return [
        {"$match": {"date": {"$gte": "2026-09-01", "$lte": "2026-09-30"}}},
        {"$lookup": {"from": "classes"}},
        {"$unwind": {"path": "$_class"}},
        {"$match": {"_class.school_id": {"$in": ["s2", "s1"]}}},
        {"$group": {"_id": "$_class.school_id", "n": {"$sum": 1}}},
    ]


def test_pipeline_legado_e_validado_fail_closed():
    assert _pipeline_school_ids(_legacy_pipeline()) == ["s1", "s2"]
    with pytest.raises(ContentReportingMonthlyError, match="contrato de agregação"):
        _pipeline_school_ids([{"$match": {"_class.school_id": {"$in": ["s1"]}}}])


@pytest.mark.asyncio
async def test_proxy_nao_acessa_collection_learning_objects_real(monkeypatch):
    async def fake_counts(db, **kwargs):
        assert not hasattr(db, "learning_objects")
        assert kwargs["tenant_id"] == "t1"
        assert kwargs["school_ids"] == ["s1", "s2"]
        return {"s1": 4, "s2": 0}

    monkeypatch.setattr(
        "services.content_reporting_monthly_s5.get_monthly_content_record_counts_by_school",
        fake_counts,
    )
    raw_db = SimpleNamespace(classes=FakeClasses([]))
    proxy = monthly_report_s5_db(raw_db, tenant_id="t1", year=2026, month=9)
    rows = await proxy.learning_objects.aggregate(_legacy_pipeline()).to_list(2000)
    assert rows == [{"_id": "s1", "n": 4}]


@pytest.mark.asyncio
async def test_wrapper_chama_gerador_g3_com_proxy_s5(monkeypatch):
    from services import monthly_report_service as mr_svc

    seen = {}

    async def fake_generate(db, **kwargs):
        seen["db"] = db
        seen["kwargs"] = kwargs
        return {"id": "r1"}

    monkeypatch.setattr(mr_svc, "generate_monthly_report", fake_generate)
    raw_db = SimpleNamespace()
    result = await generate_monthly_report_s5(
        raw_db,
        mantenedora_id="t1",
        year=2026,
        month=9,
        user={"id": "u1"},
    )
    assert result == {"id": "r1"}
    assert isinstance(seen["db"], MonthlyReportS5Db)
    assert seen["kwargs"]["mantenedora_id"] == "t1"


def test_consumidores_operacionais_usam_wrapper_s5_e_mt1():
    router = Path("routers/monthly_reports.py").read_text(encoding="utf-8")
    scheduler = Path("services/monthly_report_scheduler.py").read_text(encoding="utf-8")

    assert "generate_monthly_report_s5(" in router
    assert "resolve_operational_tenant_context" in router
    assert "context.id" in router
    assert "generate_monthly_report_s5(" in scheduler
    assert "mr_svc.generate_monthly_report(" not in scheduler


def test_s52_nao_mexe_nas_fontes_de_frequencia_cobertura_alertas():
    source = Path("services/monthly_report_service.py").read_text(encoding="utf-8")
    assert "db.attendance.aggregate" in source
    assert "db.curriculum_coverage_stats.find" in source
    assert "db.intervention_alerts.find" in source
    # O aggregate legado permanece encapsulado atrás do proxy S5 para rollback simples.
    assert "db.learning_objects.aggregate" in source
