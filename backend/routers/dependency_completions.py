"""
Dependency Completion Snapshots — núcleo documental imutável.

[Fev/2026] P1 imediato — pré-requisito para Boletim (Fase 3) e Histórico (Fase 4).

Princípios (cf. /app/docs/HISTORICO_ESCOLAR_CONTRACT.md §12-13):

1. Coleção `db.dependency_completions` é APPEND-ONLY.
2. Hook em `PUT /api/student-dependencies/{id}` cria automaticamente um snapshot
   ao mudar status para `completed | failed | cancelled`.
3. `cancelled` exige `status_reason` não vazio.
4. Snapshot captura `original_course_name_at_completion`, `original_curriculum_version`
   etc. SNAPSHOTS — não links — para sobreviver a reorganizações curriculares.
5. `document_hash_sha256` é IMUTÁVEL após emissão. Cada assinatura tem seu
   próprio `signature_hash_sha256` referenciando o `document_hash` original.
6. `data_quality` em {complete, partial, incomplete} controla se o snapshot
   pode receber assinatura final (only complete).
7. Revogação via `revoked_at` + `revoked_reason`. Documento revogado
   continua na coleção (auditoria) mas `document_status='revogado'` no público.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from tenant_scope import get_mantenedora_scope
from utils.document_hash import (
    compute_document_hash,
    compute_signature_hash,
    verify_document_hash,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
COMPLETION_RESULTS = ("approved", "failed", "cancelled")
DATA_QUALITY_VALUES = ("complete", "partial", "incomplete")
SIGNATURE_ROLES = ("diretor", "secretario")

ROLES_VIEW_COMPLETIONS = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
    "semed", "semed1", "semed2", "semed3",
}
ROLES_BACKFILL = {"super_admin", "admin", "admin_teste"}
ROLES_REVOKE = {"super_admin", "admin", "gerente", "diretor"}
ROLES_SIGN = {"diretor", "secretario", "super_admin", "admin"}

DOCUMENT_VERSION = "1.0.0"
HISTORY_SCHEMA_VERSION = "1"


# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_verification_token() -> str:
    """URL-safe, opaco, 24 chars (~144 bits de entropia)."""
    return secrets.token_urlsafe(18)


def _result_to_document_status(completion_result: str, revoked_at: Optional[str]) -> str:
    """Mapeia enum interno para representação documental pública (jurídica)."""
    if revoked_at:
        return "revogado"
    if completion_result == "approved":
        return "valido"
    if completion_result == "failed":
        return "valido_reprovado"  # documento ainda válido, registra reprovação
    if completion_result == "cancelled":
        return "cancelado_administrativamente"
    return "indefinido"


async def _resolve_data_quality(
    db, *, student_id: str, course_id: str, dependency_id: str
) -> tuple[str, Optional[float], Optional[float]]:
    """Calcula final_grade e final_attendance_pct.

    Retorna `(data_quality, grade, attendance_pct)`.
    """
    # Nota
    grade_doc = await db.grades.find_one(
        {"student_id": student_id, "course_id": course_id, "dependency_id": dependency_id},
        {"_id": 0},
    )
    final_grade = None
    if grade_doc:
        final_grade = grade_doc.get("final_average")
        if final_grade is None:
            # tenta computar simples a partir de bimestres se houver
            bimestres = [grade_doc.get(f"b{i}") for i in (1, 2, 3, 4)]
            present = [b for b in bimestres if b is not None]
            if present:
                final_grade = round(sum(present) / len(present), 2)

    # Frequência
    cursor = db.attendance.find(
        {"course_id": course_id, "records.dependency_id": dependency_id},
        {"_id": 0, "records": 1},
    )
    total = 0
    present = 0
    async for att in cursor:
        for r in att.get("records") or []:
            if r.get("dependency_id") != dependency_id or r.get("student_id") != student_id:
                continue
            total += 1
            if (r.get("status") or "").upper() in {"P", "PRESENT", "PRESENTE"}:
                present += 1
    attendance_pct = round((present / total) * 100, 2) if total > 0 else None

    if final_grade is not None and attendance_pct is not None:
        return "complete", final_grade, attendance_pct
    if final_grade is None and attendance_pct is None:
        return "incomplete", None, None
    return "partial", final_grade, attendance_pct


async def _build_completion_snapshot(
    db,
    *,
    dependency_doc: dict,
    completion_result: str,
    status_reason: Optional[str],
    completion_academic_year: int,
    issued_by_user_id: str,
) -> dict:
    """Monta o snapshot canônico de uma conclusão de dependência."""
    # Snapshots de course/turma/matriz (capturados AGORA, imutáveis)
    course = await db.courses.find_one(
        {"id": dependency_doc["course_id"]},
        {"_id": 0, "id": 1, "name": 1, "workload_hours": 1, "curriculum_version": 1},
    ) or {}
    origin_class = await db.classes.find_one(
        {"id": dependency_doc.get("origin_class_id") or dependency_doc.get("class_id")},
        {"_id": 0, "id": 1, "name": 1, "academic_year": 1, "curriculum_version": 1},
    ) or {}

    data_quality, final_grade, attendance_pct = await _resolve_data_quality(
        db,
        student_id=dependency_doc["student_id"],
        course_id=dependency_doc["course_id"],
        dependency_id=dependency_doc["id"],
    )

    # Cancelamentos não computam dados pedagógicos
    if completion_result == "cancelled":
        data_quality = "incomplete"

    issued_at = _now_iso()
    snapshot = {
        "id": str(uuid.uuid4()),
        "student_id": dependency_doc["student_id"],
        "dependency_id": dependency_doc["id"],
        "school_id": dependency_doc.get("school_id"),
        "mantenedora_id": dependency_doc.get("mantenedora_id"),

        # Snapshots imutáveis (preservam contexto curricular do momento)
        "original_course_id": dependency_doc["course_id"],
        "original_course_name_at_completion": course.get("name") or "",
        "original_curriculum_version": (
            origin_class.get("curriculum_version")
            or course.get("curriculum_version")
            or "unspecified"
        ),
        "original_academic_year": dependency_doc.get("origin_academic_year")
            or origin_class.get("academic_year"),
        "original_class_id": dependency_doc.get("origin_class_id")
            or dependency_doc.get("class_id"),

        # Conclusão
        "completion_academic_year": completion_academic_year,
        "completion_result": completion_result,
        "status_reason": status_reason,
        "final_grade": final_grade,
        "final_attendance_pct": attendance_pct,
        "workload_hours": course.get("workload_hours"),

        # Qualidade dos dados — define se pode ser assinado oficialmente
        "data_quality": data_quality,

        # Versionamento documental
        "document_version": DOCUMENT_VERSION,
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "template_version": None,         # preenchido quando boletim/PDF for gerado
        "render_engine_version": None,

        # Emissão
        "issued_at": issued_at,
        "issued_by_user_id": issued_by_user_id,

        # Verificação pública (placeholder — gerado abaixo)
        "verification_token": _gen_verification_token(),

        # Revogação (placeholder)
        "revoked_at": None,
        "revoked_reason": None,
        "revoked_by_user_id": None,
        "superseded_by_document_id": None,

        # Invalidação documental por evento acadêmico (Fase 3+ — placeholders)
        # Quando implementada, será preenchida automaticamente caso uma
        # alteração em registros pré-effective_date afete dados do snapshot.
        "invalidated_by_event_id": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "supersedes_document_id": None,

        # Assinaturas (vazias na criação)
        "signatures": [],

        # Trilha de auditoria
        "audit_trail": [
            {
                "action": "snapshot_created",
                "by_user_id": issued_by_user_id,
                "at": issued_at,
                "data_quality": data_quality,
            }
        ],
    }

    # Hash documental — IMUTÁVEL daqui em diante.
    snapshot["document_hash_sha256"] = compute_document_hash(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
async def create_completion_snapshot_on_transition(
    db,
    *,
    dependency_doc: dict,
    new_status: str,
    status_reason: Optional[str],
    issued_by_user_id: str,
    completion_academic_year: Optional[int] = None,
) -> Optional[dict]:
    """Hook idempotente — chamado quando dep muda para completed/failed/cancelled.

    Idempotência: se já existir snapshot com `dependency_id` +
    `completion_academic_year` + `completion_result` IDÊNTICOS, NÃO duplica.

    `cancelled` exige `status_reason` não-vazio (regra do owner Fev/2026).
    """
    completion_result = {
        "completed": "approved",
        "failed": "failed",
        "cancelled": "cancelled",
    }.get(new_status)
    if completion_result is None:
        return None  # transição não-documental

    if completion_result == "cancelled":
        if not status_reason or not status_reason.strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CANCELLATION_REASON_REQUIRED",
                    "message": "Cancelamento exige status_reason não vazio.",
                },
            )

    completion_year = completion_academic_year or datetime.now(timezone.utc).year

    # Idempotência defensiva
    existing = await db.dependency_completions.find_one(
        {
            "dependency_id": dependency_doc["id"],
            "completion_academic_year": completion_year,
            "completion_result": completion_result,
            "revoked_at": None,
        },
        {"_id": 0, "id": 1},
    )
    if existing:
        logger.info(
            "[completion] snapshot já existe — pulando dep_id=%s result=%s",
            dependency_doc["id"], completion_result,
        )
        return existing

    snapshot = await _build_completion_snapshot(
        db,
        dependency_doc=dependency_doc,
        completion_result=completion_result,
        status_reason=status_reason,
        completion_academic_year=completion_year,
        issued_by_user_id=issued_by_user_id,
    )
    await db.dependency_completions.insert_one(snapshot)
    snapshot.pop("_id", None)
    logger.info(
        "[completion] snapshot criado dep_id=%s result=%s data_quality=%s hash=%s",
        dependency_doc["id"], completion_result, snapshot["data_quality"],
        snapshot["document_hash_sha256"][:12],
    )
    return snapshot


# ---------------------------------------------------------------------------
async def ensure_indexes(db) -> None:
    """Cria índices únicos/eficientes — idempotente."""
    await db.dependency_completions.create_index("verification_token", unique=True, background=True)
    await db.dependency_completions.create_index([("dependency_id", 1), ("completion_academic_year", 1)], background=True)
    await db.dependency_completions.create_index([("student_id", 1), ("issued_at", -1)], background=True)
    await db.dependency_completions.create_index("mantenedora_id", background=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def setup_dependency_completions_router(db, audit_service=None):
    router = APIRouter(prefix="/dependency-completions", tags=["Dependency Completions"])

    @router.get("/student/{student_id}")
    async def list_completions_for_student(student_id: str, request: Request):
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") not in ROLES_VIEW_COMPLETIONS:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        tenant = get_mantenedora_scope(current_user, request)
        flt: dict = {"student_id": student_id}
        if tenant:
            flt["mantenedora_id"] = tenant
        items = await db.dependency_completions.find(
            flt, {"_id": 0, "audit_trail": 0}
        ).sort("issued_at", -1).to_list(200)
        return {"student_id": student_id, "items": items, "total": len(items)}

    @router.get("/{completion_id}")
    async def get_completion(completion_id: str, request: Request):
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") not in ROLES_VIEW_COMPLETIONS:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        doc = await db.dependency_completions.find_one({"id": completion_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Snapshot não encontrado.")
        return doc

    @router.post("/{completion_id}/sign")
    async def sign_completion(completion_id: str, request: Request):
        """Adiciona assinatura institucional. NÃO altera document_hash original.

        Bloqueios:
        - role autorizado (diretor/secretario/super_admin/admin)
        - data_quality DEVE ser 'complete' (HTTP 409 caso contrário)
        - documento NÃO pode estar revogado (HTTP 409)
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") not in ROLES_SIGN:
            raise HTTPException(status_code=403, detail="Sem permissão para assinar.")

        doc = await db.dependency_completions.find_one({"id": completion_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Snapshot não encontrado.")

        if doc.get("revoked_at"):
            raise HTTPException(
                status_code=409,
                detail={"code": "DOCUMENT_REVOKED", "revoked_at": doc["revoked_at"]},
            )

        if doc.get("data_quality") != "complete":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DATA_QUALITY_INSUFFICIENT",
                    "data_quality": doc.get("data_quality"),
                    "message": "Snapshot precisa estar 'complete' antes da assinatura institucional.",
                },
            )

        # Defensivo: verifica que document_hash não foi corrompido desde emissão.
        if not verify_document_hash(doc, doc["document_hash_sha256"]):
            raise HTTPException(
                status_code=500,
                detail={"code": "DOCUMENT_INTEGRITY_VIOLATED"},
            )

        # Inferir role do assinante: usa role efetivo (diretor/secretario)
        signer_role = current_user.get("role")
        if signer_role not in SIGNATURE_ROLES and signer_role in {"super_admin", "admin"}:
            # super_admin pode assinar em nome de — exige header explícito
            sign_as = request.headers.get("X-Sign-As-Role")
            if sign_as not in SIGNATURE_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "SIGN_AS_ROLE_REQUIRED",
                            "expected": list(SIGNATURE_ROLES)},
                )
            signer_role = sign_as

        # Anti-duplicidade: mesmo role não assina 2x
        if any(s.get("role") == signer_role for s in doc.get("signatures") or []):
            raise HTTPException(
                status_code=409,
                detail={"code": "ROLE_ALREADY_SIGNED", "role": signer_role},
            )

        signed_at = _now_iso()
        signature_hash = compute_signature_hash(
            document_hash=doc["document_hash_sha256"],
            role=signer_role,
            user_id=current_user.get("id") or current_user.get("user_id"),
            signed_at=signed_at,
        )
        signature = {
            "role": signer_role,
            "user_id": current_user.get("id") or current_user.get("user_id"),
            "full_name_at_signing": current_user.get("full_name") or current_user.get("name"),
            "signed_at": signed_at,
            "signed_document_hash": doc["document_hash_sha256"],  # referência ao doc original
            "signature_hash_sha256": signature_hash,
        }
        await db.dependency_completions.update_one(
            {"id": completion_id},
            {
                "$push": {
                    "signatures": signature,
                    "audit_trail": {
                        "action": "signed",
                        "by_user_id": signature["user_id"],
                        "by_role": signer_role,
                        "at": signed_at,
                    },
                },
            },
        )
        return {"id": completion_id, "signature": signature}

    @router.post("/{completion_id}/revoke")
    async def revoke_completion(completion_id: str, request: Request):
        """Revoga snapshot (doc continua na coleção; verify público diz 'revogado').

        Exige rationale ≥ 30 chars no body.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") not in ROLES_REVOKE:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        body = await request.json()
        reason = (body.get("rationale") or "").strip()
        if len(reason) < 30:
            raise HTTPException(
                status_code=422,
                detail={"code": "RATIONALE_TOO_SHORT", "min_chars": 30},
            )
        doc = await db.dependency_completions.find_one({"id": completion_id}, {"_id": 0, "id": 1, "revoked_at": 1})
        if not doc:
            raise HTTPException(status_code=404, detail="Snapshot não encontrado.")
        if doc.get("revoked_at"):
            raise HTTPException(status_code=409, detail={"code": "ALREADY_REVOKED"})
        revoked_at = _now_iso()
        await db.dependency_completions.update_one(
            {"id": completion_id},
            {
                "$set": {
                    "revoked_at": revoked_at,
                    "revoked_reason": reason,
                    "revoked_by_user_id": current_user.get("id") or current_user.get("user_id"),
                },
                "$push": {
                    "audit_trail": {
                        "action": "revoked",
                        "by_user_id": current_user.get("id") or current_user.get("user_id"),
                        "at": revoked_at,
                        "reason": reason,
                    }
                },
            },
        )
        return {"id": completion_id, "revoked_at": revoked_at}

    return router


def setup_public_verification_router(db):
    """Endpoint público para validação por terceiros (QR / faculdades)."""
    router = APIRouter(prefix="/public", tags=["Public Verification"])

    @router.get("/verify/{verification_token}")
    async def verify_completion(verification_token: str):
        """Verificação institucional sem auth — retorna apenas dados não-sensíveis.

        NÃO retorna PII além do nome dos signatários institucionais.
        Mapeia `completion_result` → `document_status` jurídico-amigável.
        """
        doc = await db.dependency_completions.find_one(
            {"verification_token": verification_token},
            {
                "_id": 0,
                "id": 1,
                "issued_at": 1,
                "completion_result": 1,
                "completion_academic_year": 1,
                "original_course_name_at_completion": 1,
                "original_academic_year": 1,
                "document_hash_sha256": 1,
                "document_version": 1,
                "history_schema_version": 1,
                "data_quality": 1,
                "revoked_at": 1,
                "signatures": 1,
                "school_id": 1,
            },
        )
        if not doc:
            # Fallback: verifica em verifiable_documents (Verifiable Documents MVP)
            # Aceita tanto verification_token UUID quanto code SIGESC-XXXX-XXXX.
            from services import verifiable_docs_service as _vsvc
            vdoc = await _vsvc.resolve_either(db, verification_token)
            if vdoc:
                # Renderiza no shape do portal verifiable_docs (LGPD-safe).
                resp = _vsvc.build_portal_response(vdoc)
                # Re-mapeia "valid" para compatibilidade com clients antigos.
                resp["valid"] = resp.get("status") == "valido"
                # Se snapshot vinculado, revalida integridade
                if resp.get("status") == "valido" and vdoc.get("snapshot_id"):
                    snap = await db.ai_analysis_snapshots.find_one(
                        {"id": vdoc["snapshot_id"]}, {"_id": 0, "expires_at_dt": 0}
                    )
                    if snap:
                        from services import snapshot_service as _snap_svc
                        integrity = _snap_svc.verify_snapshot_integrity(snap)
                        if not integrity["valid"]:
                            resp["status"] = "invalido"
                            resp["valid"] = False
                            resp["mensagem"] = (
                                "A integridade deste documento não pôde ser confirmada."
                            )
                    else:
                        resp["status"] = "invalido"
                        resp["valid"] = False
                return resp
            # Não encontrado em nenhuma fonte — shape unificado (verifiable_docs).
            from services import verifiable_docs_service as _vsvc2
            return _vsvc2.build_portal_response(None)

        # Resolve nome da escola sem PII adicional
        school_name = None
        if doc.get("school_id"):
            sch = await db.schools.find_one({"id": doc["school_id"]}, {"_id": 0, "name": 1})
            if sch:
                school_name = sch.get("name")

        document_status = _result_to_document_status(
            doc.get("completion_result"), doc.get("revoked_at")
        )
        valid = document_status not in {"revogado", "nao_encontrado"}

        # Sanitiza signatures expondo só role + nome + signed_at
        sigs_public = [
            {"role": s.get("role"),
             "full_name": s.get("full_name_at_signing"),
             "signed_at": s.get("signed_at")}
            for s in (doc.get("signatures") or [])
        ]

        return {
            "valid": valid,
            "document_status": document_status,
            "document_hash": doc.get("document_hash_sha256"),
            "issued_at": doc.get("issued_at"),
            "school_name": school_name,
            "course_name": doc.get("original_course_name_at_completion"),
            "original_academic_year": doc.get("original_academic_year"),
            "completion_academic_year": doc.get("completion_academic_year"),
            "data_quality": doc.get("data_quality"),
            "signatures": sigs_public,
            "document_version": doc.get("document_version"),
            "history_schema_version": doc.get("history_schema_version"),
        }

    return router


# ---------------------------------------------------------------------------
# Backfill admin endpoint
# ---------------------------------------------------------------------------
def setup_admin_completions_backfill_router(db):
    router = APIRouter(prefix="/admin/dependency-completions", tags=["Admin"])

    @router.post("/backfill")
    async def backfill(request: Request):
        """Gera snapshots para deps já com status completed/failed/cancelled
        que ainda não tenham snapshot. Idempotente. Suporta `?dry_run=true`.

        Estratégia híbrida (data_quality):
        - 'complete' se nota + frequência conhecidas
        - 'partial' se um deles ausente
        - 'incomplete' caso contrário (ou cancelados)
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") not in ROLES_BACKFILL:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        dry_run = request.query_params.get("dry_run") in {"1", "true", "True"}

        statuses = {"completed", "failed", "cancelled"}
        cursor = db.student_dependencies.find(
            {"status": {"$in": list(statuses)}}, {"_id": 0}
        )
        created, skipped, errors = [], [], []
        async for dep in cursor:
            existing = await db.dependency_completions.find_one(
                {"dependency_id": dep["id"], "revoked_at": None},
                {"_id": 0, "id": 1},
            )
            if existing:
                skipped.append({"dependency_id": dep["id"], "reason": "already_has_snapshot"})
                continue
            try:
                # status_reason fallback p/ cancelados antigos
                reason = dep.get("status_reason") or (
                    "Backfill retroativo — motivo não preservado" if dep["status"] == "cancelled" else None
                )
                if dry_run:
                    created.append({
                        "dependency_id": dep["id"], "would_result": dep["status"], "dry_run": True,
                    })
                    continue
                snap = await create_completion_snapshot_on_transition(
                    db,
                    dependency_doc=dep,
                    new_status=dep["status"],
                    status_reason=reason,
                    issued_by_user_id=current_user.get("id") or current_user.get("user_id"),
                    completion_academic_year=dep.get("completed_in_academic_year")
                        or datetime.now(timezone.utc).year,
                )
                created.append({"dependency_id": dep["id"], "snapshot_id": snap["id"] if snap else None,
                                "data_quality": (snap or {}).get("data_quality")})
            except Exception as e:
                logger.exception("[completion-backfill] erro dep_id=%s", dep["id"])
                errors.append({"dependency_id": dep["id"], "error": str(e)})

        return {
            "dry_run": dry_run,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "created": created[:200],
            "skipped": skipped[:200],
            "errors": errors[:50],
        }

    return router
