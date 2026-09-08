"""Contratos da evolução de Versões Curriculares por componente/série/bimestre."""
from pathlib import Path

import pytest

from routers.curriculum_scoped_versions import (
    SCOPED_KIND,
    _scope_key,
    _version_public,
    build_scoped_curriculum_router,
)
from services.curriculum_scoped_coverage_bridge import (
    VIRTUAL_VERSION_ID,
    _rewrite_virtual_plan_query,
    _scoped_scope_matchers,
)
from services.curriculum_structured_pdf import (
    StructuredCurriculumPdfError,
    extract_structured_curriculum_pdf,
    parse_complementary_table,
    parse_skill_table,
)


PILOT_MANDATORY = {
    "EF69LP03", "EF69LP05", "EF06LP04", "EF06LP05", "EF67LP38", "EF67LP32",
}
PILOT_COMPLEMENTARY = {"EF67LP08", "EF69LP07", "EF69LP08"}
PILOT_TRANSVERSAL = "EF06CO09"


def test_scope_key_isola_ano_componente_bimestre_e_serie():
    base = _scope_key(2026, "comp-lp", 3, ["6"])
    assert base == "2026|comp-lp|3|6"
    assert base != _scope_key(2026, "comp-ma", 3, ["6"])
    assert base != _scope_key(2026, "comp-lp", 2, ["6"])
    assert base != _scope_key(2026, "comp-lp", 3, ["7"])


def test_resumo_preserva_origens_normativas_separadas_do_piloto():
    doc = {
        "structured_payload": {
            "mandatory_skills": [{"code": code} for code in sorted(PILOT_MANDATORY)],
            "complementary_skills": [{"code": code} for code in sorted(PILOT_COMPLEMENTARY)],
            "transversal_skills": [{"code": PILOT_TRANSVERSAL}],
            "knowledge_object_groups": [{"practice_or_axis": "Leitura"}],
        },
        "skill_resolution": [
            {"code": code, "resolved": code != "EF67LP32"}
            for code in sorted(PILOT_MANDATORY)
        ],
    }
    result = _version_public(doc)["summary"]
    assert result == {
        "mandatory_skills": 6,
        "mandatory_resolved": 5,
        "mandatory_unresolved": 1,
        "complementary_skills": 3,
        "transversal_skills": 1,
        "knowledge_object_groups": 1,
    }


def test_parser_tabela_habilidades_reconhece_as_seis_obrigatorias_do_piloto():
    header = [
        "Código / status", "Habilidade - foco", "Objeto(s) associado(s)",
        "Evidência de aprendizagem", "Origem",
    ]
    rows = [
        [f"{code}\nDCM obrigatório", f"Foco {code}", "Objeto A; Objeto B", "Evidência", "DCM p. 41"]
        for code in sorted(PILOT_MANDATORY)
    ]
    parsed = parse_skill_table([header, *rows], source_page=3)
    assert {item["code"] for item in parsed} == PILOT_MANDATORY
    assert all(item["status"] == "mandatory" for item in parsed)
    assert all(item["knowledge_objects"] == ["Objeto A", "Objeto B"] for item in parsed)


def test_parser_tabela_complementar_nao_promove_habilidade_a_obrigatoria():
    table = [
        ["Código", "Finalidade", "Uso no 3º bimestre"],
        *[[code, "Apoio técnico", "Uso complementar"] for code in sorted(PILOT_COMPLEMENTARY)],
    ]
    parsed = parse_complementary_table(table, source_page=4)
    assert {item["code"] for item in parsed} == PILOT_COMPLEMENTARY
    assert all(item["status"] == "complementary" for item in parsed)


def test_pdf_invalido_falha_antes_de_qualquer_inferencia():
    with pytest.raises(StructuredCurriculumPdfError) as exc:
        extract_structured_curriculum_pdf(b"isto nao e pdf")
    assert exc.value.code == "CURRICULUM_PDF_INVALID"


def test_router_expoe_fluxo_completo_da_versao_escopada():
    router = build_scoped_curriculum_router(object())
    signatures = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/scoped-versions", "GET") in signatures
    assert ("/scoped-versions/upload", "POST") in signatures
    assert ("/scoped-versions/{version_id}", "GET") in signatures
    assert ("/scoped-versions/{version_id}", "PUT") in signatures
    assert ("/scoped-versions/{version_id}/refresh-skill-resolution", "POST") in signatures
    assert ("/scoped-versions/{version_id}/publish", "POST") in signatures
    assert ("/scoped-versions/{version_id}/create-teaching-plan", "POST") in signatures


def test_publicacao_supersede_somente_mesmo_scope_e_plano_usa_obrigatorias():
    source = Path("routers/curriculum_scoped_versions.py").read_text(encoding="utf-8")
    assert '"scope_key": current["scope_key"]' in source
    assert '"status": "published"' in source
    assert "CURRICULUM_VERSION_SKILLS_UNRESOLVED" in source
    assert 'payload.get("mandatory_skills")' in source
    assert 'payload.get("complementary_skills")' not in source[source.index("async def create_teaching_plan_from_version"):]
    assert "delete_from_ftp(document_url)" in source


def test_matcher_de_precedencia_e_exato_por_componente_bimestre_serie():
    scoped = [
        {
            "id": "v-lp-6-b3",
            "scope_kind": SCOPED_KIND,
            "component_id": "comp-lp",
            "bimestre": 3,
            "grade_scope": ["6"],
        }
    ]
    assert _scoped_scope_matchers(scoped) == [
        {"component_id": "comp-lp", "bimestre": 3, "grade_scope": "6"}
    ]


def test_bridge_evitar_plano_anual_duplicado_no_mesmo_escopo():
    query = {
        "mantenedora_id": "tenant-a",
        "academic_year": 2026,
        "curriculum_version_id": VIRTUAL_VERSION_ID,
        "status": "published",
        "component_id": "comp-lp",
        "grade_scope": "6",
    }
    scoped = [
        {
            "id": "v-lp-6-b3",
            "component_id": "comp-lp",
            "bimestre": 3,
            "grade_scope": ["6"],
        }
    ]
    annual = [{"id": "v-anual"}]
    rewritten = _rewrite_virtual_plan_query(query, scoped_docs=scoped, annual_docs=annual)

    base, version_clause = rewritten["$and"]
    assert base["component_id"] == "comp-lp"
    assert base["grade_scope"] == "6"
    assert "curriculum_version_id" not in base
    assert version_clause["$or"][0] == {"curriculum_version_id": {"$in": ["v-lp-6-b3"]}}
    annual_branch = version_clause["$or"][1]["$and"]
    assert annual_branch[0] == {"curriculum_version_id": {"$in": ["v-anual"]}}
    assert annual_branch[1] == {
        "$nor": [{"component_id": "comp-lp", "bimestre": 3, "grade_scope": "6"}]
    }


def test_bridge_sem_virtual_nao_altera_query():
    query = {"curriculum_version_id": "versao-real", "status": "published"}
    assert _rewrite_virtual_plan_query(query, scoped_docs=[], annual_docs=[]) == query
