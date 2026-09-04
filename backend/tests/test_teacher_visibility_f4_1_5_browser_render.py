import importlib.util
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f4_1_5_browser_render.py"
SPEC = importlib.util.spec_from_file_location("teacher_visibility_f4_1_5_browser_render", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class FakeWebSocketRoute:
    url = "wss://example.invalid/ws"

    def __getattr__(self, name):
        raise AssertionError(f"no WebSocketRoute method must be called: {name}")


def test_local_websocket_blocker_only_reads_url_and_returns():
    blocked = []
    result = module._block_websocket_locally(FakeWebSocketRoute(), blocked)
    assert result is None
    assert blocked == ["wss://example.invalid/ws"]


def test_boundary_explicitly_forbids_server_connection_and_close_calls():
    boundary = module._boundary_template()
    assert boundary["websocket_policy"] == "ROUTED_LOCAL_NO_SERVER_CONNECTION"
    assert boundary["websocket_server_connections"] == 0
    assert boundary["websocket_close_calls"] == 0
    assert boundary["websockets_blocked"] is True
    assert boundary["production_writes"] is False
    assert boundary["live_api_requests"] == 0


def test_full_scope_remains_six_pairs_times_two_surfaces():
    assert len(module.f4.TARGETS) == 6
    assert module.EXPECTED_SURFACE_COUNT == 12


def test_product_taxonomy_is_still_f41_taxonomy():
    pair = module.f41._new_pair(module.f4.TARGETS[0])
    pair["content"]["status"] = "PASS"
    pair["attendance"]["status"] = "PASS"
    result = module.f41.evaluate_pairs([pair], expected_pairs=1)
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_CURRENT"


def test_probe_error_dominates_product_failure():
    pair = module.f41._new_pair(module.f4.TARGETS[0])
    pair["content"]["probe_errors"] = ["CONTENT_TEST_PROBE_ERROR"]
    pair["content"]["status"] = "PROBE_ERROR"
    pair["attendance"]["product_failures"] = ["ATTENDANCE_TEST_PRODUCT_FAILURE"]
    pair["attendance"]["status"] = "GAP"
    result = module.f41.evaluate_pairs([pair], expected_pairs=1)
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"


def test_checkpoint_parser_accepts_f415_and_f41_streams():
    import json
    payload = {"class": "6º ANO A", "surface": "content", "stage": "probe_call_before", "status": "RUNNING"}
    line = module.CHECKPOINT_PREFIX + json.dumps(payload)
    assert module._parse_checkpoint(line) == payload
    f41line = "TEACHER_VISIBILITY_F4_1_CHECKPOINT=" + json.dumps(payload)
    assert module._parse_checkpoint(f41line) == payload


def test_nominal_budget_is_below_ten_minutes():
    assert module.NOMINAL_WORST_CASE_SECONDS < 10 * 60
    module._validate_policy()


def test_aggregate_counts_timeouts_and_structured_workers():
    rows = [
        {"worker_timeout": True, "worker_structured_json": False, "blocked_websocket_attempt_count": 1},
        {"worker_timeout": False, "worker_structured_json": True, "blocked_websocket_attempt_count": 2},
    ]
    result = module._aggregate(rows)
    assert result["worker_timeout_count"] == 1
    assert result["worker_structured_json_count"] == 1
    assert result["blocked_websocket_attempt_count"] == 3


def test_safe_code_removes_free_form_spaces():
    assert module._safe_code("websocket private / text") == "websocket_private_text"
