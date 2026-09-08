"""Gate S3 — executor reproduzível e estritamente read-only de paridade."""
from pathlib import Path

import pytest

from services.content_reporting_parity import (
    ContentReportingParityError,
    execute_content_reporting_parity,
)


TENANT = "tenant-a"
CLASS = "class-a"
COMP = "comp-a"
SHA = "f" * 40
GENERATED = "2026-09-08T01:00:00-03:00"


def _class(*, tenant=TENANT, class_id=CLASS, year=2026):
    return {
        "id": class_id,
        "school_id": "school-a",
        "mantenedora_id": tenant,
        "academic_year": year,
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º ANO",
        "atendimento_programa": None,
    }


def _assignment(*, valid_from="2026-08-18", component_id=COMP):
    return {
        "id": "assign-a",
        "teacher_id": "teacher-a",
        "class_id": CLASS,
        "component_id": component_id,
        "school_id": "school-a",
        "mantenedora_id": TENANT,
        "valid_from": valid_from,
        "valid_until": None,
        "deleted": False,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
    }


def _legacy(
    day="2026-06-10",
    *,
    item_id="lo-1",
    teacher="teacher-a",
    created_at="2026-06-11T10:00:00Z",
    number_of_classes=1,
    tenant=None,
):
    row = {
        "id": item_id,
        "academic_year": 2026,
        "class_id": CLASS,
        "course_id": COMP,
        "recorded_by": teacher,
        "date": day,
        "created_at": created_at,
        "number_of_classes": number_of_classes,
        "content": "Legado",
    }
    if tenant is not None:
        row["mantenedora_id"] = tenant
    return row


def _canonical(
    day="2026-09-01",
    *,
    item_id="ce-1",
    teacher="teacher-a",
    created_at="2026-09-02T10:00:00Z",
    number_of_classes=1,
):
    return {
        "id": item_id,
        "mantenedora_id": TENANT,
        "academic_year": 2026,
        "class_id": CLASS,
        "component_id": COMP,
        "teacher_id": teacher,
        "date": day,
        "created_at": created_at,
        "number_of_classes": number_of_classes,
        "content": "Canônico",
        "deleted": False,
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
    def __init__(self, *, classes=None, assignments=None, canonical=None, legacy=None):
        self.classes = FakeCollection(classes if classes is not None else [_class()])
        self.teacher_class_assignments = FakeCollection(assignments or [])
        self.content_entries = FakeCollection(canonical or [])
        self.learning_objects = FakeCollection(legacy or [])


async def _execute(db, consumer="PMPI_LESSONS", **kwargs):
    return await execute_content_reporting_parity(
        db,
        consumer=consumer,
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
        generated_at=GENERATED,
        code_sha=SHA,
        class_ids=[CLASS],
        **kwargs,
    )


def _metric(report, name):
    return next(row for row in report["metrics"] if row["metric"] == name)


@pytest.mark.asyncio
async def test_s3_match_quando_legado_e_projecao_sao_equivalentes():
    report = await _execute(FakeDb(legacy=[_legacy()]))

    metric = _metric(report, "record_count")
    assert metric["legacy"] == 1
    assert metric["projected"] == 1
    assert metric["delta"] == 0
    assert metric["classification"] == "MATCH"
    assert report["errors"] == []


@pytest.mark.asyncio
async def test_s3_classifica_ganho_canônico_esperado():
    report = await _execute(
        FakeDb(legacy=[_legacy()], canonical=[_canonical()])
    )

    metric = _metric(report, "record_count")
    assert metric["legacy"] == 1
    assert metric["projected"] == 2
    assert metric["delta"] == 1
    assert metric["classification"] == "EXPECTED_CANONICAL_GAIN"


@pytest.mark.asyncio
async def test_s3_classifica_exclusao_de_legado_pos_cutover():
    report = await _execute(
        FakeDb(
            assignments=[_assignment()],
            legacy=[_legacy("2026-08-20")],
        )
    )

    metric = _metric(report, "record_count")
    assert metric["legacy"] == 1
    assert metric["projected"] == 0
    assert metric["classification"] == "EXPECTED_POST_CUTOVER_LEGACY_EXCLUSION"
    assert report["shadow"]["legacy_excluded_post_cutover"] == 1


@pytest.mark.asyncio
async def test_s3_classifica_sobreposicao_historica_suprimida():
    report = await _execute(
        FakeDb(
            assignments=[_assignment()],
            canonical=[_canonical("2026-08-18", item_id="ce-overlap")],
            legacy=[_legacy("2026-08-18", item_id="lo-overlap")],
        )
    )

    metric = _metric(report, "record_count")
    assert metric["legacy"] == 1
    assert metric["projected"] == 1
    assert metric["classification"] == "HISTORICAL_OVERLAP_SUPPRESSED"
    assert report["shadow"]["legacy_duplicate_suppressed"] == 1


@pytest.mark.asyncio
async def test_s3_atraso_sem_proveniencia_comparavel_nao_fabrica_match():
    report = await _execute(
        FakeDb(legacy=[_legacy(created_at=None)]),
        consumer="PMPI_DELAY",
    )

    metric = _metric(report, "average_delay_days")
    assert metric["legacy"] is None
    assert metric["projected"] is None
    assert metric["classification"] == "PROVENANCE_INCOMPARABLE"


@pytest.mark.asyncio
async def test_s3_erro_de_escopo_vira_relatorio_scope_error_sem_excecao_operacional():
    report = await execute_content_reporting_parity(
        FakeDb(),
        consumer="PMPI_LESSONS",
        mantenedora_id=TENANT,
        academic_year=2026,
        reference_date="2026-09-08",
        generated_at=GENERATED,
        code_sha=SHA,
        class_ids=["class-fora"],
    )

    assert report["metrics"] == []
    assert report["classifications"] == ["SCOPE_ERROR"]
    assert report["errors"][0]["classification"] == "SCOPE_ERROR"


@pytest.mark.asyncio
async def test_s3_relatorio_e_hash_sao_reproduziveis_com_mesmas_entradas():
    db_a = FakeDb(legacy=[_legacy()], canonical=[_canonical()])
    db_b = FakeDb(legacy=[_legacy()], canonical=[_canonical()])

    first = await _execute(db_a, consumer="ANALYTICS_CONTENT")
    second = await _execute(db_b, consumer="ANALYTICS_CONTENT")

    assert first == second
    assert first["report_sha256"] == second["report_sha256"]
    assert len(first["cutover"]["sha256"]) == 64


@pytest.mark.asyncio
async def test_s3_consumidor_define_conjunto_de_metricas_sem_mudar_fontes():
    report = await _execute(
        FakeDb(legacy=[_legacy(number_of_classes=2)]),
        consumer="PMPI_WORKLOAD",
    )

    assert [row["metric"] for row in report["metrics"]] == ["number_of_classes_sum"]
    assert _metric(report, "number_of_classes_sum")["legacy"] == 2
    assert _metric(report, "number_of_classes_sum")["projected"] == 2


@pytest.mark.asyncio
async def test_s3_distribuicao_mensal_exposta_para_dashboard():
    report = await _execute(
        FakeDb(
            legacy=[
                _legacy("2026-06-10", item_id="lo-jun"),
                _legacy("2026-07-10", item_id="lo-jul"),
            ]
        ),
        consumer="DIARY_DASHBOARD_CONTENT",
    )

    monthly = _metric(report, "monthly_record_count")
    assert monthly["legacy"] == {"2026-06": 1, "2026-07": 1}
    assert monthly["projected"] == monthly["legacy"]
    assert monthly["classification"] == "MATCH"


def test_s3_rejeita_consumidor_desconhecido():
    with pytest.raises(ContentReportingParityError) as exc:
        # validação ocorre antes de qualquer acesso ao banco
        import asyncio

        asyncio.run(
            execute_content_reporting_parity(
                FakeDb(),
                consumer="QUALQUER_COISA",
                mantenedora_id=TENANT,
                academic_year=2026,
                reference_date="2026-09-08",
                generated_at=GENERATED,
                code_sha=SHA,
            )
        )
    assert exc.value.code == "CONTENT_REPORTING_PARITY_CONSUMER_INVALID"


def test_s3_e_estritamente_read_only_e_nao_altera_http_ou_consumidores():
    service = Path("services/content_reporting_parity.py").read_text(encoding="utf-8")
    projection = Path("services/content_reporting_projection.py").read_text(encoding="utf-8")
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
        assert token not in projection

    assert "APIRouter" not in service
    assert "@router" not in service
    for module in (
        "routers.pmpi",
        "services.pmpi_compute",
        "routers.analytics",
        "diary_dashboard",
        "monthly_report_service",
        "intervention_detector",
    ):
        assert module not in service
