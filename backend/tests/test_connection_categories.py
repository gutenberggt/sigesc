"""Regressão do mapeamento centralizado role -> categoria de conexão."""
from utils.connection_categories import (
    categorize_role,
    empty_category_counts,
    CONNECTION_CATEGORIES,
    DEFAULT_CONNECTION_CATEGORY,
)


def test_known_roles_map_to_expected_categories():
    assert categorize_role("professor") == "professores"
    assert categorize_role("aluno") == "alunos"
    assert categorize_role("ass_social") == "assistencia_social"
    assert categorize_role("ass_social_2") == "assistencia_social"
    assert categorize_role("agente_vacinas") == "saude"


def test_unknown_and_admin_roles_fallback_to_administrativas():
    for role in ("admin", "super_admin", "semed3", "secretario", "gerente", "qualquer_nova"):
        assert categorize_role(role) == DEFAULT_CONNECTION_CATEGORY


def test_case_insensitive_and_empty():
    assert categorize_role("AGENTE_VACINAS") == "saude"
    assert categorize_role("  Professor ") == "professores"
    assert categorize_role(None) == DEFAULT_CONNECTION_CATEGORY
    assert categorize_role("") == DEFAULT_CONNECTION_CATEGORY


def test_empty_counts_has_all_categories_zeroed():
    counts = empty_category_counts()
    assert set(counts.keys()) == set(CONNECTION_CATEGORIES)
    assert all(v == 0 for v in counts.values())
    assert DEFAULT_CONNECTION_CATEGORY in counts
