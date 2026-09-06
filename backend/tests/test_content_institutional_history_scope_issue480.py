from routers.content_institutional_history_scope import merge_scope_history_items


def _item(
    id_, *, assignment="current", teacher="teacher-a", component="english-final",
    tenant="tenant-1", date="2026-03-12", aula=None, deleted=False,
):
    return {
        "id": id_,
        "assignment_id": assignment,
        "teacher_id": teacher,
        "class_id": "class-1",
        "component_id": component,
        "mantenedora_id": tenant,
        "date": date,
        "aula_numero": aula,
        "deleted": deleted,
    }


def test_previous_assignment_same_scope_is_visible_but_read_only():
    base = [_item("current-1")]
    previous = _item("old-1", assignment="old-assignment", teacher="old-teacher")
    items = merge_scope_history_items(
        base,
        [previous],
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    by_id = {item["id"]: item for item in items}
    assert set(by_id) == {"current-1", "old-1"}
    assert by_id["old-1"]["read_only"] is True
    assert by_id["old-1"]["historical_scope_read"] is True
    assert by_id["old-1"]["teacher_id"] == "old-teacher"


def test_authorship_does_not_remove_same_scope_history():
    candidates = [
        _item("a", assignment="old-a", teacher="teacher-a"),
        _item("b", assignment="old-b", teacher="teacher-b"),
    ]
    items = merge_scope_history_items(
        [],
        candidates,
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    assert {item["id"] for item in items} == {"a", "b"}


def test_explicit_foreign_tenant_is_fail_closed():
    items = merge_scope_history_items(
        [],
        [_item("foreign", tenant="tenant-2")],
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    assert items == []


def test_missing_legacy_tenant_is_tolerated_under_exact_class_scope():
    items = merge_scope_history_items(
        [],
        [_item("legacy", assignment="old", tenant=None)],
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    assert [item["id"] for item in items] == ["legacy"]
    assert items[0]["read_only"] is True


def test_deleted_candidate_never_enters_read_projection():
    items = merge_scope_history_items(
        [],
        [_item("deleted", deleted=True)],
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    assert items == []


def test_base_item_is_not_duplicated_by_scope_scan():
    same = _item("same")
    same["source"] = "content_entries"
    items = merge_scope_history_items(
        [same],
        [same],
        current_assignment_id="current",
        tenant_id="tenant-1",
        valid_from="2026-08-18",
    )
    assert len(items) == 1
