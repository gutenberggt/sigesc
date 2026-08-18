import asyncio

from services.legacy_content_dvd_guard import (
    build_professor_dvd_query,
    legacy_content_block_detail,
    professor_has_active_dvd_content,
)


class FakeCollection:
    def __init__(self, result=None):
        self.result = result
        self.last_query = None

    async def find_one(self, query, projection=None):
        self.last_query = query
        return self.result


class FakeDb:
    def __init__(self, result=None):
        self.teacher_class_assignments = FakeCollection(result)


def test_non_professor_never_enters_professor_guard():
    q = build_professor_dvd_query(
        {"id": "u1", "role": "coordenador"}, class_id="c1", course_id="co1"
    )
    assert q is None


def test_professor_query_is_scoped_to_owner_class_enabled_and_component():
    q = build_professor_dvd_query(
        {"id": "u1", "role": "professor"}, class_id="c1", course_id="co1"
    )
    assert q["teacher_id"] == "u1"
    assert q["class_id"] == "c1"
    assert q["deleted"] is False
    assert q["diary_settings.enabled"] is True
    assert {"component_id": "co1"} in q["$or"]
    assert {"component_id": None} in q["$or"]


def test_active_dvd_is_detected():
    db = FakeDb({"id": "a1"})
    result = asyncio.run(
        professor_has_active_dvd_content(
            db,
            {"id": "u1", "role": "professor"},
            class_id="c1",
            course_id="co1",
        )
    )
    assert result is True
    assert db.teacher_class_assignments.last_query["teacher_id"] == "u1"


def test_missing_dvd_keeps_legacy_path_available():
    db = FakeDb(None)
    result = asyncio.run(
        professor_has_active_dvd_content(
            db,
            {"id": "u1", "role": "professor"},
            class_id="c1",
            course_id="co1",
        )
    )
    assert result is False


def test_block_detail_is_stable_and_actionable():
    detail = legacy_content_block_detail()
    assert detail["code"] == "DVD_CONTENT_LEGACY_BLOCKED"
    assert "content_entries" in detail["message"]
