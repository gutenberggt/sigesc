from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f4_1_2_browser_render.py"
spec = spec_from_file_location("teacher_visibility_f4_1_2_browser_render", SCRIPT)
mod = module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_policy_budget_stays_below_job_timeout():
    assert mod.EXPECTED_SURFACE_COUNT == 12
    assert mod.NOMINAL_WORST_CASE_SECONDS < 15 * 60
    mod._validate_policy()


def test_stream_process_forwards_checkpoint_before_timeout():
    payload = {
        "class": "6º ANO A",
        "surface": "content",
        "stage": "start",
        "status": "RUNNING",
    }
    code = (
        "import json,time;"
        f"print({mod.LEGACY_CHECKPOINT_PREFIX!r}+json.dumps({payload!r}), flush=True);"
        "time.sleep(5)"
    )
    seen = []
    started = time.monotonic()
    output, timed_out, _rc, last = mod._stream_process(
        [sys.executable, "-u", "-c", code],
        env=dict(os.environ),
        timeout_seconds=0.4,
        on_checkpoint=seen.append,
    )
    elapsed = time.monotonic() - started

    assert timed_out is True
    assert elapsed < 3
    assert seen and seen[0]["stage"] == "start"
    assert last and last["stage"] == "start"
    assert mod.LEGACY_CHECKPOINT_PREFIX in output


def test_stream_process_completes_without_timeout():
    payload = {
        "class": "6º ANO A",
        "surface": "attendance",
        "stage": "complete",
        "status": "PASS",
    }
    code = (
        "import json;"
        f"print({mod.LEGACY_CHECKPOINT_PREFIX!r}+json.dumps({payload!r}), flush=True)"
    )
    seen = []
    _output, timed_out, rc, last = mod._stream_process(
        [sys.executable, "-u", "-c", code],
        env=dict(os.environ),
        timeout_seconds=2,
        on_checkpoint=seen.append,
    )

    assert timed_out is False
    assert rc == 0
    assert seen[-1]["stage"] == "complete"
    assert last and last["status"] == "PASS"


def test_surface_timeout_uses_last_streamed_stage(monkeypatch):
    def fake_stream(*_args, **_kwargs):
        return (
            "",
            True,
            -15,
            {
                "class": "6º ANO A",
                "surface": "content",
                "stage": "start",
                "status": "RUNNING",
            },
        )

    monkeypatch.setattr(mod, "_stream_process", fake_stream)
    target = SimpleNamespace(class_name="6º ANO A")
    result, meta = mod._supervise_surface(target, "content", "a" * 40)

    assert result["status"] == "PROBE_ERROR"
    assert result["product_failures"] == []
    assert result["probe_errors"] == ["CONTENT_WALL_TIMEOUT_AFTER_start"]
    assert meta["worker_timeout"] is True
    assert meta["last_checkpoint_stage"] == "start"


def test_checkpoint_parser_rejects_unrelated_output():
    assert mod._checkpoint_payload("hello") is None
    assert mod._checkpoint_payload("https://example.invalid") is None


def test_boundary_is_inherited_fail_closed():
    boundary = mod.f411._worker_boundary_template()
    assert boundary["production_http_methods"] == ["GET"]
    assert boundary["service_workers_blocked"] is True
    assert boundary["all_api_requests_intercepted_locally"] is True
    assert boundary["live_api_requests"] == 0
    assert boundary["production_writes"] is False


def test_catastrophic_result_never_becomes_product_gap():
    result = mod._catastrophic(RuntimeError("synthetic"))
    assert result["status"] == "INCONCLUSIVE"
    assert result["classification"] == "PUBLIC_BROWSER_RENDER_PROBE_ERROR"
    assert result["product_failures"] == []
    assert result["production_writes"] is False
