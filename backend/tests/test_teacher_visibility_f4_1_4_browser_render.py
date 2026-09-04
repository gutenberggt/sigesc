import importlib.util
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f4_1_4_browser_render.py"
SPEC = importlib.util.spec_from_file_location("teacher_visibility_f4_1_4_browser_render", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _row(case, status="PASS", stage="ladder_complete"):
    return {"case": case, "status": status, "last_checkpoint_stage": stage}


def test_scope_is_only_two_representative_post_goto_surfaces():
    assert module.CASES == ("CONTENT_POST_GOTO", "ATTENDANCE_POST_GOTO")
    assert module.TARGET.class_name == "6º ANO A"


def test_diagnose_select_count_stall():
    result = module.diagnose([
        _row("CONTENT_POST_GOTO", "PROBE_ERROR", "select_count_before"),
        _row("ATTENDANCE_POST_GOTO"),
    ])
    assert result["diagnosis_code"] == "LOCATOR_SELECT_COUNT_STALL"
    assert result["first_failure_case"] == "CONTENT_POST_GOTO"


def test_diagnose_selected_options_evaluate_stall():
    result = module.diagnose([
        _row("CONTENT_POST_GOTO", "PROBE_ERROR", "selected_options_eval_before"),
    ])
    assert result["diagnosis_code"] == "LOCATOR_SELECTED_OPTIONS_EVALUATE_ALL_STALL"


def test_diagnose_route_fulfill_stall_has_priority():
    result = module.diagnose([
        _row("CONTENT_POST_GOTO", "PROBE_ERROR", "route_fulfill_api_before"),
    ])
    assert result["diagnosis_code"] == "ROUTE_FULFILL_API_CALL_STALL"


def test_diagnose_registros_click_and_tab_wait():
    click = module.diagnose([
        _row("ATTENDANCE_POST_GOTO", "PROBE_ERROR", "registros_click_before"),
    ])
    assert click["diagnosis_code"] == "REGISTROS_CLICK_STALL"
    tab = module.diagnose([
        _row("ATTENDANCE_POST_GOTO", "PROBE_ERROR", "tab_wait_before"),
    ])
    assert tab["diagnosis_code"] == "REGISTROS_TAB_WAIT_STALL"


def test_diagnose_all_healthy():
    result = module.diagnose([_row(case) for case in module.CASES])
    assert result == {
        "diagnosis_code": "POST_GOTO_DOM_LADDER_HEALTHY",
        "first_failure_case": None,
        "first_failure_stage": None,
    }


def test_boundary_is_sealed_and_cannot_claim_product_gap():
    boundary = module._boundary()
    assert boundary["production_http_methods"] == ["GET"]
    assert boundary["service_workers_blocked"] is True
    assert boundary["all_api_requests_intercepted_locally"] is True
    assert boundary["dynamic_non_api_gets_allowlisted"] is True
    assert boundary["websockets_blocked"] is True
    assert boundary["live_api_requests"] == 0
    assert boundary["real_authentication_used"] is False
    assert boundary["database_access"] is False
    assert boundary["student_data_read"] is False
    assert boundary["attendance_records_read"] is False
    assert boundary["pedagogical_text_read"] is False
    assert boundary["production_writes"] is False
    assert boundary["product_gap_claimed"] is False


def test_nominal_budget_is_under_ten_minutes():
    assert module.NOMINAL_WORST_CASE_SECONDS < 10 * 60
    module._validate_policy()


def test_checkpoint_parser_keeps_iteration_metadata():
    import json
    payload = {
        "case": "CONTENT_POST_GOTO",
        "stage": "select_count_before",
        "status": "RUNNING",
        "iteration": 3,
    }
    line = module.CHECKPOINT_PREFIX + json.dumps(payload)
    assert module._parse_checkpoint(line) == payload


def test_safe_code_removes_free_form_spaces():
    assert module._safe_code("selector operation / private text") == "selector_operation_private_text"
