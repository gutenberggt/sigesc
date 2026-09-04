#!/usr/bin/env python3
"""F4.1.5 — full browser→DOM reprobe with non-connecting WebSocket routing.

F4.1.4 localized the historical probe deadlock to WebSocketRoute.close().
Playwright routed WebSockets do not connect to the server by default, so this
probe keeps WebSockets local by returning from the route handler without
calling close() or connect_to_server().

Product semantics are intentionally inherited from F4.1:
- PASS / PUBLIC_BROWSER_RENDER_CURRENT
- FAIL / PUBLIC_BROWSER_RENDER_GAP
- INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR

Production remains read-only: public GET assets only, application /api/ fully
synthetic/local, Service Workers blocked, non-GET aborted, non-allowlisted
fetch/XHR aborted, and no real authentication/database/student data/write path.
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
import teacher_visibility_f4_1_browser_render as f41  # noqa: E402
import teacher_visibility_f4_1_1_browser_render as f411  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_5_PUBLIC_BROWSER_RENDER_V7"
WORKER_PREFIX = "TEACHER_VISIBILITY_F4_1_5_WORKER_JSON="
FINAL_PREFIX = "TEACHER_VISIBILITY_F4_1_5_JSON="
CHECKPOINT_PREFIX = "TEACHER_VISIBILITY_F4_1_5_CHECKPOINT="

SURFACE_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_5_SURFACE_WALL_TIMEOUT_SECONDS", "30"))
NAVIGATION_TIMEOUT_MS = int(os.environ.get("F4_1_5_NAVIGATION_TIMEOUT_MS", "10000"))
ACTION_TIMEOUT_MS = int(os.environ.get("F4_1_5_ACTION_TIMEOUT_MS", "5000"))
POLL_TIMEOUT_SECONDS = float(os.environ.get("F4_1_5_POLL_TIMEOUT_SECONDS", "4"))
KILL_GRACE_SECONDS = float(os.environ.get("F4_1_5_KILL_GRACE_SECONDS", "2"))
PUBLIC_VERSION_WALL_TIMEOUT_SECONDS = int(os.environ.get("F4_1_5_PUBLIC_VERSION_WALL_TIMEOUT_SECONDS", "35"))
EXPECTED_SURFACE_COUNT = len(f4.TARGETS) * 2
NOMINAL_WORST_CASE_SECONDS = (
    EXPECTED_SURFACE_COUNT * (SURFACE_WALL_TIMEOUT_SECONDS + KILL_GRACE_SECONDS)
    + PUBLIC_VERSION_WALL_TIMEOUT_SECONDS
    + KILL_GRACE_SECONDS
)


def checkpoint(target_class: str, surface: str, stage: str, status: str) -> None:
    print(
        CHECKPOINT_PREFIX
        + json.dumps(
            {"class": target_class, "surface": surface, "stage": stage, "status": status},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def _safe_code(value: BaseException | str) -> str:
    if isinstance(value, BaseException):
        value = type(value).__name__
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_")
    return (normalized or "UNKNOWN")[:120]


def _boundary_template() -> dict[str, Any]:
    return {
        "production_http_methods": ["GET"],
        "service_workers_blocked": True,
        "all_api_requests_intercepted_locally": True,
        "dynamic_non_api_gets_allowlisted": True,
        "websockets_blocked": True,
        "websocket_policy": "ROUTED_LOCAL_NO_SERVER_CONNECTION",
        "websocket_server_connections": 0,
        "websocket_close_calls": 0,
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


def _configure_f41() -> None:
    f41.NAVIGATION_TIMEOUT_MS = NAVIGATION_TIMEOUT_MS
    f41.ACTION_TIMEOUT_MS = ACTION_TIMEOUT_MS
    f41.POLL_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS


def _block_websocket_locally(web_socket_route: Any, blocked: list[str]) -> None:
    """Record the routed socket and intentionally do nothing else.

    A routed Playwright WebSocket is disconnected from the real server by
    default. Returning here therefore blocks the real connection without the
    WebSocketRoute.close() call that F4.1.4 proved can deadlock this sync probe.
    """
    blocked.append(str(web_socket_route.url))


def _run_worker(class_name: str, surface_name: str) -> dict[str, Any]:
    if surface_name not in {"content", "attendance"}:
        raise ValueError("INVALID_SURFACE")

    target = _find_target(class_name)
    _configure_f41()

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    base_origin = urllib.parse.urlsplit(f4.BASE_URL)
    intercepted_api: list[str] = []
    fixture_keys: list[str] = []
    blocked_non_get: list[str] = []
    blocked_dynamic_get: list[str] = []
    blocked_websocket: list[str] = []
    pair = f41._new_pair(target)

    checkpoint(class_name, surface_name, "worker_boot", "RUNNING")
    with sync_playwright() as playwright:
        checkpoint(class_name, surface_name, "browser_launch_before", "RUNNING")
        browser = playwright.chromium.launch(headless=True)
        checkpoint(class_name, surface_name, "browser_launch_after", "PASS")

        context = browser.new_context(service_workers="block")
        context.set_default_timeout(ACTION_TIMEOUT_MS)
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
            checkpoint(class_name, surface_name, "websocket_local_before", "RUNNING")
            _block_websocket_locally(web_socket_route, blocked_websocket)
            checkpoint(class_name, surface_name, "websocket_local_after", "PASS")

        context.route("**/*", route_handler)
        context.route_web_socket("**/*", websocket_handler)
        page = context.new_page()

        started = time.monotonic()
        try:
            checkpoint(class_name, surface_name, "probe_call_before", "RUNNING")
            if surface_name == "content":
                f41._probe_content(page, target, pair)
            else:
                f41._probe_attendance(page, target, pair)
            checkpoint(
                class_name,
                surface_name,
                "probe_call_after",
                str(pair[surface_name].get("status") or "UNKNOWN"),
            )
        finally:
            checkpoint(class_name, surface_name, "cleanup_before", "RUNNING")
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
            checkpoint(class_name, surface_name, "cleanup_after", "PASS")

    return {
        "schema": SCHEMA,
        "worker": True,
        "class": class_name,
        "surface": surface_name,
        "surface_result": pair[surface_name],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "intercepted_api_request_count": len(intercepted_api),
        "unknown_api_fixture_count": sum(1 for key in fixture_keys if key == "unknown_api_local_empty"),
        "blocked_non_get_attempt_count": len(blocked_non_get),
        "blocked_dynamic_get_attempt_count": len(blocked_dynamic_get),
        "blocked_websocket_attempt_count": len(blocked_websocket),
        **_boundary_template(),
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
    prefixes = (CHECKPOINT_PREFIX, "TEACHER_VISIBILITY_F4_1_CHECKPOINT=")
    for prefix in prefixes:
        if line.startswith(prefix):
            try:
                payload = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def _extract_worker(output: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for line in output.splitlines():
        if not line.startswith(WORKER_PREFIX):
            continue
        try:
            candidate = json.loads(line[len(WORKER_PREFIX):])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            found = candidate
    return found


def _stream_surface(target: Any, surface_name: str, expected_sha: str) -> tuple[dict[str, Any], dict[str, Any]]:
    cmd = [
        sys.executable,
        "-u",
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
        bufsize=1,
        env=_worker_env(expected_sha),
        start_new_session=True,
    )
    if proc.stdout is None:
        _kill_group(proc)
        return (
            f411._probe_error_surface(surface_name, "NO_STDOUT"),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": False,
                "last_checkpoint_stage": "NO_CHECKPOINT",
            },
        )

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + SURFACE_WALL_TIMEOUT_SECONDS
    lines: list[str] = []
    last: dict[str, Any] | None = None
    timed_out = False
    started = time.monotonic()

    def accept(raw: str) -> None:
        nonlocal last
        clean = raw.rstrip("\r\n")
        lines.append(clean)
        payload = _parse_checkpoint(clean)
        if payload is not None:
            last = payload
            if clean.startswith("TEACHER_VISIBILITY_F4_1_CHECKPOINT="):
                normalized = clean.replace("TEACHER_VISIBILITY_F4_1_CHECKPOINT=", CHECKPOINT_PREFIX, 1)
                print(normalized, flush=True)
            else:
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

    elapsed_ms = int((time.monotonic() - started) * 1000)
    last_stage = str((last or {}).get("stage") or "NO_CHECKPOINT")
    if timed_out:
        checkpoint(target.class_name, surface_name, "wall_timeout", "PROBE_ERROR")
        return (
            f411._probe_error_surface(
                surface_name,
                f"WALL_TIMEOUT_AFTER_{_safe_code(last_stage)}",
                elapsed_ms=elapsed_ms,
            ),
            {
                "worker_timeout": True,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": False,
                "last_checkpoint_stage": last_stage,
            },
        )

    output = "\n".join(lines)
    worker = _extract_worker(output)
    if proc.returncode != 0:
        return (
            f411._probe_error_surface(surface_name, f"WORKER_EXIT_{proc.returncode}", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": worker is not None,
                "last_checkpoint_stage": last_stage,
            },
        )
    if not worker or worker.get("schema") != SCHEMA:
        return (
            f411._probe_error_surface(surface_name, "WORKER_NO_STRUCTURED_JSON", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": False,
                "last_checkpoint_stage": last_stage,
            },
        )

    surface_result = worker.get("surface_result")
    if not isinstance(surface_result, dict):
        return (
            f411._probe_error_surface(surface_name, "WORKER_RESULT_INVALID", elapsed_ms=elapsed_ms),
            {
                "worker_timeout": False,
                "worker_exit_code": proc.returncode,
                "worker_structured_json": True,
                "last_checkpoint_stage": last_stage,
            },
        )

    result = dict(surface_result)
    result["elapsed_ms"] = elapsed_ms
    return (
        result,
        {
            "worker_timeout": False,
            "worker_exit_code": proc.returncode,
            "worker_structured_json": True,
            "last_checkpoint_stage": last_stage,
            "intercepted_api_request_count": int(worker.get("intercepted_api_request_count") or 0),
            "unknown_api_fixture_count": int(worker.get("unknown_api_fixture_count") or 0),
            "blocked_non_get_attempt_count": int(worker.get("blocked_non_get_attempt_count") or 0),
            "blocked_dynamic_get_attempt_count": int(worker.get("blocked_dynamic_get_attempt_count") or 0),
            "blocked_websocket_attempt_count": int(worker.get("blocked_websocket_attempt_count") or 0),
            "websocket_server_connections": int(worker.get("websocket_server_connections") or 0),
            "websocket_close_calls": int(worker.get("websocket_close_calls") or 0),
        },
    )


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "intercepted_api_request_count",
        "unknown_api_fixture_count",
        "blocked_non_get_attempt_count",
        "blocked_dynamic_get_attempt_count",
        "blocked_websocket_attempt_count",
        "websocket_server_connections",
        "websocket_close_calls",
    )
    result = {key: sum(int(row.get(key) or 0) for row in rows) for key in keys}
    result["worker_timeout_count"] = sum(1 for row in rows if row.get("worker_timeout"))
    result["worker_structured_json_count"] = sum(1 for row in rows if row.get("worker_structured_json"))
    return result


def _validate_policy() -> None:
    if SURFACE_WALL_TIMEOUT_SECONDS < 10 or SURFACE_WALL_TIMEOUT_SECONDS > 60:
        raise RuntimeError("F4_1_5_SURFACE_WALL_TIMEOUT_OUT_OF_RANGE")
    if NAVIGATION_TIMEOUT_MS < 1000 or NAVIGATION_TIMEOUT_MS > 30000:
        raise RuntimeError("F4_1_5_NAVIGATION_TIMEOUT_OUT_OF_RANGE")
    if ACTION_TIMEOUT_MS < 1000 or ACTION_TIMEOUT_MS > 15000:
        raise RuntimeError("F4_1_5_ACTION_TIMEOUT_OUT_OF_RANGE")
    if POLL_TIMEOUT_SECONDS < 1 or POLL_TIMEOUT_SECONDS > 10:
        raise RuntimeError("F4_1_5_POLL_TIMEOUT_OUT_OF_RANGE")
    if KILL_GRACE_SECONDS < 0 or KILL_GRACE_SECONDS > 5:
        raise RuntimeError("F4_1_5_KILL_GRACE_OUT_OF_RANGE")
    if NOMINAL_WORST_CASE_SECONDS >= 10 * 60:
        raise RuntimeError("F4_1_5_WORST_CASE_EXCEEDS_JOB_TIMEOUT")


def run_supervisor() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("F4_1_5_EXPECTED_SHA_INVALID")
    _validate_policy()

    # Reuse the F4.1.1 hardened public release validation; it is isolated in a
    # separate process and does not involve browser WebSocket routing.
    public_sha = f411._validate_public_version_with_wall_clock(expected_sha)
    pairs: list[dict[str, Any]] = []
    worker_meta: list[dict[str, Any]] = []

    for target in f4.TARGETS:
        pair = f41._new_pair(target)
        pairs.append(pair)
        for surface_name in ("content", "attendance"):
            surface_result, meta = _stream_surface(target, surface_name, expected_sha)
            pair[surface_name] = surface_result
            worker_meta.append({"class": target.class_name, "surface": surface_name, **meta})

    evaluation = f41.evaluate_pairs(pairs, expected_pairs=len(f4.TARGETS))
    aggregated = _aggregate(worker_meta)
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
            "surface_wall_timeout_seconds": SURFACE_WALL_TIMEOUT_SECONDS,
            "worker_navigation_timeout_ms": NAVIGATION_TIMEOUT_MS,
            "worker_action_timeout_ms": ACTION_TIMEOUT_MS,
            "worker_poll_timeout_seconds": POLL_TIMEOUT_SECONDS,
            "worker_kill_grace_seconds": KILL_GRACE_SECONDS,
            "websocket_routed_local_no_server_connection": True,
            "timeout_is_product_gap": False,
            "nominal_worst_case_seconds": NOMINAL_WORST_CASE_SECONDS,
        },
        "pairs": pairs,
        "workers": worker_meta,
        **aggregated,
        **_boundary_template(),
        **evaluation,
    }


def _catastrophic(exc: BaseException) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "target": "production-public-frontend-with-local-synthetic-api",
        "status": "INCONCLUSIVE",
        "classification": "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
        "probe_errors": [f"RUNNER:{_safe_code(exc)}"],
        "product_failures": [],
        "pairs": [],
        "workers": [],
        "catastrophic_probe_error": True,
        **_boundary_template(),
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
                "surface_result": f411._probe_error_surface(
                    surface_name,
                    f"WORKER_EXCEPTION_{_safe_code(exc)}",
                ),
                "worker_error": _safe_code(exc),
                **_boundary_template(),
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
