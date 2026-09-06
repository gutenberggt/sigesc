"""Política R2.0g.5 de paridade institucional da leitura de conteúdos.

A tela de Objetos de Conhecimento possui duas superfícies históricas no frontend:
`/professor/objetos-conhecimento` e `/admin/learning-objects`. A fonte canônica
(`content_entries`) não pode ficar invisível apenas porque o usuário autorizado
entrou pela superfície de gestão.

Este instalador amplia SOMENTE leitura. Escrita continua governada pelos papéis
já definidos em `WRITE_ROLES`/`MANAGEMENT_EDIT_ROLES`, ownership pedagógico,
escola e tenant.
"""
from __future__ import annotations


# Papéis que já possuem acesso institucional à consulta de Conteúdos e que
# precisam enxergar também registros canônicos DVD, não apenas o legado.
ADDITIONAL_INSTITUTIONAL_CONTENT_VIEW_ROLES = frozenset({
    "auxiliar_secretaria",
    "semed",
    "semed1",
    "semed2",
})


def _extend_roles(current, additional):
    return list(dict.fromkeys([*(current or []), *sorted(additional)]))


def install_content_institutional_visibility_policy(
    content_entries_mod,
    content_dvd_history_mod,
    diary_assignment_access_mod,
    diary_assignment_snapshot_access_mod,
):
    """Alinha readers canônicos com os perfis já autorizados na UI institucional.

    O patch é deliberadamente aditivo e read-only:
    - não altera `WRITE_ROLES`;
    - não altera `MANAGEMENT_EDIT_ROLES`;
    - não cria/migra/copias documentos;
    - não relaxa escola/tenant, que continuam validados pelos serviços canônicos.
    """
    additional = ADDITIONAL_INSTITUTIONAL_CONTENT_VIEW_ROLES

    content_entries_mod.VIEW_ROLES = _extend_roles(
        content_entries_mod.VIEW_ROLES,
        additional,
    )
    content_dvd_history_mod.VIEW_ROLES = _extend_roles(
        content_dvd_history_mod.VIEW_ROLES,
        additional,
    )

    management_view_roles = frozenset(
        set(diary_assignment_access_mod.MANAGEMENT_VIEW_ROLES) | set(additional)
    )
    diary_assignment_access_mod.MANAGEMENT_VIEW_ROLES = management_view_roles

    # diary_assignment_snapshot_access importa a constante por valor durante o
    # carregamento do módulo; atualizamos também o global efetivamente consultado
    # por authorize_assignment_snapshot_access().
    diary_assignment_snapshot_access_mod.MANAGEMENT_VIEW_ROLES = management_view_roles

    return {
        "content_view_roles": tuple(content_entries_mod.VIEW_ROLES),
        "dvd_history_view_roles": tuple(content_dvd_history_mod.VIEW_ROLES),
        "management_view_roles": tuple(sorted(management_view_roles)),
    }
