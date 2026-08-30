import asyncio

from services import legacy_content_dvd_guard as guard


USER = {
    "id": "teacher-user-1",
    "role": "professor",
    "mantenedora_id": "tenant-1",
}


def _run(coro):
    return asyncio.run(coro)


def _item(*, class_id="class-1", component_id="course-1", content_enabled=True):
    return {
        "class_id": class_id,
        "component_id": component_id,
        "capabilities": {"content_enabled": content_enabled},
    }


def test_raw_enabled_assignment_without_canonical_diary_does_not_block_legacy(monkeypatch):
    calls = []

    async def fake_list_teacher_diaries(db, current_user, **kwargs):
        calls.append((db, current_user, kwargs))
        return {"items": [], "total": 0, "blocked_total": 7}

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)
    db = object()

    blocked = _run(
        guard.professor_has_active_dvd_content(
            db,
            USER,
            class_id="class-1",
            on_date="2026-08-30",
        )
    )

    assert blocked is False
    assert calls == [
        (
            db,
            USER,
            {
                "reference_date": "2026-08-30",
                "active_mantenedora_id": "tenant-1",
            },
        )
    ]


def test_canonical_content_enabled_diary_blocks_legacy(monkeypatch):
    async def fake_list_teacher_diaries(*args, **kwargs):
        return {
            "items": [
                _item(class_id="other-class"),
                _item(class_id="class-1", component_id="course-1", content_enabled=True),
            ]
        }

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)

    assert _run(
        guard.professor_has_active_dvd_content(
            object(), USER, class_id="class-1", course_id="course-1"
        )
    ) is True


def test_content_disabled_or_other_component_does_not_block(monkeypatch):
    async def fake_list_teacher_diaries(*args, **kwargs):
        return {
            "items": [
                _item(class_id="class-1", component_id="course-1", content_enabled=False),
                _item(class_id="class-1", component_id="course-2", content_enabled=True),
            ]
        }

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)

    assert _run(
        guard.professor_has_active_dvd_content(
            object(), USER, class_id="class-1", course_id="course-1"
        )
    ) is False


def test_class_wide_diary_does_not_match_component_scoped_request(monkeypatch):
    async def fake_list_teacher_diaries(*args, **kwargs):
        return {"items": [_item(class_id="class-1", component_id=None, content_enabled=True)]}

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)

    assert _run(
        guard.professor_has_active_dvd_content(
            object(), USER, class_id="class-1", course_id="course-9"
        )
    ) is False


def test_class_wide_diary_matches_class_level_request_without_component(monkeypatch):
    async def fake_list_teacher_diaries(*args, **kwargs):
        return {"items": [_item(class_id="class-1", component_id=None, content_enabled=True)]}

    monkeypatch.setattr(guard, "list_teacher_diaries", fake_list_teacher_diaries)

    assert _run(
        guard.professor_has_active_dvd_content(
            object(), USER, class_id="class-1"
        )
    ) is True


def test_non_professor_never_invokes_canonical_diary_reader(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("list_teacher_diaries must not run for non-professor")

    monkeypatch.setattr(guard, "list_teacher_diaries", forbidden)

    assert _run(
        guard.professor_has_active_dvd_content(
            object(), {"id": "admin-1", "role": "admin"}, class_id="class-1"
        )
    ) is False
