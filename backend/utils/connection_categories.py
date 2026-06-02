"""Mapeamento CENTRALIZADO de role -> categoria de conexão.

Usado na página "Usuários Online" para subdividir as conexões registradas
(logins bem-sucedidos) por categoria de perfil.

➜ Para adicionar uma role a uma categoria (ex.: uma NOVA role de Saúde),
  basta incluí-la no conjunto correspondente abaixo. Nenhuma outra mudança
  de código é necessária (o endpoint e o frontend consomem este mapa).

Qualquer role não listada cai automaticamente em `DEFAULT_CONNECTION_CATEGORY`
("administrativas").
"""

# Categoria -> conjunto de roles que pertencem a ela.
CONNECTION_CATEGORY_ROLES = {
    "professores": {"professor"},
    "alunos": {"aluno"},
    "assistencia_social": {"ass_social", "ass_social_2"},
    # Saúde: vacinas e demais agentes de saúde (adicione novas roles aqui).
    "saude": {"agente_vacinas"},
}

# Categoria padrão para todas as roles não mapeadas acima.
DEFAULT_CONNECTION_CATEGORY = "administrativas"

# Ordem canônica das categorias (inclui a padrão por último).
CONNECTION_CATEGORIES = list(CONNECTION_CATEGORY_ROLES.keys()) + [DEFAULT_CONNECTION_CATEGORY]


def categorize_role(role: str) -> str:
    """Retorna a categoria de conexão de uma role (case-insensitive)."""
    r = (role or "").strip().lower()
    for category, roles in CONNECTION_CATEGORY_ROLES.items():
        if r in roles:
            return category
    return DEFAULT_CONNECTION_CATEGORY


def empty_category_counts() -> dict:
    """Dict zerado com todas as categorias na ordem canônica."""
    return {c: 0 for c in CONNECTION_CATEGORIES}
