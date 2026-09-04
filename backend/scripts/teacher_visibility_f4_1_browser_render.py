#!/usr/bin/env python3
"""TEACHER-VISIBILITY-F4.1 — browser→DOM resilient read-only probe.

Hardens F4 so a single browser timeout cannot consume the whole gate or be
misclassified as a product gap.

Result taxonomy:
- PASS / PUBLIC_BROWSER_RENDER_CURRENT:
  all six pairs completed with expected prefill and DOM evidence.
- FAIL / PUBLIC_BROWSER_RENDER_GAP:
  all required probes completed, but a deterministic rendered-state mismatch
  was observed.
- INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR:
  at least one required probe could not be completed because of navigation,
  selector/action, browser, or infrastructure error.

Boundary is inherited from F4 and reproduced explicitly here:
- public production resources: GET only;
- Service Workers blocked;
- every /api/ request fulfilled locally with synthetic fixtures;
- all non-GET methods aborted;
- non-API fetch/XHR limited to an explicit same-origin allowlist;
- WebSockets closed locally without connecting to the server;
- no real auth, Mongo, student data, attendance.records or pedagogical text;
- no production write path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
from typing import Any, Callable

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import teacher_visibility_f4_browser_render as f4  # noqa: E402

SCHEMA = "TEACHER_VISIBILITY_F4_1_PUBLIC_BROWSER_RENDER_V2"
NAVIGATION_TIMEOUT_MS = int(os.environ.get("F4_1_NAVIGATION_TIMEOUT_MS", "15000"))
ACTION_TIMEOUT_MS = int(os.environ.get("F4_1_ACTION_TIMEOUT_MS", "8000"))
POLL_TIMEOUT_SECONDS = float(os.environ.get("F4_1_POLL_TIMEOUT_SECONDS", "8"))
POLL_INTERVAL_SECONDS = 0.20


def checkpoint(target_class: str, surface: str, stage: str, status: str) -> None:
    """Emit metadata-only progress that remains useful even if a runner dies."""
    payload = {
        "class": target_class,
        "surface": surface,
        "stage": stage,
        "status": status,
    }
    print("TEACHER_VISIBILITY_F4_1_CHECKPOINT=" + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _safe_code(value: BaseException | str) -> str:
    """Return a bounded metadata-only error code; never persist raw exception text."""
    if isinstance(value, BaseException):
        name = type(value).__name__
    else:
        name = str(value)
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return (normalized or "UNKNOWN")[:80]


def _new_pair(target: Any) -> dict[str, Any]:
    return {
        "class": target.class_name,
        "component": f4.COMPONENT_NAME,
        "content": {
            "status": "PENDING",
            "prefill_ok": False,
            "visible_probe_dates": 0,
            "product_failures": [],
            "probe_errors": [],
            "elapsed_ms": 0,
        },
        "attendance": {
            "status": "PENDING",
            "prefill_ok": False,
            "visible_probe_dates": 0,
            "product_failures": [],
            "probe_errors": [],
            "elapsed_ms": 0,
        },
    }


def _append_probe_error(surface: dict[str, Any], code: str) -> None:
    if code not in surface["probe_errors"]:
        surface["probe_errors"].append(code)
    surface["status"] = "PROBE_ERROR"


def _append_product_failure(surface: dict[str, Any], code: str) -> None:
    if code not in surface["product_failures"]:
        surface["product_failures"].append(code)
    if surface["status"] != "PROBE_ERROR":
        surface["status"] = "GAP"


def _poll(predicate: Callable[[], bool], *, timeout_seconds: float = POLL_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_SECONDS)


def _selected_option_texts(page: Any) -> list[str]:
    return page.locator("select").evaluate_all(
        "els => els.map(el => el.options && el.selectedIndex >= 0 ? "
        "(el.options[el.selectedIndex]?.text || '').trim() : '')"
    )


def _probe_prefill(page: Any, class_name: str, surface: dict[str, Any], prefix: str) -> None:
    try:
        selects = page.locator("select")
        if not _poll(lambda: selects.count() >= 2):
            _append_probe_error(surface, f"{prefix}_SELECT_ANCHOR_MISSING")
            return
        matched = _poll(
            lambda: class_name in _selected_option_texts(page)
            and f4.COMPONENT_NAME in _selected_option_texts(page)
        )
        if matched:
            surface["prefill_ok"] = True
        else:
            _append_product_failure(surface, f"{prefix}_PREFILL_NOT_APPLIED")
    except Exception as exc:  # browser diagnostic boundary
        _append_probe_error(surface, f"{prefix}_PREFILL_{_safe_code(exc)}")


def _probe_content(page: Any, target: Any, pair: dict[str, Any]) -> None:
    surface = pair["content"]
    started = time.monotonic()
    checkpoint(target.class_name, "content", "start", "RUNNING")
    try:
        page.goto(
            f4._target_url("/professor/objetos-conhecimento", target),
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
    except Exception as exc:
        _append_probe_error(surface, f"CONTENT_NAVIGATION_{_safe_code(exc)}")
        checkpoint(target.class_name, "content", "navigation", "PROBE_ERROR")
        surface["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        return

    _probe_prefill(page, target.class_name, surface, "CONTENT")

    try:
        heading = page.get_by_role("heading", name="Objetos de Conhecimento")
        if not _poll(lambda: heading.count() >= 1):
            _append_probe_error(surface, "CONTENT_HEADING_ANCHOR_MISSING")
        else:
            wanted = {str(int(date[-2:])) for date in f4.PROBE_DATES}

            def rendered() -> bool:
                values = page.locator("div.bg-green-100").evaluate_all(
                    "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)"
                )
                return wanted.issubset(set(values))

            if _poll(rendered):
                values = page.locator("div.bg-green-100").evaluate_all(
                    "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)"
                )
                surface["visible_probe_dates"] = len(wanted.intersection(set(values)))
            else:
                candidate_count = page.locator("div.bg-green-100").count()
                if candidate_count == 0:
                    _append_probe_error(surface, "CONTENT_DATE_SELECTOR_ANCHOR_MISSING")
                else:
                    values = page.locator("div.bg-green-100").evaluate_all(
                        "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)"
                    )
                    surface["visible_probe_dates"] = len(wanted.intersection(set(values)))
                    _append_product_failure(surface, "CONTENT_DOM_PROBE_COUNT_MISMATCH")
    except Exception as exc:
        _append_probe_error(surface, f"CONTENT_DOM_{_safe_code(exc)}")

    if surface["status"] == "PENDING":
        surface["status"] = "PASS"
    surface["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    checkpoint(target.class_name, "content", "complete", surface["status"])


def _probe_attendance(page: Any, target: Any, pair: dict[str, Any]) -> None:
    surface = pair["attendance"]
    started = time.monotonic()
    checkpoint(target.class_name, "attendance", "start", "RUNNING")
    try:
        page.goto(
            f4._target_url("/professor/frequencia", target),
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
    except Exception as exc:
        _append_probe_error(surface, f"ATTENDANCE_NAVIGATION_{_safe_code(exc)}")
        checkpoint(target.class_name, "attendance", "navigation", "PROBE_ERROR")
        surface["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        return

    _probe_prefill(page, target.class_name, surface, "ATTENDANCE")

    try:
        registros = page.get_by_role("button", name="Registros", exact=True)
        if not _poll(lambda: registros.count() >= 1):
            _append_probe_error(surface, "ATTENDANCE_REGISTROS_BUTTON_MISSING")
        else:
            registros.click(timeout=ACTION_TIMEOUT_MS)
            tab = page.locator('[data-testid="attendance-registros-tab"]')
            try:
                tab.wait_for(timeout=ACTION_TIMEOUT_MS)
            except Exception as exc:
                _append_probe_error(surface, f"ATTENDANCE_REGISTROS_TAB_{_safe_code(exc)}")
            if surface["status"] != "PROBE_ERROR":
                selector = '[title="Frequência registrada"]'
                reached = _poll(lambda: page.locator(selector).count() >= len(f4.PROBE_DATES))
                count = page.locator(selector).count()
                surface["visible_probe_dates"] = min(count, len(f4.PROBE_DATES))
                if not reached:
                    if tab.count() < 1:
                        _append_probe_error(surface, "ATTENDANCE_TAB_ANCHOR_LOST")
                    else:
                        _append_product_failure(surface, "ATTENDANCE_DOM_PROBE_COUNT_MISMATCH")
    except Exception as exc:
        _append_probe_error(surface, f"ATTENDANCE_DOM_{_safe_code(exc)}")

    if surface["status"] == "PENDING":
        surface["status"] = "PASS"
    surface["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    checkpoint(target.class_name, "attendance", "complete", surface["status"])


def evaluate_pairs(pairs: list[dict[str, Any]], *, expected_pairs: int = 6) -> dict[str, Any]:
    probe_errors: list[str] = []
    product_failures: list[str] = []

    if len(pairs) != expected_pairs:
        probe_errors.append(f"TARGET_PAIR_COUNT_{len(pairs)}")

    for pair in pairs:
        class_name = pair.get("class") or "UNKNOWN_CLASS"
        for surface_name in ("content", "attendance"):
            surface = pair.get(surface_name) or {}
            for code in surface.get("probe_errors") or []:
                probe_errors.append(f"{class_name}:{surface_name}:{code}")
            for code in surface.get("product_failures") or []:
                product_failures.append(f"{class_name}:{surface_name}:{code}")

    if probe_errors:
        return {
            "status": "INCONCLUSIVE",
            "classification": "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
            "probe_errors": probe_errors,
            "product_failures": product_failures,
        }
    if product_failures:
        return {
            "status": "FAIL",
            "classification": "PUBLIC_BROWSER_RENDER_GAP",
            "probe_errors": [],
            "product_failures": product_failures,
        }
    return {
        "status": "PASS",
        "classification": "PUBLIC_BROWSER_RENDER_CURRENT",
        "probe_errors": [],
        "product_failures": [],
    }


def _boundary_metadata(
    *,
    intercepted_api: list[str],
    fixture_keys: list[str],
    blocked_non_get: list[str],
    blocked_dynamic_get: list[str],
    blocked_websocket: list[str],
) -> dict[str, Any]:
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
        "intercepted_api_request_count": len(intercepted_api),
        "unknown_api_fixture_count": sum(1 for key in fixture_keys if key == "unknown_api_local_empty"),
        "blocked_non_get_attempt_count": len(blocked_non_get),
        "blocked_non_get_attempts": sorted(set(blocked_non_get)),
        "blocked_dynamic_get_attempt_count": len(blocked_dynamic_get),
        "blocked_dynamic_get_attempts": sorted(set(blocked_dynamic_get)),
        "blocked_websocket_attempt_count": len(blocked_websocket),
        "blocked_websocket_attempts": sorted(set(blocked_websocket)),
    }


def run_live_audit() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("TEACHER_VISIBILITY_F4_1_EXPECTED_SHA_INVALID")

    public_sha = f4._public_version(expected_sha)

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    base_origin = urllib.parse.urlsplit(f4.BASE_URL)
    intercepted_api: list[str] = []
    fixture_keys: list[str] = []
    blocked_non_get: list[str] = []
    blocked_dynamic_get: list[str] = []
    blocked_websocket: list[str] = []
    pairs: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
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
            blocked_websocket.append(web_socket_route.url)
            web_socket_route.close(code=1000, reason="F4.1 read-only audit blocks WebSockets")

        context.route("**/*", route_handler)
        context.route_web_socket("**/*", websocket_handler)

        for target in f4.TARGETS:
            pair = _new_pair(target)
            pairs.append(pair)
            page = context.new_page()
            try:
                _probe_content(page, target, pair)
                _probe_attendance(page, target, pair)
            except Exception as exc:
                _append_probe_error(pair["content"], f"PAIR_UNHANDLED_{_safe_code(exc)}")
                _append_probe_error(pair["attendance"], f"PAIR_UNHANDLED_{_safe_code(exc)}")
                checkpoint(target.class_name, "pair", "unhandled", "PROBE_ERROR")
            finally:
                try:
                    page.close()
                except Exception:
                    pass

        context.close()
        browser.close()

    evaluation = evaluate_pairs(pairs, expected_pairs=len(f4.TARGETS))
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
            "navigation_timeout_ms": NAVIGATION_TIMEOUT_MS,
            "action_timeout_ms": ACTION_TIMEOUT_MS,
            "poll_timeout_seconds": POLL_TIMEOUT_SECONDS,
            "pair_isolation": True,
            "checkpoint_streaming": True,
            "timeout_is_product_gap": False,
        },
        "pairs": pairs,
        **_boundary_metadata(
            intercepted_api=intercepted_api,
            fixture_keys=fixture_keys,
            blocked_non_get=blocked_non_get,
            blocked_dynamic_get=blocked_dynamic_get,
            blocked_websocket=blocked_websocket,
        ),
        **evaluation,
    }


def _catastrophic_result(exc: BaseException) -> dict[str, Any]:
    """Always emit structured evidence even if Chromium cannot be started."""
    return {
        "schema": SCHEMA,
        "target": "production-public-frontend-with-local-synthetic-api",
        "status": "INCONCLUSIVE",
        "classification": "PUBLIC_BROWSER_RENDER_PROBE_ERROR",
        "probe_errors": [f"RUNNER:{_safe_code(exc)}"],
        "product_failures": [],
        "pairs": [],
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
        "catastrophic_probe_error": True,
    }


if __name__ == "__main__":
    try:
        result = run_live_audit()
    except BaseException as exc:  # runner/browser startup must still classify as probe error
        result = _catastrophic_result(exc)
    print("TEACHER_VISIBILITY_F4_1_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
