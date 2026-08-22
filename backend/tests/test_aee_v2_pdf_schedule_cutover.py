import asyncio
from copy import deepcopy
from types import ModuleType

from fastapi import APIRouter, FastAPI

from aee_v2.pdf_schedule_cutover import (
    apply_pdf_schedule_cutover,
    build_pdf_cutover_context,
    install_aee_v2_pdf_schedule_cutover,
)


def _item(plan_id="p1", *, sessions=None, status="parity", parity=True, source="legacy"):
    if sessions is None:
        sessions = [
            {
                "weekday": "terca",
                "start": "09:30",
                "end": "11:00",
                "local": "Sala de Recursos Multifuncionais",
                "modalidade": "individual",
            }
        ]
    return {
        "legacy_plano_id": plan_id,
        "status": status,
        "effective_source": source,
        "effective_version": None,
        "legacy_sessions": deepcopy(sessions),
        "effective_sessions": deepcopy(sessions),
        "parity": parity,
        "error": None,
    }


def _diagnostic(*items, status="parity", errors=0, divergences=0):
    items = list(items) or [_item()]
    return {
        "phase": "6.3A",
        "mode": "shadow_read_only",
        "status": status,
        "plans_total": len(items),
        "sidecar_active_plans": sum(1 for i in items if i.get("effective_source") == "sidecar_active"),
        "legacy_plans": sum(1 for i in items if i.get("effective_source") == "legacy"),
        "parity_plans": sum(1 for i in items if i.get("status") == "parity"),
        "divergent_plans": divergences,
        "error_plans": errors,
        "items": items,
    }


def _payload():
    fichas = [
        {
            "plano": {
                "id": "p1",
                "student_id": "s1",
                "dias_atendimento": ["terca"],
                "horario_inicio": "09:30",
                "horario_fim": "11:00",
                "local_atendimento": "Sala de Recursos Multifuncionais",
                "modalidade": "individual",
            },
            "student": {"id": "s1", "full_name": "Estudante Teste"},
            "atendimentos": [],
            "estatisticas": {},
        }
    ]
    grade = {
        "terca": [
            {
                "student_name": "Estudante Teste",
                "horario_inicio": "09:30",
                "horario_fim": "11:00",
            }
        ]
    }
    return fichas, grade


def test_parity_diagnostic_authorizes_cutover():
    context = build_pdf_cutover_context(
        _diagnostic(_item(source="sidecar_active"))
    )

    assert context["status"] == "effective"
    assert context["grade_source"] == "effective"
    assert context["blockers"] == []
    assert "p1" in context["items"]


def test_divergence_or_error_blocks_cutover_fail_closed():
    divergent = build_pdf_cutover_context(
        _diagnostic(
            _item(status="divergent", parity=False),
            status="divergent",
            divergences=1,
        )
    )
    assert divergent["status"] == "blocked"
    assert divergent["grade_source"] == "legacy"

    errored = build_pdf_cutover_context(
        _diagnostic(_item(), status="partial_error", errors=1)
    )
    assert errored["status"] == "blocked"
    assert errored["grade_source"] == "legacy"


def test_apply_cutover_uses_effective_schedule_without_mutating_legacy_payload():
    sessions = [
        {
            "weekday": "terca",
            "start": "09:30",
            "end": "11:00",
            "local": "Sala de Recursos Multifuncionais",
            "modalidade": "individual",
        },
        {
            "weekday": "quinta",
            "start": "09:30",
            "end": "11:00",
            "local": "Sala de Recursos Multifuncionais",
            "modalidade": "individual",
        },
    ]
    context = build_pdf_cutover_context(_diagnostic(_item(sessions=sessions)))
    fichas, grade = _payload()
    original_fichas = deepcopy(fichas)
    original_grade = deepcopy(grade)

    effective_fichas, effective_grade, metadata = apply_pdf_schedule_cutover(
        fichas,
        grade,
        context,
    )

    assert metadata["status"] == "effective"
    assert metadata["sessions_total"] == 2
    assert effective_fichas[0]["plano"]["dias_atendimento"] == ["terca", "quinta"]
    assert effective_fichas[0]["plano"]["horario_inicio"] == "09:30"
    assert set(effective_grade) == {"terca", "quinta"}
    assert fichas == original_fichas
    assert grade == original_grade


def test_non_flattenable_schedule_blocks_atomically_and_preserves_legacy():
    sessions = [
        {
            "weekday": "terca",
            "start": "09:30",
            "end": "11:00",
            "local": "Sala de Recursos Multifuncionais",
            "modalidade": "individual",
        },
        {
            "weekday": "quinta",
            "start": "13:00",
            "end": "14:00",
            "local": "Sala de Recursos Multifuncionais",
            "modalidade": "individual",
        },
    ]
    # O teste força um contexto previamente autorizado para provar que a segunda
    # barreira (lossless flattening) continua fail-closed.
    context = {
        "status": "effective",
        "grade_source": "effective",
        "diagnostic": _diagnostic(_item(sessions=sessions)),
        "items": {"p1": _item(sessions=sessions)},
        "blockers": [],
    }
    fichas, grade = _payload()

    result_fichas, result_grade, metadata = apply_pdf_schedule_cutover(
        fichas,
        grade,
        context,
    )

    assert metadata["status"] == "blocked"
    assert metadata["grade_source"] == "legacy"
    assert any(b["code"] == "AEE_V2_PDF_CUTOVER_NOT_FLATTENABLE" for b in metadata["blockers"])
    assert result_fichas is fichas
    assert result_grade is grade


def test_route_wrapper_and_generator_adapter_survive_include_router_and_preserve_response():
    router = APIRouter(prefix="/aee")
    generator_module = ModuleType("fake_pdf_diario_aee")
    captured = {}

    def generate_diario_aee_pdf(*, fichas, grade_horarios):
        captured["fichas"] = deepcopy(fichas)
        captured["grade"] = deepcopy(grade_horarios)
        return b"PDF-ORIGINAL"

    generator_module.generate_diario_aee_pdf = generate_diario_aee_pdf

    @router.get("/diario/pdf")
    async def get_diario_aee_pdf(request=None, school_id: str = "school", academic_year: int = 2026):
        fichas, grade = _payload()
        pdf = generator_module.generate_diario_aee_pdf(
            fichas=fichas,
            grade_horarios=grade,
        )
        return {"pdf": pdf, "marker": "original-response"}

    async def user_getter(_request):
        return {"id": "u1", "role": "admin"}

    async def diagnostics_builder(*args, **kwargs):
        sessions = [
            {
                "weekday": "terca",
                "start": "09:30",
                "end": "11:00",
                "local": "Sala de Recursos Multifuncionais",
                "modalidade": "individual",
            }
        ]
        return _diagnostic(_item(sessions=sessions, source="sidecar_active"))

    install_aee_v2_pdf_schedule_cutover(
        router,
        db=object(),
        user_getter=user_getter,
        generator_module=generator_module,
        diagnostics_builder=diagnostics_builder,
    )
    # Idempotência.
    install_aee_v2_pdf_schedule_cutover(
        router,
        db=object(),
        user_getter=user_getter,
        generator_module=generator_module,
        diagnostics_builder=diagnostics_builder,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    route = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/api/aee/diario/pdf"
        and "GET" in (getattr(r, "methods", set()) or set())
    )

    assert route.endpoint.__code__.co_filename.endswith("/aee_v2/pdf_schedule_cutover.py")
    assert hasattr(route.endpoint, "__wrapped__")

    response = asyncio.run(
        route.endpoint(request=object(), school_id="school", academic_year=2026)
    )

    assert response == {"pdf": b"PDF-ORIGINAL", "marker": "original-response"}
    assert captured["fichas"][0]["plano"]["dias_atendimento"] == ["terca"]
    assert captured["grade"]["terca"][0]["horario_inicio"] == "09:30"
