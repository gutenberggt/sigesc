from pathlib import Path
import importlib.util
import io


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ana_lucia_f2_1_runtime_legacy_audit.py"
spec = importlib.util.spec_from_file_location("ana_lucia_f2_1", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_structural_json_counter_ignores_braces_inside_strings():
    payload = b'[{"content":"texto { x } e \\" }","id":"1"},{"content":"outro"}]'
    assert mod._count_top_level_json_objects(io.BytesIO(payload)) == 2


def test_content_tenant_gap_is_classified_before_generic_zero():
    mongo = {
        "total": 24,
        "missing_tenant": 24,
        "target_tenant": 0,
        "academic_year_string": 0,
        "academic_year_int": 24,
    }
    assert mod.classify_content(
        mongo,
        {"status": 200, "count": 0},
        {"status": 200, "count": 0},
        component_exposed=True,
        content_diaries=0,
    ) == "CONTENT_TENANT_METADATA_GAP"


def test_content_reaches_screen_when_http_and_selection_are_healthy():
    mongo = {
        "total": 4,
        "missing_tenant": 0,
        "target_tenant": 4,
        "academic_year_string": 0,
        "academic_year_int": 4,
    }
    assert mod.classify_content(
        mongo,
        {"status": 200, "count": 4},
        {"status": 200, "count": 4},
        component_exposed=True,
        content_diaries=0,
    ) == "CONTENT_REACHES_SCREEN"


def test_attendance_detects_out_of_scope_raw_dvd_guard():
    mongo = {
        "collections": {
            "attendance": {"documents": 10, "distinct_dates": 5},
            "attendance_documentary": {"documents": 0},
        }
    }
    assert mod.classify_attendance(
        mongo,
        {"status": 409, "count": None},
        {"status": 200, "count": 5},
        component_exposed=True,
        raw_dvd_year_rows=1,
        outside_dvd_scope=True,
    ) == "ATTENDANCE_RAW_DVD_YEAR_GUARD_OUT_OF_SCOPE"


def test_attendance_documentary_only_is_explicit():
    mongo = {
        "collections": {
            "attendance": {"documents": 0, "distinct_dates": 0},
            "attendance_documentary": {"documents": 3},
        }
    }
    assert mod.classify_attendance(
        mongo,
        {"status": 200, "count": 0},
        {"status": 200, "count": 0},
        component_exposed=True,
        raw_dvd_year_rows=0,
        outside_dvd_scope=True,
    ) == "ATTENDANCE_DOCUMENTARY_ONLY_NOT_IN_LEGACY_READER"
