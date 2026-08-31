"""
Multi-tenancy — escopo canônico por Mantenedora.

MT-1 (31/08/2026):
- o plano operacional exige exatamente uma mantenedora ativa;
- `super_admin` pode alternar a mantenedora ativa, mas não opera em modo
  "Todas" nas rotas de negócio;
- cross-tenant permanece permitido somente em uma allowlist explícita de
  control plane;
- ausência, tenant inexistente/inativo e documento de domínio sem tenant
  falham fechados.

Helpers principais:
- get_mantenedora_scope(user, request): ID efetivo ou sentinela fail-closed.
- resolve_operational_tenant_context(db, user, request): SSoT assíncrona que
  valida existência/status da mantenedora e registra o contexto na request.
- apply_tenant_filter(query, user, request): injeta o tenant em queries.
- assert_same_tenant(doc, user, request): rejeita documento sem tenant ou de
  outro tenant em rotas operacionais.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from tenant_audit import log_tenant_event


INVALID_TENANT_SENTINEL = "__INVALID_TENANT__"

# Cross-tenant é permitido somente nestes endpoints de CONTROL PLANE e somente
# para super_admin. Prefixos sem /api existem apenas para testes/unitários.
CONTROL_PLANE_PATH_PREFIXES = (
    "/api/mantenedoras",
    "/mantenedoras",
    "/api/tenant",
    "/tenant",
)

# Endpoints de sessão/identidade que precisam continuar acessíveis antes da
# seleção da mantenedora (login bootstrap, perfil da sessão, logout e CSRF).
# `register` NÃO está aqui: criação de identidade pertence ao plano operacional
# quando houver usuário autenticado e será endurecida definitivamente na MT-2.
SESSION_PLANE_PATHS = frozenset(
    {
        "/api/auth/me",
        "/auth/me",
        "/api/auth/permissions",
        "/auth/permissions",
        "/api/auth/logout",
        "/auth/logout",
        "/api/auth/logout-all",
        "/auth/logout-all",
        "/api/auth/csrf-token",
        "/auth/csrf-token",
        "/api/auth/change-account",
        "/auth/change-account",
        "/api/auth/resend-email-change",
        "/auth/resend-email-change",
    }
)


@dataclass(frozen=True)
class OperationalTenantContext:
    """Contexto operacional já validado para uma request."""

    id: str
    name: Optional[str]
    source: str
    legacy_status_implicit: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "legacy_status_implicit": self.legacy_status_implicit,
        }


def get_user_mantenedora_id(user: dict) -> Optional[str]:
    if not user:
        return None
    value = user.get("mantenedora_id")
    return str(value).strip() if value else None


def is_super_admin(user: dict) -> bool:
    if not user:
        return False
    if user.get("role") == "super_admin":
        return True
    roles = user.get("roles") or []
    return "super_admin" in roles


def _request_path(request: Optional[Request]) -> str:
    if request is None:
        return ""
    try:
        return str(request.url.path or "")
    except Exception:
        return str((request.scope or {}).get("path") or "")


def _matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def is_control_plane_request(user: dict, request: Optional[Request]) -> bool:
    """Retorna True apenas para super_admin em endpoint explicitamente global."""
    if not is_super_admin(user):
        return False
    path = _request_path(request)
    return any(_matches_prefix(path, prefix) for prefix in CONTROL_PLANE_PATH_PREFIXES)


def is_session_plane_request(request: Optional[Request]) -> bool:
    return _request_path(request) in SESSION_PLANE_PATHS


def requires_operational_tenant_context(
    user: dict,
    request: Optional[Request],
) -> bool:
    """Define se a request autenticada deve possuir tenant operacional."""
    if is_session_plane_request(request):
        return False
    if is_control_plane_request(user, request):
        return False
    return True


def _selected_superadmin_tenant(
    request: Optional[Request],
) -> tuple[Optional[str], Optional[str]]:
    if request is None:
        return None, None
    hdr = (request.headers.get("X-Mantenedora-Id") or "").strip()
    if hdr:
        return hdr, "header"
    qp = None
    try:
        qp = (request.query_params.get("mantenedora_id") or "").strip()
    except Exception:
        qp = None
    if qp:
        return qp, "query"
    return None, None


def get_mantenedora_scope(
    user: dict,
    request: Optional[Request] = None,
) -> Optional[str]:
    """Resolve o ID de tenant sem consultar o banco.

    Semântica MT-1:
    - super_admin com seleção explícita -> tenant selecionado;
    - super_admin sem seleção em CONTROL PLANE -> None (cross-tenant explícito);
    - qualquer rota operacional sem tenant -> sentinela impossível;
    - não-super_admin ignora qualquer header de override e usa apenas seu tenant.
    """
    if is_super_admin(user):
        selected, _source = _selected_superadmin_tenant(request)
        if selected:
            return selected
        if is_control_plane_request(user, request):
            return None
        log_tenant_event(
            "missing_tenant",
            user,
            request,
            extra={"context": "operational_super_admin"},
        )
        return INVALID_TENANT_SENTINEL

    mid = get_user_mantenedora_id(user)
    if mid:
        return mid

    log_tenant_event(
        "missing_tenant",
        user,
        request,
        extra={"context": "operational_user"},
    )
    return INVALID_TENANT_SENTINEL


def _tenant_is_active(doc: dict) -> bool:
    """Compatibilidade com schemas `ativo`, `ativa` e `status`.

    Registros legados sem marcador de status continuam operáveis nesta fase,
    mas o contexto registra `legacy_status_implicit=True` para rastreabilidade.
    """
    if doc.get("ativo") is False or doc.get("ativa") is False:
        return False
    status_value = str(doc.get("status") or "").strip().lower()
    if status_value in {
        "inactive",
        "inativo",
        "disabled",
        "desativado",
        "desativada",
    }:
        return False
    return True


async def resolve_operational_tenant_context(
    db,
    user: dict,
    request: Optional[Request] = None,
) -> OperationalTenantContext:
    """SSoT do tenant operacional: exige tenant existente e ativo.

    O resultado é cacheado em `request.state` para que múltiplas verificações
    no mesmo ciclo HTTP não repitam consulta ao MongoDB.
    """
    cached = None
    if request is not None:
        cached = getattr(request.state, "operational_tenant_context", None)
    if isinstance(cached, OperationalTenantContext):
        return cached

    mid = get_mantenedora_scope(user, request)
    if not mid or mid == INVALID_TENANT_SENTINEL:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TENANT_CONTEXT_REQUIRED",
                "message": (
                    "Selecione uma mantenedora ativa antes de acessar "
                    "módulos operacionais."
                ),
            },
        )

    doc = await db.mantenedoras.find_one({"id": mid}, {"_id": 0})
    if not doc:
        log_tenant_event(
            "invalid_tenant",
            user,
            request,
            requested_mantenedora=mid,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TENANT_CONTEXT_INVALID",
                "message": "A mantenedora selecionada não existe.",
            },
        )

    if not _tenant_is_active(doc):
        log_tenant_event(
            "inactive_tenant",
            user,
            request,
            requested_mantenedora=mid,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "TENANT_INACTIVE",
                "message": "A mantenedora selecionada está inativa.",
            },
        )

    _selected, source = _selected_superadmin_tenant(request)
    if not is_super_admin(user):
        source = "user"

    legacy_status_implicit = not any(
        key in doc for key in ("ativo", "ativa", "status")
    )
    ctx = OperationalTenantContext(
        id=mid,
        name=doc.get("nome") or doc.get("name"),
        source=source or "user",
        legacy_status_implicit=legacy_status_implicit,
    )
    if request is not None:
        request.state.operational_tenant_context = ctx
        request.state.active_mantenedora_id = ctx.id
    return ctx


def apply_tenant_filter(
    base_query: dict,
    user: dict,
    request: Optional[Request] = None,
) -> dict:
    """Injeta tenant em query MongoDB; ausência operacional casa com nada."""
    q = dict(base_query)
    mid = get_mantenedora_scope(user, request)

    # Somente CONTROL PLANE explícito de super_admin pode permanecer sem filtro.
    if mid is None and is_control_plane_request(user, request):
        return q

    # Mantém o contrato estático pré-existente dos guards F2.6 e aplica a
    # sentinela fail-closed quando a resolução operacional não produz tenant.
    if mid:
        q['mantenedora_id'] = mid
    else:
        q['mantenedora_id'] = INVALID_TENANT_SENTINEL
    return q


def assert_same_tenant(
    doc: dict,
    user: dict,
    request: Optional[Request] = None,
) -> None:
    """Rejeita documento sem tenant ou de tenant divergente (fail-closed)."""
    if doc is None:
        return

    user_mid = get_mantenedora_scope(user, request)
    if user_mid is None and is_control_plane_request(user, request):
        return

    if not user_mid or user_mid == INVALID_TENANT_SENTINEL:
        raise HTTPException(
            status_code=409,
            detail="Mantenedora operacional não selecionada",
        )

    doc_mid = doc.get("mantenedora_id")
    if not doc_mid:
        log_tenant_event(
            "missing_document_tenant",
            user,
            request,
            extra={"document_id": doc.get("id")},
        )
        raise HTTPException(
            status_code=403,
            detail="Registro sem mantenedora_id; saneamento governado é necessário.",
        )

    if str(doc_mid) != str(user_mid):
        log_tenant_event(
            "cross_tenant_attempt",
            user,
            request,
            requested_mantenedora=str(doc_mid),
        )
        raise HTTPException(
            status_code=403,
            detail="Registro pertence a outra mantenedora",
        )


async def resolve_tenant_id_for_create(
    db,
    user: dict,
    request: Optional[Request] = None,
    school_id: Optional[str] = None,
    class_id: Optional[str] = None,
    student_id: Optional[str] = None,
    staff_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve o tenant de criação a partir do contexto operacional.

    MT-1 remove a antiga derivação implícita por parent para super_admin sem
    seleção. Validação completa dos parent IDs pertence à MT-2.
    """
    _ = (db, school_id, class_id, student_id, staff_id)
    scope = get_mantenedora_scope(user, request)
    if scope and scope != INVALID_TENANT_SENTINEL:
        return scope
    return None


async def resolve_active_mantenedora(
    db,
    user: dict,
    request: Optional[Request] = None,
    *,
    fallback_to_first: bool = False,
) -> Optional[dict]:
    """Resolve a mantenedora ativa sem fallback operacional silencioso.

    `fallback_to_first` só é honrado em CONTROL PLANE explícito; em rotas de
    negócio, ausência de tenant gera erro via OperationalTenantContext.
    """
    if (
        fallback_to_first
        and is_control_plane_request(user, request)
        and get_mantenedora_scope(user, request) is None
    ):
        doc = await db.mantenedoras.find_one({}, {"_id": 0})
        if doc and _tenant_is_active(doc):
            return doc
        return None

    ctx = await resolve_operational_tenant_context(db, user, request)
    return await db.mantenedoras.find_one({"id": ctx.id}, {"_id": 0})
