from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
F4_SCRIPT = SCRIPTS / "teacher_visibility_f4_browser_render.py"
F41_SCRIPT = SCRIPTS / "teacher_visibility_f4_1_browser_render.py"

f4_spec = spec_from_file_location("teacher_visibility_f4_browser_render", F4_SCRIPT)
f4_module = module_from_spec(f4_spec)
assert f4_spec and f4_spec.loader
sys.modules[f4_spec.name] = f4_module
f4_spec.loader.exec_module(f4_module)

spec = spec_from_file_location("teacher_visibility_f4_1", F41_SCRIPT)
module = module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _pair(class_name="6º ANO A"):
    target = SimpleNamespace(class_name=class_name)
    return module._new_pair(target)


def test_f41_reuses_exact_six_pair_scope_from_f4():
    assert [target.class_name for target in module.f4.TARGETS] == [
        "6º ANO A",
        "6º ANO B",
        "7º ANO A",
        "7º ANO B",
        "8º ANO A",
        "9º ANO A",
    ]
    assert module.f4.COMPONENT_NAME == "Matemática"
    assert module.f4.TARGET_SCHOOL == "E M E I E F Jose Pereira Barbosa"


def test_probe_error_has_precedence_and_is_inconclusive():
    pairs = [_pair(target.class_name) for target in module.f4.TARGETS]
    for pair in pairs:
        pair["content"]["status"] = "PASS"
        pair["attendance"]["status"] = "PASS"
        pair["content"]["prefill_ok"] = True
        pair["attendance"]["prefill_ok"] = True
        pair["content"]["visible_probe_dates"] = 3
        pair["attendance"]["visible_probe_dates"] = 3

    pairs[0]["content"]["probe_errors"].append("CONTENT_HEADING_ANCHOR_MISSING")
    result = module.evaluate_pairs(pairs)
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["probe_errors"] == [
        "6º ANO A:content:CONTENT_HEADING_ANCHOR_MISSING"
    ]


def test_product_gap_requires_completed_probe_without_probe_error():
    pairs = [_pair(target.class_name) for target in module.f4.TARGETS]
    for pair in pairs:
        pair["content"]["status"] = "PASS"
        pair["attendance"]["status"] = "PASS"
        pair["content"]["prefill_ok"] = True
        pair["attendance"]["prefill_ok"] = True
        pair["content"]["visible_probe_dates"] = 3
        pair["attendance"]["visible_probe_dates"] = 3

    pairs[2]["attendance"]["status"] = "GAP"
    pairs[2]["attendance"]["product_failures"].append("ATTENDANCE_DOM_PROBE_COUNT_MISMATCH")
    result = module.evaluate_pairs(pairs)
    assert result["status"] == "FAIL"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_GAP"
    assert result["probe_errors"] == []
    assert result["product_failures"] == [
        "7º ANO A:attendance:ATTENDANCE_DOM_PROBE_COUNT_MISMATCH"
    ]


def test_all_pairs_pass_classifies_current():
    pairs = [_pair(target.class_name) for target in module.f4.TARGETS]
    for pair in pairs:
        pair["content"]["status"] = "PASS"
        pair["attendance"]["status"] = "PASS"
        pair["content"]["prefill_ok"] = True
        pair["attendance"]["prefill_ok"] = True
        pair["content"]["visible_probe_dates"] = 3
        pair["attendance"]["visible_probe_dates"] = 3

    result = module.evaluate_pairs(pairs)
    assert result == {
        "status": "PASS",
        "classification": "PUBLIC_BROWSER_RENDER_CURRENT",
        "probe_errors": [],
        "product_failures": [],
    }


def test_pair_count_mismatch_is_probe_error_not_product_gap():
    result = module.evaluate_pairs([], expected_pairs=6)
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["probe_errors"] == ["TARGET_PAIR_COUNT_0"]


def test_safe_code_never_persists_exception_message():
    exc = RuntimeError("https://sigesc.aprenderdigital.top/api/private?student=123")
    assert module._safe_code(exc) == "RuntimeError"


def test_catastrophic_result_is_inconclusive_and_read_only():
    result = module._catastrophic_result(RuntimeError("boom"))
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["probe_errors"] == ["RUNNER:RuntimeError"]
    assert result["production_writes"] is False
    assert result["live_api_requests"] == 0
    assert result["real_authentication_used"] is False
    assert result["database_access"] is False


def test_source_seals_timeout_semantics_pair_isolation_and_boundary():
    source = F41_SCRIPT.read_text(encoding="utf-8")
    required = [
        'service_workers="block"',
        'if "/api/" in parsed.path:',
        "route.fulfill(",
        'if method != "GET":',
        'request.resource_type in {"xhr", "fetch"}',
        "parsed.path in f4.PUBLIC_DYNAMIC_GET_PATHS",
        'context.route_web_socket("**/*", websocket_handler)',
        "web_socket_route.close(",
        "route.abort()",
        "route.continue_()",
        '"timeout_is_product_gap": False',
        '"pair_isolation": True',
        "TEACHER_VISIBILITY_F4_1_CHECKPOINT=",
        "if not _poll(lambda: selects.count() >= 2)",
        "if not _poll(lambda: heading.count() >= 1)",
        "if not _poll(lambda: registros.count() >= 1)",
        "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
    ]
    for marker in required:
        assert marker in source

    forbidden = [
        "MongoClient",
        "create_access_token",
        "/auth/login",
        "connect_to_server",
        "attendance.records[",
    ]
    for marker in forbidden:
        assert marker not in source
