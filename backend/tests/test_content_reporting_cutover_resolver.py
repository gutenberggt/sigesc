"""Gate S2 — resolver canônico de escopos de cutover para reporting."""
from pathlib import Path

import pytest

from services.content_reporting_cutover_resolver import (
    ContentReportingCutoverResolutionError,
    resolve_content_reporting_cutover_scopes,
)


TENANT = "tenant-a"
CLASS = "class-a"
COMP = "comp-a"


def _class(*, year=2026, tenant=TENANT, class_id=CLASS):
    return {
        "id": class_id,
        "school_id": "school-a",
        "mantenedora_id": tenant,
        "academic_year": year,
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º ANO",
        "atendimento_programa": None,
    }


def _assignment(
    *,
    item_id="a-1",
    class_id=CLASS,
    component_id=COMP,
    tenant=TENANT,
    valid_from="2026-08-18",
    valid_until=None,
    deleted=False,
    enabled=True,
    profile="regular",
    school_id="school-a",
):
    return {
        "id": item_id,
        "teacher_id": f"teacher-{item_id}",
        "class_id": class_id,
        "component_id": component_id,
        "school_id": school_id,
        "mantenedora_id": tenant,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "deleted": deleted,
        "diary_settings": {
            "enabled": enabled,
            "schema_version": 1,
            "profile": profile,
            "student_scope": "all",
        },
    }


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


def _value(doc, path):
    value = doc
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(doc, query):
    for key, expected in query.items():
        value = _value(doc, key)
        if isinstance(expected, dict):
            for op, target in expected.items():
                if op == "$in" and value not in target:
                    return False
            continue
        if value != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def find(self, query, projection=None):
        del projection
        return FakeCursor([doc for doc in self.docs if _matches(doc, query)])


class FakeDb:
    def __init__(self, *, classes=None, assignments=None):
        self.classes = FakeCollection(classes if classes is not None else [_class()])
        self.teacher_class_assignments = FakeCollection(
            assignments if assignments is not None else []
        )


@pytest.mark.asyncio
async def test_s2_resolve_vinculo_especifico_de_componente():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(assignments=[_assignment()]),
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
        class_ids=[CLASS],
    )

    assert len(result.scopes) == 1
    scope = result.scopes[0]
    assert scope.class_id == CLASS
    assert scope.component_id == COMP
    assert scope.valid_from == "2026-08-18"
    assert result.diagnostics["assignments_current_content"] == 1


@pytest.mark.asyncio
async def test_s2_resolve_vinculo_classwide():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(assignments=[_assignment(component_id=None)]),
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
    )

    assert len(result.scopes) == 1
    assert result.scopes[0].component_id is None
    assert result.scopes[0].valid_from == "2026-08-18"


@pytest.mark.asyncio
async def test_s2_preserva_classwide_e_especifico_para_precedencia_do_read_model():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(
            assignments=[
                _assignment(item_id="wide", component_id=None, valid_from="2026-08-01"),
                _assignment(item_id="exact", component_id=COMP, valid_from="2026-08-18"),
            ]
        ),
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
    )

    by_key = {(scope.class_id, scope.component_id): scope.valid_from for scope in result.scopes}
    assert by_key[(CLASS, None)] == "2026-08-01"
    assert by_key[(CLASS, COMP)] == "2026-08-18"


@pytest.mark.asyncio
async def test_s2_ignora_vinculo_encerrado_desabilitado_ou_excluido():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(
            assignments=[
                _assignment(item_id="ended", valid_until="2026-08-31"),
                _assignment(item_id="disabled", enabled=False),
                _assignment(item_id="deleted", deleted=True),
            ]
        ),
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
    )

    assert result.scopes == ()
    assert result.diagnostics["assignments_ignored_not_current"] == 1
    assert result.diagnostics["assignments_ignored_disabled"] == 1
    assert result.diagnostics["assignments_ignored_deleted"] == 1


@pytest.mark.asyncio
async def test_s2_falha_fechado_em_tenant_divergente_no_vinculo():
    with pytest.raises(ContentReportingCutoverResolutionError) as exc:
        await resolve_content_reporting_cutover_scopes(
            FakeDb(assignments=[_assignment(tenant="tenant-b")]),
            mantenedora_id=TENANT,
            academic_year=2026,
            reference_date="2026-09-08",
        )

    assert exc.value.code == "CONTENT_REPORTING_CUTOVER_TENANT_MISMATCH"


@pytest.mark.asyncio
async def test_s2_aceita_ano_historico_persistido_como_string():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(
            classes=[_class(year="2025")],
            assignments=[_assignment(valid_from="2025-08-18")],
        ),
        mantenedora_id=TENANT,
        academic_year=2025,
        reference_date="2025-10-15",
    )

    assert len(result.scopes) == 1
    assert result.scopes[0].valid_from == "2025-08-18"
    assert result.academic_year == 2025


@pytest.mark.asyncio
async def test_s2_sem_vinculo_valido_retorna_ausencia_de_cutover_sem_inferir_dados():
    result = await resolve_content_reporting_cutover_scopes(
        FakeDb(assignments=[]),
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
    )

    assert result.scopes == ()
    assert result.diagnostics["assignments_seen"] == 0


@pytest.mark.asyncio
async def test_s2_falha_fechado_em_datas_de_corte_ambiguas_no_mesmo_escopo():
    with pytest.raises(ContentReportingCutoverResolutionError) as exc:
        await resolve_content_reporting_cutover_scopes(
            FakeDb(
                assignments=[
                    _assignment(item_id="a", valid_from="2026-08-18"),
                    _assignment(item_id="b", valid_from="2026-08-20"),
                ]
            ),
            mantenedora_id=TENANT,
            academic_year=2026,
            reference_date="2026-09-08",
        )

    assert exc.value.code == "CONTENT_REPORTING_CUTOVER_AMBIGUOUS"


@pytest.mark.asyncio
async def test_s2_rejeita_reference_date_de_outro_ano():
    with pytest.raises(ContentReportingCutoverResolutionError) as exc:
        await resolve_content_reporting_cutover_scopes(
            FakeDb(),
            mantenedora_id=TENANT,
            academic_year=2026,
            reference_date="2025-12-31",
        )

    assert exc.value.code == "CONTENT_REPORTING_CUTOVER_REFERENCE_YEAR_MISMATCH"


def test_s2_e_estritamente_read_only_e_nao_importa_consumidores():
    service = Path("services/content_reporting_cutover_resolver.py").read_text(encoding="utf-8")
    forbidden_mutations = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
    )
    for token in forbidden_mutations:
        assert token not in service

    for consumer in (
        "pmpi_compute",
        "intervention_detector",
        "diary_dashboard",
        "analytics",
        "monthly_report_service",
    ):
        assert consumer not in service
