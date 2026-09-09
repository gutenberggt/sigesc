"""F2.1C — domínio documental, pós-validação e rollback da retificação.

Este módulo fecha o terceiro eixo anterior à saga executável. Ele concentra:
- inventário documental unificado e tenant-scoped;
- classificação fail-closed de artefatos resolvíveis/bloqueantes;
- revogação governada e idempotente de documentos rastreados;
- reconhecimento explícito da lacuna histórica de PDFs síncronos sem ledger;
- elegibilidade de rollback;
- detector de resíduos acadêmicos na turma de origem.

Nenhum router público importa este módulo nesta fase.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from services.verifiable_docs_service import revoke_document

DOCUMENT_LEDGER_COLLECTION = "document_rectifications"
DOCUMENT_LEDGER_INDEX = "uq_document_rectification_protocol_artifact"
DOCUMENT_ACKNOWLEDGEMENT = (
    "ESTOU CIENTE DE QUE PODEM EXISTIR DOCUMENTOS ANTERIORES NÃO RASTREADOS E QUE DEVEM SER SUBSTITUÍDOS"
)
UNTRACKED_PATHS = (
    "documents.boletim.sync",
    "documents.ficha_individual.sync",
    "documents.declaracoes.sync",
)


class DocumentRectificationError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 409, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _tenant(query: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    out = dict(query)
    out["mantenedora_id"] = tenant_id
    return out


def _year_values(year: int) -> list[Any]:
    return [year, str(year)]


async def _find(db, collection: str, query: dict[str, Any], *, limit: int = 5000) -> list[dict[str, Any]]:
    docs = await db[collection].find(query, {"_id": 0}).to_list(limit)
    return sorted(docs, key=_canonical)


def _artifact_key(kind: str, doc: Mapping[str, Any]) -> str:
    for field in ("code", "id", "token_hash", "verification_token", "snapshot_id", "job_id", "file_id"):
        if doc.get(field) not in (None, ""):
            return f"{kind}:{doc.get(field)}"
    return f"{kind}:sha256:{_digest(doc)}"


def _active_verifiable(doc: Mapping[str, Any]) -> bool:
    return not bool(doc.get("revoked")) and not bool(doc.get("revoked_at")) and not bool(doc.get("superseded_at"))


def _active_verification(doc: Mapping[str, Any]) -> bool:
    return not bool(doc.get("revoked_at"))


async def ensure_document_rectification_indexes(db) -> None:
    await db[DOCUMENT_LEDGER_COLLECTION].create_index(
        [("mantenedora_id", 1), ("protocol", 1), ("artifact_kind", 1), ("artifact_key", 1)],
        unique=True,
        name=DOCUMENT_LEDGER_INDEX,
    )


async def build_rectification_document_inventory(
    db,
    *,
    student_id: str,
    source_class_id: str,
    academic_year: int,
    tenant_id: str,
) -> dict[str, Any]:
    """Agrega o vetor documental exigido pela F0 sem qualquer escrita."""
    years = _year_values(academic_year)
    school_logs = await _find(db, "school_documents_log", _tenant({"student_id": student_id}, tenant_id), limit=2000)
    vdocs = await _find(
        db,
        "verifiable_documents",
        _tenant(
            {"$or": [
                {"student_id": student_id},
                {"entity_id": student_id},
                {"public_metadata.student_id": student_id},
            ]},
            tenant_id,
        ),
        limit=2000,
    )
    bulletins = await _find(
        db,
        "bulletin_verifications",
        _tenant({"student_id": student_id, "academic_year": {"$in": years}}, tenant_id),
        limit=2000,
    )
    histories = await _find(
        db,
        "history_verifications",
        _tenant({"student_id": student_id}, tenant_id),
        limit=2000,
    )
    manuals = await _find(db, "manual_document_issuances", _tenant({"student_id": student_id}, tenant_id), limit=2000)
    diaries = await _find(
        db,
        "diary_snapshots",
        _tenant({"class_id": source_class_id, "academic_year": {"$in": years}}, tenant_id),
        limit=2000,
    )
    promotion_books = await _find(
        db,
        "promotion_books",
        _tenant({"class_id": source_class_id, "academic_year": {"$in": years}}, tenant_id),
        limit=500,
    )
    render_jobs = await _find(
        db,
        "document_render_jobs",
        _tenant(
            {"$or": [
                {"student_id": student_id},
                {"source_snapshot_id": {"$regex": student_id}},
            ]},
            tenant_id,
        ),
        limit=2000,
    )

    vdocs_by_code = {str(d.get("code")): d for d in vdocs if d.get("code")}
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    revocable: list[dict[str, Any]] = []

    for doc in vdocs:
        if _active_verifiable(doc) and doc.get("code"):
            revocable.append({"kind": "verifiable_document", "artifact_key": _artifact_key("verifiable_document", doc), "snapshot": doc})

    for log in school_logs:
        code = str(log.get("code") or "")
        if not code:
            blockers.append({
                "code": "DOCUMENT_RESOLUTION_REQUIRED_F1_3",
                "message": "Há declaração escolar rastreada sem código verificável suficiente para revogação automática.",
                "detail": {"school_document_log_id": log.get("id")},
            })
        elif code not in vdocs_by_code:
            blockers.append({
                "code": "DOCUMENT_RESOLUTION_REQUIRED_F1_3",
                "message": "O log de declaração escolar referencia código sem documento verificável tenant-scoped correspondente.",
                "detail": {"school_document_log_id": log.get("id"), "code": code},
            })

    for doc in bulletins:
        if _active_verification(doc):
            revocable.append({"kind": "bulletin_verification", "artifact_key": _artifact_key("bulletin_verification", doc), "snapshot": doc})
    for doc in histories:
        if _active_verification(doc):
            revocable.append({"kind": "history_verification", "artifact_key": _artifact_key("history_verification", doc), "snapshot": doc})

    if manuals:
        blockers.append({
            "code": "BLOCKED_DOCUMENT_REVIEW_REQUIRED",
            "message": "Existe Ficha Individual manual rastreada sem política automática de revogação/supersessão.",
            "detail": {"count": len(manuals), "ids": [d.get("id") for d in manuals[:20]]},
        })
    if diaries:
        blockers.append({
            "code": "DIARY_SNAPSHOT_SUPERSESSION_REQUIRED",
            "message": "Há Diário Escolar publicado/imutável na turma de origem; a retificação exige workflow institucional de supersessão.",
            "detail": {"count": len(diaries), "ids": [d.get("id") for d in diaries[:20]]},
        })
    if promotion_books:
        warnings.append({
            "code": "PROMOTION_BOOK_DOCUMENT_RISK",
            "message": "A turma de origem possui Livro de Promoção numerado; isso eleva o risco documental, mas não prova emissão de PDF.",
            "detail": {"count": len(promotion_books)},
        })
    if render_jobs:
        warnings.append({
            "code": "DOCUMENT_RENDER_JOBS_PRESENT",
            "message": "Há render jobs relacionados ao estudante; as verificações rastreadas correspondentes devem permanecer coerentes.",
            "detail": {"count": len(render_jobs)},
        })

    tracked_counts = {
        "school_documents_log": len(school_logs),
        "verifiable_documents": len(vdocs),
        "bulletin_verifications": len(bulletins),
        "history_verifications": len(histories),
        "manual_document_issuances": len(manuals),
        "diary_snapshots": len(diaries),
        "promotion_books": len(promotion_books),
        "document_render_jobs": len(render_jobs),
    }
    normalized = {
        "student_id": student_id,
        "source_class_id": source_class_id,
        "academic_year": academic_year,
        "tracked_counts": tracked_counts,
        "revocable": [(x["kind"], x["artifact_key"], _digest(x["snapshot"])) for x in revocable],
        "blockers": blockers,
        "warnings": warnings,
    }
    return {
        "coverage_complete": False,
        "can_prove_no_prior_issuance": False,
        "requires_untracked_acknowledgement": True,
        "untracked_paths_present": list(UNTRACKED_PATHS),
        "coverage_gap": {
            "code": "SYNC_PDF_LEDGER_GAP",
            "message": "Podem existir PDFs históricos emitidos por caminhos síncronos sem ledger; a execução exige reconhecimento administrativo explícito.",
            "gate": "F2.2_EXECUTION_ACK",
        },
        "tracked_counts": tracked_counts,
        "tracked_total": sum(tracked_counts.values()),
        "revocable": revocable,
        "blocking": blockers,
        "blockers": blockers,
        "warnings": warnings,
        "can_resolve_for_execution": not blockers,
        "inventory_digest": _digest(normalized),
    }


async def _pending_ledger(db, *, tenant_id: str, protocol: str, kind: str, artifact_key: str, snapshot: Mapping[str, Any], actor: Mapping[str, Any]) -> dict[str, Any]:
    await ensure_document_rectification_indexes(db)
    query = {"mantenedora_id": tenant_id, "protocol": protocol, "artifact_kind": kind, "artifact_key": artifact_key}
    prior = await db[DOCUMENT_LEDGER_COLLECTION].find_one(query, {"_id": 0})
    if prior:
        return prior
    doc = {
        "id": str(uuid.uuid4()),
        **query,
        "state": "PENDING",
        "artifact_before": dict(snapshot),
        "artifact_before_hash": _digest(snapshot),
        "created_at": _now(),
        "created_by": actor.get("id"),
        "actor_role": actor.get("role"),
    }
    await db[DOCUMENT_LEDGER_COLLECTION].update_one(query, {"$setOnInsert": doc}, upsert=True)
    return await db[DOCUMENT_LEDGER_COLLECTION].find_one(query, {"_id": 0})


async def _mark_document_applied(db, query: Mapping[str, Any], *, after: Mapping[str, Any] | None = None) -> None:
    await db[DOCUMENT_LEDGER_COLLECTION].update_one(
        dict(query),
        {"$set": {"state": "APPLIED", "applied_at": _now(), "artifact_after": dict(after or {}), "artifact_after_hash": _digest(after or {})}},
    )


async def _revoke_verification_collection(db, *, collection: str, snapshot: Mapping[str, Any], tenant_id: str, actor: Mapping[str, Any], protocol: str) -> dict[str, Any]:
    key_query: dict[str, Any]
    if snapshot.get("id"):
        key_query = {"id": snapshot.get("id")}
    elif snapshot.get("token_hash"):
        key_query = {"token_hash": snapshot.get("token_hash")}
    else:
        raise DocumentRectificationError(
            "DOCUMENT_VERIFICATION_IDENTITY_MISSING",
            f"{collection} não possui identidade estável para revogação.",
        )
    query = _tenant(key_query, tenant_id)
    current = await db[collection].find_one(query, {"_id": 0})
    if not current:
        raise DocumentRectificationError("DOCUMENT_VERIFICATION_NOT_FOUND", f"Registro {collection} não foi encontrado no tenant operacional.")
    if current.get("revoked_at"):
        return current

    revoked_at = _now()
    result = await db[collection].update_one(
        {**query, "revoked_at": current.get("revoked_at")},
        {"$set": {
            "revoked_at": revoked_at,
            "revoked_by": actor.get("id"),
            "revoked_reason": f"Retificação de matrícula/turma — protocolo {protocol}",
            "rectification_protocol": protocol,
        }},
    )
    if result.modified_count != 1:
        latest = await db[collection].find_one(query, {"_id": 0})
        if latest and latest.get("revoked_at") and latest.get("rectification_protocol") == protocol:
            return latest
        raise DocumentRectificationError("DOCUMENT_VERIFICATION_CAS_CONFLICT", f"{collection} mudou durante a revogação.")

    after = await db[collection].find_one(query, {"_id": 0})
    if not after:
        raise DocumentRectificationError("DOCUMENT_VERIFICATION_NOT_FOUND", f"Registro {collection} desapareceu após a revogação.")
    return after


async def resolve_rectification_documents(
    db,
    *,
    protocol: str,
    student_id: str,
    source_class_id: str,
    academic_year: int,
    tenant_id: str,
    actor: Mapping[str, Any],
    acknowledgement: str,
) -> dict[str, Any]:
    """Resolve somente artefatos rastreados que possuem revogação segura."""
    if acknowledgement != DOCUMENT_ACKNOWLEDGEMENT:
        raise DocumentRectificationError(
            "DOCUMENT_UNTRACKED_ACKNOWLEDGEMENT_REQUIRED",
            "A declaração explícita sobre PDFs históricos não rastreados é obrigatória.",
            status_code=422,
        )
    inventory = await build_rectification_document_inventory(
        db,
        student_id=student_id,
        source_class_id=source_class_id,
        academic_year=academic_year,
        tenant_id=tenant_id,
    )
    if inventory["blockers"]:
        raise DocumentRectificationError(
            "DOCUMENT_RESOLUTION_BLOCKED",
            "Há artefatos documentais que exigem revisão/supersessão antes da retificação.",
            detail={"blockers": inventory["blockers"]},
        )

    applied: list[dict[str, Any]] = []
    reason = f"Retificação de matrícula/turma — protocolo {protocol}"
    for item in inventory["revocable"]:
        kind = item["kind"]
        artifact_key = item["artifact_key"]
        snapshot = item["snapshot"]
        ledger = await _pending_ledger(
            db,
            tenant_id=tenant_id,
            protocol=protocol,
            kind=kind,
            artifact_key=artifact_key,
            snapshot=snapshot,
            actor=actor,
        )
        query = {"mantenedora_id": tenant_id, "protocol": protocol, "artifact_kind": kind, "artifact_key": artifact_key}
        if ledger.get("state") == "APPLIED":
            applied.append({**ledger, "idempotent_replay": True})
            continue
        try:
            if kind == "verifiable_document":
                code = snapshot.get("code")
                if not code:
                    raise DocumentRectificationError("DOCUMENT_CODE_MISSING", "Documento verificável sem código não pode ser revogado automaticamente.")
                current = await db.verifiable_documents.find_one(_tenant({"code": code}, tenant_id), {"_id": 0})
                if current and not current.get("revoked"):
                    after = await revoke_document(db, code=code, reason=reason, user=dict(actor))
                else:
                    after = current or snapshot
            elif kind == "bulletin_verification":
                after = await _revoke_verification_collection(db, collection="bulletin_verifications", snapshot=snapshot, tenant_id=tenant_id, actor=actor, protocol=protocol)
            elif kind == "history_verification":
                after = await _revoke_verification_collection(db, collection="history_verifications", snapshot=snapshot, tenant_id=tenant_id, actor=actor, protocol=protocol)
            else:  # pragma: no cover - revocable é fechado acima
                raise DocumentRectificationError("DOCUMENT_KIND_UNSUPPORTED", f"Tipo documental não suportado: {kind}")
            await _mark_document_applied(db, query, after=after)
            final = await db[DOCUMENT_LEDGER_COLLECTION].find_one(query, {"_id": 0})
            applied.append({**(final or {}), "idempotent_replay": False})
        except Exception as exc:
            await db[DOCUMENT_LEDGER_COLLECTION].update_one(
                query,
                {"$set": {"state": "FAILED_MANUAL_RECOVERY", "failed_at": _now(), "failure_message": str(exc)}},
            )
            if isinstance(exc, DocumentRectificationError):
                raise
            raise DocumentRectificationError(
                "DOCUMENT_RESOLUTION_FAILED",
                "Falha ao invalidar documento rastreado; recuperação manual é necessária.",
                detail={"artifact_kind": kind, "artifact_key": artifact_key},
            ) from exc

    return {
        "protocol": protocol,
        "inventory_digest": inventory["inventory_digest"],
        "applied": applied,
        "revoked_count": len(applied),
        "untracked_acknowledgement_recorded": True,
    }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _issued_after(doc: Mapping[str, Any], since: datetime) -> bool:
    for field in ("emitted_at", "created_at", "generated_at", "completed_at", "issued_at"):
        dt = _parse_dt(doc.get(field))
        if dt and dt > since:
            return True
    return False


async def check_rectification_rollback_eligibility(
    db,
    *,
    protocol: str,
    student_id: str,
    source_class_id: str,
    academic_year: int,
    tenant_id: str,
    executed_at: str,
) -> dict[str, Any]:
    """Rollback é fail-closed diante de revogação irreversível ou nova emissão."""
    applied_docs = await db[DOCUMENT_LEDGER_COLLECTION].find(
        {"mantenedora_id": tenant_id, "protocol": protocol, "state": "APPLIED"}, {"_id": 0}
    ).to_list(2000)
    blockers: list[dict[str, Any]] = []
    if applied_docs:
        blockers.append({
            "code": "ROLLBACK_DOCUMENT_REVOCATION_IRREVERSIBLE",
            "message": "A retificação revogou documentos rastreados; o serviço documental não permite desfazer revogação.",
            "detail": {"count": len(applied_docs)},
        })

    since = _parse_dt(executed_at)
    if not since:
        blockers.append({"code": "ROLLBACK_EXECUTED_AT_INVALID", "message": "Não foi possível validar o instante da execução.", "detail": None})
    else:
        inventory = await build_rectification_document_inventory(
            db,
            student_id=student_id,
            source_class_id=source_class_id,
            academic_year=academic_year,
            tenant_id=tenant_id,
        )
        current_docs: list[dict[str, Any]] = []
        for item in inventory["revocable"]:
            current_docs.append(item["snapshot"])
        for collection, query in (
            ("school_documents_log", _tenant({"student_id": student_id}, tenant_id)),
            ("manual_document_issuances", _tenant({"student_id": student_id}, tenant_id)),
        ):
            current_docs.extend(await _find(db, collection, query, limit=2000))
        newer = [d for d in current_docs if _issued_after(d, since)]
        if newer:
            blockers.append({
                "code": "ROLLBACK_NEW_DOCUMENT_ISSUANCE",
                "message": "Há documento emitido depois da retificação; a reversão tornaria essa emissão inconsistente.",
                "detail": {"count": len(newer)},
            })

    return {"eligible": not blockers, "blockers": blockers}


async def detect_rectification_origin_residues(
    db,
    *,
    student_id: str,
    source_enrollment_id: str,
    source_class_id: str,
    academic_year: int,
    tenant_id: str,
) -> dict[str, Any]:
    years = _year_values(academic_year)
    enrollment_source = await db.enrollments.count_documents(
        _tenant({"id": source_enrollment_id, "student_id": student_id, "class_id": source_class_id, "status": "active"}, tenant_id)
    )
    attendance_source = await db.attendance.count_documents(
        _tenant({"class_id": source_class_id, "academic_year": {"$in": years}, "records.student_id": student_id}, tenant_id)
    )
    grades_source = await db.grades.count_documents(
        _tenant({"student_id": student_id, "class_id": source_class_id, "academic_year": {"$in": years}}, tenant_id)
    )
    student = await db.students.find_one(_tenant({"id": student_id}, tenant_id), {"_id": 0, "class_id": 1})
    projection_source = 1 if student and str(student.get("class_id") or "") == str(source_class_id) else 0
    residues = {
        "active_enrollment_in_source": enrollment_source,
        "attendance_records_in_source": attendance_source,
        "grades_in_source": grades_source,
        "student_projection_in_source": projection_source,
    }
    return {"ok": all(v == 0 for v in residues.values()), "residues": residues}
