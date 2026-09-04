#!/usr/bin/env python3
"""TEACHER-VISIBILITY-F4.1.1 — browser→DOM probe with hard wall-clock isolation.

Purpose:
- keep the exact F4/F4.1 diagnostic scope and read-only production boundary;
- prevent a Playwright call or routing callback from consuming the whole GitHub job;
- isolate each class/surface in its own OS process;
- classify any worker timeout/crash as PROBE_ERROR, never as PRODUCT_GAP.

No product code, data, authentication, database, or production write path is used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.parse
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import teacher_visibility_f4_browser_render as f4  # noqa: E402
import teacher_visibility_f4_1_browser_render as f41  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_1_PUBLIC_BROWSER_RENDER_V3"
WORKER_PREFIX = "TEACHER_VISIBILITY_F4_1_1_WORKER_JSON="
FINAL_PREFIX = "TEACHER_VISIBILITY_F4_1_1_JSON="
CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_1_CHECKPOINT="

SURFACE_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_1_SURFACE_WALL_TIMEOUT_SECONDS", "40"))
WORKER_NAVIGATION_TIMEOUT_MS = int(os.environ.get("F4_1_1_NAVIGATION_TIMEOUT_MS", "10000"))
WORKER_ACTION_TIMEOUT_MS = int(os.environ.get("F4_1_1_ACTION_TIMEOUT_MS", "5000"))
WORKER_POLL_TIMEOUT_SECONDS = float(os.environ.get("F4_1_1_POLL_TIMEOUT_SECONDS", "4"))
WORKER_KILL_GRACE_SECONDS = float(os.environ.get("F4_1_1_KILL_GRACE_SECONDS", "2"))
PUBLIC_VERSION_TIMEOUT_BUDGET_SECONDS = 35
EXPECTED_SURFACE_COUNT = len(f4.TARGETS) * 2
NOMINAL_WORST_CASE_SECONDS = EXPECTED_SURFACE_COUNT * SURFACE_WALL_TIMEOUT_SECONDS + PUBLIC_VERSION_TIMEOUT_BUDGET_SECONDS


def checkpoint(target_class: str, surface: str, stage: str, status: str) -> None:
    payload = {
        "class": target_class,
        "surface": surface,
        "stage": stage,
        "status": status,
    }
    print(CHECKPOINT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _safe_code(value: BaseException | str) -> str:
    if isinstance(value, BaseException):
        value = type(value).__name__
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_")
    return (normalized or "UNKNOWN")[:100]


def _blank_pair(target: Any) -> dict[str, Any]:
    return f41._new_pair(target)


def _probe_error_surface(surface_name: str, code: str, *, elapsed_ms: int = 0) -> dict[str, Any]:
    return {
        "status": "PROBE_ERROR",
        "prefill_ok": False,
        "visible_probe_dates": 0,
        "product_failures": [],
        "probe_errors": [f"{surface_name.upper()}_{_safe_code(code)}"],
        "elapsed_ms": max(0, int(elapsed_ms)),
    }


def _worker_boundary_template() -> dict[str, Any]:
    return {
        "production_http_methods": ["GET"],
        "service_workers_blocked": True,
        "all_api_requests_intercepted_locally": True,
        "dynamic_non_api_gets_allowlisted": True,
        "websockets_blocked": True,
        "live_api_requests": 0,
        "real_authentication_used": False,
        "database_access": False,
        "student_data_read": False,
        "attendance_records_read": False,
        "pedagogical_text_read": False,
        "production_writes": False,
    }


def _find_target(class_name: str) -> Any:
    for target in f4.TARGETS:
        if target.class_name == class_name:
            return target
    raise ValueError("UNKNOWN_TARGET_CLASS")


def _configure_worker_probe_policy() -> None:
    # F4.1 reads module constants during import. Override the imported values only
    # inside this short-lived worker process; F4/F4.1 source remains untouched.
    f41.NAVIGATION_TIMEOUT_MS = WORKER_NAVIGATION_TIMEOUT_MS
    f41.ACTION_TIMEOUT_MS = WORKER_ACTION_TIMEOUT_MS
    f41.POLL_TIMEOUT_SECONDS = WORKER_POLL_TIMEOUT_SECONDS


def _run_worker(class_name: str, surface_name: str) -> dict[str, Any]:
    if surface_name not in {"content", "attendance"}:
        raise ValueError("INVALID_SURFACE")

    target = _find_target(class_name)
    _configure_worker_probe_policy()

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    base_origin = urllib.parse.urlsplit(f4.BASE_URL)
    intercepted_api: list[str] = []
    fixture_keys: list[str] = []
    blocked_non_get: list[str] = []
    blocked_dynamic_get: list[str] = []
    blocked_websocket: list[str] = []
    pair = _blank_pair(target)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.set_default_timeout(WORKER_ACTION_TIMEOUT_MS)
        context.add_init_script(f4._init_script())

        def route_handler(route: Any, request: Any) -> None:
            method = request.method.upper()
            parsed = urllib.parse.urlsplit(request.url)

            if method != "GET":
                blocked_non_get.append(f"{method} {parsed.path}")
                route.abort()
                return

            if "/api/" in parsed.path:
                status, body, fixture_key = f4.fixture_for_api(request.url)
                intercepted_api.append(parsed.path)
                fixture_keys.append(fixture_key)
                route.fulfill(
                    status=status,
                    content_type="application/json; charset=utf-8",
                    body=json.dumps(body, ensure_ascii=False),
                )
                return

            if request.resource_type in {"xhr", "fetch"}:
                same_public_origin = (
                    parsed.scheme == base_origin.scheme
                    and parsed.netloc == base_origin.netloc
                )
                if same_public_origin and parsed.path in f4.PUBLIC_DYNAMIC_GET_PATHS:
                    route.continue_()
                    return
                blocked_dynamic_get.append(f"{request.resource_type} {parsed.netloc}{parsed.path}")
                route.abort()
                return

            route.continue_()

        def websocket_handler(web_socket_route: Any) -> None:
            blocked_websocket.append(web_socket_route.url)
            web_socket_route.close(code=1000, reason="F4.1.1 read-only audit blocks WebSockets")

        context.route("**/*", route_handler)
        context.route_web_socket("**/*", websocket_handler)

        page = context.new_page()
        started = time.monotonic()
        try:
            if surface_name == "content":
                f41._probe_content(page, target, pair)
            else:
                f41._probe_attendance(page, target, pair)
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    return {
        "schema": SCHEMA,
        "worker": True,
        "class": class_name,
        "surface": surface_name,
        "surface_result": pair[surface_name],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **f41._boundary_metadata(
            intercepted_api=intercepted_api,
            fixture_keys=fixture_keys,
            blocked_non_get=blocked_non_get,
            blocked_dynamic_get=blocked_dynamic_get,
            blocked_websocket=blocked_websocket,
        ),
    }


def _worker_env(expected_sha: str) -> dict[str, str]:
    env = dict(os.environ)
    env["EXPECTED_PRODUCTION_SHA"] = expected_sha
    env["F4_1_NAVIGATION_TIMEOUT_MS"] = str(WORKER_NAVIGATION_TIMEOUT_MS)
    env["F4_1_ACTION_TIMEOUT_MS"] = str(WORKER_ACTION_TIMEOUT_MS)
    env["F4_1_POLL_TIMEOUT_SECONDS"] = str(WORKER_POLL_TIMEOUT_SECONDS)
    return env


def _kill_worker_group(proc: subprocess.Popen[str]) -> None:
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


def _extract_worker_json(output: str) -> dict[str, Any] | None:
    payload: dict[str, Any] | None = None
    for raw in output.splitlines():
        if raw.startswith(WORKER_PREFIX):
            try:
                candidate = json.loads(raw[len(WORKER_PREFIX):])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                payload = candidate
    return payload


def _forward_worker_checkpoints(output: str) -> None:
    for raw in output.splitlines():
        if raw.startswith("TEACHER_VISIBILITY_F4_1_CHECKPOINT="):
            print(raw.replace(
                "TEACHER_VISIBILITY_F4_1_CHECKPOINT=",
                CHECKPOINT_PREFIX,
                1,
            ), flush=True)


def _supervise_surface(target: Any, surface_name: str, expected_sha: str) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    checkpoint(target.class_name, surface_name, "worker_start", "RUNNING")

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--class-name",
        target.class_name,
        "--surface",
        surface_name,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_worker_env(expected_sha),
        start_new_session=True,
    )

    try:
        stdout, _ = proc.communicate(timeout=SURFACE_WALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if isinstance(exc.output, str):
            partial = exc.output
        _kill_worker_group(proc)
        try:
            remaining, _ = proc.communicate(timeout=WORKER_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            remaining = ""
        output = partial + (remaining or "")
        _forward_worker_checkpoints(output)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        checkpoint(target.class_name, surface_name, "wall_timeout", "PROBE_ERROR")
        return (
            _probe_error_surface(surface_name, "WALL_TIMEOUT", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": True,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": False,
            },
        )

    _forward_worker_checkpoints(stdout or "")
    elapsed_ms = int((time.monotonic() - started) * 1000)
    worker = _extract_worker_json(stdout or "")

    if proc.returncode != 0:
        checkpoint(target.class_name, surface_name, "worker_exit", "PROBE_ERROR")
        return (
            _probe_error_surface(surface_name, f"WORKER_EXIT_{proc.returncode}", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": worker is not None,
            },
        )

    if not worker or worker.get("schema") != SCHEMA:
        checkpoint(target.class_name, surface_name, "worker_json", "PROBE_ERROR")
        return (
            _probe_error_surface(surface_name, "WORKER_NO_STRUCTURED_JSON", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": False,
            },
        )

    result = worker.get("surface_result")
    if not isinstance(result, dict):
        checkpoint(target.class_name, surface_name, "worker_result", "PROBE_ERROR")
        return (
            _probe_error_surface(surface_name, "WORKER_RESULT_INVALID", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": True,
            },
        )

    result = dict(result)
    result["elapsed_ms"] = elapsed_ms
    checkpoint(target.class_name, surface_name, "worker_complete", str(result.get("status") or "UNKNOWN"))
    return (
        result,
        {
            "worker_timeout": False,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": True,
            "intercepted_api_request_count": int(worker.get("intercepted_api_request_count") or 0),
            "unknown_api_fixture_count": int(worker.get("unknown_api_fixture_count") or 0),
            "blocked_non_get_attempt_count": int(worker.get("blocked_non_get_attempt_count") or 0),
            "blocked_dynamic_get_attempt_count": int(worker.get("blocked_dynamic_get_attempt_count") or 0),
            "blocked_websocket_attempt_count": int(worker.get("blocked_websocket_attempt_count") or 0),
        },
    )


def _aggregate_worker_meta(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "worker_timeout_count": sum(1 for row in rows if row.get("worker_timeout")),
        "worker_structured_json_count": sum(1 for row in rows if row.get("worker_structured_json")),
        "intercepted_api_request_count": sum(int(row.get("intercepted_api_request_count") or 0) for row in rows),
        "unknown_api_fixture_count": sum(int(row.get("unknown_api_fixture_count") or 0) for row in rows),
        "blocked_non_get_attempt_count": sum(int(row.get("blocked_non_get_attempt_count") or 0) for row in rows),
        "blocked_dynamic_get_attempt_count": sum(int(row.get("blocked_dynamic_get_attempt_count") or 0) for row in rows),
        "blocked_websocket_attempt_count": sum(int(row.get("blocked_websocket_attempt_count") or 0) for row in rows),
    }


def run_supervisor() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("TEACHER_VISIBILITY_F4_1_1_EXPECTED_SHA_INVALID")

    if SURFACE_WALL_TIMEOUT_SECONDS < 5 or SURFACE_WALL_TIMEOUT_SECONDS > 60:
        raise RuntimeError("TEACHER_VISIBILITY_F4_1_1_WALL_TIMEOUT_OUT_OF_RANGE")

    public_sha = f4._public_version(expected_sha)
    pairs: list[dict[str, Any]] = []
    worker_meta: list[dict[str, Any]] = []

    for target in f4.TARGETS:
        pair = _blank_pair(target)
        pairs.append(pair)
        for surface_name in ("content", "attendance"):
            surface_result, meta = _supervise_surface(target, surface_name, expected_sha)
            pair[surface_name] = surface_result
            worker_meta.append({
                "class": target.class_name,
                "surface": surface_name,
                **meta,
            })

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
            "surface_wall_timeout_seconds": SURFACE_WALL_TIMEOUT_SECONDS,
            "worker_navigation_timeout_ms": WORKER_NAVIGATION_TIMEOUT_MS,
            "worker_action_timeout_ms": WORKER_ACTION_TIMEOUT_MS,
            "worker_poll_timeout_seconds": WORKER_POLL_TIMEOUT_SECONDS,
            "checkpoint_streaming": True,
            "timeout_is_product_gap": False,
            "global_job_timeout_must_not_be_primary_control": True,
            "nominal_worst_case_seconds": NOMINAL_WORST_CASE_SECONDS,
        },
        "pairs": pairs,
        "workers": worker_meta,
        **_aggregate_worker_meta(worker_meta),
        **_worker_boundary_template(),
        **evaluation,
    }


def _catastrophic_result(exc: BaseException) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "target": "production-public-frontend-with-local-synthetic-api",
        "status": "INCONCLUSIVE",
        "classification": "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
        "probe_errors": [f"RUNNER:{_safe_code(exc)}"],
        "product_failures": [],
        "pairs": [],
        "workers": [],
        "probe_policy": {
            "process_isolation": True,
            "surface_isolation": True,
            "surface_wall_timeout_seconds": SURFACE_WALL_TIMEOUT_SECONDS,
            "timeout_is_product_gap": False,
        },
        **_worker_boundary_template(),
        "catastrophic_probe_error": True,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--class-name")
    parser.add_argument("--surface", choices=("content", "attendance"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.worker:
        try:
            if not args.class_name or not args.surface:
                raise ValueError("WORKER_ARGUMENTS_REQUIRED")
            result = _run_worker(args.class_name, args.surface)
        except BaseException as exc:
            surface_name = args.surface or "content"
            result = {
                "schema": SCHEMA,
                "worker": True,
                "class": args.class_name or "UNKNOWN_CLASS",
                "surface": surface_name,
                "surface_result": _probe_error_surface(
                    surface_name,
                    f"WORKER_EXCEPTION_{_safe_code(exc)}",
                ),
                "worker_error": _safe_code(exc),
                **_worker_boundary_template(),
            }
        print(WORKER_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return 0

    try:
        result = run_supervisor()
    except BaseException as exc:
        result = _catastrophic_result(exc)
    print(FINAL_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
