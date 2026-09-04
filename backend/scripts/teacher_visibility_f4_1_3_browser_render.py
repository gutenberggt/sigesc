#!/usr/bin/env python3
"""F4.1.3 — decompose page.goto / route handling without touching product.

Scope is intentionally narrow. This probe does NOT assert React/product health.
It distinguishes browser/network baseline, routed static navigation, app-document
navigation with all subresources blocked, and the full F4 read-only route policy.

Production boundary:
- public resources are GET-only;
- no real application API request is ever allowed to production;
- non-GET methods are aborted before network;
- full-app /api/ requests are fulfilled locally from the F4 synthetic fixtures;
- Service Workers are blocked and WebSockets are closed locally;
- no real auth, Mongo, student data, attendance.records, pedagogical text or write.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import selectors
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
import teacher_visibility_f4_1_1_browser_render as f411  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_3_GOTO_ROUTE_DECOMPOSITION_V5"
WORKER_PREFIX = "TEACHER_VISIBILITY_F4_1_3_WORKER_JSON="
FINAL_PREFIX = "TEACHER_VISIBILITY_F4_1_3_JSON="
CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_3_CHECKPOINT="

CASE_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_3_CASE_WALL_TIMEOUT_SECONDS", "25"))
GOTO_TIMEOUT_MS = int(os.environ.get("F4_1_3_GOTO_TIMEOUT_MS", "8000"))
KILL_GRACE_SECONDS = float(os.environ.get("F4_1_3_KILL_GRACE_SECONDS", "2"))
PUBLIC_VERSION_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_3_PUBLIC_VERSION_WALL_TIMEOUT_SECONDS", "35"))

CASES = (
    "STATIC_DIRECT",
    "STATIC_ROUTED_CONTINUE",
    "APP_DOCUMENT_ONLY_CONTENT",
    "APP_FULL_CONTENT",
    "APP_FULL_ATTENDANCE",
)
NOMINAL_WORST_CASE_SECONDS = (
    len(CASES) * (CASE_WALL_TIMEOUT_SECONDS + KILL_GRACE_SECONDS)
    + PUBLIC_VERSION_WALL_TIMEOUT_SECONDS
    + KILL_GRACE_SECONDS
)
REPRESENTATIVE_TARGET = f4.TARGETS[0]


def _safe_code(value: BaseException | str) -> str:
    if isinstance(value, BaseException):
        value = type(value).__name__
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_")
    return (normalized or "UNKNOWN")[:120]


def checkpoint(case: str, stage: str, status: str, resource_type: str | None = None) -> None:
    payload: dict[str, Any] = {"case": case, "stage": stage, "status": status}
    if resource_type:
        payload["resource_type"] = resource_type
    print(CHECKPOINT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _boundary() -> dict[str, Any]:
    return {
        "production_http_methods": ["GET"],
        "service_workers_blocked": True,
        "all_api_requests_intercepted_locally": True,
        "websockets_blocked": True,
        "live_api_requests": 0,
        "real_authentication_used": False,
        "database_access": False,
        "student_data_read": False,
        "attendance_records_read": False,
        "pedagogical_text_read": False,
        "production_writes": False,
        "product_gap_claimed": False,
    }


def _case_url(case: str) -> str:
    if case in {"STATIC_DIRECT", "STATIC_ROUTED_CONTINUE"}:
        return f"{f4.BASE_URL}/version.json?f413={int(time.time())}"
    if case in {"APP_DOCUMENT_ONLY_CONTENT", "APP_FULL_CONTENT"}:
        return f4._target_url("/professor/objetos-conhecimento", REPRESENTATIVE_TARGET)
    if case == "APP_FULL_ATTENDANCE":
        return f4._target_url("/professor/frequencia", REPRESENTATIVE_TARGET)
    raise ValueError("UNKNOWN_CASE")


def _case_mode(case: str) -> str:
    if case == "STATIC_DIRECT":
        return "direct"
    if case == "STATIC_ROUTED_CONTINUE":
        return "static_routed"
    if case == "APP_DOCUMENT_ONLY_CONTENT":
        return "document_only"
    if case in {"APP_FULL_CONTENT", "APP_FULL_ATTENDANCE"}:
        return "full"
    raise ValueError("UNKNOWN_CASE")


def _run_case_worker(case: str) -> dict[str, Any]:
    if case not in CASES:
        raise ValueError("UNKNOWN_CASE")

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    mode = _case_mode(case)
    target_url = _case_url(case)
    base_origin = urllib.parse.urlsplit(f4.BASE_URL)
    route_counts: dict[str, int] = {}
    route_actions: dict[str, int] = {}
    emitted: set[str] = set()

    def emit_once(stage: str, resource_type: str | None = None) -> None:
        key = f"{stage}:{resource_type or ''}"
        if key not in emitted:
            emitted.add(key)
            checkpoint(case, stage, "RUNNING", resource_type)

    checkpoint(case, "sync_playwright_before", "RUNNING")
    with sync_playwright() as playwright:
        checkpoint(case, "sync_playwright_after", "PASS")
        checkpoint(case, "browser_launch_before", "RUNNING")
        browser = playwright.chromium.launch(headless=True)
        checkpoint(case, "browser_launch_after", "PASS")

        checkpoint(case, "context_create_before", "RUNNING")
        context = browser.new_context(service_workers="block")
        context.set_default_timeout(5000)
        if mode in {"document_only", "full"}:
            context.add_init_script(f4._init_script())
        checkpoint(case, "context_create_after", "PASS")

        def route_handler(route: Any, request: Any) -> None:
            resource_type = str(request.resource_type or "unknown")
            route_counts[resource_type] = route_counts.get(resource_type, 0) + 1
            emit_once("route_enter", resource_type)

            method = request.method.upper()
            parsed = urllib.parse.urlsplit(request.url)
            if method != "GET":
                emit_once("route_abort_before_non_get", resource_type)
                route_actions["abort_non_get"] = route_actions.get("abort_non_get", 0) + 1
                route.abort()
                emit_once("route_abort_after_non_get", resource_type)
                return

            if mode == "document_only":
                if resource_type == "document":
                    emit_once("route_continue_before_document", resource_type)
                    route_actions["continue_document"] = route_actions.get("continue_document", 0) + 1
                    route.continue_()
                    emit_once("route_continue_after_document", resource_type)
                else:
                    emit_once("route_abort_before_subresource", resource_type)
                    route_actions["abort_subresource"] = route_actions.get("abort_subresource", 0) + 1
                    route.abort()
                    emit_once("route_abort_after_subresource", resource_type)
                return

            if mode == "full":
                if "/api/" in parsed.path:
                    emit_once("route_fixture_before_api", resource_type)
                    status, body, _fixture_key = f4.fixture_for_api(request.url)
                    route_actions["fulfill_api"] = route_actions.get("fulfill_api", 0) + 1
                    route.fulfill(
                        status=status,
                        content_type="application/json; charset=utf-8",
                        body=json.dumps(body, ensure_ascii=False),
                    )
                    emit_once("route_fixture_after_api", resource_type)
                    return

                if resource_type in {"xhr", "fetch"}:
                    same_public_origin = (
                        parsed.scheme == base_origin.scheme
                        and parsed.netloc == base_origin.netloc
                    )
                    if same_public_origin and parsed.path in f4.PUBLIC_DYNAMIC_GET_PATHS:
                        emit_once("route_continue_before_dynamic", resource_type)
                        route_actions["continue_dynamic"] = route_actions.get("continue_dynamic", 0) + 1
                        route.continue_()
                        emit_once("route_continue_after_dynamic", resource_type)
                        return
                    emit_once("route_abort_before_dynamic", resource_type)
                    route_actions["abort_dynamic"] = route_actions.get("abort_dynamic", 0) + 1
                    route.abort()
                    emit_once("route_abort_after_dynamic", resource_type)
                    return

            # static_routed and non-dynamic full-app assets both reach this branch.
            emit_once("route_continue_before_public", resource_type)
            route_actions["continue_public"] = route_actions.get("continue_public", 0) + 1
            route.continue_()
            emit_once("route_continue_after_public", resource_type)

        def websocket_handler(web_socket_route: Any) -> None:
            emit_once("websocket_close_before", "websocket")
            web_socket_route.close(code=1000, reason="F4.1.3 read-only route decomposition")
            emit_once("websocket_close_after", "websocket")

        if mode != "direct":
            checkpoint(case, "route_install_before", "RUNNING")
            context.route("**/*", route_handler)
            context.route_web_socket("**/*", websocket_handler)
            checkpoint(case, "route_install_after", "PASS")

        checkpoint(case, "page_create_before", "RUNNING")
        page = context.new_page()
        checkpoint(case, "page_create_after", "PASS")

        started = time.monotonic()
        result_status = "PASS"
        error_code: str | None = None
        try:
            checkpoint(case, "goto_before", "RUNNING")
            page.goto(target_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            checkpoint(case, "goto_after", "PASS")
        except Exception as exc:  # diagnostic path only
            result_status = "PROBE_ERROR"
            error_code = f"GOTO_{_safe_code(exc)}"
            checkpoint(case, "goto_exception", "PROBE_ERROR")
        elapsed_ms = int((time.monotonic() - started) * 1000)

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
        "case": case,
        "mode": mode,
        "status": result_status,
        "error_code": error_code,
        "elapsed_ms": elapsed_ms,
        "route_counts": dict(sorted(route_counts.items())),
        "route_actions": dict(sorted(route_actions.items())),
        **_boundary(),
    }


def _worker_env(expected_sha: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["EXPECTED_PRODUCTION_SHA"] = expected_sha
    return env


def _kill_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _parse_checkpoint(line: str) -> dict[str, Any] | None:
    if not line.startswith(CHECKPOINT_PREFIX):
        return None
    try:
        payload = json.loads(line[len(CHECKPOINT_PREFIX):])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_worker(output: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for line in output.splitlines():
        if line.startswith(WORKER_PREFIX):
            try:
                candidate = json.loads(line[len(WORKER_PREFIX):])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                found = candidate
    return found


def _stream_case(case: str, expected_sha: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--worker",
        "--case",
        case,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_worker_env(expected_sha),
        start_new_session=True,
    )
    if proc.stdout is None:
        _kill_group(proc)
        return {
            "case": case,
            "status": "PROBE_ERROR",
            "error_code": "NO_STDOUT",
            "timed_out": False,
            "last_checkpoint_stage": "NO_CHECKPOINT",
        }

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + CASE_WALL_TIMEOUT_SECONDS
    lines: list[str] = []
    last: dict[str, Any] | None = None
    timed_out = False

    def accept(raw: str) -> None:
        nonlocal last
        clean = raw.rstrip("\r\n")
        lines.append(clean)
        payload = _parse_checkpoint(clean)
        if payload is not None:
            last = payload
            print(clean, flush=True)

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
            drain_deadline = time.monotonic() + KILL_GRACE_SECONDS
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

    last_stage = str((last or {}).get("stage") or "NO_CHECKPOINT")
    if timed_out:
        checkpoint(case, "wall_timeout", "PROBE_ERROR")
        return {
            "case": case,
            "status": "PROBE_ERROR",
            "error_code": f"WALL_TIMEOUT_AFTER_{_safe_code(last_stage)}",
            "timed_out": True,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": False,
            "last_checkpoint_stage": last_stage,
        }

    output = "\n".join(lines)
    worker = _extract_worker(output)
    if proc.returncode != 0:
        return {
            "case": case,
            "status": "PROBE_ERROR",
            "error_code": f"WORKER_EXIT_{proc.returncode}",
            "timed_out": False,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": worker is not None,
            "last_checkpoint_stage": last_stage,
        }
    if not worker or worker.get("schema") != SCHEMA:
        return {
            "case": case,
            "status": "PROBE_ERROR",
            "error_code": "WORKER_NO_STRUCTURED_JSON",
            "timed_out": False,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": False,
            "last_checkpoint_stage": last_stage,
        }

    return {
        **worker,
        "timed_out": False,
        "worker_exit_code": proc.returncode,
        "worker_structured_json": True,
        "last_checkpoint_stage": last_stage,
    }


def diagnose(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {str(row.get("case")): row for row in cases}
    first_failure: dict[str, Any] | None = None
    for name in CASES:
        row = by_name.get(name) or {}
        if row.get("status") != "PASS":
            first_failure = row
            break

    if first_failure is None:
        return {
            "diagnosis_code": "GOTO_ROUTE_DECOMPOSITION_HEALTHY",
            "first_failure_case": None,
            "first_failure_stage": None,
        }

    stage = str(first_failure.get("last_checkpoint_stage") or "NO_CHECKPOINT")
    case = str(first_failure.get("case") or "UNKNOWN_CASE")
    if "route_continue_before" in stage:
        code = "ROUTE_CONTINUE_CALL_STALL"
    elif "route_abort_before" in stage:
        code = "ROUTE_ABORT_CALL_STALL"
    elif "route_fixture_before_api" in stage:
        code = "ROUTE_FULFILL_API_CALL_STALL"
    elif stage == "goto_before":
        code = "PAGE_GOTO_BEFORE_FIRST_ROUTE_EVENT_STALL"
    elif stage.startswith("route_"):
        code = "ROUTE_HANDLER_STAGE_STALL"
    elif case == "STATIC_DIRECT":
        code = "BROWSER_NETWORK_BASELINE_FAILURE"
    elif case == "STATIC_ROUTED_CONTINUE":
        code = "ROUTED_STATIC_NAVIGATION_FAILURE"
    elif case == "APP_DOCUMENT_ONLY_CONTENT":
        code = "APP_DOCUMENT_NAVIGATION_FAILURE"
    else:
        code = "FULL_APP_ROUTE_NAVIGATION_FAILURE"

    return {
        "diagnosis_code": code,
        "first_failure_case": case,
        "first_failure_stage": stage,
    }


def _validate_policy() -> None:
    if CASE_WALL_TIMEOUT_SECONDS < 5 or CASE_WALL_TIMEOUT_SECONDS > 60:
        raise RuntimeError("F4_1_3_CASE_WALL_TIMEOUT_OUT_OF_RANGE")
    if GOTO_TIMEOUT_MS < 1000 or GOTO_TIMEOUT_MS > 30000:
        raise RuntimeError("F4_1_3_GOTO_TIMEOUT_OUT_OF_RANGE")
    if KILL_GRACE_SECONDS < 0 or KILL_GRACE_SECONDS > 5:
        raise RuntimeError("F4_1_3_KILL_GRACE_OUT_OF_RANGE")
    if NOMINAL_WORST_CASE_SECONDS >= 10 * 60:
        raise RuntimeError("F4_1_3_WORST_CASE_EXCEEDS_JOB_TIMEOUT")


def run_supervisor() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("F4_1_3_EXPECTED_SHA_INVALID")
    _validate_policy()

    public_sha = f411._validate_public_version_with_wall_clock(expected_sha)
    results = [_stream_case(case, expected_sha) for case in CASES]
    stage_counts: dict[str, int] = {}
    for row in results:
        stage = str(row.get("last_checkpoint_stage") or "NO_CHECKPOINT")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    return {
        "schema": SCHEMA,
        "status": "PASS",
        "classification": "NAVIGATION_ROUTE_DECOMPOSITION_COMPLETE",
        "expected_production_sha": expected_sha,
        "public_version_sha": public_sha,
        "representative_class": REPRESENTATIVE_TARGET.class_name,
        "case_count": len(CASES),
        "cases": results,
        "last_checkpoint_stage_counts": dict(sorted(stage_counts.items())),
        "probe_policy": {
            "case_process_isolation": True,
            "case_stdout_streaming": True,
            "case_wall_timeout_seconds": CASE_WALL_TIMEOUT_SECONDS,
            "goto_timeout_ms": GOTO_TIMEOUT_MS,
            "kill_grace_seconds": KILL_GRACE_SECONDS,
            "nominal_worst_case_seconds": NOMINAL_WORST_CASE_SECONDS,
            "product_gap_inference_allowed": False,
        },
        **diagnose(results),
        **_boundary(),
    }


def _catastrophic(exc: BaseException) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "INCONCLUSIVE",
        "classification": "NAVIGATION_ROUTE_DECOMPOSITION_PROBE_ERROR",
        "diagnosis_code": f"RUNNER_{_safe_code(exc)}",
        "first_failure_case": None,
        "first_failure_stage": None,
        "cases": [],
        "last_checkpoint_stage_counts": {},
        **_boundary(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case", choices=CASES)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.worker:
        try:
            if not args.case:
                raise ValueError("WORKER_CASE_REQUIRED")
            result = _run_case_worker(args.case)
        except BaseException as exc:
            result = {
                "schema": SCHEMA,
                "worker": True,
                "case": args.case or "UNKNOWN_CASE",
                "status": "PROBE_ERROR",
                "error_code": f"WORKER_EXCEPTION_{_safe_code(exc)}",
                **_boundary(),
            }
        print(WORKER_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return 0

    try:
        result = run_supervisor()
    except BaseException as exc:
        result = _catastrophic(exc)
    print(FINAL_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
