#!/usr/bin/env python3
"""F4.1.2 — stream F4.1.1 worker checkpoints under the same hard wall clock.

This iteration changes only the diagnostic supervisor. It runs the already-reviewed
F4.1.1 worker unchanged, consumes its stdout incrementally, forwards metadata-only
checkpoints while the child is alive, and records the last observed stage on timeout.

Timeout/crash/no JSON remains PROBE_ERROR, never PRODUCT_GAP. Production access
remains public GET only with the F4 synthetic/local API boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
from typing import Any, Callable

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import teacher_visibility_f4_browser_render as f4  # noqa: E402
import teacher_visibility_f4_1_browser_render as f41  # noqa: E402
import teacher_visibility_f4_1_1_browser_render as f411  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_2_PUBLIC_BROWSER_RENDER_V4"
FINAL_PREFIX = "TEACHER_VISIBILITY_F4_1_2_JSON="
CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_2_CHECKPOINT="
LEGACY_CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_CHECKPOINT="

SURFACE_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_2_SURFACE_WALL_TIMEOUT_SECONDS", "40"))
WORKER_KILL_GRACE_SECONDS = float(os.environ.get("F4_1_2_KILL_GRACE_SECONDS", "2"))
PUBLIC_VERSION_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_2_PUBLIC_VERSION_WALL_TIMEOUT_SECONDS", "35"))
EXPECTED_SURFACE_COUNT = len(f4.TARGETS) * 2
NOMINAL_WORST_CASE_SECONDS = (
    EXPECTED_SURFACE_COUNT * (SURFACE_WALL_TIMEOUT_SECONDS + WORKER_KILL_GRACE_SECONDS)
    + PUBLIC_VERSION_WALL_TIMEOUT_SECONDS
    + WORKER_KILL_GRACE_SECONDS
)


def checkpoint(target_class: str, surface: str, stage: str, status: str) -> None:
    payload = {"class": target_class, "surface": surface, "stage": stage, "status": status}
    print(CHECKPOINT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _worker_env(expected_sha: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["EXPECTED_PRODUCTION_SHA"] = expected_sha
    # Keep exactly the F4.1.1 runtime probe policy.
    env["F4_1_NAVIGATION_TIMEOUT_MS"] = os.environ.get("F4_1_2_NAVIGATION_TIMEOUT_MS", "10000")
    env["F4_1_ACTION_TIMEOUT_MS"] = os.environ.get("F4_1_2_ACTION_TIMEOUT_MS", "5000")
    env["F4_1_POLL_TIMEOUT_SECONDS"] = os.environ.get("F4_1_2_POLL_TIMEOUT_SECONDS", "4")
    return env


def _kill_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + WORKER_KILL_GRACE_SECONDS
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _checkpoint_payload(line: str) -> dict[str, Any] | None:
    if not line.startswith(LEGACY_CHECKPOINT_PREFIX):
        return None
    try:
        payload = json.loads(line[len(LEGACY_CHECKPOINT_PREFIX):])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _forward(payload: dict[str, Any]) -> None:
    # Explicitly whitelist metadata-only fields.
    checkpoint(
        str(payload.get("class") or "UNKNOWN_CLASS"),
        str(payload.get("surface") or "unknown"),
        str(payload.get("stage") or "unknown"),
        str(payload.get("status") or "UNKNOWN"),
    )


def _stream_process(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: float,
    on_checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, bool, int | None, dict[str, Any] | None]:
    """Consume stdout incrementally while enforcing a process-group wall clock."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        start_new_session=True,
    )
    if proc.stdout is None:
        _kill_group(proc)
        return "", False, proc.returncode, None

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    lines: list[str] = []
    last_checkpoint: dict[str, Any] | None = None
    timed_out = False

    def accept(line: str) -> None:
        nonlocal last_checkpoint
        clean = line.rstrip("\r\n")
        lines.append(clean)
        payload = _checkpoint_payload(clean)
        if payload is not None:
            last_checkpoint = payload
            if on_checkpoint is not None:
                on_checkpoint(payload)

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = proc.poll() is None
                break

            for key, _ in selector.select(timeout=min(0.25, remaining)):
                line = key.fileobj.readline()
                if line:
                    accept(line)

            if proc.poll() is not None:
                for line in proc.stdout:
                    accept(line)
                break

        if timed_out:
            _kill_group(proc)
            drain_deadline = time.monotonic() + WORKER_KILL_GRACE_SECONDS
            while time.monotonic() < drain_deadline:
                events = selector.select(timeout=0.05)
                if not events:
                    if proc.poll() is not None:
                        break
                    continue
                for key, _ in events:
                    line = key.fileobj.readline()
                    if line:
                        accept(line)
    finally:
        try:
            selector.unregister(proc.stdout)
        except Exception:
            pass
        selector.close()
        try:
            proc.stdout.close()
        except Exception:
            pass

    return "\n".join(lines), timed_out, proc.returncode, last_checkpoint


def _extract_worker(output: str) -> dict[str, Any] | None:
    return f411._extract_worker_json(output)


def _supervise_surface(target: Any, surface: str, expected_sha: str) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    checkpoint(target.class_name, surface, "worker_start", "RUNNING")
    cmd = [
        sys.executable,
        "-u",
        str(THIS_DIR / "teacher_visibility_f4_1_1_browser_render.py"),
        "--worker",
        "--class-name",
        target.class_name,
        "--surface",
        surface,
    ]
    output, timed_out, returncode, last = _stream_process(
        cmd,
        env=_worker_env(expected_sha),
        timeout_seconds=SURFACE_WALL_TIMEOUT_SECONDS,
        on_checkpoint=_forward,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    last_stage = str((last or {}).get("stage") or "NO_CHECKPOINT")

    if timed_out:
        checkpoint(target.class_name, surface, "wall_timeout", "PROBE_ERROR")
        code = f"WALL_TIMEOUT_AFTER_{f411._safe_code(last_stage)}"
        return (
            f411._probe_error_surface(surface, code, elapsed_ms=elapsed_ms),
            {
                "worker_timeout": True,
                "worker_exit_code": returncode,
                "worker_structured_json": False,
                "last_checkpoint_stage": last_stage,
            },
        )

    worker = _extract_worker(output)
    if returncode != 0:
        checkpoint(target.class_name, surface, "worker_exit", "PROBE_ERROR")
        return (
            f411._probe_error_surface(surface, f"WORKER_EXIT_{returncode}", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": returncode,
                "worker_structured_json": worker is not None,
                "last_checkpoint_stage": last_stage,
            },
        )

    if not worker or worker.get("schema") != f411.SCHEMA:
        checkpoint(target.class_name, surface, "worker_json", "PROBE_ERROR")
        return (
            f411._probe_error_surface(surface, "WORKER_NO_STRUCTURED_JSON", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": returncode,
                "worker_structured_json": False,
                "last_checkpoint_stage": last_stage,
            },
        )

    result = worker.get("surface_result")
    if not isinstance(result, dict):
        checkpoint(target.class_name, surface, "worker_result", "PROBE_ERROR")
        return (
            f411._probe_error_surface(surface, "WORKER_RESULT_INVALID", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": returncode,
                "worker_structured_json": True,
                "last_checkpoint_stage": last_stage,
            },
        )

    result = dict(result)
    result["elapsed_ms"] = elapsed_ms
    checkpoint(target.class_name, surface, "worker_complete", str(result.get("status") or "UNKNOWN"))
    return (
        result,
        {
            "worker_timeout": False,
            "worker_exit_code": returncode,
            "worker_structured_json": True,
            "last_checkpoint_stage": last_stage,
            "intercepted_api_request_count": int(worker.get("intercepted_api_request_count") or 0),
            "unknown_api_fixture_count": int(worker.get("unknown_api_fixture_count") or 0),
            "blocked_non_get_attempt_count": int(worker.get("blocked_non_get_attempt_count") or 0),
            "blocked_dynamic_get_attempt_count": int(worker.get("blocked_dynamic_get_attempt_count") or 0),
            "blocked_websocket_attempt_count": int(worker.get("blocked_websocket_attempt_count") or 0),
        },
    )


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = f411._aggregate_worker_meta(rows)
    counts: dict[str, int] = {}
    for row in rows:
        stage = str(row.get("last_checkpoint_stage") or "NO_CHECKPOINT")
        counts[stage] = counts.get(stage, 0) + 1
    result["last_checkpoint_stage_counts"] = dict(sorted(counts.items()))
    return result


def _validate_policy() -> None:
    if SURFACE_WALL_TIMEOUT_SECONDS < 5 or SURFACE_WALL_TIMEOUT_SECONDS > 60:
        raise RuntimeError("F4_1_2_SURFACE_WALL_TIMEOUT_OUT_OF_RANGE")
    if WORKER_KILL_GRACE_SECONDS < 0 or WORKER_KILL_GRACE_SECONDS > 5:
        raise RuntimeError("F4_1_2_KILL_GRACE_OUT_OF_RANGE")
    if NOMINAL_WORST_CASE_SECONDS >= 15 * 60:
        raise RuntimeError("F4_1_2_WORST_CASE_EXCEEDS_JOB_TIMEOUT")


def run() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("F4_1_2_EXPECTED_SHA_INVALID")
    _validate_policy()

    # Reuse the F4.1.1 version worker; it already completed in <1s in run 33901292880.
    public_sha = f411._validate_public_version_with_wall_clock(expected_sha)
    pairs: list[dict[str, Any]] = []
    workers: list[dict[str, Any]] = []

    for target in f4.TARGETS:
        pair = f41._new_pair(target)
        pairs.append(pair)
        for surface in ("content", "attendance"):
            surface_result, meta = _supervise_surface(target, surface, expected_sha)
            pair[surface] = surface_result
            workers.append({"class": target.class_name, "surface": surface, **meta})

    evaluation = f41.evaluate_pairs(pairs, expected_pairs=len(f4.TARGETS))
    return {
        "schema": SCHEMA,
        "target": "production-public-frontend-with-local-synthetic-api",
        "expected_production_sha": expected_sha,
        "public_version_sha": public_sha,
        "academic_year": f4.ACADEMIC_YEAR,
        "target_school": f4.TARGET_SCHOOL,
        "target_pair_count": len(f4.TARGETS),
        "probe_date_count": len(f4.PROBE_DATES),
        "probe_policy": {
            "process_isolation": True,
            "surface_isolation": True,
            "surface_stdout_streaming": True,
            "incremental_checkpoint_forwarding": True,
            "surface_wall_timeout_seconds": SURFACE_WALL_TIMEOUT_SECONDS,
            "worker_kill_grace_seconds": WORKER_KILL_GRACE_SECONDS,
            "timeout_is_product_gap": False,
            "nominal_worst_case_seconds": NOMINAL_WORST_CASE_SECONDS,
        },
        "pairs": pairs,
        "workers": workers,
        **_aggregate(workers),
        **f411._worker_boundary_template(),
        **evaluation,
    }


def _catastrophic(exc: BaseException) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "target": "production-public-frontend-with-local-synthetic-api",
        "status": "INCONCLUSIVE",
        "classification": "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
        "probe_errors": [f"RUNNER:{f411._safe_code(exc)}"],
        "product_failures": [],
        "pairs": [],
        "workers": [],
        "probe_policy": {
            "process_isolation": True,
            "surface_isolation": True,
            "surface_stdout_streaming": True,
            "timeout_is_product_gap": False,
        },
        **f411._worker_boundary_template(),
        "catastrophic_probe_error": True,
    }


def main() -> int:
    try:
        result = run()
    except BaseException as exc:
        result = _catastrophic(exc)
    print(FINAL_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
