import asyncio

import services.legacy_content_dvd_guard as guard
from services.legacy_content_dvd_guard import (
    build_professor_dvd_query,
    legacy_content_block_detail,
)


def test_non_professor_never_enters_professor_guard():
    q = build_professor_dvd_query(
        {"id": "u1", "role": "coordenador"}, class_id="c1", course_id="co1"
    )
    assert q is None


def test_professor_query_is_scoped_to_owner_class_enabled_component_and_validity():
    q = build_professor_dvd_query(
        {"id": "u1", "role": "professor"},
        class_id="c1",
        course_id="co1",
        on_date="2026-08-18",
    )
    assert q["teacher_id"] == "u1"
    assert q["class_id"] == "c1"
    assert q["deleted"] is False
    assert q["diary_settings.enabled"] is True
    assert {"valid_from": {"$lte": "2026-08-18"}} in q["$and"][0]["$or"]
    assert {"valid_until": {"$gte": "2026-08-18"}} in q["$and"][1]["$or"]
    component_clause = q["$and"][2]["$or"]
    assert {"component_id": "co1"} in component_clause
    assert {"component_id": None} in component_clause


def test_broad_professor_query_still_detects_any_active_dvd_candidate():
    q = build_professor_dvd_query(
        {"id": "u1", "role": "professor"}, on_date="2026-08-18"
    )
    assert q["teacher_id"] == "u1"
    assert "class_id" not in q
    assert q["diary_settings.enabled"] is True


def test_canonical_content_diary_is_detected(monkeypatch):
    calls = []

    async def fake_list_teacher_diaries(db, current_user, **kwargs):
        calls.append((db, current_user, kwargs))
        return {
            "items": [
                {
                    "class_id": "c1",
                    "component_id": "co1",
                    "capabilities": {"content_enabled": True},
                }
            ]
        }

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)
    db = object()
    user = {"id": "u1", "role": "professor", "mantenedora_id": "m1"}

    result = asyncio.run(
        guard.professor_has_active_dvd_content(
            db,
            user,
            class_id="c1",
            course_id="co1",
            on_date="2026-08-18",
        )
    )

    assert result is True
    assert calls == [
        (
            db,
            user,
            {"reference_date": "2026-08-18", "active_mantenedora_id": "m1"},
        )
    ]


def test_missing_canonical_content_diary_keeps_legacy_path_available(monkeypatch):
    async def fake_list_teacher_diaries(*args, **kwargs):
        return {"items": [], "blocked_total": 7}

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)

    result = asyncio.run(
        guard.professor_has_active_dvd_content(
            object(),
            {"id": "u1", "role": "professor"},
            class_id="c1",
            course_id="co1",
            on_date="2026-08-18",
        )
    )
    assert result is False


def test_block_detail_is_stable_and_actionable():
    detail = legacy_content_block_detail()
    assert detail["code"] == "DVD_CONTENT_LEGACY_BLOCKED"
    assert "content_entries" in detail["message"]
