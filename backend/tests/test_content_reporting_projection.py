"""Contratos da fundação shadow do read model institucional de Conteúdo."""
from pathlib import Path

import pytest

from services.content_reporting_projection import (
    ContentReportingCutoverScope,
    ContentReportingProjectionError,
    list_reporting_content_shadow,
    merge_reporting_content,
    normalize_cutover_scopes,
)


TENANT = "tenant-a"
CLASS = "class-a"
COMP = "comp-a"
TEACHER = "teacher-a"


def _canonical(date, *, tenant=TENANT, item_id="ce-1", component=COMP, teacher=TEACHER):
    return {
        "id": item_id,
        "mantenedora_id": tenant,
        "academic_year": 2026,
        "class_id": CLASS,
        "component_id": component,
        "teacher_id": teacher,
        "date": date,
        "number_of_classes": 1,
        "content": "Canônico",
        "deleted": False,
    }


def _legacy(date, *, tenant=None, item_id="lo-1", component=COMP, teacher=TEACHER):
    row = {
        "id": item_id,
        "academic_year": 2026,
        "class_id": CLASS,
        "course_id": component,
        "recorded_by": teacher,
        "date": date,
        "number_of_classes": 1,
        "content": "Legado",
    }
    if tenant is not None:
        row["mantenedora_id"] = tenant
    return row


def _scope(component=COMP, valid_from="2026-08-18"):
    return ContentReportingCutoverScope(
        class_id=CLASS,
        component_id=component,
        valid_from=valid_from,
    )


def test_legacy_antes_do_cutover_permanece_e_pos_cutover_e_excluido():
    result = merge_reporting_content(
        [_canonical("2026-08-20")],
        [
            _legacy("2026-06-01", item_id="lo-old"),
            _legacy("2026-08-19", item_id="lo-after"),
        ],
        tenant_id=TENANT,
        cutover_scopes=[_scope()],
    )

    assert [item["id"] for item in result["items"]] == ["ce-1", "lo-old"]
    assert result["shadow"]["canonical_count"] == 1
    assert result["shadow"]["legacy_kept_count"] == 1
    assert result["shadow"]["legacy_excluded_post_cutover"] == 1


def test_canonic_at_cutover_wins_semantic_duplicate():
    result = merge_reporting_content(
        [_canonical("2026-08-18", item_id="ce-cut")],
        [_legacy("2026-08-18", item_id="lo-cut")],
        tenant_id=TENANT,
        cutover_scopes=[_scope()],
    )

    assert [item["id"] for item in result["items"]] == ["ce-cut"]
    assert result["shadow"]["legacy_duplicate_suppressed"] == 1


def test_sem_cutover_explicito_legado_continua_elegivel_sem_heuristica():
    result = merge_reporting_content(
        [_canonical("2026-08-20", item_id="ce-new")],
        [_legacy("2026-08-19", item_id="lo-still-visible", teacher="teacher-b")],
        tenant_id=TENANT,
        cutover_scopes=[],
    )

    assert {item["id"] for item in result["items"]} == {"ce-new", "lo-still-visible"}
    assert result["shadow"]["legacy_excluded_post_cutover"] == 0


def test_classwide_cutover_aplica_e_especifico_tem_precedencia():
    scopes = [
        ContentReportingCutoverScope(class_id=CLASS, valid_from="2026-08-01"),
        ContentReportingCutoverScope(class_id=CLASS, component_id=COMP, valid_from="2026-08-18"),
    ]
    result = merge_reporting_content(
        [],
        [
            _legacy("2026-08-10", item_id="lo-specific", component=COMP),
            _legacy("2026-08-10", item_id="lo-classwide", component="comp-b"),
        ],
        tenant_id=TENANT,
        cutover_scopes=scopes,
    )

    assert [item["id"] for item in result["items"]] == ["lo-specific"]
    assert result["shadow"]["legacy_excluded_post_cutover"] == 1


def test_cutover_ambiguo_falha_fechado():
    with pytest.raises(ContentReportingProjectionError) as exc:
        normalize_cutover_scopes([
            _scope(valid_from="2026-08-18"),
            _scope(valid_from="2026-08-19"),
        ])
    assert exc.value.code == "CONTENT_REPORTING_CUTOVER_AMBIGUOUS"


def test_tenant_explicito_divergente_nunca_cruza_read_model():
    result = merge_reporting_content(
        [_canonical("2026-08-20", tenant="tenant-b", item_id="ce-wrong")],
        [_legacy("2026-06-01", tenant="tenant-b", item_id="lo-wrong")],
        tenant_id=TENANT,
        cutover_scopes=[_scope()],
    )
    assert result["items"] == []
    assert result["shadow"]["tenant_mismatch_rejected"] == 2


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
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        value = _value(doc, key)
        if isinstance(expected, dict):
            for op, target in expected.items():
                if op == "$in" and value not in target:
                    return False
                if op == "$ne" and value == target:
                    return False
                if op == "$gte" and (value is None or value < target):
                    return False
                if op == "$lte" and (value is None or value > target):
                    return False
            continue
        if value != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def find(self, query, projection=None):
        docs = [doc for doc in self.docs if _matches(doc, query)]
        if projection:
            include = [key for key, enabled in projection.items() if enabled and key != "_id"]
            if include:
                docs = [{key: _value(doc, key) for key in include} for doc in docs]
        return FakeCursor(docs)


class FakeDb:
    def __init__(self):
        self.classes = FakeCollection([
            {"id": CLASS, "mantenedora_id": TENANT, "academic_year": 2026},
            {"id": "class-other", "mantenedora_id": "tenant-b", "academic_year": 2026},
        ])
        self.content_entries = FakeCollection([_canonical("2026-08-20")])
        self.learning_objects = FakeCollection([_legacy("2026-06-01", item_id="lo-old")])


@pytest.mark.asyncio
async def test_loader_ancora_turma_no_tenant_e_ano():
    result = await list_reporting_content_shadow(
        FakeDb(),
        mantenedora_id=TENANT,
        academic_year=2026,
        class_ids=[CLASS],
        cutover_scopes=[_scope()],
    )
    assert result["scope"]["class_ids"] == [CLASS]
    assert {item["id"] for item in result["items"]} == {"ce-1", "lo-old"}


@pytest.mark.asyncio
async def test_loader_rejeita_turma_de_outro_tenant_em_vez_de_filtrar_silenciosamente():
    with pytest.raises(ContentReportingProjectionError) as exc:
        await list_reporting_content_shadow(
            FakeDb(),
            mantenedora_id=TENANT,
            academic_year=2026,
            class_ids=["class-other"],
        )
    assert exc.value.code == "CONTENT_REPORTING_CLASS_OUT_OF_SCOPE"


def test_fundacao_e_estritamente_read_only_e_nao_faz_cutover_de_consumidores():
    service = Path("services/content_reporting_projection.py").read_text(encoding="utf-8")
    forbidden_mutations = (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    )
    for token in forbidden_mutations:
        assert token not in service

    # Esta PR é somente fundação/shadow: nenhum consumidor operacional deve ser
    # importado ou monkey-patched por este serviço.
    for consumer in (
        "pmpi_compute", "intervention_detector", "diary_dashboard",
        "analytics", "monthly_report_service",
    ):
        assert consumer not in service
