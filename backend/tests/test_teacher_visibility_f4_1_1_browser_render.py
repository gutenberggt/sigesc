from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
F4_SCRIPT = SCRIPTS / "teacher_visibility_f4_browser_render.py"
F41_SCRIPT = SCRIPTS / "teacher_visibility_f4_1_browser_render.py"
F411_SCRIPT = SCRIPTS / "teacher_visibility_f4_1_1_browser_render.py"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "teacher-visibility-f4-1-1-browser-render.yml"

f4_spec = spec_from_file_location("teacher_visibility_f4_browser_render", F4_SCRIPT)
f4_module = module_from_spec(f4_spec)
assert f4_spec and f4_spec.loader
sys.modules[f4_spec.name] = f4_module
f4_spec.loader.exec_module(f4_module)

f41_spec = spec_from_file_location("teacher_visibility_f4_1_browser_render", F41_SCRIPT)
f41_module = module_from_spec(f41_spec)
assert f41_spec and f41_spec.loader
sys.modules[f41_spec.name] = f41_module
f41_spec.loader.exec_module(f41_module)

spec = spec_from_file_location("teacher_visibility_f4_1_1", F411_SCRIPT)
module = module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _pass_surface():
    return {
        "status": "PASS",
        "prefill_ok": True,
        "visible_probe_dates": 3,
        "product_failures": [],
        "probe_errors": [],
        "elapsed_ms": 100,
    }


def test_f411_reuses_exact_six_pair_scope():
    assert [target.class_name for target in module.f4.TARGETS] == [
        "6º ANO A",
        "6º ANO B",
        "7º ANO A",
        "7º ANO B",
        "8º ANO A",
        "9º ANO A",
    ]
    assert module.EXPECTED_SURFACE_COUNT == 12
    assert module.f4.COMPONENT_NAME == "Matemática"


def test_nominal_wall_clock_budget_includes_kill_grace_and_version_worker():
    expected = (
        module.EXPECTED_SURFACE_COUNT
        * (module.SURFACE_WALL_TIMEOUT_SECONDS + module.WORKER_KILL_GRACE_SECONDS)
        + module.PUBLIC_VERSION_WALL_TIMEOUT_SECONDS
        + module.WORKER_KILL_GRACE_SECONDS
    )
    assert module.NOMINAL_WORST_CASE_SECONDS == expected
    assert 5 <= module.SURFACE_WALL_TIMEOUT_SECONDS <= 60
    assert 5 <= module.PUBLIC_VERSION_WALL_TIMEOUT_SECONDS <= 60
    assert 0 <= module.WORKER_KILL_GRACE_SECONDS <= 5
    assert module.NOMINAL_WORST_CASE_SECONDS < 15 * 60


def test_wall_timeout_surface_is_probe_error_not_gap():
    surface = module._probe_error_surface("content", "WALL_TIMEOUT", elapsed_ms=40000)
    assert surface["status"] == "PROBE_ERROR"
    assert surface["probe_errors"] == ["CONTENT_WALL_TIMEOUT"]
    assert surface["product_failures"] == []
    assert surface["elapsed_ms"] == 40000


def test_extract_worker_json_uses_last_valid_structured_line():
    payload = {
        "schema": module.SCHEMA,
        "worker": True,
        "surface_result": _pass_surface(),
    }
    output = "\n".join([
        "noise",
        module.WORKER_PREFIX + "{bad json",
        module.WORKER_PREFIX + json.dumps(payload),
    ])
    assert module._extract_worker_json(output) == payload


def test_extract_prefixed_json_supports_version_worker():
    payload = {
        "schema": module.SCHEMA,
        "version_worker": True,
        "status": "PASS",
        "public_version_sha": "a" * 40,
    }
    output = module.VERSION_PREFIX + json.dumps(payload)
    assert module._extract_prefixed_json(output, module.VERSION_PREFIX) == payload


def test_public_version_wall_timeout_is_contained_by_supervisor(monkeypatch):
    class FakeProcess:
        pid = 12345
        returncode = None

        def __init__(self):
            self.communicate_calls = 0

        def communicate(self, timeout):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise module.subprocess.TimeoutExpired(
                    cmd="version-worker",
                    timeout=timeout,
                    output="",
                )
            self.returncode = -15
            return "", None

        def poll(self):
            return self.returncode

    fake = FakeProcess()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: fake)
    monkeypatch.setattr(module, "_kill_worker_group", lambda proc: setattr(proc, "returncode", -15))

    with pytest.raises(RuntimeError, match="PUBLIC_VERSION_WALL_TIMEOUT"):
        module._validate_public_version_with_wall_clock("a" * 40)

    assert fake.communicate_calls == 2


def test_aggregate_worker_meta_counts_timeouts_and_boundary_events():
    rows = [
        {
            "worker_timeout": True,
            "worker_structured_json": False,
            "intercepted_api_request_count": 0,
            "unknown_api_fixture_count": 0,
            "blocked_non_get_attempt_count": 0,
            "blocked_dynamic_get_attempt_count": 1,
            "blocked_websocket_attempt_count": 0,
        },
        {
            "worker_timeout": False,
            "worker_structured_json": True,
            "intercepted_api_request_count": 4,
            "unknown_api_fixture_count": 1,
            "blocked_non_get_attempt_count": 1,
            "blocked_dynamic_get_attempt_count": 0,
            "blocked_websocket_attempt_count": 2,
        },
    ]
    result = module._aggregate_worker_meta(rows)
    assert result == {
        "worker_timeout_count": 1,
        "worker_structured_json_count": 1,
        "intercepted_api_request_count": 4,
        "unknown_api_fixture_count": 1,
        "blocked_non_get_attempt_count": 1,
        "blocked_dynamic_get_attempt_count": 1,
        "blocked_websocket_attempt_count": 2,
    }


def test_f41_evaluation_keeps_probe_error_precedence_for_f411_pairs():
    pairs = [module._blank_pair(target) for target in module.f4.TARGETS]
    for pair in pairs:
        pair["content"] = _pass_surface()
        pair["attendance"] = _pass_surface()
    pairs[0]["content"] = module._probe_error_surface("content", "WALL_TIMEOUT")

    result = module.f41.evaluate_pairs(pairs, expected_pairs=6)
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["probe_errors"] == ["6º ANO A:content:CONTENT_WALL_TIMEOUT"]


def test_product_gap_remains_possible_only_after_completed_worker_result():
    pairs = [module._blank_pair(target) for target in module.f4.TARGETS]
    for pair in pairs:
        pair["content"] = _pass_surface()
        pair["attendance"] = _pass_surface()

    pairs[3]["attendance"] = _pass_surface()
    pairs[3]["attendance"]["status"] = "GAP"
    pairs[3]["attendance"]["product_failures"] = ["ATTENDANCE_DOM_PROBE_COUNT_MISMATCH"]

    result = module.f41.evaluate_pairs(pairs, expected_pairs=6)
    assert result["status"] == "FAIL"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_GAP"
    assert result["probe_errors"] == []


def test_catastrophic_result_is_read_only_and_inconclusive():
    result = module._catastrophic_result(RuntimeError("secret URL /api/student/123"))
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["probe_errors"] == ["RUNNER:RuntimeError"]
    assert result["production_writes"] is False
    assert result["live_api_requests"] == 0
    assert result["real_authentication_used"] is False
    assert result["database_access"] is False
    assert result["probe_policy"]["public_version_process_isolation"] is True


def test_source_seals_external_wall_clock_process_isolation_and_boundary():
    source = F411_SCRIPT.read_text(encoding="utf-8")
    required = [
        "subprocess.Popen(",
        "start_new_session=True",
        "proc.communicate(timeout=SURFACE_WALL_TIMEOUT_SECONDS)",
        "proc.communicate(timeout=PUBLIC_VERSION_WALL_TIMEOUT_SECONDS)",
        "except subprocess.TimeoutExpired",
        "os.killpg(proc.pid, signal.SIGTERM)",
        "os.killpg(proc.pid, signal.SIGKILL)",
        "PUBLIC_VERSION_WALL_TIMEOUT",
        "--version-worker",
        "VERSION_PREFIX",
        "WALL_TIMEOUT",
        '"process_isolation": True',
        '"surface_isolation": True',
        '"public_version_process_isolation": True',
        '"timeout_is_product_gap": False',
        'service_workers="block"',
        'if method != "GET":',
        'if "/api/" in parsed.path:',
        "route.fulfill(",
        'request.resource_type in {"xhr", "fetch"}',
        "route.abort()",
        "route.continue_()",
        'context.route_web_socket("**/*", websocket_handler)',
        "web_socket_route.close(",
        '"production_writes": False',
        "TEACHER_VISIBILITY_F4_1_1_CHECKPOINT=",
        "TEACHER_VISIBILITY_F4_1_1_JSON=",
    ]
    for marker in required:
        assert marker in source

    forbidden = [
        "MongoClient",
        "pymongo",
        "create_access_token",
        "/auth/login",
        "SIGESC_PROD_SSH",
        "docker exec",
        "connect_to_server",
        'method="POST"',
        'method="PUT"',
        'method="PATCH"',
        'method="DELETE"',
    ]
    for marker in forbidden:
        assert marker not in source


def test_workflow_finalizer_survives_probe_failure_and_keeps_owner_gate():
    source = WORKFLOW.read_text(encoding="utf-8")
    required = [
        "timeout-minutes: 15",
        "Ensure structured fallback evidence",
        "if: always()",
        "Comment diagnosis and close gate even after probe failure",
        "if: always() && steps.context.outcome == 'success'",
        "TEACHER_VISIBILITY_F4_1_1=AUTHORIZED",
        "CONFIRMATION=AUDIT_PUBLIC_BROWSER_RENDER_READ_ONLY",
        "TRACKING_ISSUE",
        "TARGET_SHA",
        "EXPECTED_PRODUCTION_SHA",
        "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
        "PUBLIC_BROWSER_RENDER_GAP",
        "PUBLIC_BROWSER_RENDER_CURRENT",
    ]
    for marker in required:
        assert marker in source
