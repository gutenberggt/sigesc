"""Gate S5.3 — PMPI usa S1/S2 para os KPIs de Conteúdo."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.content_reporting_pmpi_s5 import (
    ContentReportingPmpiError,
    get_pmpi_content_facts,
)
from services import pmpi_compute


class Cursor:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]
        self._limit = None

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length):
        docs = self.docs[: self._limit or length]
        return [dict(d) for d in docs]

    def __aiter__(self):
        self._iter = iter(self.docs[: self._limit] if self._limit else self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class Collection:
    def __init__(self, docs=()):
        self.docs = [dict(d) for d in docs]

    def find(self, query, projection=None):
        docs = self.docs
        for key, expected in query.items():
            if key.startswith("$"):
                continue
            if isinstance(expected, dict) and "$in" in expected:
                docs = [d for d in docs if d.get(key) in expected["$in"]]
            else:
                docs = [d for d in docs if d.get(key) == expected]
        if projection:
            included = [k for k, v in projection.items() if v and k != "_id"]
            if included:
                docs = [{k: d.get(k) for k in included} for d in docs]
        return Cursor(docs)

    async def find_one(self, query, projection=None, sort=None):
        docs = await self.find(query, projection).to_list(100)
        if sort and docs:
            key, direction = sort[0]
            docs.sort(key=lambda d: d.get(key) or 0, reverse=direction < 0)
        return docs[0] if docs else None

    def aggregate(self, pipeline):
        return Cursor([])


@pytest.mark.asyncio
async def test_fatos_pmpi_usam_s2_s1_e_boundary(monkeypatch):
    calls = {}

    async def resolver(db, **kwargs):
        calls["resolver"] = kwargs
        return SimpleNamespace(scopes=[])

    async def projection(db, **kwargs):
        calls["projection"] = kwargs
        return {
            "items": [
                {
                    "id": "a",
                    "class_id": "c1",
                    "date": "2026-08-30",
                    "created_at": "2026-08-31T10:00:00+00:00",
                    "number_of_classes": 2,
                },
                {
                    "id": "b",
                    "class_id": "c1",
                    "date": "2026-09-05",
                    "created_at": "2026-09-05T11:00:00+00:00",
                    "number_of_classes": 3,
                },
            ],
            "source_metrics": {"projected": {"number_of_classes_sum": 5}},
        }

    monkeypatch.setattr(
        "services.content_reporting_pmpi_s5.resolve_content_reporting_cutover_scopes",
        resolver,
    )
    monkeypatch.setattr(
        "services.content_reporting_pmpi_s5.list_reporting_content_shadow",
        projection,
    )

    db = SimpleNamespace(
        schools=Collection([{"id": "s1", "mantenedora_id": "t1"}]),
        classes=Collection([{"id": "c1", "school_id": "s1", "mantenedora_id": "t1", "academic_year": 2026}]),
        content_entries=Collection(),
        learning_objects=Collection(),
    )
    facts = await get_pmpi_content_facts(
        db,
        school_id="s1",
        tenant_id="t1",
        days_window=30,
        now=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
    )

    assert facts["record_count_window"] == 2
    assert facts["number_of_classes_sum_year"] == 5
    assert facts["delay_fully_comparable"] is True
    assert facts["delay_sample_count"] == 2
    assert calls["resolver"]["mantenedora_id"] == "t1"
    assert calls["resolver"]["class_ids"] == ["c1"]
    assert calls["projection"]["start_date"] == "2026-01-01"
    assert calls["projection"]["end_date"] == "2026-09-07"


@pytest.mark.asyncio
async def test_tenant_ambiguo_falha_fechado():
    db = SimpleNamespace(
        schools=Collection([
            {"id": "s1", "mantenedora_id": "t1"},
            {"id": "s1", "mantenedora_id": "t2"},
        ]),
        classes=Collection(),
        content_entries=Collection(),
        learning_objects=Collection(),
    )
    with pytest.raises(ContentReportingPmpiError) as exc:
        await get_pmpi_content_facts(db, school_id="s1")
    assert exc.value.code == "CONTENT_REPORTING_PMPI_TENANT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_pmpi_atraso_incomparavel_vira_sem_dados(monkeypatch):
    async def fake_facts(*args, **kwargs):
        return {
            "record_count_window": 4,
            "number_of_classes_sum_year": 20,
            "delay_average_days": 1.5,
            "delay_sample_count": 3,
            "delay_incomparable_count": 1,
            "delay_fully_comparable": False,
        }

    async def fake_classes(*args, **kwargs):
        return ["c1"]

    async def fake_count(*args, **kwargs):
        return 0

    monkeypatch.setattr(pmpi_compute, "get_pmpi_content_facts", fake_facts)
    monkeypatch.setattr(pmpi_compute, "_get_class_ids", fake_classes)
    monkeypatch.setattr(pmpi_compute, "_count_with_fallback", fake_count)

    classes = Collection([{"id": "c1", "school_id": "s1", "academic_year": 2026}])
    courses = Collection([])
    attendance = Collection([])
    db = SimpleNamespace(classes=classes, courses=courses, attendance=attendance)
    db.__getitem__ = lambda self, key: getattr(self, key)

    # pmpi_compute usa current_db[coll]; wrapper simples com __getitem__ real.
    class Db(SimpleNamespace):
        def __getitem__(self, key):
            return getattr(self, key)

    db = Db(classes=classes, courses=courses, attendance=attendance, enrollments=Collection(), grades=Collection())
    result = await pmpi_compute.compute_kpis_for_school(db, "s1", tenant_id="t1")

    assert result["aulas_lancadas"]["detail"]["source"] == "content_reporting_s1_s2"
    assert result["atrasos_dias"]["value"] is None
    assert result["atrasos_dias"]["detail"]["provenance_incomparable"] is True
    assert result["carga_horaria"]["detail"]["source"] == "content_reporting_s1_s2"


def test_calculos_operacionais_pmpi_nao_leem_learning_objects_diretamente():
    shared = Path("services/pmpi_compute.py").read_text(encoding="utf-8")
    router = Path("routers/pmpi.py").read_text(encoding="utf-8")

    assert "current_db.learning_objects" not in shared
    assert '"learning_objects"' not in shared
    helper_start = router.index("async def _compute_kpis_for_school")
    overview_start = router.index('@router.get("/overview")')
    helper = router[helper_start:overview_start]
    assert "learning_objects" not in helper
    assert "compute_kpis_for_school(" in helper
    assert "tenant_filter_base.get(\"mantenedora_id\")" in helper


def test_diag_legado_e_explicitamente_separado_do_kpi():
    router = Path("routers/pmpi.py").read_text(encoding="utf-8")
    diag_start = router.index('@router.get("/_diag/{school_id}")')
    diag = router[diag_start:]
    assert "diagnóstico legado" in diag.lower()
    assert "KPIs usam S1/S2" in diag
