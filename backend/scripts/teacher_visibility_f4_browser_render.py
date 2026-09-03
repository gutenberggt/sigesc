#!/usr/bin/env python3
"""TEACHER-VISIBILITY-F4 — prova browser→DOM sem API real de produção.

Executa os assets públicos que a produção entrega dentro de Chromium/Playwright e
prova a renderização das superfícies históricas de conteúdo e frequência para os
seis pares de Matemática do caso Luiz Gomes.

Boundary forte:
- produção é acessada somente para recursos públicos via GET;
- Service Worker é bloqueado no contexto de auditoria para que nenhuma request
  escape da interceptação do Playwright;
- TODA URL contendo /api/ é respondida localmente com fixture sintética;
- qualquer método diferente de GET é abortado antes da rede;
- fetch/XHR não-API só pode alcançar uma allowlist pública e explícita;
- WebSockets são fechados antes de qualquer conexão com servidor;
- não há login, JWT, senha, Mongo, estudante, attendance.records ou texto pedagógico;
- nenhuma mutação de produção é possível por este coletor.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

ACADEMIC_YEAR = 2026
BASE_URL = os.environ.get("SIGESC_FRONTEND_BASE", "https://sigesc.aprenderdigital.top").rstrip("/")
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_CLASSES = (
    "6º ANO A",
    "6º ANO B",
    "7º ANO A",
    "7º ANO B",
    "8º ANO A",
    "9º ANO A",
)
COMPONENT_NAME = "Matemática"
PROBE_DATES = ("2026-09-01", "2026-09-02", "2026-09-03")
FIXED_BROWSER_NOW = "2026-09-03T15:00:00.000Z"
PUBLIC_DYNAMIC_GET_PATHS = frozenset({
    "/version.json",
    "/asset-manifest.json",
    "/manifest.json",
})


@dataclass(frozen=True)
class Target:
    class_name: str
    class_id: str
    course_id: str
    grade_level: str


def build_targets() -> list[Target]:
    targets: list[Target] = []
    for index, class_name in enumerate(TARGET_CLASSES, start=1):
        grade_match = re.match(r"(\d+)", class_name)
        grade = grade_match.group(1) if grade_match else ""
        targets.append(Target(
            class_name=class_name,
            class_id=f"f4-class-{index}",
            course_id=f"f4-course-{index}",
            grade_level=grade,
        ))
    return targets


TARGETS = build_targets()
TARGET_BY_CLASS_ID = {target.class_id: target for target in TARGETS}


def _synthetic_user() -> dict[str, Any]:
    return {
        "id": "f4-professor",
        "email": "f4-browser-audit@example.invalid",
        "full_name": "Professor Sintético F4",
        "name": "Professor Sintético F4",
        "role": "professor",
        "mantenedora_id": "f4-tenant",
        "school_links": [{"school_id": "f4-school", "roles": ["professor"]}],
    }


def _synthetic_turmas() -> list[dict[str, Any]]:
    return [
        {
            "id": target.class_id,
            "name": target.class_name,
            "school_id": "f4-school",
            "school_name": TARGET_SCHOOL,
            "academic_year": ACADEMIC_YEAR,
            "education_level": "fundamental_anos_finais",
            "grade_level": target.grade_level,
            "componentes": [{
                "id": target.course_id,
                "name": COMPONENT_NAME,
                "assignment_id": f"f4-legacy-assignment-{index}",
            }],
        }
        for index, target in enumerate(TARGETS, start=1)
    ]


def _learning_objects_fixture(query: dict[str, list[str]]) -> list[dict[str, Any]]:
    class_id = (query.get("class_id") or [""])[0]
    course_id = (
        (query.get("course_id") or [""])[0]
        or (query.get("component_id") or [""])[0]
    )
    target = TARGET_BY_CLASS_ID.get(class_id)
    if not target or course_id != target.course_id:
        return []
    return [
        {
            "id": f"f4-record-{target.class_id}-{day}",
            "class_id": target.class_id,
            "course_id": target.course_id,
            "component_id": target.course_id,
            "date": date,
            "academic_year": ACADEMIC_YEAR,
            "source": "learning_objects",
            "legacy": True,
            "read_only": True,
            "number_of_classes": 1,
        }
        for day, date in enumerate(PROBE_DATES, start=1)
    ]


def _open_edit_status() -> dict[str, Any]:
    return {
        "ano_letivo": ACADEMIC_YEAR,
        "pode_editar_todos": True,
        "bimestres": [
            {"bimestre": number, "pode_editar": True, "data_limite": None, "motivo": "F4"}
            for number in range(1, 5)
        ],
    }


def fixture_for_api(url: str) -> tuple[int, Any, str]:
    """Resolve uma chamada /api/ inteiramente em memória.

    O terceiro retorno é uma chave de diagnóstico, nunca um ID técnico real.
    """
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    if path.endswith("/api/auth/me"):
        return 200, _synthetic_user(), "auth_me"
    if path.endswith("/api/professor/turmas"):
        return 200, _synthetic_turmas(), "professor_turmas"
    if path.endswith("/api/professor/diarios"):
        return 200, {"items": [], "total": 0, "blocked_total": 0}, "professor_diarios_empty"
    if path.endswith("/api/learning-objects"):
        return 200, _learning_objects_fixture(query), "learning_objects_synthetic"
    if path.endswith("/api/attendance/dates-with-records"):
        return 200, {"dates": list(PROBE_DATES)}, "attendance_dates_synthetic"
    if path.endswith("/api/attendance/bimestre-summary"):
        return 200, [], "attendance_bimestre_summary_empty"
    if "/api/attendance/by-class/" in path:
        return 200, {"students": [], "records": [], "date": PROBE_DATES[-1]}, "attendance_body_synthetic_empty"
    if "/api/attendance/check-date" in path:
        return 200, {"allowed": True, "is_school_day": True}, "attendance_check_date"
    if path.endswith("/api/attendance/settings"):
        return 200, {"allow_future_dates": False}, "attendance_settings"
    if "/api/calendar/edit-status/" in path or path.endswith("/api/calendar/edit-status"):
        return 200, _open_edit_status(), "calendar_edit_status"
    if "/api/calendar" in path or "/api/events" in path:
        if "calendario-letivo" in path or "calendario_letivo" in path:
            return 200, {}, "calendar_school_year_empty"
        return 200, [], "calendar_events_empty"
    if "/api/medical" in path or "/api/vaccine" in path or "/api/vacina" in path:
        return 200, {}, "ancillary_health_empty"
    if "/api/branding" in path or "/api/mantenedora" in path:
        return 200, {}, "branding_empty"
    if "/api/permissions" in path or "/api/announcements" in path or "/api/messages" in path:
        return 200, [], "ancillary_empty"

    # Fail-safe local: uma API desconhecida nunca é encaminhada à produção.
    return 200, {}, "unknown_api_local_empty"


def evaluate_pair(pair: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    expected = len(PROBE_DATES)
    if not pair.get("content_prefill_ok"):
        failures.append("CONTENT_PREFILL_NOT_APPLIED")
    if int(pair.get("content_visible_probe_dates") or 0) != expected:
        failures.append("CONTENT_DOM_PROBE_COUNT_MISMATCH")
    if not pair.get("attendance_prefill_ok"):
        failures.append("ATTENDANCE_PREFILL_NOT_APPLIED")
    if int(pair.get("attendance_visible_probe_dates") or 0) != expected:
        failures.append("ATTENDANCE_DOM_PROBE_COUNT_MISMATCH")
    return not failures, failures


def evaluate_result(pairs: list[dict[str, Any]], *, expected_pairs: int = 6) -> dict[str, Any]:
    failures: list[str] = []
    if len(pairs) != expected_pairs:
        failures.append(f"TARGET_PAIR_COUNT:{len(pairs)}")
    for pair in pairs:
        ok, pair_failures = evaluate_pair(pair)
        if not ok:
            failures.extend(f"{pair.get('class')}:{failure}" for failure in pair_failures)
    return {
        "status": "PASS" if not failures else "FAIL",
        "classification": "PUBLIC_BROWSER_RENDER_CURRENT" if not failures else "PUBLIC_BROWSER_RENDER_GAP",
        "failures": failures,
    }


def _public_version(expected_sha: str) -> str:
    nonce = f"f4-{expected_sha[:12]}-{int(time.time())}"
    request = urllib.request.Request(
        f"{BASE_URL}/version.json?{nonce}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "sigesc-teacher-visibility-f4-readonly",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    actual = str(payload.get("git_sha") or "").strip()
    if actual != expected_sha:
        raise RuntimeError(f"TEACHER_VISIBILITY_F4_PUBLIC_VERSION_MISMATCH:{actual}")
    return actual


def _init_script() -> str:
    return f"""
    (() => {{
      const fixed = Date.parse({json.dumps(FIXED_BROWSER_NOW)});
      const RealDate = Date;
      class FixedDate extends RealDate {{
        constructor(...args) {{
          if (args.length === 0) super(fixed); else super(...args);
        }}
        static now() {{ return fixed; }}
      }}
      window.Date = FixedDate;
      localStorage.setItem('accessToken', 'f4-synthetic-local-token');
      localStorage.setItem('userData', JSON.stringify({json.dumps(_synthetic_user(), ensure_ascii=False)}));
      localStorage.setItem('lastLoginTime', String(fixed));
      localStorage.setItem('lastActivityTime', String(fixed));
    }})();
    """


def _selected_option_texts(page) -> list[str]:
    return page.locator("select").evaluate_all(
        "els => els.map(el => el.options && el.selectedIndex >= 0 ? (el.options[el.selectedIndex]?.text || '').trim() : '')"
    )


def _wait_prefill(page, class_name: str) -> bool:
    try:
        page.wait_for_function(
            """([klass, component]) => Array.from(document.querySelectorAll('select')).some(el =>
                 (el.options[el.selectedIndex]?.text || '').trim() === klass) &&
               Array.from(document.querySelectorAll('select')).some(el =>
                 (el.options[el.selectedIndex]?.text || '').trim() === component)""",
            arg=[class_name, COMPONENT_NAME],
            timeout=15000,
        )
        selected = _selected_option_texts(page)
        return class_name in selected and COMPONENT_NAME in selected
    except Exception:  # pragma: no cover - browser diagnostic path
        return False


def _content_visible_probe_dates(page) -> int:
    page.get_by_role("heading", name="Objetos de Conhecimento").wait_for(timeout=15000)
    wanted = sorted({str(int(date[-2:])) for date in PROBE_DATES})
    page.wait_for_function(
        """wanted => {
          const visible = new Set(
            Array.from(document.querySelectorAll('div.bg-green-100'))
              .map(el => (el.textContent || '').trim())
          );
          return wanted.every(day => visible.has(day));
        }""",
        arg=wanted,
        timeout=15000,
    )
    values = page.locator("div.bg-green-100").evaluate_all(
        "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)"
    )
    return len(set(wanted).intersection(set(values)))


def _attendance_visible_probe_dates(page) -> int:
    page.get_by_role("button", name="Registros", exact=True).click()
    page.locator('[data-testid="attendance-registros-tab"]').wait_for(timeout=15000)
    page.wait_for_function(
        "count => document.querySelectorAll('[title=\"Frequência registrada\"]').length >= count",
        arg=len(PROBE_DATES),
        timeout=15000,
    )
    return page.locator('[title="Frequência registrada"]').count()


def _target_url(path: str, target: Target) -> str:
    query = urllib.parse.urlencode({
        "academic_year": ACADEMIC_YEAR,
        "school_id": "f4-school",
        "class_id": target.class_id,
        "course_id": target.course_id,
    })
    return f"{BASE_URL}{path}?{query}"


def run_live_audit() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("TEACHER_VISIBILITY_F4_EXPECTED_SHA_INVALID")

    public_sha = _public_version(expected_sha)

    # Import tardio: testes unitários das fixtures não exigem Playwright instalado.
    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    base_origin = urllib.parse.urlsplit(BASE_URL)
    intercepted_api: list[str] = []
    fixture_keys: list[str] = []
    blocked_non_get: list[str] = []
    blocked_dynamic_get: list[str] = []
    blocked_websocket: list[str] = []
    pairs: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.add_init_script(_init_script())

        def route_handler(route, request):
            method = request.method.upper()
            parsed = urllib.parse.urlsplit(request.url)
            if method != "GET":
                blocked_non_get.append(f"{method} {parsed.path}")
                route.abort()
                return
            if "/api/" in parsed.path:
                status, body, fixture_key = fixture_for_api(request.url)
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
                if same_public_origin and parsed.path in PUBLIC_DYNAMIC_GET_PATHS:
                    route.continue_()
                    return
                blocked_dynamic_get.append(f"{request.resource_type} {parsed.netloc}{parsed.path}")
                route.abort()
                return
            route.continue_()

        def websocket_handler(web_socket_route):
            blocked_websocket.append(web_socket_route.url)
            web_socket_route.close(code=1000, reason="F4 read-only audit blocks WebSockets")

        context.route("**/*", route_handler)
        context.route_web_socket("**/*", websocket_handler)
        page = context.new_page()

        for target in TARGETS:
            page.goto(
                _target_url("/professor/objetos-conhecimento", target),
                wait_until="domcontentloaded",
                timeout=45000,
            )
            content_prefill = _wait_prefill(page, target.class_name)
            content_visible = _content_visible_probe_dates(page)

            page.goto(
                _target_url("/professor/frequencia", target),
                wait_until="domcontentloaded",
                timeout=45000,
            )
            attendance_prefill = _wait_prefill(page, target.class_name)
            attendance_visible = _attendance_visible_probe_dates(page)

            pairs.append({
                "class": target.class_name,
                "component": COMPONENT_NAME,
                "content_prefill_ok": content_prefill,
                "content_visible_probe_dates": content_visible,
                "attendance_prefill_ok": attendance_prefill,
                "attendance_visible_probe_dates": attendance_visible,
            })

        context.close()
        browser.close()

    evaluation = evaluate_result(pairs)
    unknown_count = sum(1 for key in fixture_keys if key == "unknown_api_local_empty")
    return {
        "schema": "TEACHER_VISIBILITY_F4_PUBLIC_BROWSER_RENDER_V1",
        "target": "production-public-frontend-with-local-synthetic-api",
        "expected_production_sha": expected_sha,
        "public_version_sha": public_sha,
        "academic_year": ACADEMIC_YEAR,
        "target_school": TARGET_SCHOOL,
        "target_pair_count": len(TARGETS),
        "probe_date_count": len(PROBE_DATES),
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
        "unknown_api_fixture_count": unknown_count,
        "blocked_non_get_attempt_count": len(blocked_non_get),
        "blocked_non_get_attempts": sorted(set(blocked_non_get)),
        "blocked_dynamic_get_attempt_count": len(blocked_dynamic_get),
        "blocked_dynamic_get_attempts": sorted(set(blocked_dynamic_get)),
        "blocked_websocket_attempt_count": len(blocked_websocket),
        "blocked_websocket_attempts": sorted(set(blocked_websocket)),
        "pairs": pairs,
        **evaluation,
    }


if __name__ == "__main__":
    result = run_live_audit()
    print("TEACHER_VISIBILITY_F4_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
