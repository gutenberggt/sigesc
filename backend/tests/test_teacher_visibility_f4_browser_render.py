from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f4_browser_render.py"
spec = spec_from_file_location("teacher_visibility_f4", SCRIPT)
module = module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_exact_target_scope_has_six_luiz_math_pairs():
    targets = module.build_targets()
    assert [target.class_name for target in targets] == [
        "6º ANO A",
        "6º ANO B",
        "7º ANO A",
        "7º ANO B",
        "8º ANO A",
        "9º ANO A",
    ]
    assert len({target.class_id for target in targets}) == 6
    assert len({target.course_id for target in targets}) == 6
    assert module.COMPONENT_NAME == "Matemática"
    assert module.TARGET_SCHOOL == "E M E I E F Jose Pereira Barbosa"


def test_public_dynamic_get_allowlist_is_narrow_and_explicit():
    assert module.PUBLIC_DYNAMIC_GET_PATHS == frozenset({
        "/version.json",
        "/asset-manifest.json",
        "/manifest.json",
    })


def test_learning_object_fixture_is_metadata_only_and_synthetic():
    target = module.TARGETS[0]
    status, payload, key = module.fixture_for_api(
        f"https://example.invalid/api/learning-objects?class_id={target.class_id}&course_id={target.course_id}&academic_year=2026&month=9"
    )
    assert status == 200
    assert key == "learning_objects_synthetic"
    assert len(payload) == len(module.PROBE_DATES)
    forbidden = {
        "content", "methodology", "observations", "resources", "students",
        "attendance", "attendance_records", "records", "student_id", "student_name",
    }
    for row in payload:
        assert forbidden.isdisjoint(row)
        assert row["source"] == "learning_objects"
        assert row["legacy"] is True
        assert row["read_only"] is True
        assert row["date"] in module.PROBE_DATES


def test_attendance_fixture_exposes_only_probe_dates():
    status, payload, key = module.fixture_for_api(
        "https://example.invalid/api/attendance/dates-with-records?class_id=f4-class-1&academic_year=2026&course_id=f4-course-1"
    )
    assert status == 200
    assert key == "attendance_dates_synthetic"
    assert payload == {"dates": list(module.PROBE_DATES)}
    assert "records" not in payload
    assert "students" not in payload


def test_unknown_api_is_always_resolved_locally():
    status, payload, key = module.fixture_for_api(
        "https://sigesc.aprenderdigital.top/api/something-new?x=1"
    )
    assert status == 200
    assert payload == {}
    assert key == "unknown_api_local_empty"


def test_pair_evaluation_requires_prefill_and_three_dom_dates():
    good = {
        "class": "6º ANO A",
        "component": "Matemática",
        "content_prefill_ok": True,
        "content_visible_probe_dates": 3,
        "attendance_prefill_ok": True,
        "attendance_visible_probe_dates": 3,
    }
    ok, failures = module.evaluate_pair(good)
    assert ok is True
    assert failures == []

    bad = {**good, "attendance_visible_probe_dates": 0}
    ok, failures = module.evaluate_pair(bad)
    assert ok is False
    assert failures == ["ATTENDANCE_DOM_PROBE_COUNT_MISMATCH"]


def test_global_evaluation_requires_all_six_pairs():
    pairs = [
        {
            "class": target.class_name,
            "component": "Matemática",
            "content_prefill_ok": True,
            "content_visible_probe_dates": 3,
            "attendance_prefill_ok": True,
            "attendance_visible_probe_dates": 3,
        }
        for target in module.TARGETS
    ]
    result = module.evaluate_result(pairs)
    assert result["status"] == "PASS"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_CURRENT"
    assert result["failures"] == []


def test_source_seals_no_real_api_and_no_production_write_boundary():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'service_workers="block"' in source
    assert 'if "/api/" in parsed.path:' in source
    assert "route.fulfill(" in source
    assert 'if method != "GET":' in source
    assert 'request.resource_type in {"xhr", "fetch"}' in source
    assert "parsed.path in PUBLIC_DYNAMIC_GET_PATHS" in source
    assert "blocked_dynamic_get.append" in source
    assert 'context.route_web_socket("**/*", websocket_handler)' in source
    assert "web_socket_route.close(" in source
    assert "route.abort()" in source
    assert "route.continue_()" in source
    assert "MongoClient" not in source
    assert "create_access_token" not in source
    assert "/auth/login" not in source
    assert "connect_to_server" not in source
    assert "attendance.records" in source  # boundary declaration only
