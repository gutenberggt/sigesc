"""Gate S5.4 — Analytics usa S1/S2 sem reescrever o router legado."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.content_reporting_analytics_s5 import (
    ContentReportingAnalyticsDb,
    ContentReportingAnalyticsError,
    execute_analytics_content_pipeline,
    install_content_reporting_analytics_setup,
)


class Cursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, length=None):
        rows = self.docs if length is None else self.docs[:length]
        return [dict(doc) for doc in rows]

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class Collection:
    def __init__(self, docs=()):
        self.docs = [dict(doc) for doc in docs]

    def find(self, query, projection=None):
        docs = list(self.docs)
        for key, expected in query.items():
            if isinstance(expected, dict) and "$in" in expected:
                docs = [doc for doc in docs if doc.get(key) in expected["$in"]]
            else:
                docs = [doc for doc in docs if doc.get(key) == expected]
        if projection:
            included = [key for key, value in projection.items() if value and key != "_id"]
            if included:
                docs = [{key: doc.get(key) for key in included} for doc in docs]
        return Cursor(docs)


class Db(SimpleNamespace):
    def __getitem__(self, key):
        return getattr(self, key)


def _db():
    return Db(
        classes=Collection([
            {"id": "c1", "mantenedora_id": "t1", "academic_year": 2026},
            {"id": "c2", "mantenedora_id": "t1", "academic_year": "2026"},
        ]),
        teacher_class_assignments=Collection(),
        content_entries=Collection(),
        learning_objects=Collection(),
        schools=Collection(),
    )


async def _stub_projection(monkeypatch, items):
    async def resolver(db, **kwargs):
        return SimpleNamespace(scopes=[])

    async def projection(db, **kwargs):
        return {"items": [dict(item) for item in items], "source_metrics": {"projected": {}}}

    monkeypatch.setattr(
        "services.content_reporting_analytics_s5.resolve_content_reporting_cutover_scopes",
        resolver,
    )
    monkeypatch.setattr(
        "services.content_reporting_analytics_s5.list_reporting_content_shadow",
        projection,
    )


@pytest.mark.asyncio
async def test_ranking_preserva_soma_number_of_classes_por_turma(monkeypatch):
    await _stub_projection(monkeypatch, [
        {"class_id": "c1", "component_id": "p", "date": "2026-03-01", "number_of_classes": 2},
        {"class_id": "c1", "component_id": "m", "date": "2026-03-02", "number_of_classes": 3},
        {"class_id": "c2", "component_id": "p", "date": "2026-03-01", "number_of_classes": 1},
    ])
    pipeline = [
        {"$match": {"class_id": {"$in": ["c1", "c2"]}, "academic_year": {"$in": ["2026", 2026]}}},
        {"$group": {"_id": "$class_id", "count": {"$sum": "$number_of_classes"}}},
    ]
    rows = await execute_analytics_content_pipeline(
        _db(), pipeline, now=datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    )
    assert rows == [{"_id": "c1", "count": 5}, {"_id": "c2", "count": 1}]


@pytest.mark.asyncio
async def test_desempenho_regencia_preserva_datas_unicas_por_turma(monkeypatch):
    await _stub_projection(monkeypatch, [
        {"class_id": "c1", "component_id": None, "date": "2026-08-10", "number_of_classes": 1},
        {"class_id": "c1", "component_id": None, "date": "2026-08-10", "number_of_classes": 1},
        {"class_id": "c1", "component_id": None, "date": "2026-08-11", "number_of_classes": 1},
    ])
    pipeline = [
        {"$match": {"class_id": {"$in": ["c1"]}, "academic_year": {"$in": ["2026", 2026]}, "date": {"$lte": "2026-09-07"}}},
        {"$group": {"_id": "$class_id", "dates": {"$addToSet": "$date"}}},
    ]
    rows = await execute_analytics_content_pipeline(_db(), pipeline)
    assert rows == [{"_id": "c1", "dates": ["2026-08-10", "2026-08-11"]}]


@pytest.mark.asyncio
async def test_desempenho_por_componente_preserva_course_id_compat(monkeypatch):
    await _stub_projection(monkeypatch, [
        {"class_id": "c1", "component_id": "ing", "date": "2026-08-20", "number_of_classes": 1},
        {"class_id": "c1", "course_id": "ing", "date": "2026-08-21", "number_of_classes": 1},
        {"class_id": "c1", "component_id": "mat", "date": "2026-08-22", "number_of_classes": 1},
    ])
    pipeline = [
        {"$match": {"class_id": {"$in": ["c1"]}, "academic_year": {"$in": ["2026", 2026]}, "date": {"$lte": "2026-09-07"}}},
        {"$group": {"_id": {"c": "$class_id", "k": "$course_id"}, "dates": {"$addToSet": "$date"}}},
    ]
    rows = await execute_analytics_content_pipeline(_db(), pipeline)
    assert rows == [
        {"_id": {"c": "c1", "k": "ing"}, "dates": ["2026-08-20", "2026-08-21"]},
        {"_id": {"c": "c1", "k": "mat"}, "dates": ["2026-08-22"]},
    ]


@pytest.mark.asyncio
async def test_pipeline_desconhecido_falha_fechado():
    pipeline = [
        {"$match": {"class_id": {"$in": ["c1"]}, "academic_year": 2026}},
        {"$group": {"_id": "$teacher_id", "count": {"$sum": 1}}},
    ]
    with pytest.raises(ContentReportingAnalyticsError) as exc:
        await execute_analytics_content_pipeline(_db(), pipeline)
    assert exc.value.code == "CONTENT_REPORTING_ANALYTICS_PIPELINE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_tenant_ambiguo_falha_fechado():
    db = _db()
    db.classes = Collection([
        {"id": "c1", "mantenedora_id": "t1", "academic_year": 2026},
        {"id": "c1", "mantenedora_id": "t2", "academic_year": 2026},
    ])
    pipeline = [
        {"$match": {"class_id": {"$in": ["c1"]}, "academic_year": 2026}},
        {"$group": {"_id": "$class_id", "count": {"$sum": "$number_of_classes"}}},
    ]
    with pytest.raises(ContentReportingAnalyticsError) as exc:
        await execute_analytics_content_pipeline(db, pipeline)
    assert exc.value.code == "CONTENT_REPORTING_ANALYTICS_TENANT_AMBIGUOUS"


def test_setup_envolve_db_principal_e_sandbox_sem_tocar_demais_colecoes():
    captured = {}

    def legacy_setup(db, audit_service=None, sandbox_db=None):
        captured["db"] = db
        captured["sandbox"] = sandbox_db
        captured["audit"] = audit_service
        return "router"

    setup = install_content_reporting_analytics_setup(legacy_setup)
    primary = _db()
    sandbox = _db()
    assert setup(primary, "audit", sandbox) == "router"
    assert isinstance(captured["db"], ContentReportingAnalyticsDb)
    assert isinstance(captured["sandbox"], ContentReportingAnalyticsDb)
    assert captured["db"].classes is primary.classes
    assert captured["audit"] == "audit"


def test_pacote_routers_exporta_setup_s5_sem_reescrever_analytics():
    init_source = Path("routers/__init__.py").read_text(encoding="utf-8")
    analytics_source = Path("routers/analytics.py").read_text(encoding="utf-8")
    assert "install_content_reporting_analytics_setup" in init_source
    assert "setup_analytics_router = install_content_reporting_analytics_setup(_setup_analytics_router)" in init_source
    # O legado pode manter as três expressões; a troca ocorre no DB injetado.
    assert analytics_source.count("current_db.learning_objects.aggregate") == 3
