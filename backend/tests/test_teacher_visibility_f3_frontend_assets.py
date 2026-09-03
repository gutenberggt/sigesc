from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f3_frontend_assets.py"
spec = importlib.util.spec_from_file_location("teacher_visibility_f3_frontend_assets", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_extract_script_sources_deduplicates_and_preserves_order():
    html = """
    <html><body>
      <script defer src="/static/js/runtime.1.js"></script>
      <script src='/static/js/main.abc.js'></script>
      <script src="/static/js/main.abc.js"></script>
    </body></html>
    """
    assert mod.extract_script_sources(html) == [
        "/static/js/runtime.1.js",
        "/static/js/main.abc.js",
    ]


def _good_snapshot():
    return {
        "version": {"git_sha": "a" * 40},
        "service_worker": {
            "expected_release_sha_present": True,
            "placeholder_absent": True,
            "skip_waiting": True,
            "clients_claim": True,
            "sha_cache_name": True,
            "headers": {"cache-control": "no-cache"},
        },
        "javascript": {
            "asset_count": 1,
            "content_bridge_signature": True,
            "attendance_bridge_signature": True,
        },
    }


def test_evaluate_snapshot_passes_only_complete_current_contract():
    result = mod.evaluate_snapshot(_good_snapshot(), "a" * 40)
    assert result["status"] == "PASS"
    assert result["classification"] == "PUBLIC_FRONTEND_ASSETS_CURRENT"
    assert result["failures"] == []


def test_evaluate_snapshot_fails_on_version_and_bridge_drift():
    snapshot = _good_snapshot()
    snapshot["version"]["git_sha"] = "b" * 40
    snapshot["javascript"]["content_bridge_signature"] = False
    result = mod.evaluate_snapshot(snapshot, "a" * 40)
    assert result["status"] == "FAIL"
    assert "PUBLIC_VERSION_SHA_MISMATCH" in result["failures"]
    assert "CONTENT_BRIDGE_SIGNATURE_MISSING" in result["failures"]


def test_evaluate_snapshot_warns_on_immutable_service_worker_cache():
    snapshot = _good_snapshot()
    snapshot["service_worker"]["headers"]["cache-control"] = "public, max-age=31536000, immutable"
    result = mod.evaluate_snapshot(snapshot, "a" * 40)
    assert result["status"] == "PASS"
    assert result["warnings"] == ["SERVICE_WORKER_CACHE_POLICY_IMMUTABLE"]
