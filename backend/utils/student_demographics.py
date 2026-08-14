"""Regras canônicas de auditoria para raça/cor e comunidade tradicional.

Nenhuma função deste módulo altera dados. A finalidade é identificar registros
legados que precisam de revisão antes de estreitar o domínio de ``color_race``.
"""

CANONICAL_COLOR_RACE = {
    "branca",
    "preta",
    "parda",
    "amarela",
    "indigena",
    "nao_declarada",
}

TRADITIONAL_COMMUNITIES = {
    "quilombola",
    "cigano",
    "ribeirinho",
    "extrativista",
}

VALID_COMMUNITY_VALUES = {"nao_pertence", *TRADITIONAL_COMMUNITIES}


def audit_race_community_record(student: dict) -> dict:
    """Classifica inconsistências semânticas sem reinterpretar o registro."""
    color_race = student.get("color_race")
    community = student.get("comunidade_tradicional")
    issues = []

    if color_race in TRADITIONAL_COMMUNITIES:
        issues.append("traditional_value_in_color_race")
        if community in TRADITIONAL_COMMUNITIES and community != color_race:
            issues.append("traditional_dimensions_conflict")
        elif community in (None, "", "nao_pertence"):
            issues.append("traditional_community_needs_confirmation")

    if color_race not in (None, "") and color_race not in CANONICAL_COLOR_RACE and color_race not in TRADITIONAL_COMMUNITIES:
        issues.append("unsupported_color_race")

    if community not in (None, "") and community not in VALID_COMMUNITY_VALUES:
        issues.append("unsupported_traditional_community")

    return {
        "color_race": color_race,
        "comunidade_tradicional": community,
        "issues": issues,
        "needs_review": bool(issues),
    }
