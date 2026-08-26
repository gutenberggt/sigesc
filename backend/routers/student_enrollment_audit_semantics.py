"""Semântica segura da Auditoria de Matrículas.

Problema tratado:
- o endpoint legado considera qualquer ``enrollment_number`` vazio como erro;
- movimentações canônicas liberam o número do vínculo histórico e o preservam em
  ``previous_enrollment_number`` para que o vínculo ativo possa reutilizar a mesma
  identidade sem violar o índice único;
- portanto, vínculo histórico encerrado + ``previous_enrollment_number`` preenchido
  NÃO é "matrícula sem número" acionável.

Esta camada é deliberadamente conservadora:
- mantém o endpoint GET legado e apenas reclassifica a contagem de ``enrollments``;
- expõe ``empty_raw`` e ``historical_preserved`` para rastreabilidade;
- só reduz ``empty`` quando a partição raw = actionable + preserved fecha exatamente;
- desativa o reparo automático legado, que gerava números novos indiscriminadamente.

Nenhuma função deste módulo escreve no MongoDB.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import HTTPException, Request, status

from auth_middleware import AuthMiddleware


AUDIT_PATH = "/students/enrollment-audit"
REPAIR_PATH = "/students/enrollment-audit/repair"

HISTORICAL_STATUSES = frozenset({
    "relocated",
    "transferred",
    "progressed",
    "completed",
    "cancelled",
    "dropout",
    # Legados conhecidos; não devem voltar a ser criados, mas podem existir.
    "reclassified",
    "inactive",
    "deceased",
})

EMPTY_NUMBER_COND = {
    "$or": [
        {"enrollment_number": {"$exists": False}},
        {"enrollment_number": None},
        {"enrollment_number": ""},
    ]
}

HISTORICAL_PRESERVED_COND = {
    "$and": [
        EMPTY_NUMBER_COND,
        {"status": {"$in": sorted(HISTORICAL_STATUSES)}},
        {"previous_enrollment_number": {"$gt": ""}},
    ]
}

ACTIONABLE_EMPTY_COND = {
    "$and": [
        EMPTY_NUMBER_COND,
        {
            "$nor": [
                {
                    "status": {"$in": sorted(HISTORICAL_STATUSES)},
                    "previous_enrollment_number": {"$gt": ""},
                }
            ]
        },
    ]
}

_ALLOWED_ROLES = ["super_admin", "admin", "admin_teste", "gerente"]


def classify_empty_enrollment(doc: dict) -> str:
    """Classifica um documento para testes/auditoria sem reinterpretar números.

    Retornos:
    - ``numbered``: enrollment_number atual presente;
    - ``historical_preserved``: histórico encerrado, número atual vazio e snapshot
      preservado em previous_enrollment_number;
    - ``actionable_empty``: vazio que ainda exige investigação/correção governada.
    """
    number = str(doc.get("enrollment_number") or "").strip()
    if number:
        return "numbered"

    previous = str(doc.get("previous_enrollment_number") or "").strip()
    status_value = str(doc.get("status") or "").strip().lower()
    if previous and status_value in HISTORICAL_STATUSES:
        return "historical_preserved"
    return "actionable_empty"


def _remove_route(base_router: Any, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def _scope_base(current_user: dict) -> dict:
    """Espelha exatamente o escopo dos endpoints legados de auditoria."""
    role = current_user.get("role")
    base: dict = {}
    if role != "super_admin":
        tenant_id = current_user.get("mantenedora_id")
        if tenant_id:
            base["mantenedora_id"] = tenant_id
    if role == "secretario":
        base["school_id"] = {"$in": current_user.get("school_ids", []) or []}
    return base


def _db_for_user(db, sandbox_db, current_user: dict):
    if current_user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


async def _semantic_counts(current_db, base: dict) -> tuple[int, int]:
    preserved = await current_db.enrollments.count_documents(
        {**base, **HISTORICAL_PRESERVED_COND}
    )
    actionable = await current_db.enrollments.count_documents(
        {**base, **ACTIONABLE_EMPTY_COND}
    )
    return int(actionable), int(preserved)


def install_student_enrollment_audit_semantics(
    base_router: Any,
    db,
    sandbox_db=None,
):
    """Instala semântica histórica no GET e aposenta o repair automático legado."""
    if getattr(base_router, "_student_enrollment_audit_semantics_installed", False):
        return base_router

    current_audit = _remove_route(base_router, AUDIT_PATH, "GET")
    current_repair = _remove_route(base_router, REPAIR_PATH, "POST")
    if current_audit is None or current_repair is None:
        raise RuntimeError(
            "Enrollment Audit Semantics não pôde ser instalado: rotas legadas esperadas ausentes."
        )

    @base_router.get("/enrollment-audit")
    @wraps(current_audit)
    async def semantic_enrollment_audit(request: Request):
        result = await current_audit(request)

        current_user = await AuthMiddleware.require_roles(_ALLOWED_ROLES)(request)
        current_db = _db_for_user(db, sandbox_db, current_user)
        base = _scope_base(current_user)

        raw_empty = int((result.get("enrollments") or {}).get("empty", 0))
        actionable, preserved = await _semantic_counts(current_db, base)
        partition_ok = raw_empty == actionable + preserved

        enrollment_block = result.setdefault("enrollments", {})
        enrollment_block["empty_raw"] = raw_empty
        enrollment_block["historical_preserved"] = preserved
        enrollment_block["semantic_partition_ok"] = partition_ok
        enrollment_block["semantics_version"] = "historical-previous-v1"

        # Fail-closed: se a partição não fechar, NÃO escondemos nenhum vazio.
        enrollment_block["empty"] = actionable if partition_ok else raw_empty

        result["repair_policy"] = {
            "enabled": False,
            "code": "GOVERNED_RECONCILIATION_REQUIRED",
            "message": (
                "O reparo automático de números foi desativado. "
                "Correções de identidade de matrícula exigem reconciliação governada e preflight."
            ),
        }
        return result

    @base_router.post("/enrollment-audit/repair")
    @wraps(current_repair)
    async def blocked_legacy_enrollment_repair(request: Request):
        # Preserva exatamente a autenticação/autorização da rota anterior antes de
        # informar que o mecanismo automático foi aposentado.
        await AuthMiddleware.require_roles(_ALLOWED_ROLES)(request)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Reparo automático de números de matrícula desativado por segurança. "
                "A identidade institucional deve ser reconciliada por processo governado, "
                "com evidência histórica, preflight e manifesto selado."
            ),
        )

    setattr(base_router, "_student_enrollment_audit_semantics_installed", True)
    return base_router
