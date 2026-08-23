import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from aee_v2.plano_pdf_effective import (
    build_plano_pdf_effective_context,
    install_aee_v2_plano_pdf_effective,
    install_plano_pdf_generator_effective,
    project_effective_pdf_plan,
)


class FakeDossier:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, mode="python"):
        assert mode in {"python", "json"}
        return deepcopy(self.payload)


def dossier_payload(*, sessions=None):
    return {
        "schema_version": 2,
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "professor_aee_responsavel_id": "prof-1",
        "professor_aee_responsavel_nome": "Professor Efetivo",
        "publico_alvo": "deficiencia_intelectual",
        "turma_origem_id": "class-1",
        "turma_origem_nome": "5º ANO A",
        "escola_origem_nome": "Escola Origem",
        "professor_regente_id": "regente-1",
        "professor_regente_nome": "Professor Regente",
        "study_case": {
            "state": "complete",
            "fundamentacao_pedagogica_identificacao": "Fundamentação V2",
            "demanda_inicial_contexto": "Situação V2",
            "barreiras_contexto": ["Barreira A"],
            "potencialidades": "Potencialidades V2",
            "demandas_apoio": "Demandas V2",
            "comunicacao_participacao": "Comunicação V2",
        },
        "paee": {
            "state": "complete",
            "barreiras_prioritarias": ["Barreira prioritária"],
            "objetivos": [
                {
                    "descricao": "Objetivo V2",
                    "prazo": "bimestral",
                    "status": "em_andamento",
                    "indicadores": ["Indicador 1"],
                }
            ],
            "materiais_recursos": [
                {
                    "tipo": "outro",
                    "descricao": "Recurso V2",
                    "disponivel": True,
                }
            ],
            "indicadores_progresso": "Indicadores V2",
            "frequencia_revisao": "bimestral",
            "criterios_ajuste": "Critérios V2",
        },
        "pei": {
            "state": "complete",
            "articulacao_sala_comum": "Articulação V2",
            "combinados_professor_regente": "Combinados V2",
            "acessibilidade_curricular": "Curricular V2",
            "acessibilidade_didatico_pedagogica": "Didática V2",
            "acessibilidade_avaliativa": "Avaliativa V2",
            "adaptacoes_por_componente": "Adaptações V2",
        },
        "schedule": {
            "carga_horaria_semanal": "1h30",
            "sessions": sessions
            if sessions is not None
            else [
                {
                    "weekday": "terca",
                    "start": "09:30",
                    "end": "11:00",
                    "local": "SALA DE RECURSOS MULTIFUNCIONAIS",
                    "modalidade": "individual",
                }
            ],
        },
        "lifecycle": {
            "status": "active",
            "version": 2,
            "elaborated_at": "2026-08-01",
            "effective_from": "2026-08-01",
            "effective_to": "2026-12-20",
            "review_at": "2026-09-14",
            "periodo_vigencia_legacy": None,
        },
        "provenance": {"legacy_plano_id": "legacy-1"},
    }


def legacy_plan():
    return {
        "id": "legacy-1",
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "status": "rascunho",
        "professor_aee_nome": "Professor Legado",
        "publico_alvo": "deficiencia_fisica",
        "criterio_elegibilidade": "Fundamentação legado",
        "dias_atendimento": ["segunda"],
        "horario_inicio": "13:00",
        "horario_fim": "14:00",
        "local_atendimento": "Local legado",
        "modalidade": "individual",
        "barreiras": [{"descricao": "Barreira legado"}],
        "objetivos": [{"descricao": "Objetivo legado"}],
        "recursos_acessibilidade": [{"descricao": "Recurso legado"}],
    }


def resolved(source="sidecar_active", payload=None):
    return SimpleNamespace(
        source=source,
        active_snapshot_id="snapshot-1" if source == "sidecar_active" else None,
        document_version=1 if source == "sidecar_active" else None,
        revision=14 if source == "sidecar_active" else None,
        dossier=FakeDossier(payload or dossier_payload()),
    )


def test_build_context_sidecar_active_serializes_version_and_dossier():
    async def fake_resolver(db, plano_id):
        assert db == "db"
        assert plano_id == "legacy-1"
        return resolved()

    context = asyncio.run(
        build_plano_pdf_effective_context("db", "legacy-1", resolver=fake_resolver)
    )

    assert context["status"] == "effective"
    assert context["plan_source"] == "sidecar_active"
    assert context["effective_version"] == {
        "active_snapshot_id": "snapshot-1",
        "document_version": 1,
        "revision": 14,
    }
    assert context["dossier"]["schema_version"] == 2
    assert context["blockers"] == []


def test_build_context_legacy_keeps_legacy_as_effective_source():
    async def fake_resolver(db, plano_id):
        return resolved(source="legacy")

    context = asyncio.run(
        build_plano_pdf_effective_context("db", "legacy-1", resolver=fake_resolver)
    )

    assert context["status"] == "legacy"
    assert context["effective_source"] == "legacy"
    assert context["effective_version"] is None
    assert context["dossier"] is None


def test_project_active_snapshot_maps_pdf_fields_without_mutating_legacy():
    original = legacy_plan()
    before = deepcopy(original)
    context = {
        "status": "effective",
        "effective_source": "sidecar_active",
        "effective_version": {
            "active_snapshot_id": "snapshot-1",
            "document_version": 1,
            "revision": 14,
        },
        "dossier": dossier_payload(),
        "blockers": [],
    }

    projected, metadata = project_effective_pdf_plan(original, context)

    assert original == before
    assert projected is not original
    assert metadata["status"] == "effective"
    assert metadata["plan_source"] == "sidecar_active"
    assert projected["status"] == "ativo"
    assert projected["criterio_elegibilidade"] == "Fundamentação V2"
    assert projected["professor_aee_nome"] == "Professor Efetivo"
    assert projected["dias_atendimento"] == ["terca"]
    assert projected["horario_inicio"] == "09:30"
    assert projected["horario_fim"] == "11:00"
    assert projected["barreiras"] == [{"descricao": "Barreira prioritária"}]
    assert projected["objetivos"][0]["descricao"] == "Objetivo V2"
    assert projected["recursos_acessibilidade"][0]["descricao"] == "Recurso V2"
    assert "Curricular: Curricular V2" in projected["adequacoes_curriculares"]
    assert "Didático-pedagógica: Didática V2" in projected["adequacoes_curriculares"]
    assert "Avaliativa: Avaliativa V2" in projected["adequacoes_curriculares"]
    assert projected["data_revisao"] == "2026-09-14"


def test_single_curricular_accessibility_preserves_legacy_pdf_semantics():
    original = legacy_plan()
    payload = dossier_payload()
    payload["pei"]["acessibilidade_curricular"] = "Adequação curricular"
    payload["pei"]["acessibilidade_didatico_pedagogica"] = None
    payload["pei"]["acessibilidade_avaliativa"] = None

    projected, metadata = project_effective_pdf_plan(
        original,
        {
            "status": "effective",
            "effective_source": "sidecar_active",
            "dossier": payload,
            "blockers": [],
        },
    )

    assert metadata["status"] == "effective"
    assert projected["adequacoes_curriculares"] == "Adequação curricular"


def test_non_flattenable_schedule_blocks_and_returns_same_legacy_object():
    sessions = [
        {
            "weekday": "terca",
            "start": "09:30",
            "end": "11:00",
            "local": "SRM",
            "modalidade": "individual",
        },
        {
            "weekday": "quinta",
            "start": "13:30",
            "end": "15:00",
            "local": "SRM",
            "modalidade": "individual",
        },
    ]
    original = legacy_plan()
    context = {
        "status": "effective",
        "effective_source": "sidecar_active",
        "dossier": dossier_payload(sessions=sessions),
        "blockers": [],
    }

    projected, metadata = project_effective_pdf_plan(original, context)

    assert projected is original
    assert metadata["status"] == "blocked"
    assert any(
        item["code"] == "AEE_V2_PLANO_PDF_NOT_FLATTENABLE"
        for item in metadata["blockers"]
    )


def test_identity_mismatch_blocks_cutover():
    payload = dossier_payload()
    payload["student_id"] = "other-student"
    original = legacy_plan()

    projected, metadata = project_effective_pdf_plan(
        original,
        {
            "status": "effective",
            "effective_source": "sidecar_active",
            "dossier": payload,
            "blockers": [],
        },
    )

    assert projected is original
    assert metadata["status"] == "blocked"
    assert any(
        item["code"] == "AEE_V2_PLANO_PDF_IDENTITY_MISMATCH"
        and item["field"] == "student_id"
        for item in metadata["blockers"]
    )


def test_generator_adapter_is_idempotent_and_uses_context_only_when_present():
    calls = []

    def original_generator(plano, student, school, mantenedora):
        calls.append(deepcopy(plano))
        return plano.get("criterio_elegibilidade")

    module = SimpleNamespace(generate_plano_aee_pdf=original_generator)
    install_plano_pdf_generator_effective(module)
    wrapped = module.generate_plano_aee_pdf
    install_plano_pdf_generator_effective(module)
    assert module.generate_plano_aee_pdf is wrapped

    # Sem contexto, comportamento legado puro.
    assert wrapped(legacy_plan(), {}, {}, {}) == "Fundamentação legado"


def test_route_and_generator_cutover_survive_fastapi_include_router():
    generator_calls = []

    def original_generator(plano, student, school, mantenedora):
        generator_calls.append(deepcopy(plano))
        return {"source_value": plano.get("criterio_elegibilidade")}

    generator_module = SimpleNamespace(generate_plano_aee_pdf=original_generator)
    router = APIRouter(prefix="/aee")

    @router.get("/planos/{plano_id}/pdf")
    async def legacy_pdf(plano_id: str):
        return generator_module.generate_plano_aee_pdf(
            legacy_plan(),
            {},
            {},
            {},
        )

    async def fake_resolver(db, plano_id):
        assert plano_id == "legacy-1"
        return resolved()

    install_aee_v2_plano_pdf_effective(
        router,
        "db",
        generator_module=generator_module,
        resolver=fake_resolver,
    )
    # Idempotência do router.
    first = router.routes[0].endpoint
    install_aee_v2_plano_pdf_effective(
        router,
        "db",
        generator_module=generator_module,
        resolver=fake_resolver,
    )
    assert router.routes[0].endpoint is first

    app = FastAPI()
    app.include_router(router, prefix="/api")
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/aee/planos/{plano_id}/pdf"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1
    route = matches[0]
    assert route.endpoint.__code__.co_filename.endswith("/aee_v2/plano_pdf_effective.py")
    assert route.endpoint.__wrapped__.__code__.co_filename.endswith(
        "/tests/test_aee_v2_plano_pdf_effective.py"
    )

    result = asyncio.run(route.endpoint(plano_id="legacy-1"))
    assert result == {"source_value": "Fundamentação V2"}
    assert generator_calls[-1]["horario_inicio"] == "09:30"
    assert generator_calls[-1]["status"] == "ativo"

    # ContextVar foi resetado: chamada direta seguinte volta ao legado.
    result_after = generator_module.generate_plano_aee_pdf(legacy_plan(), {}, {}, {})
    assert result_after == {"source_value": "Fundamentação legado"}
