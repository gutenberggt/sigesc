import asyncio

import pytest

from mig.cmde.external_ids import COLLECTION as EXTERNAL_IDS_COLLECTION
from mig.cmde.preview import (
    CmdeOperationalPreviewService,
    CmdeStudentPreviewRequestDTO,
)
from mig.core.exceptions import MigConfigError, MigForbiddenError


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self._skip = 0
        self._limit = None

    def sort(self, key, direction):
        reverse = direction < 0
        self.docs.sort(key=lambda item: str(item.get(key, "")), reverse=reverse)
        return self

    def skip(self, value):
        self._skip = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length):
        docs = self.docs[self._skip :]
        if self._limit is not None:
            docs = docs[: self._limit]
        return [dict(doc) for doc in docs[:length]]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.write_attempts = 0

    @staticmethod
    def _matches_value(actual, expected):
        if isinstance(expected, dict) and "$in" in expected:
            return actual in expected["$in"]
        return actual == expected

    @classmethod
    def _matches(cls, doc, query):
        return all(cls._matches_value(doc.get(key), value) for key, value in query.items())

    async def count_documents(self, query):
        return sum(self._matches(doc, query) for doc in self.docs)

    def find(self, query, projection=None):
        return FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    async def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, document):
        self.write_attempts += 1
        raise AssertionError("preview B.6 tentou escrever no banco")

    async def update_one(self, *args, **kwargs):
        self.write_attempts += 1
        raise AssertionError("preview B.6 tentou atualizar o banco")

    async def create_index(self, *args, **kwargs):
        self.write_attempts += 1
        raise AssertionError("preview B.6 tentou criar índice")


class FakeDB:
    def __init__(self, collections=None):
        self.collections = {
            name: FakeCollection(docs) for name, docs in (collections or {}).items()
        }

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def total_write_attempts(self):
        return sum(collection.write_attempts for collection in self.collections.values())


def run(coro):
    return asyncio.run(coro)


def base_student(student_id="student-1", *, cpf="12345678901"):
    return {
        "id": student_id,
        "mantenedora_id": "tenant-a",
        "full_name": "Maria da Silva",
        "birth_date": "2012-05-10",
        "cpf": cpf,
        "address": {
            "zip_code": "68543000",
            "state": "PA",
            "state_ibge_code": "15",
            "city": "Floresta do Araguaia",
            "city_ibge_code": "1503044",
            "neighborhood": "Centro",
            "street": "Rua Exemplo",
            "number": "100",
        },
    }


def base_enrollment(
    enrollment_id="enrollment-1",
    *,
    student_id="student-1",
    legacy_sgp_id=None,
):
    return {
        "id": enrollment_id,
        "mantenedora_id": "tenant-a",
        "student_id": student_id,
        "school_id": "school-1",
        "class_id": None,
        "academic_year": 2026,
        "enrollment_number": f"MAT-{enrollment_id}",
        "enrollment_date": "2026-02-02",
        "status": "active",
        "sgp_enrollment_id": legacy_sgp_id,
    }


def base_school():
    return {
        "id": "school-1",
        "mantenedora_id": "tenant-a",
        "name": "Escola Municipal Exemplo",
        "inep_code": "15012345",
    }


def external_id_doc(entity_type, internal_id, external_id):
    return {
        "id": f"link-{entity_type}-{internal_id}",
        "provider": "cmde",
        "namespace": "sgp",
        "tenant_id": "tenant-a",
        "entity_type": entity_type,
        "internal_id": internal_id,
        "external_id": str(external_id),
        "source": "cmde_lookup",
        "correlation_id": None,
        "lote_id": None,
        "created_at": "2026-08-14T10:00:00+00:00",
        "updated_at": "2026-08-14T10:00:00+00:00",
    }


def build_db(*, students=None, enrollments=None, external_ids=None):
    return FakeDB(
        {
            "students": students or [base_student()],
            "enrollments": enrollments or [base_enrollment()],
            "schools": [base_school()],
            "classes": [],
            EXTERNAL_IDS_COLLECTION: external_ids or [],
        }
    )


def test_preview_ready_page_builds_exact_candidate_and_batch_payload_without_writes():
    db = build_db(
        enrollments=[base_enrollment(legacy_sgp_id="999999")],
        external_ids=[
            external_id_doc("student", "student-1", "123456"),
            external_id_doc("enrollment", "enrollment-1", "987654"),
        ],
    )
    service = CmdeOperationalPreviewService(db)

    report = run(
        service.build(
            CmdeStudentPreviewRequestDTO(),
            context={"tenant": "tenant-a", "actor": "admin@example.com"},
        )
    )

    assert report.mode == "dry_run"
    assert report.provider_called is False
    assert report.write_attempted is False
    assert report.queue_touched is False
    assert report.total_matching == 1
    assert report.page_records == 1
    assert report.ready_records == 1
    assert report.blocked_records == 0
    assert report.page_ready is True
    assert report.page_payload is not None
    assert len(report.page_payload["estudantes"]) == 1

    record = report.records[0]
    assert record.ready is True
    assert record.external_ids.student_external_id == "123456"
    # B.5 é SSoT: o legado 999999 não pode vencer o vínculo MIG 987654.
    assert record.external_ids.enrollment_external_id == "987654"
    assert record.candidate_payload_record == report.page_payload["estudantes"][0]

    payload = record.candidate_payload_record
    assert payload["co_entidade"] == "15012345"
    assert payload["co_matricula_rede"] == "MAT-enrollment-1"
    assert payload["estudante_nome"] == "Maria da Silva"
    assert payload["estudante_cpf"] == "12345678901"
    assert payload["estudante_co_uf_res"] == 15
    assert payload["estudante_co_municipio_res"] == 1503044
    assert "student_id" not in payload
    assert "enrollment_id" not in payload
    assert "id_sgp_estudante" not in payload
    assert "id_sgp_matricula" not in payload
    assert db.total_write_attempts() == 0


def test_mixed_page_never_builds_partial_batch_payload():
    students = [
        base_student("student-1"),
        base_student("student-2", cpf=None),
    ]
    enrollments = [
        base_enrollment("enrollment-1", student_id="student-1"),
        base_enrollment("enrollment-2", student_id="student-2"),
    ]
    db = build_db(students=students, enrollments=enrollments)
    service = CmdeOperationalPreviewService(db)

    report = run(
        service.build(
            CmdeStudentPreviewRequestDTO(),
            context={"tenant": "tenant-a"},
        )
    )

    assert report.page_records == 2
    assert report.ready_records == 1
    assert report.blocked_records == 1
    assert report.page_ready is False
    assert report.page_payload is None
    assert report.blocker_counts["missing_required"] == 1

    ready_record = next(record for record in report.records if record.ready)
    blocked_record = next(record for record in report.records if not record.ready)
    assert ready_record.candidate_payload_record is not None
    assert blocked_record.candidate_payload_record is None
    assert any(issue.field == "student.cpf" for issue in blocked_record.issues)
    assert db.total_write_attempts() == 0


def test_missing_student_is_reported_as_projection_failure_instead_of_being_hidden():
    db = build_db(students=[], enrollments=[base_enrollment()])
    service = CmdeOperationalPreviewService(db)

    report = run(
        service.build(
            CmdeStudentPreviewRequestDTO(),
            context={"tenant": "tenant-a"},
        )
    )

    assert report.page_records == 1
    assert report.blocked_records == 1
    assert report.page_payload is None
    assert report.records[0].readiness is None
    assert report.records[0].issues[0].code == "canonical_projection_failed"


def test_unsupported_known_lot_type_is_fail_closed_and_has_no_payload():
    db = build_db()
    service = CmdeOperationalPreviewService(db)

    report = run(
        service.build(
            CmdeStudentPreviewRequestDTO(lot_type="student_edit"),
            context={"tenant": "tenant-a"},
        )
    )

    assert report.endpoint == "/api/v2/estudantes/edicao/lote"
    assert report.ready_records == 0
    assert report.blocked_records == 1
    assert report.page_payload is None
    assert report.records[0].issues[0].code == "unsupported_lot_type"


def test_preview_requires_explicit_tenant_for_cross_tenant_context():
    db = build_db()
    service = CmdeOperationalPreviewService(db)

    with pytest.raises(MigConfigError, match="tenant_id é obrigatório"):
        run(service.build(CmdeStudentPreviewRequestDTO(), context={"tenant": None}))


def test_preview_rejects_tenant_override_that_diverges_from_authenticated_scope():
    db = build_db()
    service = CmdeOperationalPreviewService(db)

    request = CmdeStudentPreviewRequestDTO(tenant_id="tenant-b")
    with pytest.raises(MigForbiddenError, match="diverge"):
        run(service.build(request, context={"tenant": "tenant-a"}))


def test_dry_run_false_is_rejected_by_request_contract():
    with pytest.raises(Exception):
        CmdeStudentPreviewRequestDTO(dry_run=False)


def test_filters_and_pagination_apply_only_to_active_enrollments_of_tenant():
    enrollments = [
        base_enrollment("enrollment-1", student_id="student-1"),
        {**base_enrollment("enrollment-2", student_id="student-2"), "status": "completed"},
        {**base_enrollment("enrollment-3", student_id="student-3"), "mantenedora_id": "tenant-b"},
    ]
    students = [
        base_student("student-1"),
        base_student("student-2"),
        {**base_student("student-3"), "mantenedora_id": "tenant-b"},
    ]
    db = build_db(students=students, enrollments=enrollments)
    service = CmdeOperationalPreviewService(db)

    report = run(
        service.build(
            CmdeStudentPreviewRequestDTO(student_id="student-1", page_size=1),
            context={"tenant": "tenant-a"},
        )
    )

    assert report.total_matching == 1
    assert report.total_pages == 1
    assert report.page_records == 1
    assert report.records[0].student_id == "student-1"
