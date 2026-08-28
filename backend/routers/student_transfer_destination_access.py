"""P1 — autorização da escola de destino para matrícula de estudante transferido.

Contrato institucional:
- estudante ATIVO continua restrito à escola vinculada ao secretário;
- estudante TRANSFERIDO pode ser consultado por secretário de outra escola da MESMA
  mantenedora para viabilizar a matrícula de entrada;
- consultar um transferido não concede permissão sobre a escola de origem;
- qualquer mudança de escola ou reativação feita por secretário exige que a
  escola FINAL esteja no escopo escolar do JWT;
- o fluxo legado continua responsável por validar turma, criar enrollment,
  preservar histórico e aplicar as demais regras de domínio;
- documentos históricos passam pela mesma normalização não persistente usada por
  ``student_legacy_compat`` antes de serem devolvidos ao contrato ``Student``.

A camada é deliberadamente pequena e fail-closed. Ela não grava diretamente no
MongoDB e não altera lotações, JWTs ou regras de estudantes ativos.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import HTTPException, Request, status

from auth_middleware import AuthMiddleware
from models import Student, StudentUpdate
from tenant_scope import get_mantenedora_scope
from .student_legacy_compat import normalize_legacy_student_doc


ROUTE_PATH = "/students/{student_id}"
TRANSFERRED_STATUSES = frozenset({"transferred", "transferido"})
ACTIVE_STATUSES = frozenset({"active", "ativo"})


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _payload(model: StudentUpdate) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)  # pragma: no cover - Pydantic v1


def _db_for_user(db, sandbox_db, current_user: dict):
    if current_user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


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


def _assert_transfer_candidate_same_tenant(
    student_doc: dict,
    current_user: dict,
    request: Request,
) -> None:
    """Libera consulta do transferido somente com tenant explícito e coincidente."""
    student_tenant = str(student_doc.get("mantenedora_id") or "").strip()
    user_tenant = str(get_mantenedora_scope(current_user, request) or "").strip()

    if not student_tenant or not user_tenant or student_tenant != user_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Estudante transferido não pertence à mantenedora do usuário",
        )


async def _assert_secretary_destination_access(
    *,
    request: Request,
    current_user: dict,
    student_doc: dict,
    student_update: StudentUpdate,
) -> None:
    """Protege a escola FINAL quando o secretário movimenta/reactiva o estudante."""
    if current_user.get("role") != "secretario":
        return

    payload = _payload(student_update)
    if not payload:
        return

    old_school_id = str(student_doc.get("school_id") or "").strip()
    target_school_id = str(payload.get("school_id") or old_school_id).strip()
    school_is_changing = "school_id" in payload and target_school_id != old_school_id
    becoming_active = "status" in payload and _norm(payload.get("status")) in ACTIVE_STATUSES

    # Edição meramente cadastral de estudante não ativo continua possível sem exigir
    # vínculo com a escola histórica. A autorização de destino só entra quando a
    # operação efetivamente muda escola ou reativa o estudante.
    if not school_is_changing and not becoming_active:
        return

    if not target_school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escola de destino é obrigatória para efetivar a matrícula",
        )

    # Fonte de verdade: school_ids do JWT. verify_school_access também aplica a
    # guarda cross-tenant da escola de destino.
    await AuthMiddleware.verify_school_access(request, target_school_id)


def install_student_transfer_destination_access(
    base_router: Any,
    db,
    sandbox_db=None,
):
    """Instala leitura tenant-wide do transferido + guarda da escola de destino."""
    if getattr(base_router, "_student_transfer_destination_access_installed", False):
        return base_router

    current_get = _remove_route(base_router, ROUTE_PATH, "GET")
    current_update = _remove_route(base_router, ROUTE_PATH, "PUT")
    if current_get is None or current_update is None:
        raise RuntimeError(
            "Transfer Destination Access não pôde ser instalado: "
            "rotas GET/PUT de estudante esperadas ausentes."
        )

    @base_router.get("/{student_id}", response_model=Student)
    @wraps(current_get)
    async def transfer_aware_get_student(student_id: str, request: Request):
        current_user = await AuthMiddleware.get_current_user(request)

        # Todos os demais perfis preservam exatamente a autorização anterior.
        if current_user.get("role") != "secretario":
            return await current_get(student_id, request)

        current_db = _db_for_user(db, sandbox_db, current_user)
        student_doc = await current_db.students.find_one(
            {"id": student_id}, {"_id": 0}
        )
        if not student_doc:
            # Preserva a resposta/semântica 404 do endpoint anterior.
            return await current_get(student_id, request)

        if _norm(student_doc.get("status")) not in TRANSFERRED_STATUSES:
            # Estudante ativo (ou qualquer outro status) continua sujeito ao vínculo
            # com sua escola atual, exatamente como antes.
            return await current_get(student_id, request)

        _assert_transfer_candidate_same_tenant(student_doc, current_user, request)

        # O #178 antecedeu a camada P0 de compatibilidade legada. Como esta leitura
        # autorizada não chama a rota anterior, aplicamos aqui a MESMA projeção
        # não persistente para não reintroduzir ResponseValidationError em cadastros
        # históricos (address string, certificado/comunidade legados).
        return normalize_legacy_student_doc(student_doc)

    @base_router.put("/{student_id}", response_model=Student)
    @wraps(current_update)
    async def destination_guarded_update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user.get("role") == "secretario":
            current_db = _db_for_user(db, sandbox_db, current_user)
            student_doc = await current_db.students.find_one(
                {"id": student_id},
                {"_id": 0, "id": 1, "school_id": 1, "status": 1, "mantenedora_id": 1},
            )
            if student_doc:
                # A origem transferida pode ser de outra escola, mas jamais de
                # outra mantenedora. Para status não transferido, a rota anterior
                # continua fazendo suas próprias verificações de origem.
                if _norm(student_doc.get("status")) in TRANSFERRED_STATUSES:
                    _assert_transfer_candidate_same_tenant(student_doc, current_user, request)

                await _assert_secretary_destination_access(
                    request=request,
                    current_user=current_user,
                    student_doc=student_doc,
                    student_update=student_update,
                )

        return await current_update(student_id, student_update, request)

    setattr(base_router, "_student_transfer_destination_access_installed", True)
    return base_router
