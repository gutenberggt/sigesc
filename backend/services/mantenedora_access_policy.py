"""Política canônica de ativação, manutenção e acesso por Mantenedora.

Este módulo é deliberadamente puro: não acessa banco, request ou autenticação.
A mesma regra é consumida pelo tenant_scope (enforcement global) e pelo
control-plane da mantenedora (configuração/preview), evitando divergência.

Invariantes de segurança:
- tenant desativado é fail-closed por padrão;
- a exceção por papel remove apenas a trava institucional, nunca o RBAC;
- apenas o papel ativo da sessão é considerado para a exceção;
- super_admin não recebe bypass operacional implícito em tenant desativado;
- manutenção é um estado independente da disponibilidade institucional;
- em mantenedora ativa sob manutenção, somente super_admin mantém acesso
  operacional; os demais usuários são bloqueados antes do RBAC.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any


INACTIVE_ACCESS_ROLES_FIELD = "acesso_desativado_roles"
MAINTENANCE_MODE_FIELD = "maintenance_mode"

# Papéis que podem ser explicitamente liberados enquanto a mantenedora estiver
# desativada. super_admin é propositalmente ausente: seu acesso administrativo
# é tratado somente pelo CONTROL PLANE explícito no tenant_scope. Assim, uma
# mantenedora inativa continua bloqueada para o super_admin em rotas operacionais.
CONFIGURABLE_INACTIVE_ACCESS_ROLES = (
    "gerente",
    "admin",
    "admin_teste",
    "secretario",
    "diretor",
    "coordenador",
    "apoio_pedagogico",
    "auxiliar_secretaria",
    "professor",
    "semed",
    "semed1",
    "semed2",
    "semed3",
    "ass_social",
    "ass_social_2",
    "agente_vacinas",
    "aluno",  # nomenclature-allow: identificador técnico legado da role; UI usa Estudante
    "responsavel",
)

INACTIVE_ACCESS_ROLE_LABELS = {
    "gerente": "Gerente",
    "admin": "Administrador",
    "admin_teste": "Administrador de Teste",
    "secretario": "Secretário(a)",
    "diretor": "Diretor(a)",
    "coordenador": "Coordenador(a)",
    "apoio_pedagogico": "Apoio Pedagógico",
    "auxiliar_secretaria": "Auxiliar de Secretaria",
    "professor": "Professor(a)",
    "semed": "SEMED",
    "semed1": "Tutor",
    "semed2": "Analista",
    "semed3": "Administração",
    "ass_social": "Assistente Social",
    "ass_social_2": "Assistente Social 2",
    "agente_vacinas": "Agente de Vacinas",
    "aluno": "Estudante",  # nomenclature-allow: chave técnica legada; rótulo institucional é Estudante
    "responsavel": "Responsável(is)",
}


def is_super_admin(user: Mapping[str, Any] | None) -> bool:
    if not user:
        return False
    if user.get("role") == "super_admin":
        return True
    return "super_admin" in (user.get("roles") or [])


def is_tenant_active(doc: Mapping[str, Any] | None) -> bool:
    """Compatibilidade com os marcadores históricos ``ativo``, ``ativa`` e ``status``."""
    if not doc:
        return False
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


def is_tenant_in_maintenance(doc: Mapping[str, Any] | None) -> bool:
    """Retorna o estado canônico de manutenção, com default seguro ``False``.

    O campo é propositalmente independente de ``ativo``/``status``: suspensão
    institucional e manutenção técnica possuem semânticas e políticas distintas.
    """
    return bool(doc and doc.get(MAINTENANCE_MODE_FIELD) is True)


def normalize_allowed_roles(values: Iterable[Any] | None) -> list[str]:
    allowed = set(CONFIGURABLE_INACTIVE_ACCESS_ROLES)
    normalized = {
        str(value).strip()
        for value in (values or [])
        if str(value).strip() in allowed
    }
    return sorted(normalized)


def inactive_allowed_roles(doc: Mapping[str, Any] | None) -> list[str]:
    if not doc:
        return []
    return normalize_allowed_roles(doc.get(INACTIVE_ACCESS_ROLES_FIELD) or [])


def can_access_tenant(doc: Mapping[str, Any] | None, user: Mapping[str, Any] | None) -> bool:
    """Decide somente a trava de DISPONIBILIDADE institucional da mantenedora.

    - mantenedora ativa: esta trava está liberada; manutenção é avaliada depois,
      de forma independente, pelo ``tenant_scope``;
    - mantenedora desativada: somente o papel ATIVO da sessão pode atravessar
      quando estiver explicitamente assinalado na configuração;
    - super_admin não recebe bypass operacional implícito. Seu acesso de gestão
      a tenant inativo existe somente em rotas de CONTROL PLANE explicitamente
      allowlisted no ``tenant_scope``.

    O RBAC normal continua sendo aplicado depois desta decisão.
    """
    if is_tenant_active(doc):
        return True
    role = str((user or {}).get("role") or "").strip()
    return bool(role and role in inactive_allowed_roles(doc))
