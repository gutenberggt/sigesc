"""AEE v2 Fase 2 — API de persistência sidecar e versionamento.

O adapter mantém o router AEE legado intacto e adiciona apenas endpoints v2.
Nenhum endpoint deste arquivo grava em ``planos_aee``.
"""

from __future__ import annotations

import logging
from typing import Iterable

from fastapi import HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from aee_v2.repository import (
    AEEV2Conflict,
    AEEV2IntegrityError,
    AEEV2NotFound,
    AEEV2Repository,
    AEEV2ValidationError,
)
from aee_v2.versioning import (
    AEEV2ActivationRequest,
    AEEV2PAEEUpdate,
    AEEV2PEIUpdate,
    AEEV2ScheduleUpdate,
    AEEV2State,
    AEEV2StudyCaseUpdate,
)


logger = logging.getLogger(__name__)


class AEEV2StartRevisionRequest(BaseModel):
    expected_head_revision: int = Field(ge=1)


async def _require_role(request: Request, roles: Iterable[str]) -> dict:
    user = await AuthMiddleware.get_current_user(request)
    if user.get("role") not in set(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado ao módulo AEE",
        )
    return user


async def _load_plan_for_access(
    db,
    *,
    plano_id: str,
    current_user: dict,
    write: bool,
    write_roles: Iterable[str],
    access_roles: Iterable[str],
) -> dict:
    allowed = set(write_roles if write else access_roles)
    if current_user.get("role") not in allowed:
        detail = (
            "Seu perfil permite apenas visualização no módulo AEE"
            if write
            else "Acesso não autorizado ao módulo AEE"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    plano = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
    if not plano:
        raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

    # Mantém para professor o mesmo princípio de escopo já usado na listagem AEE:
    # responsável pedagógico ou criador histórico. Não amplia acesso.
    if current_user.get("role") == "professor":
        uid = current_user.get("id")
        if uid not in {plano.get("professor_aee_id"), plano.get("created_by")}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este Plano AEE não está vinculado ao professor autenticado.",
            )
    return plano


def _translate_repository_error(exc: Exception):
    if isinstance(exc, AEEV2NotFound):
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": str(exc)}) from exc
    if isinstance(exc, AEEV2ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "blockers": exc.blockers},
        ) from exc
    if isinstance(exc, (AEEV2Conflict, AEEV2IntegrityError)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    raise exc


async def _audit_sidecar(
    audit_service,
    *,
    action: str,
    request: Request,
    user: dict,
    plano: dict,
    state: AEEV2State,
    description: str,
):
    """Auditoria secundária; snapshots continuam sendo a trilha imutável primária."""
    try:
        head = state.head.model_dump(mode="json") if state.head else None
        await audit_service.log(
            action=action,
            collection="aee_dossier_v2_snapshots",
            user=user,
            request=request,
            document_id=plano.get("id"),
            description=description,
            school_id=plano.get("school_id"),
            academic_year=plano.get("academic_year"),
            old_value=None,
            new_value={
                "legacy_plano_id": plano.get("id"),
                "head": head,
            },
        )
    except Exception as exc:  # pragma: no cover - infraestrutura secundária
        logger.warning("Falha ao duplicar auditoria AEE v2 no audit_service: %s", exc)


def install_aee_v2_persistence(
    base_router,
    db,
    audit_service,
    *,
    access_roles: Iterable[str],
    write_roles: Iterable[str],
):
    if getattr(base_router, "_aee_v2_persistence_installed", False):
        return base_router

    repo = AEEV2Repository(db)

    @base_router.get(
        "/planos/{plano_id}/dossie-v2/state",
        response_model=AEEV2State,
    )
    async def get_aee_v2_state(plano_id: str, request: Request):
        current_user = await _require_role(request, access_roles)
        await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=False,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            return await repo.get_state(plano_id)
        except Exception as exc:
            _translate_repository_error(exc)

    @base_router.post(
        "/planos/{plano_id}/dossie-v2/bootstrap",
        response_model=AEEV2State,
        status_code=status.HTTP_201_CREATED,
    )
    async def bootstrap_aee_v2(plano_id: str, request: Request):
        current_user = await _require_role(request, write_roles)
        plano = await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=True,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            state = await repo.bootstrap(plano, actor=current_user)
        except Exception as exc:
            _translate_repository_error(exc)
        await _audit_sidecar(
            audit_service,
            action="create",
            request=request,
            user=current_user,
            plano=plano,
            state=state,
            description="Inicializou sidecar versionado do Dossiê AEE v2",
        )
        return state

    @base_router.get("/planos/{plano_id}/dossie-v2/snapshots")
    async def list_aee_v2_snapshots(
        plano_id: str,
        request: Request,
        limit: int = Query(100, ge=1, le=500),
    ):
        current_user = await _require_role(request, access_roles)
        await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=False,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        return {"items": await repo.list_snapshots(plano_id, limit=limit)}

    @base_router.get("/planos/{plano_id}/dossie-v2/activation-validation")
    async def validate_aee_v2_activation(plano_id: str, request: Request):
        current_user = await _require_role(request, access_roles)
        await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=False,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            return await repo.validate_working_for_activation(plano_id)
        except Exception as exc:
            _translate_repository_error(exc)

    async def _save_section(
        *,
        plano_id: str,
        request: Request,
        payload,
        section_name: str,
    ):
        current_user = await _require_role(request, write_roles)
        plano = await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=True,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            state = await repo.save_section(
                plano_id,
                section_name=section_name,
                section=payload.section,
                expected_head_revision=payload.expected_head_revision,
                expected_working_snapshot_id=payload.expected_working_snapshot_id,
                actor=current_user,
            )
        except Exception as exc:
            _translate_repository_error(exc)
        await _audit_sidecar(
            audit_service,
            action="update",
            request=request,
            user=current_user,
            plano=plano,
            state=state,
            description=f"Atualizou seção {section_name} do Dossiê AEE v2",
        )
        return state

    @base_router.patch(
        "/planos/{plano_id}/dossie-v2/sections/study-case",
        response_model=AEEV2State,
    )
    async def update_aee_v2_study_case(
        plano_id: str,
        payload: AEEV2StudyCaseUpdate,
        request: Request,
    ):
        return await _save_section(
            plano_id=plano_id,
            request=request,
            payload=payload,
            section_name="study_case",
        )

    @base_router.patch(
        "/planos/{plano_id}/dossie-v2/sections/paee",
        response_model=AEEV2State,
    )
    async def update_aee_v2_paee(
        plano_id: str,
        payload: AEEV2PAEEUpdate,
        request: Request,
    ):
        return await _save_section(
            plano_id=plano_id,
            request=request,
            payload=payload,
            section_name="paee",
        )

    @base_router.patch(
        "/planos/{plano_id}/dossie-v2/sections/pei",
        response_model=AEEV2State,
    )
    async def update_aee_v2_pei(
        plano_id: str,
        payload: AEEV2PEIUpdate,
        request: Request,
    ):
        return await _save_section(
            plano_id=plano_id,
            request=request,
            payload=payload,
            section_name="pei",
        )

    @base_router.patch(
        "/planos/{plano_id}/dossie-v2/sections/schedule",
        response_model=AEEV2State,
    )
    async def update_aee_v2_schedule(
        plano_id: str,
        payload: AEEV2ScheduleUpdate,
        request: Request,
    ):
        return await _save_section(
            plano_id=plano_id,
            request=request,
            payload=payload,
            section_name="schedule",
        )

    @base_router.post(
        "/planos/{plano_id}/dossie-v2/revisions",
        response_model=AEEV2State,
        status_code=status.HTTP_201_CREATED,
    )
    async def start_aee_v2_revision(
        plano_id: str,
        payload: AEEV2StartRevisionRequest,
        request: Request,
    ):
        current_user = await _require_role(request, write_roles)
        plano = await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=True,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            state = await repo.start_revision(
                plano_id,
                expected_head_revision=payload.expected_head_revision,
                actor=current_user,
            )
        except Exception as exc:
            _translate_repository_error(exc)
        await _audit_sidecar(
            audit_service,
            action="create",
            request=request,
            user=current_user,
            plano=plano,
            state=state,
            description="Abriu nova versão documental do Dossiê AEE v2",
        )
        return state

    @base_router.post(
        "/planos/{plano_id}/dossie-v2/activate",
        response_model=AEEV2State,
    )
    async def activate_aee_v2(
        plano_id: str,
        payload: AEEV2ActivationRequest,
        request: Request,
    ):
        current_user = await _require_role(request, write_roles)
        plano = await _load_plan_for_access(
            db,
            plano_id=plano_id,
            current_user=current_user,
            write=True,
            write_roles=write_roles,
            access_roles=access_roles,
        )
        try:
            state = await repo.activate(
                plano_id,
                expected_head_revision=payload.expected_head_revision,
                expected_working_snapshot_id=payload.expected_working_snapshot_id,
                actor=current_user,
            )
        except Exception as exc:
            _translate_repository_error(exc)
        await _audit_sidecar(
            audit_service,
            action="publish",
            request=request,
            user=current_user,
            plano=plano,
            state=state,
            description="Tornou vigente uma versão do Dossiê AEE v2",
        )
        return state

    setattr(base_router, "_aee_v2_persistence_installed", True)
    return base_router


def install_aee_v2_persistence_setup(aee_module):
    """Encadeia a Fase 2 depois das camadas P0 e Fase 1."""
    if getattr(aee_module, "_aee_v2_persistence_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router
    access_roles = tuple(getattr(aee_module, "ROLES_AEE", ()))
    write_roles = tuple(getattr(aee_module, "ROLES_AEE_WRITE", ()))

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_persistence(
            configured,
            db,
            audit_service,
            access_roles=access_roles,
            write_roles=write_roles,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_persistence_setup_installed = True
