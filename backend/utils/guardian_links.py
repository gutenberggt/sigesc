"""Regras canônicas para vínculo estudante-responsável.

Mantém a noção de responsável principal no vínculo, sem transformar a pessoa
Guardian em "principal" de forma global.
"""


def _unique_ids(values):
    seen = set()
    result = []
    for value in values or []:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_guardian_student_links(student_ids, primary_student_ids):
    """Normaliza vínculos e garante que todo vínculo principal também seja comum.

    Retorna duas listas deduplicadas preservando ordem. ``primary_student_ids``
    deve ser subconjunto de ``student_ids``; inconsistências são rejeitadas para
    evitar vínculo principal órfão ou implícito.
    """
    linked = _unique_ids(student_ids)
    primary = _unique_ids(primary_student_ids)
    linked_set = set(linked)
    missing = [student_id for student_id in primary if student_id not in linked_set]
    if missing:
        raise ValueError(
            "Todo estudante marcado como responsável legal principal deve estar "
            "também na lista de estudantes vinculados."
        )
    return linked, primary
