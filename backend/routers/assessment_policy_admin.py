"""Administração assistida da Assessment Policy v1.

Este router é deliberadamente separado do runtime oficial de Notas.
Na Sprint 007 NÃO existe endpoint de publish/cutover.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from assessment_policy.assisted_config import (
    AssistedPolicyConfiguration,
    LegacyFieldMappingConfig,
    preview_assisted_configuration,
)
from assessment_policy.exceptions import AssessmentPolicyError
from assessment_policy.pilot_runner import run_candidate_dry_run
from assessment_policy.registry import AssessmentPolicyRegistry
from assessment_policy.repository import AssessmentPolicyRepository
from assessment_policy.models import PolicyStatus
from auth_middleware import AuthMiddleware
from tenant_scope import is_super_admin, resolve_active_mantenedora


router = APIRouter(prefix="/assessment-policy-admin", tags=["Assessment Policy Admin"])


class CandidatePilotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    legacy_mapping: LegacyFieldMappingConfig
    reference_date: date
    class_ids: Optional[List[str]] = None
    tolerance: str = "0.01"
    limit: Optional[int] = Field(default=None, ge=1, le=5000)


def _raise_policy_http(exc: AssessmentPolicyError) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    del audit_service, kwargs

    def get_db_for_user(user: dict):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db is not None else db
        return db

    async def require_admin_context(request: Request):
        current_user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(current_user):
            raise HTTPException(
                status_code=403,
                detail="A configuração da política avaliativa exige super_admin nesta fase.",
            )
        current_db = get_db_for_user(current_user)
        mantenedora = await resolve_active_mantenedora(
            current_db,
            current_user,
            request,
            fallback_to_first=True,
        )
        if not mantenedora or not mantenedora.get("id"):
            raise HTTPException(status_code=404, detail="Mantenedora ativa não encontrada")
        return current_user, current_db, mantenedora, str(mantenedora["id"])

    @router.get("/overview")
    async def overview(request: Request, academic_year: Optional[int] = None):
        _, current_db, mantenedora, tenant_id = await require_admin_context(request)
        repository = AssessmentPolicyRepository(current_db)
        policies = await repository.list_by_tenant(
            tenant_id,
            academic_year=academic_year,
        )
        return {
            "mantenedora": {
                "id": tenant_id,
                "nome": mantenedora.get("nome"),
            },
            "legacy_reference": {
                "media_aprovacao": mantenedora.get("media_aprovacao"),
                "frequencia_minima": mantenedora.get("frequencia_minima"),
                "aprovacao_com_dependencia": mantenedora.get("aprovacao_com_dependencia"),
                "max_componentes_dependencia": mantenedora.get("max_componentes_dependencia"),
                "cursar_apenas_dependencia": mantenedora.get("cursar_apenas_dependencia"),
                "qtd_componentes_apenas_dependencia": mantenedora.get("qtd_componentes_apenas_dependencia"),
                "reference_only": True,
            },
            "source_of_truth": "assessment_policies",
            "publish_available": False,
            "cutover_available": False,
            "policies": [
                {
                    "id": item.id,
                    "policy_key": item.policy_key,
                    "version": item.version,
                    "name": item.name,
                    "status": item.status.value,
                    "academic_year": item.academic_year,
                    "effective_from": item.effective_from,
                    "effective_until": item.effective_until,
                    "scope": item.scope.model_dump(mode="json"),
                    "rule_hash": item.rule_hash,
                    "revision": item.revision,
                }
                for item in policies
            ],
        }

    @router.post("/preview")
    async def preview(configuration: AssistedPolicyConfiguration, request: Request):
        _, _, _, tenant_id = await require_admin_context(request)
        if configuration.policy.mantenedora_id != tenant_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ASSESSMENT_POLICY_TENANT_MISMATCH",
                    "message": "Policy candidata não pertence à mantenedora ativa.",
                },
            )
        return preview_assisted_configuration(configuration).model_dump(mode="json")

    @router.post("/drafts")
    async def create_draft(configuration: AssistedPolicyConfiguration, request: Request):
        current_user, current_db, _, tenant_id = await require_admin_context(request)
        preview = preview_assisted_configuration(configuration)
        if configuration.policy.mantenedora_id != tenant_id:
            raise HTTPException(status_code=422, detail="Policy pertence a outra mantenedora")
        if not preview.can_save_draft:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ASSESSMENT_ASSISTED_DRAFT_NOT_SAVABLE",
                    "issues": [item.model_dump(mode="json") for item in preview.issues],
                },
            )
        registry = AssessmentPolicyRegistry(AssessmentPolicyRepository(current_db))
        try:
            created = await registry.create_draft(
                tenant_id,
                configuration.policy,
                actor_id=str(current_user.get("id") or "unknown"),
            )
        except AssessmentPolicyError as exc:
            _raise_policy_http(exc)
        return created.model_dump(mode="json")

    @router.put("/drafts/{policy_id}")
    async def save_draft(
        policy_id: str,
        configuration: AssistedPolicyConfiguration,
        request: Request,
    ):
        current_user, current_db, _, tenant_id = await require_admin_context(request)
        if configuration.policy.id != policy_id:
            raise HTTPException(status_code=422, detail="policy_id da URL difere do payload")
        if configuration.policy.mantenedora_id != tenant_id:
            raise HTTPException(status_code=422, detail="Policy pertence a outra mantenedora")
        preview = preview_assisted_configuration(configuration)
        if not preview.can_save_draft:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ASSESSMENT_ASSISTED_DRAFT_NOT_SAVABLE",
                    "issues": [item.model_dump(mode="json") for item in preview.issues],
                },
            )
        registry = AssessmentPolicyRegistry(AssessmentPolicyRepository(current_db))
        try:
            saved = await registry.save_draft(
                tenant_id,
                configuration.policy,
                actor_id=str(current_user.get("id") or "unknown"),
            )
        except AssessmentPolicyError as exc:
            _raise_policy_http(exc)
        return saved.model_dump(mode="json")

    @router.post("/drafts/{policy_id}/validate")
    async def validate_draft(policy_id: str, request: Request):
        current_user, current_db, _, tenant_id = await require_admin_context(request)
        registry = AssessmentPolicyRegistry(AssessmentPolicyRepository(current_db))
        try:
            validated, report = await registry.validate_draft(
                tenant_id,
                policy_id,
                actor_id=str(current_user.get("id") or "unknown"),
            )
        except AssessmentPolicyError as exc:
            _raise_policy_http(exc)
        return {
            "policy": validated.model_dump(mode="json"),
            "validation": report.model_dump(mode="json"),
            "publish_available": False,
        }

    @router.post("/pilot")
    async def pilot(payload: CandidatePilotRequest, request: Request):
        _, current_db, _, tenant_id = await require_admin_context(request)
        repository = AssessmentPolicyRepository(current_db)
        policy = await repository.get(payload.policy_id, tenant_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy candidata não encontrada")
        if policy.status not in {PolicyStatus.DRAFT, PolicyStatus.VALIDATED}:
            raise HTTPException(
                status_code=422,
                detail="Piloto desta sprint aceita apenas draft/validated; published usa o Shadow Runner oficial.",
            )
        try:
            report = await run_candidate_dry_run(
                current_db,
                policy=policy,
                mapping=payload.legacy_mapping.to_runtime(),
                reference_date=payload.reference_date,
                class_ids=payload.class_ids,
                tolerance=payload.tolerance,
                limit=payload.limit,
            )
        except AssessmentPolicyError as exc:
            _raise_policy_http(exc)
        return asdict(report)

    return router


def install_assessment_policy_admin_setup(mantenedora_module) -> None:
    """Acopla este router ao módulo de Mantenedora sem tocar em server.py.

    O `server.py` já configura e inclui `mantenedora_mod.router`. Envolver o
    setup existente mantém esse bootstrap intacto e adiciona as rotas da Sprint
    007 somente quando a Mantenedora é configurada.
    """

    if getattr(mantenedora_module, "_assessment_policy_admin_setup_installed", False):
        return

    original_setup = mantenedora_module.setup_router

    def wrapped_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        result = original_setup(db, audit_service, sandbox_db, **kwargs)
        setup_router(db, audit_service, sandbox_db, **kwargs)
        if not getattr(mantenedora_module, "_assessment_policy_admin_routes_included", False):
            mantenedora_module.router.include_router(router)
            mantenedora_module._assessment_policy_admin_routes_included = True
        return result

    mantenedora_module.setup_router = wrapped_setup
    mantenedora_module._assessment_policy_admin_setup_installed = True
