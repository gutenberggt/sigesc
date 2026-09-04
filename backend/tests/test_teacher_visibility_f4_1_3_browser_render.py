import importlib.util
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f4_1_3_browser_render.py"
SPEC = importlib.util.spec_from_file_location("teacher_visibility_f4_1_3_browser_render", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def row(case, status="PASS", stage="goto_after"):
    return {
        "case": case,
        "status": status,
        "last_checkpoint_stage": stage,
    }


def test_case_matrix_is_narrow_and_ordered():
    assert module.CASES == (
        "STATIC_DIRECT",
        "STATIC_ROUTED_CONTINUE",
        "APP_DOCUMENT_ONLY_CONTENT",
        "APP_FULL_CONTENT",
        "APP_FULL_ATTENDANCE",
    )
    assert module.REPRESENTATIVE_TARGET.class_name == "6º ANO A"


def test_modes_keep_static_direct_unrouted_and_app_full_explicit():
    assert module._case_mode("STATIC_DIRECT") == "direct"
    assert module._case_mode("STATIC_ROUTED_CONTINUE") == "static_routed"
    assert module._case_mode("APP_DOCUMENT_ONLY_CONTENT") == "document_only"
    assert module._case_mode("APP_FULL_CONTENT") == "full"
    assert module._case_mode("APP_FULL_ATTENDANCE") == "full"


def test_diagnose_route_continue_stall():
    cases = [row(name) for name in module.CASES]
    cases[1] = row("STATIC_ROUTED_CONTINUE", "PROBE_ERROR", "route_continue_before_public")
    result = module.diagnose(cases)
    assert result["diagnosis_code"] == "ROUTE_CONTINUE_CALL_STALL"
    assert result["first_failure_case"] == "STATIC_ROUTED_CONTINUE"
    assert result["first_failure_stage"] == "route_continue_before_public"


def test_diagnose_page_goto_before_first_route_event():
    cases = [row(name) for name in module.CASES]
    cases[0] = row("STATIC_DIRECT", "PROBE_ERROR", "goto_before")
    result = module.diagnose(cases)
    assert result["diagnosis_code"] == "PAGE_GOTO_BEFORE_FIRST_ROUTE_EVENT_STALL"
    assert result["first_failure_case"] == "STATIC_DIRECT"


def test_diagnose_document_only_failure_without_route_specific_stage():
    cases = [row(name) for name in module.CASES]
    cases[2] = row("APP_DOCUMENT_ONLY_CONTENT", "PROBE_ERROR", "browser_launch_after")
    result = module.diagnose(cases)
    assert result["diagnosis_code"] == "APP_DOCUMENT_NAVIGATION_FAILURE"


def test_diagnose_all_cases_healthy():
    result = module.diagnose([row(name) for name in module.CASES])
    assert result == {
        "diagnosis_code": "GOTO_ROUTE_DECOMPOSITION_HEALTHY",
        "first_failure_case": None,
        "first_failure_stage": None,
    }


def test_checkpoint_parser_accepts_only_f413_prefix():
    payload = {"case": "STATIC_DIRECT", "stage": "goto_before", "status": "RUNNING"}
    line = module.CHECKPOINT_PREFIX + __import__("json").dumps(payload)
    assert module._parse_checkpoint(line) == payload
    assert module._parse_checkpoint("TEACHER_VISIBILITY_F4_1_CHECKPOINT={}") is None


def test_boundary_is_read_only_and_never_claims_product_gap():
    boundary = module._boundary()
    assert boundary["production_http_methods"] == ["GET"]
    assert boundary["all_api_requests_intercepted_locally"] is True
    assert boundary["service_workers_blocked"] is True
    assert boundary["websockets_blocked"] is True
    assert boundary["live_api_requests"] == 0
    assert boundary["real_authentication_used"] is False
    assert boundary["database_access"] is False
    assert boundary["student_data_read"] is False
    assert boundary["attendance_records_read"] is False
    assert boundary["pedagogical_text_read"] is False
    assert boundary["production_writes"] is False
    assert boundary["product_gap_claimed"] is False


def test_nominal_budget_is_below_ten_minute_job_cap():
    assert module.NOMINAL_WORST_CASE_SECONDS < 10 * 60
    module._validate_policy()


def test_safe_code_never_persists_free_form_spaces():
    assert module._safe_code("route continue / sensitive text") == "route_continue_sensitive_text"
