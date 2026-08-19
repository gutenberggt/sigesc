"""P0 — regressão de visibilidade do histórico de Conteúdos no DVD."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import services.content_history_bridge as bridge


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


def _matches(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$lt" in expected and not (value is not None and value < expected["$lt"]):
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            continue
        if value != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def find(self, query, _projection=None):
        return FakeCursor([doc for doc in self.docs if _matches(doc, query)])


class FakeDb:
    def __init__(self, canonical=None, legacy=None):
        self.content_entries = FakeCollection(canonical or [])
        self.learning_objects = FakeCollection(legacy or [])


def _assignment(**overrides):
    data = {
        "id": "assignment-1",
        "class_id": "class-1",
        "component_id": "math",
        "teacher_id": "teacher-1",
        "valid_from": "2026-08-18",
    }
    data.update(overrides)
    return data


def _canonical(doc_id="canonical-1", date="2026-08-18", **overrides):
    data = {
        "id": doc_id,
        "assignment_id": "assignment-1",
        "class_id": "class-1",
        "component_id": "math",
        "course_id": "math",
        "teacher_id": "teacher-1",
        "date": date,
        "aula_numero": 1,
        "deleted": False,
        "content": "Conteúdo DVD",
    }
    data.update(overrides)
    return data


def _legacy(doc_id="legacy-1", date="2026-08-17", **overrides):
    data = {
        "id": doc_id,
        "class_id": "class-1",
        "course_id": "math",
        "recorded_by": "teacher-1",
        "date": date,
        "content": "Conteúdo histórico",
        "academic_year": 2026,
    }
    data.update(overrides)
    return data


@pytest.fixture
def authorized(monkeypatch):
    async def fake_authorize(*_args, **_kwargs):
        return SimpleNamespace(assignment=_assignment())

    async def fake_filter(_db, _user, entries, **_kwargs):
        return entries

    monkeypatch.setattr(bridge, "authorize_assignment_access", fake_authorize)
    monkeypatch.setattr(bridge, "filter_visible_content_entries", fake_filter)


@pytest.mark.asyncio
async def test_merge_preserva_legado_e_canonico_na_fronteira(authorized):
    db = FakeDb(
        canonical=[
            _canonical("canonical-before", "2026-08-17"),
            _canonical("canonical-boundary", "2026-08-18"),
            _canonical("canonical-after", "2026-08-19"),
        ],
        legacy=[
            _legacy("legacy-before", "2026-08-17"),
            _legacy("legacy-boundary", "2026-08-18"),
            _legacy("legacy-after", "2026-08-19"),
        ],
    )

    result = await bridge.list_assignment_content_history(
        db,
        {"id": "teacher-1"},
        assignment_id="assignment-1",
        class_id="class-1",
        component_id="math",
    )

    ids = [item["id"] for item in result["items"]]
    assert "legacy-before" in ids
    assert "legacy-boundary" not in ids
    assert "legacy-after" not in ids
    assert "canonical-before" not in ids
    assert "canonical-boundary" in ids
    assert "canonical-after" in ids
    assert result["history_bridge"]["valid_from"] == "2026-08-18"


@pytest.mark.asyncio
async def test_legado_e_explicitamente_read_only_sem_assignment_retroativo(authorized):
    db = FakeDb(legacy=[_legacy()])
    result = await bridge.list_assignment_content_history(
        db,
        {"id": "teacher-1"},
        assignment_id="assignment-1",
        class_id="class-1",
        component_id="math",
    )

    item = result["items"][0]
    assert item["source"] == "learning_objects"
    assert item["legacy"] is True
    assert item["read_only"] is True
    assert item["assignment_id"] is None
    assert item["teacher_id"] == "teacher-1"
    assert item["recorded_by"] == "teacher-1"


@pytest.mark.asyncio
async def test_data_exata_anterior_retorna_somente_legado(authorized):
    db = FakeDb(
        canonical=[_canonical(date="2026-08-17")],
        legacy=[_legacy(date="2026-08-17")],
    )
    result = await bridge.list_assignment_content_history(
        db,
        {"id": "teacher-1"},
        assignment_id="assignment-1",
        class_id="class-1",
        component_id="math",
        date="2026-08-17",
    )
    assert [item["id"] for item in result["items"]] == ["legacy-1"]


@pytest.mark.asyncio
async def test_data_exata_no_cutover_retorna_somente_canonico(authorized):
    db = FakeDb(
        canonical=[_canonical(date="2026-08-18")],
        legacy=[_legacy(date="2026-08-18")],
    )
    result = await bridge.list_assignment_content_history(
        db,
        {"id": "teacher-1"},
        assignment_id="assignment-1",
        class_id="class-1",
        component_id="math",
        date="2026-08-18",
    )
    assert [item["id"] for item in result["items"]] == ["canonical-1"]


@pytest.mark.asyncio
async def test_teacher_id_divergente_falha_fechado(authorized):
    with pytest.raises(bridge.ContentHistoryBridgeError) as exc:
        await bridge.list_assignment_content_history(
            FakeDb(),
            {"id": "teacher-1"},
            assignment_id="assignment-1",
            class_id="class-1",
            component_id="math",
            teacher_id="teacher-2",
        )
    assert exc.value.code == "CONTENT_TEACHER_MISMATCH"


@pytest.mark.asyncio
async def test_componente_divergente_falha_fechado(authorized):
    with pytest.raises(bridge.ContentHistoryBridgeError) as exc:
        await bridge.list_assignment_content_history(
            FakeDb(),
            {"id": "teacher-1"},
            assignment_id="assignment-1",
            class_id="class-1",
            component_id="history",
        )
    assert exc.value.code == "COMPONENT_MISMATCH"


def test_frontend_bloqueia_escrita_em_historico_legado():
    src = Path("../frontend/src/services/contentDvdBridge.js").read_text(encoding="utf-8")
    assert "DVD_LEGACY_CONTENT_READ_ONLY" in src
    assert "isLegacyReadOnly(current)" in src
    assert "cachedLegacyAdapter" in src
    assert "source: record.source || 'content_entries'" in src


def test_adaptador_substitui_apenas_superficies_de_leitura():
    src = Path("routers/content_dvd_history.py").read_text(encoding="utf-8")
    assert '_remove_route(base_router, "/content-entries", "GET")' in src
    assert '"/learning-objects/pdf/bimestre/{class_id}", "GET"' in src
    assert "list_assignment_content_history" in src
    assert "insert_one(" not in src
    assert "update_one(" not in src
    assert "delete_one(" not in src
