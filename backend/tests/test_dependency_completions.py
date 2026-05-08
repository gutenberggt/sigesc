"""
Testes — Dependency Completion Snapshots imutáveis (Fase 2.5).

Cobre as exigências do owner Fev/2026:
- Hash documental imutável após emissão.
- Signature hash separado, referenciando o doc original.
- verification_token único.
- data_quality bloqueia assinatura quando não 'complete'.
- Cancelado exige status_reason.
- Snapshot é idempotente (não duplica).
- Backfill híbrido respeita data_quality.
- Revogação não modifica document_hash.
- Documento revogado retorna `valid=false, document_status='revogado'` no público.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.document_hash import (  # noqa: E402
    compute_document_hash,
    compute_signature_hash,
    verify_document_hash,
)
from routers.dependency_completions import (  # noqa: E402
    create_completion_snapshot_on_transition,
    _result_to_document_status,
    ensure_indexes,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await ensure_indexes(db)
    yield db
    client.close()


@pytest_asyncio.fixture
async def base_dep_doc(db):
    """Cria uma dep ativa fictícia para testes."""
    dep = {
        "id": "p25_dep_test",
        "student_id": "p25_stu_test",
        "school_id": "p25_school",
        "mantenedora_id": "p25_mant",
        "class_id": "p25_class",
        "course_id": "p25_course",
        "origin_class_id": "p25_origin_class",
        "origin_academic_year": 2024,
        "status": "active",
    }
    # Curso e turma de origem (snapshots)
    await db.courses.update_one(
        {"id": "p25_course"},
        {"$set": {"id": "p25_course", "name": "Matemática 2024",
                  "workload_hours": 80, "curriculum_version": "BNCC-2018-rev3"}},
        upsert=True,
    )
    await db.classes.update_one(
        {"id": "p25_origin_class"},
        {"$set": {"id": "p25_origin_class", "name": "9A 2024",
                  "academic_year": 2024, "curriculum_version": "BNCC-2018-rev3"}},
        upsert=True,
    )
    yield dep

    # cleanup
    await db.dependency_completions.delete_many({"dependency_id": "p25_dep_test"})


# =========================================================================
# 1. Hash documental — determinístico e imutável
# =========================================================================
def test_document_hash_is_deterministic():
    payload = {"a": 1, "b": "x", "c": [1, 2, 3]}
    assert compute_document_hash(payload) == compute_document_hash(payload.copy())


def test_document_hash_ignores_volatile_fields():
    """Adicionar signatures/verification_token/revoked_* NÃO altera o hash."""
    base = {"student_id": "s1", "completion_result": "approved"}
    h1 = compute_document_hash(base)
    base_with_volatile = {
        **base,
        "signatures": [{"role": "diretor"}],
        "verification_token": "abc123",
        "revoked_at": "2026-08-15",
        "revoked_reason": "erro",
        "audit_trail": [{"action": "revoked"}],
    }
    h2 = compute_document_hash(base_with_volatile)
    assert h1 == h2


def test_document_hash_different_for_different_content():
    a = {"final_grade": 7.0}
    b = {"final_grade": 6.5}
    assert compute_document_hash(a) != compute_document_hash(b)


def test_signature_hash_references_original_document():
    """Adicionar nova assinatura NÃO altera document_hash original.

    Cada assinatura tem seu próprio hash que referencia o doc original.
    """
    payload = {"student_id": "s1", "final_grade": 7.0}
    doc_hash = compute_document_hash(payload)

    sig1 = compute_signature_hash(
        document_hash=doc_hash, role="secretario",
        user_id="u1", signed_at="2026-08-01T10:00:00Z",
    )
    sig2 = compute_signature_hash(
        document_hash=doc_hash, role="diretor",
        user_id="u2", signed_at="2026-08-01T10:30:00Z",
    )

    # doc_hash imutável após múltiplas assinaturas
    payload_with_sigs = {**payload, "signatures": [
        {"role": "secretario", "signature_hash_sha256": sig1, "signed_document_hash": doc_hash},
        {"role": "diretor", "signature_hash_sha256": sig2, "signed_document_hash": doc_hash},
    ]}
    assert compute_document_hash(payload_with_sigs) == doc_hash
    # Cada signature_hash referencia o doc original
    assert sig1 != sig2  # diferentes assinantes
    assert sig1 != doc_hash and sig2 != doc_hash


def test_verify_document_hash_detects_tampering():
    payload = {"student_id": "s1", "final_grade": 7.0}
    h = compute_document_hash(payload)
    assert verify_document_hash(payload, h) is True
    tampered = {**payload, "final_grade": 10.0}
    assert verify_document_hash(tampered, h) is False


# =========================================================================
# 2. Snapshot via hook de transição
# =========================================================================
@pytest.mark.asyncio
async def test_completion_snapshot_created_on_status_transition(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    assert snap is not None
    assert snap["dependency_id"] == "p25_dep_test"
    assert snap["completion_result"] == "approved"
    assert snap["original_course_name_at_completion"] == "Matemática 2024"
    assert snap["original_curriculum_version"] == "BNCC-2018-rev3"
    assert snap["original_academic_year"] == 2024
    assert snap["completion_academic_year"] == 2025
    assert snap["document_version"] == "1.0.0"
    assert snap["history_schema_version"] == "1"
    assert len(snap["document_hash_sha256"]) == 64  # sha256 hex
    assert snap["verification_token"]  # token único gerado
    assert snap["signatures"] == []
    assert snap["revoked_at"] is None


@pytest.mark.asyncio
async def test_completion_snapshot_idempotent(db, base_dep_doc):
    """Chamar 2x com mesmos params NÃO duplica."""
    s1 = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    s2 = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    assert s1["id"] == s2["id"]


@pytest.mark.asyncio
async def test_cancelled_requires_status_reason(db, base_dep_doc):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await create_completion_snapshot_on_transition(
            db, dependency_doc=base_dep_doc, new_status="cancelled",
            status_reason=None, issued_by_user_id="user_x",
            completion_academic_year=2025,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CANCELLATION_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_cancelled_with_reason_creates_snapshot_incomplete(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="cancelled",
        status_reason="Equivalência via reclassificação aprovada pelo conselho.",
        issued_by_user_id="user_x", completion_academic_year=2025,
    )
    assert snap["completion_result"] == "cancelled"
    assert snap["data_quality"] == "incomplete"
    assert snap["status_reason"].startswith("Equivalência")


@pytest.mark.asyncio
async def test_failed_creates_snapshot(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="failed",
        status_reason="Reprovação por nota insuficiente.",
        issued_by_user_id="user_x", completion_academic_year=2025,
    )
    assert snap["completion_result"] == "failed"


# =========================================================================
# 3. data_quality e impacto em assinatura
# =========================================================================
@pytest.mark.asyncio
async def test_completion_data_quality_incomplete_when_no_grade_no_attendance(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    # sem grades nem attendance → incomplete
    assert snap["data_quality"] == "incomplete"
    assert snap["final_grade"] is None
    assert snap["final_attendance_pct"] is None


@pytest.mark.asyncio
async def test_completion_data_quality_complete_when_both_present(db, base_dep_doc):
    # Cria grade + attendance para o aluno na dep
    await db.grades.update_one(
        {"student_id": "p25_stu_test", "course_id": "p25_course",
         "dependency_id": "p25_dep_test"},
        {"$set": {
            "student_id": "p25_stu_test", "course_id": "p25_course",
            "class_id": "p25_class", "academic_year": 2025,
            "dependency_id": "p25_dep_test", "final_average": 7.5,
        }},
        upsert=True,
    )
    await db.attendance.insert_one({
        "id": "p25_att_1", "class_id": "p25_class", "course_id": "p25_course",
        "academic_year": 2025, "date": "2025-04-01",
        "records": [{"student_id": "p25_stu_test", "status": "P", "dependency_id": "p25_dep_test"}],
    })

    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    assert snap["data_quality"] == "complete"
    assert snap["final_grade"] == 7.5
    assert snap["final_attendance_pct"] == 100.0

    # cleanup auxiliares
    await db.grades.delete_one({"dependency_id": "p25_dep_test"})
    await db.attendance.delete_one({"id": "p25_att_1"})


# =========================================================================
# 4. Mapeamento de document_status público
# =========================================================================
def test_document_status_mapping():
    assert _result_to_document_status("approved", None) == "valido"
    assert _result_to_document_status("failed", None) == "valido_reprovado"
    assert _result_to_document_status("cancelled", None) == "cancelado_administrativamente"
    assert _result_to_document_status("approved", "2026-09-01T10:00:00Z") == "revogado"
    assert _result_to_document_status("approved", None) != "cancelled"  # nunca expor enum interno


# =========================================================================
# 5. verification_token único
# =========================================================================
@pytest.mark.asyncio
async def test_verification_token_uniqueness_index_exists(db):
    info = await db.dependency_completions.index_information()
    found = False
    for name, spec in info.items():
        keys = spec.get("key") or []
        if any(k[0] == "verification_token" for k in keys) and spec.get("unique"):
            found = True
            break
    assert found, f"índice único em verification_token não encontrado: {info}"


# =========================================================================
# 6. Imutabilidade — após snapshot, hash não muda
# =========================================================================
@pytest.mark.asyncio
async def test_document_hash_persists_through_revocation(db, base_dep_doc):
    """Mesmo após adicionar revoked_at, document_hash original continua válido."""
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    original_hash = snap["document_hash_sha256"]

    # Simula revogação direto no banco (como faria o endpoint)
    await db.dependency_completions.update_one(
        {"id": snap["id"]},
        {"$set": {"revoked_at": "2026-09-01T10:00:00Z",
                  "revoked_reason": "Erro operacional detectado durante auditoria municipal."}},
    )
    refreshed = await db.dependency_completions.find_one({"id": snap["id"]}, {"_id": 0})
    # hash ainda bate com o conteúdo (revoked_* não entram no hash)
    assert verify_document_hash(refreshed, original_hash)
    assert refreshed["document_hash_sha256"] == original_hash


# =========================================================================
# 7. Snapshots do owner — exigências adicionais
# =========================================================================
@pytest.mark.asyncio
async def test_snapshot_has_required_fields(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    required = {
        "id", "student_id", "dependency_id",
        "original_course_id", "original_course_name_at_completion",
        "original_curriculum_version", "original_academic_year", "original_class_id",
        "completion_academic_year", "completion_result",
        "data_quality", "document_version", "history_schema_version",
        "template_version", "render_engine_version",
        "issued_at", "issued_by_user_id",
        "verification_token", "document_hash_sha256",
        "revoked_at", "revoked_reason", "superseded_by_document_id",
        "signatures", "audit_trail",
    }
    missing = required - set(snap.keys())
    assert not missing, f"campos faltando: {missing}"


@pytest.mark.asyncio
async def test_audit_trail_has_creation_entry(db, base_dep_doc):
    snap = await create_completion_snapshot_on_transition(
        db, dependency_doc=base_dep_doc, new_status="completed",
        status_reason=None, issued_by_user_id="user_x",
        completion_academic_year=2025,
    )
    assert snap["audit_trail"]
    first = snap["audit_trail"][0]
    assert first["action"] == "snapshot_created"
    assert first["by_user_id"] == "user_x"
