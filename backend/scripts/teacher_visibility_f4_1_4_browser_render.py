#!/usr/bin/env python3
"""F4.1.4 — post-goto DOM ladder for teacher visibility browser diagnostics.

F4.1.3 proved page.goto and the basic F4 route policy healthy. This probe keeps
production read-only and decomposes only the synchronous Playwright operations
that F4.1 executes after navigation: prefill selectors/evaluate_all, content DOM
anchors, and attendance Registros controls.

This is an instrument diagnostic. It cannot declare a product gap.
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
from typing import Any, Callable

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import teacher_visibility_f4_browser_render as f4  # noqa: E402
import teacher_visibility_f4_1_1_browser_render as f411  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_4_POST_GOTO_DOM_LADDER_V6"
WORKER_PREFIX = "TEACHER_VISIBILITY_F4_1_4_WORKER_JSON="
FINAL_PREFIX = "TEACHER_VISIBILITY_F4_1_4_JSON="
CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_4_CHECKPOINT="

CASES = ("CONTENT_POST_GOTO", "ATTENDANCE_POST_GOTO")
TARGET = f4.TARGETS[0]
CASE_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_4_CASE_WALL_TIMEOUT_SECONDS", "35"))
GOTO_TIMEOUT_MS = int(os.environ.get("F4_1_4_GOTO_TIMEOUT_MS", "8000"))
ACTION_TIMEOUT_MS = int(os.environ.get("F4_1_4_ACTION_TIMEOUT_MS", "5000"))
POLL_TIMEOUT_SECONDS = float(os.environ.get("F4_1_4_POLL_TIMEOUT_SECONDS", "4"))
POLL_INTERVAL_SECONDS = 0.20
KILL_GRACE_SECONDS = float(os.environ.get("F4_1_4_KILL_GRACE_SECONDS", "2"))
PUBLIC_VERSION_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_4_PUBLIC_VERSION_WALL_TIMEOUT_SECONDS", "35"))
NOMINAL_WORST_CASE_SECONDS = (
    len(CASES) * (CASE_WALL_TIMEOUT_SECONDS + KILL_GRACE_SECONDS)
    + PUBLIC_VERSION_WALL_TIMEOUT_SECONDS
    + KILL_GRACE_SECONDS
)


def _safe_code(value: BaseException | str) -> str:
    if isinstance(value, BaseException):
        value = type(value).__name__
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_")
    return (normalized or "UNKNOWN")[:120]


def checkpoint(
    case: str,
    stage: str,
    status: str,
    *,
    iteration: int | None = None,
    resource_type: str | None = None,
) -> None:
    payload: dict[str, Any] = {"case": case, "stage": stage, "status": status}
    if iteration is not None:
        payload["iteration"] = iteration
    if resource_type:
        payload["resource_type"] = resource_type
    print(CHECKPOINT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _boundary() -> dict[str, Any]:
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
        "product_gap_claimed": False,
    }


def _target_url(case: str) -> str:
    if case == "CONTENT_POST_GOTO":
        return f4._target_url("/professor/objetos-conhecimento", TARGET)
    if case == "ATTENDANCE_POST_GOTO":
        return f4._target_url("/professor/frequencia", TARGET)
    raise ValueError("UNKNOWN_CASE")


def _instrumented_poll(
    case: str,
    stage_prefix: str,
    operation: Callable[[int], bool],
    *,
    timeout_seconds: float = POLL_TIMEOUT_SECONDS,
) -> tuple[bool, int]:
    deadline = time.monotonic() + timeout_seconds
    iteration = 0
    while True:
        iteration += 1
        checkpoint(case, f"{stage_prefix}_before", "RUNNING", iteration=iteration)
        matched = bool(operation(iteration))
        checkpoint(case, f"{stage_prefix}_after", "PASS", iteration=iteration)
        if matched:
            return True, iteration
        if time.monotonic() >= deadline:
            return False, iteration
        time.sleep(POLL_INTERVAL_SECONDS)


def _run_worker(case: str) -> dict[str, Any]:
    if case not in CASES:
        raise ValueError("UNKNOWN_CASE")

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    base_origin = urllib.parse.urlsplit(f4.BASE_URL)
    route_counts: dict[str, int] = {}
    route_actions: dict[str, int] = {}
    emitted: set[str] = set()
    observations: dict[str, Any] = {}

    def emit_route_once(stage: str, resource_type: str) -> None:
        key = f"{stage}:{resource_type}"
        if key not in emitted:
            emitted.add(key)
            checkpoint(case, stage, "RUNNING", resource_type=resource_type)

    checkpoint(case, "sync_playwright_before", "RUNNING")
    with sync_playwright() as playwright:
        checkpoint(case, "sync_playwright_after", "PASS")
        checkpoint(case, "browser_launch_before", "RUNNING")
        browser = playwright.chromium.launch(headless=True)
        checkpoint(case, "browser_launch_after", "PASS")

        checkpoint(case, "context_create_before", "RUNNING")
        context = browser.new_context(service_workers="block")
        context.set_default_timeout(ACTION_TIMEOUT_MS)
        context.add_init_script(f4._init_script())
        checkpoint(case, "context_create_after", "PASS")

        def route_handler(route: Any, request: Any) -> None:
            resource_type = str(request.resource_type or "unknown")
            route_counts[resource_type] = route_counts.get(resource_type, 0) + 1
            emit_route_once("route_enter", resource_type)

            method = request.method.upper()
            parsed = urllib.parse.urlsplit(request.url)
            if method != "GET":
                emit_route_once("route_abort_non_get_before", resource_type)
                route_actions["abort_non_get"] = route_actions.get("abort_non_get", 0) + 1
                route.abort()
                emit_route_once("route_abort_non_get_after", resource_type)
                return

            if "/api/" in parsed.path:
                emit_route_once("route_fulfill_api_before", resource_type)
                status, body, _fixture_key = f4.fixture_for_api(request.url)
                route_actions["fulfill_api"] = route_actions.get("fulfill_api", 0) + 1
                route.fulfill(
                    status=status,
                    content_type="application/json; charset=utf-8",
                    body=json.dumps(body, ensure_ascii=False),
                )
                emit_route_once("route_fulfill_api_after", resource_type)
                return

            if resource_type in {"xhr", "fetch"}:
                same_public_origin = (
                    parsed.scheme == base_origin.scheme
                    and parsed.netloc == base_origin.netloc
                )
                if same_public_origin and parsed.path in f4.PUBLIC_DYNAMIC_GET_PATHS:
                    emit_route_once("route_continue_dynamic_before", resource_type)
                    route_actions["continue_dynamic"] = route_actions.get("continue_dynamic", 0) + 1
                    route.continue_()
                    emit_route_once("route_continue_dynamic_after", resource_type)
                    return
                emit_route_once("route_abort_dynamic_before", resource_type)
                route_actions["abort_dynamic"] = route_actions.get("abort_dynamic", 0) + 1
                route.abort()
                emit_route_once("route_abort_dynamic_after", resource_type)
                return

            emit_route_once("route_continue_public_before", resource_type)
            route_actions["continue_public"] = route_actions.get("continue_public", 0) + 1
            route.continue_()
            emit_route_once("route_continue_public_after", resource_type)

        def websocket_handler(web_socket_route: Any) -> None:
            emit_route_once("websocket_close_before", "websocket")
            web_socket_route.close(code=1000, reason="F4.1.4 read-only post-goto DOM ladder")
            emit_route_once("websocket_close_after", "websocket")

        checkpoint(case, "route_install_before", "RUNNING")
        context.route("**/*", route_handler)
        context.route_web_socket("**/*", websocket_handler)
        checkpoint(case, "route_install_after", "PASS")

        checkpoint(case, "page_create_before", "RUNNING")
        page = context.new_page()
        checkpoint(case, "page_create_after", "PASS")

        status = "PASS"
        error_code: str | None = None
        started = time.monotonic()
        try:
            checkpoint(case, "goto_before", "RUNNING")
            page.goto(_target_url(case), wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            checkpoint(case, "goto_after", "PASS")

            # Reproduce F4.1 prefill semantics with instrumentation around every
            # synchronous Playwright call that may otherwise block invisibly.
            checkpoint(case, "select_locator_before", "RUNNING")
            selects = page.locator("select")
            checkpoint(case, "select_locator_after", "PASS")

            select_count = 0
            def count_selects(_iteration: int) -> bool:
                nonlocal select_count
                select_count = selects.count()
                return select_count >= 2

            anchors_ok, count_iterations = _instrumented_poll(
                case, "select_count", count_selects
            )
            observations["select_count"] = select_count
            observations["select_count_iterations"] = count_iterations
            observations["select_anchor_ok"] = anchors_ok

            if anchors_ok:
                selected_texts: list[str] = []
                def evaluate_selected(_iteration: int) -> bool:
                    nonlocal selected_texts
                    checkpoint(case, "selected_options_eval_before", "RUNNING", iteration=_iteration)
                    selected_texts = selects.evaluate_all(
                        "els => els.map(el => el.options && el.selectedIndex >= 0 ? "
                        "(el.options[el.selectedIndex]?.text || '').trim() : '')"
                    )
                    checkpoint(case, "selected_options_eval_after", "PASS", iteration=_iteration)
                    return TARGET.class_name in selected_texts and f4.COMPONENT_NAME in selected_texts

                prefill_ok, eval_iterations = _instrumented_poll(
                    case, "prefill_match", evaluate_selected
                )
                observations["prefill_ok"] = prefill_ok
                observations["prefill_eval_iterations"] = eval_iterations
                observations["selected_option_count"] = len(selected_texts)
            else:
                observations["prefill_ok"] = False

            if case == "CONTENT_POST_GOTO":
                checkpoint(case, "heading_locator_before", "RUNNING")
                heading = page.get_by_role("heading", name="Objetos de Conhecimento")
                checkpoint(case, "heading_locator_after", "PASS")
                heading_count = 0
                def count_heading(_iteration: int) -> bool:
                    nonlocal heading_count
                    heading_count = heading.count()
                    return heading_count >= 1
                heading_ok, heading_iterations = _instrumented_poll(
                    case, "heading_count", count_heading
                )
                observations["heading_count"] = heading_count
                observations["heading_ok"] = heading_ok
                observations["heading_iterations"] = heading_iterations

                checkpoint(case, "green_locator_before", "RUNNING")
                green = page.locator("div.bg-green-100")
                checkpoint(case, "green_locator_after", "PASS")
                green_values: list[str] = []
                wanted = {str(int(date[-2:])) for date in f4.PROBE_DATES}
                def eval_green(_iteration: int) -> bool:
                    nonlocal green_values
                    checkpoint(case, "green_eval_before", "RUNNING", iteration=_iteration)
                    green_values = green.evaluate_all(
                        "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)"
                    )
                    checkpoint(case, "green_eval_after", "PASS", iteration=_iteration)
                    return wanted.issubset(set(green_values))
                green_ok, green_iterations = _instrumented_poll(
                    case, "green_match", eval_green
                )
                observations["green_visible_count"] = len(wanted.intersection(set(green_values)))
                observations["green_ok"] = green_ok
                observations["green_iterations"] = green_iterations

            else:
                checkpoint(case, "registros_locator_before", "RUNNING")
                registros = page.get_by_role("button", name="Registros", exact=True)
                checkpoint(case, "registros_locator_after", "PASS")
                registros_count = 0
                def count_registros(_iteration: int) -> bool:
                    nonlocal registros_count
                    registros_count = registros.count()
                    return registros_count >= 1
                registros_ok, registros_iterations = _instrumented_poll(
                    case, "registros_count", count_registros
                )
                observations["registros_count"] = registros_count
                observations["registros_ok"] = registros_ok
                observations["registros_iterations"] = registros_iterations

                if registros_ok:
                    checkpoint(case, "registros_click_before", "RUNNING")
                    registros.click(timeout=ACTION_TIMEOUT_MS)
                    checkpoint(case, "registros_click_after", "PASS")

                    checkpoint(case, "tab_locator_before", "RUNNING")
                    tab = page.locator('[data-testid="attendance-registros-tab"]')
                    checkpoint(case, "tab_locator_after", "PASS")
                    checkpoint(case, "tab_wait_before", "RUNNING")
                    tab.wait_for(timeout=ACTION_TIMEOUT_MS)
                    checkpoint(case, "tab_wait_after", "PASS")

                    checkpoint(case, "attendance_marker_locator_before", "RUNNING")
                    markers = page.locator('[title="Frequência registrada"]')
                    checkpoint(case, "attendance_marker_locator_after", "PASS")
                    marker_count = 0
                    def count_markers(_iteration: int) -> bool:
                        nonlocal marker_count
                        marker_count = markers.count()
                        return marker_count >= len(f4.PROBE_DATES)
                    markers_ok, marker_iterations = _instrumented_poll(
                        case, "attendance_marker_count", count_markers
                    )
                    observations["marker_count"] = marker_count
                    observations["markers_ok"] = markers_ok
                    observations["marker_iterations"] = marker_iterations

            checkpoint(case, "ladder_complete", "PASS")
        except Exception as exc:
            status = "PROBE_ERROR"
            error_code = f"WORKER_{_safe_code(exc)}"
            checkpoint(case, "worker_exception", "PROBE_ERROR")

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
        "status": status,
        "error_code": error_code,
        "elapsed_ms": elapsed_ms,
        "observations": observations,
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
    cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--worker", "--case", case]
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
    last_iteration = (last or {}).get("iteration")
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
            "last_checkpoint_iteration": last_iteration,
        }

    output = "\n".join(lines)
    worker = _extract_worker(output)
    if proc.returncode != 0 or not worker or worker.get("schema") != SCHEMA:
        return {
            "case": case,
            "status": "PROBE_ERROR",
            "error_code": (
                f"WORKER_EXIT_{proc.returncode}" if proc.returncode != 0
                else "WORKER_NO_STRUCTURED_JSON"
            ),
            "timed_out": False,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": worker is not None,
            "last_checkpoint_stage": last_stage,
            "last_checkpoint_iteration": last_iteration,
        }

    return {
        **worker,
        "timed_out": False,
        "worker_exit_code": proc.returncode,
        "worker_structured_json": True,
        "last_checkpoint_stage": last_stage,
        "last_checkpoint_iteration": last_iteration,
    }


def diagnose(cases: list[dict[str, Any]]) -> dict[str, Any]:
    first = next((row for row in cases if row.get("status") != "PASS"), None)
    if first is None:
        return {
            "diagnosis_code": "POST_GOTO_DOM_LADDER_HEALTHY",
            "first_failure_case": None,
            "first_failure_stage": None,
        }

    stage = str(first.get("last_checkpoint_stage") or "NO_CHECKPOINT")
    case = str(first.get("case") or "UNKNOWN_CASE")
    if "route_fulfill_api_before" in stage:
        code = "ROUTE_FULFILL_API_CALL_STALL"
    elif "route_continue" in stage and stage.endswith("_before"):
        code = "ROUTE_CONTINUE_CALL_STALL"
    elif "route_abort" in stage and stage.endswith("_before"):
        code = "ROUTE_ABORT_CALL_STALL"
    elif "select_count_before" in stage:
        code = "LOCATOR_SELECT_COUNT_STALL"
    elif "selected_options_eval_before" in stage:
        code = "LOCATOR_SELECTED_OPTIONS_EVALUATE_ALL_STALL"
    elif "heading_count_before" in stage:
        code = "LOCATOR_HEADING_COUNT_STALL"
    elif "green_eval_before" in stage:
        code = "LOCATOR_CONTENT_DATES_EVALUATE_ALL_STALL"
    elif "registros_count_before" in stage:
        code = "LOCATOR_REGISTROS_COUNT_STALL"
    elif stage == "registros_click_before":
        code = "REGISTROS_CLICK_STALL"
    elif stage == "tab_wait_before":
        code = "REGISTROS_TAB_WAIT_STALL"
    elif "attendance_marker_count_before" in stage:
        code = "ATTENDANCE_MARKER_COUNT_STALL"
    elif stage == "goto_before":
        code = "PAGE_GOTO_REGRESSION_STALL"
    else:
        code = "POST_GOTO_UNCLASSIFIED_PROBE_STAGE"

    return {
        "diagnosis_code": code,
        "first_failure_case": case,
        "first_failure_stage": stage,
    }


def _validate_policy() -> None:
    if CASE_WALL_TIMEOUT_SECONDS < 10 or CASE_WALL_TIMEOUT_SECONDS > 60:
        raise RuntimeError("F4_1_4_CASE_WALL_TIMEOUT_OUT_OF_RANGE")
    if GOTO_TIMEOUT_MS < 1000 or GOTO_TIMEOUT_MS > 30000:
        raise RuntimeError("F4_1_4_GOTO_TIMEOUT_OUT_OF_RANGE")
    if ACTION_TIMEOUT_MS < 1000 or ACTION_TIMEOUT_MS > 15000:
        raise RuntimeError("F4_1_4_ACTION_TIMEOUT_OUT_OF_RANGE")
    if POLL_TIMEOUT_SECONDS < 1 or POLL_TIMEOUT_SECONDS > 10:
        raise RuntimeError("F4_1_4_POLL_TIMEOUT_OUT_OF_RANGE")
    if KILL_GRACE_SECONDS < 0 or KILL_GRACE_SECONDS > 5:
        raise RuntimeError("F4_1_4_KILL_GRACE_OUT_OF_RANGE")
    if NOMINAL_WORST_CASE_SECONDS >= 10 * 60:
        raise RuntimeError("F4_1_4_WORST_CASE_EXCEEDS_JOB_TIMEOUT")


def run_supervisor() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("F4_1_4_EXPECTED_SHA_INVALID")
    _validate_policy()
    public_sha = f411._validate_public_version_with_wall_clock(expected_sha)
    results = [_stream_case(case, expected_sha) for case in CASES]
    return {
        "schema": SCHEMA,
        "status": "PASS",
        "classification": "POST_GOTO_DOM_LADDER_COMPLETE",
        "expected_production_sha": expected_sha,
        "public_version_sha": public_sha,
        "representative_class": TARGET.class_name,
        "case_count": len(CASES),
        "cases": results,
        "probe_policy": {
            "case_process_isolation": True,
            "case_stdout_streaming": True,
            "case_wall_timeout_seconds": CASE_WALL_TIMEOUT_SECONDS,
            "goto_timeout_ms": GOTO_TIMEOUT_MS,
            "action_timeout_ms": ACTION_TIMEOUT_MS,
            "poll_timeout_seconds": POLL_TIMEOUT_SECONDS,
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
        "classification": "POST_GOTO_DOM_LADDER_PROBE_ERROR",
        "diagnosis_code": f"RUNNER_{_safe_code(exc)}",
        "first_failure_case": None,
        "first_failure_stage": None,
        "cases": [],
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
            result = _run_worker(args.case)
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
