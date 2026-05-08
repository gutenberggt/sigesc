"""
Filtros canônicos para excluir registros de Dependência de Estudos
de cálculos pedagógicos regulares.

[Fev/2026] P0 — exigência operacional do owner.

============================================================================
REGRA CRÍTICA — NÃO REMOVA SEM AUTORIZAÇÃO EXPLÍCITA DO PROPRIETÁRIO.
============================================================================

Dependência de Estudos é uma entidade pedagógica COMPLEMENTAR, não substitutiva.
Notas e frequência registradas com `dependency_id != null` representam o aluno
cumprindo a dependência de um ANO ANTERIOR — não compõem o cálculo da turma
no ano corrente.

Estes registros NÃO devem contaminar:
- médias finais regulares da turma
- frequência regular da turma
- ranking pedagógico
- aprovação padrão
- estatísticas de turma (IDEB, etc.)
- dashboards de coordenação
- indicadores de SEMED
- relatórios oficiais

Estratégia (defesa em profundidade — exigência híbrida do owner):
1. Mongo: `match` com `regular_only_filter()` ou `regular_only_aggregate_match()`
   exclui via índice eficiente.
2. Python: `is_regular_grade(g)` / `is_regular_attendance_record(r)` é a ÚLTIMA
   barreira contra dados inconsistentes (migrations antigas, inserts manuais,
   bugs de integração futura).

Nunca confie em uma camada só.

Se daqui 8 meses alguém quiser remover esse helper "por otimização":
- ele leu este docstring;
- ele entende que está abrindo um buraco no histórico escolar;
- ele tem que alinhar com o time de produto antes.
"""
from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T", bound=dict)


# ============================================================================
# Filtros Mongo
# ============================================================================
def regular_only_filter() -> dict:
    """Filtro Mongo padrão para `find()` excluir registros com dependency_id.

    Cobre:
    - documentos antigos sem o campo (interpretados como regulares).
    - documentos novos com `dependency_id: null`.

    Uso:
        flt = {"class_id": cid, "academic_year": year, **regular_only_filter()}
        await db.grades.find(flt, {"_id": 0}).to_list(...)
    """
    return {"dependency_id": {"$in": [None]}}


def regular_only_aggregate_match() -> dict:
    """Mesma semântica em pipelines `$match`.

    Uso:
        pipeline = [
            {"$match": {"class_id": cid, **regular_only_aggregate_match()}},
            ...
        ]
    """
    return {"dependency_id": {"$in": [None]}}


def with_regular_only(filter_dict: dict) -> dict:
    """Anexa o filtro regular-only a um filter existente sem mutar o original."""
    out = dict(filter_dict)
    out.update(regular_only_filter())
    return out


# ============================================================================
# Defesa em profundidade — Python (última barreira)
# ============================================================================
def is_regular_grade(grade: dict | None) -> bool:
    """True se a nota É regular (NÃO carrega dependency_id).

    Use em loops de cálculo de média/agregação para descartar registros
    que escaparam do filtro Mongo (migrations antigas, etc.).
    """
    if grade is None:
        return False
    return not grade.get("dependency_id")


def is_regular_attendance_record(record: dict | None) -> bool:
    """True se o registro de frequência é regular."""
    if record is None:
        return False
    return not record.get("dependency_id")


def keep_regular_only(items: Iterable[T]) -> list[T]:
    """Filtra in-memory, descartando items com dependency_id."""
    return [it for it in items if not it.get("dependency_id")]
