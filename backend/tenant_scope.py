"""
Multi-tenancy — Escopo por Mantenedora.

⚠️  LEIA ANTES DE MEXER EM NOVOS ROUTERS  ⚠️

Modelo:
  - `super_admin`  → enxerga tudo, pode criar mantenedoras, designar gerentes,
    alternar contexto ativo via header `X-Mantenedora-Id` ou query `?mantenedora_id=...`.
  - `gerente`      → admin limitado à sua própria mantenedora.
  - demais roles   → limitados à mantenedora do próprio usuário.

Helpers principais:
  - get_mantenedora_scope(user, request) → mantenedora_id ativa para a request.
  - apply_tenant_filter(query, user, request) → injeta filtro em queries MongoDB.
  - assert_same_tenant(doc, user, request) → 403 se o documento vier de outro tenant.

Coleções com escopo obrigatório (devem persistir `mantenedora_id` ao criar):
  schools, staff, students, classes, courses, enrollments, grades,
  learning_objects, calendar_events, calendario_letivo, payroll_items,
  school_assignments, teacher_assignments, mantenedora_documentos,
  announcements, pre_matriculas.

Coleções cross-tenant (sem `mantenedora_id`):
  mantenedoras (a própria tabela de tenants), users (o campo está no user),
  audit_logs (inclui `mantenedora_id` por registro mas não filtra na UI).

Quando criar novo endpoint/router:
  1. Ler `mantenedora_id` via get_mantenedora_scope().
  2. Na criação: inserir `mantenedora_id` no documento.
  3. Na leitura: incluir no filtro do find().
  4. Na atualização/deleção: validar via assert_same_tenant().
"""
from __future__ import annotations
from typing import Optional
from fastapi import Request, HTTPException

from tenant_audit import log_tenant_event

# Sentinela de tenant inexistente. Usada no FAIL-CLOSED: quando um usuário
# não-super_admin não possui mantenedora_id, o filtro passa a casar com NADA
# (em vez de remover o filtro e expor TODOS os tenants).
INVALID_TENANT_SENTINEL = "__INVALID_TENANT__"


def get_user_mantenedora_id(user: dict) -> Optional[str]:
    if not user:
        return None
    return user.get('mantenedora_id')


def is_super_admin(user: dict) -> bool:
    if not user:
        return False
    if user.get('role') == 'super_admin':
        return True
    roles = user.get('roles') or []
    return 'super_admin' in roles


def get_mantenedora_scope(user: dict, request: Optional[Request] = None) -> Optional[str]:
    """
    Retorna a mantenedora_id ativa para a request do usuário.
    - super_admin pode enviar X-Mantenedora-Id (header) ou ?mantenedora_id= (query)
      para atuar sob um tenant específico; caso contrário atua cross-tenant (None).
    - Qualquer outro usuário fica travado em sua própria mantenedora.
    """
    if is_super_admin(user):
        if request is not None:
            hdr = request.headers.get('X-Mantenedora-Id')
            if hdr:
                return hdr
            qp = request.query_params.get('mantenedora_id') if hasattr(request, 'query_params') else None
            if qp:
                return qp
        return None  # cross-tenant (enxerga tudo)
    return get_user_mantenedora_id(user)


def apply_tenant_filter(base_query: dict, user: dict, request: Optional[Request] = None) -> dict:
    """Retorna base_query acrescido de {'mantenedora_id': ...}.

    Regra de segurança (FAIL-CLOSED) — padrão de toda a plataforma:
      - super_admin SEM escopo (sem header/query) → cross-tenant (sem filtro).
      - super_admin COM escopo → filtra pela mantenedora ativa.
      - qualquer outro perfil → SEMPRE travado na própria mantenedora.
      - qualquer outro perfil SEM mantenedora_id → filtro IMPOSSÍVEL
        (`__INVALID_TENANT__`): sem tenant = NENHUM dado. Nunca todos.
    """
    q = dict(base_query)
    if is_super_admin(user):
        mid = get_mantenedora_scope(user, request)
        if mid is None:
            return q  # cross-tenant intencional (super_admin)
        q['mantenedora_id'] = mid
        return q

    # Não-super_admin: travado na própria mantenedora.
    mid = get_user_mantenedora_id(user)
    if not mid:
        # FAIL-CLOSED + auditoria: sem tenant → nenhum dado.
        log_tenant_event('missing_tenant', user, request)
        q['mantenedora_id'] = INVALID_TENANT_SENTINEL
        return q
    q['mantenedora_id'] = mid
    return q


def assert_same_tenant(doc: dict, user: dict, request: Optional[Request] = None) -> None:
    """Garante que o documento pertence ao tenant da request. 403 caso contrário."""
    if doc is None:
        return
    if is_super_admin(user) and get_mantenedora_scope(user, request) is None:
        return
    doc_mid = doc.get('mantenedora_id')
    user_mid = get_mantenedora_scope(user, request)
    if doc_mid and user_mid and doc_mid != user_mid:
        log_tenant_event('cross_tenant_attempt', user, request, requested_mantenedora=doc_mid)
        raise HTTPException(status_code=403, detail="Registro pertence a outra mantenedora")


async def resolve_tenant_id_for_create(db, user: dict, request: Optional[Request] = None,
                                        school_id: Optional[str] = None,
                                        class_id: Optional[str] = None,
                                        student_id: Optional[str] = None,
                                        staff_id: Optional[str] = None) -> Optional[str]:
    """
    Resolve o mantenedora_id a ser gravado em um novo documento.
    Ordem de preferência:
      1. scope ativo do usuário (header/query para super_admin, ou mantenedora_id próprio)
      2. school_id → schools.mantenedora_id
      3. class_id → classes.mantenedora_id
      4. student_id → students.mantenedora_id
      5. staff_id → staff.mantenedora_id
    Retorna None se não conseguir derivar (deixa a critério do caller decidir se é erro).
    """
    scope = get_mantenedora_scope(user, request)
    if scope:
        return scope
    # super_admin sem header → deriva do parent
    if school_id:
        doc = await db.schools.find_one({'id': school_id}, {'_id': 0, 'mantenedora_id': 1})
        if doc and doc.get('mantenedora_id'):
            return doc['mantenedora_id']
    if class_id:
        doc = await db.classes.find_one({'id': class_id}, {'_id': 0, 'mantenedora_id': 1})
        if doc and doc.get('mantenedora_id'):
            return doc['mantenedora_id']
    if student_id:
        doc = await db.students.find_one({'id': student_id}, {'_id': 0, 'mantenedora_id': 1})
        if doc and doc.get('mantenedora_id'):
            return doc['mantenedora_id']
    if staff_id:
        doc = await db.staff.find_one({'id': staff_id}, {'_id': 0, 'mantenedora_id': 1})
        if doc and doc.get('mantenedora_id'):
            return doc['mantenedora_id']
    return None


async def resolve_active_mantenedora(
    db,
    user: dict,
    request: Optional[Request] = None,
    *,
    fallback_to_first: bool = True,
) -> Optional[dict]:
    """Resolve o documento da mantenedora ativa para a request.

    Fonte única de verdade para qualquer endpoint que precise ler campos
    de configuração da mantenedora (limites de dependência, parâmetros
    pedagógicos, branding etc.). Substitui implementações pontuais como
    `routers/mantenedora.py::_resolve_active` e
    `routers/student_dependencies.py::_get_mantenedora_config`.

    Estratégia:
      1. `get_mantenedora_scope(user, request)` (considera header/query
         de super_admin + mantenedora_id do user).
      2. Se não encontrado e `fallback_to_first=True`, retorna a primeira
         mantenedora cadastrada (caso super_admin sem scope OU user legado
         sem `mantenedora_id`).
      3. Retorna `None` se não houver mantenedora cadastrada.

    Sempre exclui `_id` da projection (BSON ObjectId).
    """
    scope_id = get_mantenedora_scope(user, request)
    if scope_id:
        doc = await db.mantenedoras.find_one({"id": scope_id}, {"_id": 0})
        if doc:
            return doc
        # Escopo aponta para tenant inexistente → não vaza para outro tenant.
        return None
    # scope_id None:
    #  - super_admin sem header/query → pode usar fallback (cross-tenant).
    #  - qualquer outro perfil → NUNCA cair na "primeira mantenedora" (vazamento).
    #    Tenant ausente para não-super_admin = erro/sem dados.
    if not is_super_admin(user):
        log_tenant_event('missing_tenant', user, request, extra={'context': 'resolve_active_mantenedora'})
        return None
    if fallback_to_first:
        return await db.mantenedoras.find_one({}, {"_id": 0})
    return None
