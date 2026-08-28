from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import course_missing_containment as containment


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return list(self.rows)


class FakeCourses:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, projection):
        self.queries.append((query, projection))
        wanted = set(query["id"]["$in"])
        return FakeCursor([row for row in self.rows if row.get("id") in wanted])


class FakeDB:
    def __init__(self, courses):
        self.courses = FakeCourses(courses)


@pytest.mark.asyncio
async def test_missing_course_is_explicit_and_original_id_is_preserved():
    db = FakeDB([])
    payload = {"id": "lo-1", "course_id": "missing-course"}

    result = await containment.enrich_course_reference_response(db, payload)

    assert result is payload
    assert payload["course_id"] == "missing-course"
    assert payload["course_name"] == containment.HISTORICAL_COURSE_UNAVAILABLE_LABEL
    assert payload["course_reference_state"] == containment.HISTORICAL_COURSE_MISSING_STATE
    assert payload["course_reference_integrity"] == {
        "state": containment.HISTORICAL_COURSE_MISSING_STATE,
        "course_id": "missing-course",
        "remap_applied": False,
        "automatic_course_creation": False,
        "source_preserved": True,
    }


@pytest.mark.asyncio
async def test_existing_course_is_resolved_without_false_missing_marker():
    db = FakeDB([{"id": "course-1", "name": "O Eu, O Outro e Nós"}])
    payload = {"id": "lo-1", "course_id": "course-1"}

    await containment.enrich_course_reference_response(db, payload)

    assert payload["course_id"] == "course-1"
    assert payload["course_name"] == "O Eu, O Outro e Nós"
    assert "course_reference_state" not in payload
    assert "course_reference_integrity" not in payload


@pytest.mark.asyncio
async def test_existing_course_does_not_overwrite_preexisting_display_name():
    db = FakeDB([{"id": "course-1", "name": "Nome atual"}])
    payload = {
        "id": "assignment-1",
        "course_id": "course-1",
        "course_name": "Nome já enriquecido",
    }

    await containment.enrich_course_reference_response(db, payload)

    assert payload["course_name"] == "Nome já enriquecido"


@pytest.mark.asyncio
async def test_mixed_list_only_marks_missing_reference():
    db = FakeDB([{"id": "course-ok", "name": "Corpo, Gestos e Movimentos"}])
    payload = [
        {"id": "a", "course_id": "course-ok"},
        {"id": "b", "course_id": "course-gone"},
    ]

    await containment.enrich_course_reference_response(db, payload)

    assert payload[0]["course_name"] == "Corpo, Gestos e Movimentos"
    assert "course_reference_state" not in payload[0]
    assert payload[1]["course_id"] == "course-gone"
    assert payload[1]["course_reference_state"] == "HISTORICAL_COURSE_MISSING"


@pytest.mark.asyncio
async def test_payload_without_course_reference_is_unchanged_and_does_not_query():
    db = FakeDB([])
    payload = {"id": "x", "class_id": "class-1"}

    result = await containment.enrich_course_reference_response(db, payload)

    assert result == {"id": "x", "class_id": "class-1"}
    assert db.courses.queries == []


class FakeDependant:
    def __init__(self, call):
        self.call = call


class FakeRoute:
    def __init__(self, path, methods, endpoint):
        self.path = path
        self.methods = set(methods)
        self.endpoint = endpoint
        self.dependant = FakeDependant(endpoint)


class FakeRouter:
    def __init__(self, routes):
        self.routes = routes


@pytest.mark.asyncio
async def test_router_wrapper_contains_only_selected_get_route():
    db = FakeDB([])

    async def selected_endpoint():
        return {"course_id": "gone"}

    async def writer_endpoint():
        return {"course_id": "gone"}

    selected = FakeRoute("/teacher-assignments", {"GET"}, selected_endpoint)
    writer = FakeRoute("/teacher-assignments", {"POST"}, writer_endpoint)
    router = FakeRouter([selected, writer])

    containment._wrap_router_read_responses(
        router,
        db,
        {("/teacher-assignments", "GET")},
    )

    read_result = await selected.dependant.call()
    write_result = await writer.dependant.call()

    assert read_result["course_reference_state"] == "HISTORICAL_COURSE_MISSING"
    assert write_result == {"course_id": "gone"}
    assert writer.dependant.call is writer_endpoint


def test_setup_installation_is_idempotent_and_preserves_setup_contract():
    db = FakeDB([])
    router = FakeRouter([])

    def setup_router(received_db, marker=None):
        assert received_db is db
        assert marker == "ok"
        return router

    module = SimpleNamespace(setup_router=setup_router)

    containment._install_module_setup(module, module_key="assignments")
    installed_once = module.setup_router
    containment._install_module_setup(module, module_key="assignments")

    assert module.setup_router is installed_once
    assert module.setup_router(db, marker="ok") is router


def test_runtime_module_has_no_mongo_mutators_or_case_specific_uuid():
    source = inspect.getsource(containment)
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".find_one_and_update(",
        ".find_one_and_delete(",
        ".find_one_and_replace(",
    )

    assert not any(token in source for token in forbidden)
    assert "c2d05a04-b735-494d-bc7b-53ce34081488" not in source


def test_containment_is_response_layer_only():
    source_path = Path(containment.__file__)
    source = source_path.read_text(encoding="utf-8")

    assert "remap_applied" in source
    assert "automatic_course_creation" in source
    assert "source_preserved" in source
    assert "Componente histórico indisponível" in source
