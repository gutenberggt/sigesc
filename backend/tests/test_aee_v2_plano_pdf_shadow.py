import asyncio
from copy import deepcopy

from fastapi import APIRouter, FastAPI

from aee_v2.plano_pdf_shadow import (
    PDF_PLAN_FIELDS,
    build_plano_pdf_shadow,
    compare_pdf_plan_fields,
    install_aee_v2_plano_pdf_shadow,
)


class _Plans:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query, projection):
        if self.doc and self.doc.get("id") == query.get("id"):
            return deepcopy(self.doc)
        return None


class _DB:
    def __init__(self, doc):
        self.planos_aee = _Plans(doc)


def _legacy_plan():
    return {
        "id": "plan-1",
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "status": "ativo",
        "data_elaboracao": "2026-02-01",
        "periodo_vigencia": "2026-02-01 a 2026-12-15",
        "publico_alvo": "deficiencia_intelectual",
        "criterio_elegibilidade": "Fundamentação legado",
        "escola_origem_nome": "Escola",
        "turma_origem_nome": "Turma A",
        "professor_regente_nome": "Regente",
        "professor_aee_nome": "Professor AEE",
        "orientacoes_sala_comum": "Orientações",
        "combinados_professor_regente": "Combinados",
        "adequacoes_curriculares": "Adequações",
        "adaptacoes_por_componente": "Adaptações",
        "linha_base_situacao_atual": "Situação",
        "linha_base_potencialidades": "Potencialidades",
        "linha_base_dificuldades": "Dificuldades",
        "linha_base_comunicacao": "Comunicação",
        "modalidade": "individual",
        "carga_horaria_semanal": "1h30",
        "dias_atendimento": ["terca"],
        "horario_inicio": "09:30",
        "horario_fim": "11:00",
        "local_atendimento": "Sala de Recursos Multifuncionais",
        "barreiras": [{"descricao": "Barreira"}],
        "objetivos": [{"descricao": "Objetivo", "prazo": "bimestral"}],
        "recursos_acessibilidade": [{"descricao": "Recurso", "tipo": "outro"}],
        "indicadores_progresso": "Indicadores",
        "frequencia_revisao": "bimestral",
        "criterios_ajuste": "Critérios",
        "data_revisao": "2026-09-14",
    }


def test_compare_uses_only_rendered_semantics():
    legacy = _legacy_plan()
    candidate = deepcopy(legacy)
    candidate["objetivos"] = [{"descricao": "Objetivo", "prazo": "anual"}]
    candidate["recursos_acessibilidade"] = [{"descricao": "Recurso", "tipo": "tecnologia"}]

    result = compare_pdf_plan_fields(legacy, candidate)

    assert result["fields_total"] == len(PDF_PLAN_FIELDS)
    assert result["parity"] is True
    assert result["divergent_fields"] == []


def test_sidecar_shadow_detects_field_names_without_mutating_legacy():
    async def scenario():
        legacy = _legacy_plan()
        db = _DB(legacy)
        before = deepcopy(legacy)

        async def context_builder(db, plano_id):
            return {
                "status": "effective",
                "effective_source": "sidecar_active",
                "effective_version": {
                    "active_snapshot_id": "snap-1",
                    "document_version": 1,
                    "revision": 14,
                },
            }

        def projector(plan, context):
            candidate = deepcopy(plan)
            candidate["status"] = "revisao"
            candidate["horario_inicio"] = "10:00"
            return candidate, {
                "status": "effective",
                "plan_source": "sidecar_active",
                "blockers": [],
            }

        diagnostic = await build_plano_pdf_shadow(
            db,
            "plan-1",
            context_builder=context_builder,
            projector=projector,
        )

        assert legacy == before
        assert diagnostic["status"] == "divergent"
        assert diagnostic["effective_source"] == "sidecar_active"
        assert diagnostic["divergent_fields"] == ["status", "horario_inicio"]
        assert diagnostic["divergent_count"] == 2
        assert "Fundamentação legado" not in repr(diagnostic)

    asyncio.run(scenario())


def test_legacy_shadow_reports_full_parity():
    async def scenario():
        legacy = _legacy_plan()
        db = _DB(legacy)

        async def context_builder(db, plano_id):
            return {
                "status": "legacy",
                "effective_source": "legacy",
                "effective_version": None,
            }

        def projector(plan, context):
            return plan, {
                "status": "legacy",
                "plan_source": "legacy",
                "blockers": [],
            }

        diagnostic = await build_plano_pdf_shadow(
            db,
            "plan-1",
            context_builder=context_builder,
            projector=projector,
        )

        assert diagnostic["status"] == "parity"
        assert diagnostic["parity"] is True
        assert diagnostic["equal_count"] == len(PDF_PLAN_FIELDS)
        assert diagnostic["divergent_count"] == 0

    asyncio.run(scenario())


def test_blocked_projection_is_explicit_and_fail_closed():
    async def scenario():
        legacy = _legacy_plan()
        db = _DB(legacy)

        async def context_builder(db, plano_id):
            return {
                "status": "effective",
                "effective_source": "sidecar_active",
                "effective_version": {"document_version": 1, "revision": 14},
            }

        def projector(plan, context):
            return plan, {
                "status": "blocked",
                "plan_source": "legacy",
                "blockers": [{"code": "AEE_V2_PLANO_PDF_NOT_FLATTENABLE"}],
            }

        diagnostic = await build_plano_pdf_shadow(
            db,
            "plan-1",
            context_builder=context_builder,
            projector=projector,
        )

        assert diagnostic["status"] == "blocked"
        assert diagnostic["parity"] is None
        assert diagnostic["blockers"][0]["code"] == "AEE_V2_PLANO_PDF_NOT_FLATTENABLE"

    asyncio.run(scenario())


def test_route_returns_exact_same_legacy_pdf_response_object():
    async def scenario():
        router = APIRouter()
        sentinel = object()
        calls = []

        @router.get("/aee/planos/{plano_id}/pdf")
        async def legacy_pdf(plano_id: str):
            calls.append(("legacy", plano_id))
            return sentinel

        async def diagnostic_builder(db, plano_id):
            calls.append(("shadow", plano_id))
            return {
                "phase": "6.5A",
                "mode": "shadow_read_only",
                "status": "parity",
                "effective_source": "legacy",
                "effective_version": None,
                "fields_total": len(PDF_PLAN_FIELDS),
                "equal_count": len(PDF_PLAN_FIELDS),
                "divergent_count": 0,
                "divergent_fields": [],
                "parity": True,
                "blockers": [],
                "error": None,
            }

        install_aee_v2_plano_pdf_shadow(
            router,
            object(),
            diagnostics_builder=diagnostic_builder,
        )

        route = next(r for r in router.routes if r.path == "/aee/planos/{plano_id}/pdf")
        result = await route.endpoint(plano_id="plan-1")

        assert result is sentinel
        assert calls == [("legacy", "plan-1"), ("shadow", "plan-1")]

    asyncio.run(scenario())


def test_install_is_idempotent_and_survives_fastapi_include_router():
    router = APIRouter()

    @router.get("/aee/planos/{plano_id}/pdf")
    async def legacy_pdf(plano_id: str):
        return {"id": plano_id}

    install_aee_v2_plano_pdf_shadow(router, object())
    first = next(r for r in router.routes if r.path == "/aee/planos/{plano_id}/pdf").endpoint
    install_aee_v2_plano_pdf_shadow(router, object())
    second = next(r for r in router.routes if r.path == "/aee/planos/{plano_id}/pdf").endpoint

    assert first is second

    app = FastAPI()
    app.include_router(router, prefix="/api")
    final = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/api/aee/planos/{plano_id}/pdf"
    )

    assert final.endpoint.__code__.co_filename.endswith("/aee_v2/plano_pdf_shadow.py")
    assert hasattr(final.endpoint, "__wrapped__")


def test_runtime_setup_activates_6_5b_cutover_after_6_5a_homologation():
    source = open("routers/__init__.py", encoding="utf-8").read()

    assert "install_aee_v2_plano_pdf_effective_setup(_aee_mod)" in source
    assert "install_aee_v2_plano_pdf_shadow_setup(_aee_mod)" not in source
