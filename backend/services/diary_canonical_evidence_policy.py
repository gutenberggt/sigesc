"""Política canônica de casamento de evidências do Diário.

A identidade de leitura do diário é institucional, não autoral:

- frequência de Anos Finais é comprovada por turma/data/componente/slot;
- um documento agregado legado sem ``aula_numero`` nunca é expandido
  artificialmente para cobrir dois ou mais slots estritos;
- quando todos os slots numerados esperados já existem, um agregado legado
  estruturalmente equivalente é preservado como rastreabilidade, mas não vira
  uma aula extra nem um falso órfão;
- conteúdo é comprovado por turma/data/componente e pode cobrir todos os slots
  do componente naquele dia quando existe um único registro válido;
- ``teacher_id``, ``created_by`` e ``updated_by`` são metadados de autoria e
  auditoria, não chaves de visibilidade.

O módulo é puro e não consulta MongoDB. Routers/serviços entregam somente o
recorte de turma já autorizado por RBAC/tenant/escola.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _day(row: Mapping[str, Any]) -> str:
    return _sid(row.get("date"))[:10]


def _component(row: Mapping[str, Any]) -> str:
    return _sid(row.get("component_id") or row.get("course_id"))


def _aula(row: Mapping[str, Any]) -> str:
    return _sid(row.get("aula_numero"))


def _version(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("version") or 0)
    except (TypeError, ValueError):
        return 0


def _stable_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("id"))


def _declared_classes(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("number_of_classes") or 0)
    except (TypeError, ValueError):
        return 0


def _latest(rows: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    materialized = list(rows)
    if not materialized:
        return None
    return max(materialized, key=lambda row: (_version(row), _stable_id(row)))


def select_strict_attendance(
    expected_entry: Mapping[str, Any],
    attendance_rows: Iterable[Mapping[str, Any]],
    *,
    expected_slot_count_for_component_day: int,
    used_ids: set[str] | None = None,
) -> Mapping[str, Any] | None:
    """Seleciona uma frequência para um slot estrito.

    A autoria não participa do matching. Para dois slots esperados, dois
    documentos numerados distintos são necessários. Um agregado legado sem
    ``aula_numero`` só pode casar quando existe exatamente um slot esperado no
    componente/data; portanto nunca transforma uma frequência em duas.
    """
    used = used_ids if used_ids is not None else set()
    date = _day(expected_entry)
    component = _component(expected_entry)
    aula = _aula(expected_entry)

    rows = [
        row for row in attendance_rows
        if _day(row) == date
        and _component(row) == component
        and _stable_id(row) not in used
    ]

    exact = [row for row in rows if aula and _aula(row) == aula]
    picked = _latest(exact)
    if picked is not None:
        return picked

    if expected_slot_count_for_component_day != 1:
        return None

    aggregates = [row for row in rows if not _aula(row)]
    if len(aggregates) != 1:
        return None
    return aggregates[0]


def shadowed_legacy_attendance_ids(
    expected_entries: Iterable[Mapping[str, Any]],
    attendance_rows: Iterable[Mapping[str, Any]],
) -> set[str]:
    """Identifica agregados legados cobertos integralmente por sessões exatas.

    É uma regra conservadora. Um agregado sem ``aula_numero`` só é classificado
    como *shadowed* quando, no mesmo dia+componente:

    - existe ao menos um slot esperado numerado;
    - há uma sessão numerada para CADA ``aula_numero`` esperado; e
    - ``number_of_classes`` do agregado coincide exatamente com a quantidade
      de slots esperados.

    O agregado não é apagado nem alterado. Ele apenas deixa de representar uma
    terceira aula e deixa de ser sinalizado como órfão na projeção canônica.
    """
    expected_aulas: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entry in expected_entries:
        key = (_day(entry), _component(entry))
        aula = _aula(entry)
        if key[0] and key[1] and aula:
            expected_aulas[key].add(aula)

    session_aulas: dict[tuple[str, str], set[str]] = defaultdict(set)
    aggregates: list[Mapping[str, Any]] = []
    for row in attendance_rows:
        key = (_day(row), _component(row))
        if not key[0] or not key[1]:
            continue
        aula = _aula(row)
        if aula:
            session_aulas[key].add(aula)
        else:
            aggregates.append(row)

    shadowed: set[str] = set()
    for row in aggregates:
        key = (_day(row), _component(row))
        expected = expected_aulas.get(key) or set()
        if not expected:
            continue
        if not expected.issubset(session_aulas.get(key) or set()):
            continue
        if _declared_classes(row) != len(expected):
            continue
        row_id = _stable_id(row)
        if row_id:
            shadowed.add(row_id)
    return shadowed


def build_content_day_index(
    content_rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    """Indexa conteúdo por data+componente, deliberadamente sem autoria."""
    index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in content_rows:
        if row.get("deleted") is True:
            continue
        date = _day(row)
        component = _component(row)
        if not date or not component:
            continue
        index[(date, component)].append(row)
    return dict(index)


def select_content_for_slot(
    expected_entry: Mapping[str, Any],
    content_rows: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Seleciona conteúdo institucional para um slot esperado.

    Regras:
    1. mesmo dia + mesmo componente é obrigatório;
    2. autoria é ignorada para leitura;
    3. se houver conteúdo do slot exato, vence a maior versão desse slot;
    4. conteúdo sem ``aula_numero`` cobre o componente no dia;
    5. se existir exatamente um único registro do componente no dia, ele pode
       cobrir todos os slots daquele componente, mesmo que tenha aula_numero;
    6. múltiplos registros de slots diferentes não são colapsados entre si.
    """
    date = _day(expected_entry)
    component = _component(expected_entry)
    aula = _aula(expected_entry)
    rows = [
        row for row in content_rows
        if row.get("deleted") is not True
        and _day(row) == date
        and _component(row) == component
    ]
    if not rows:
        return None

    exact = [row for row in rows if aula and _aula(row) == aula]
    picked = _latest(exact)
    if picked is not None:
        return picked

    day_level = [row for row in rows if not _aula(row)]
    picked = _latest(day_level)
    if picked is not None:
        return picked

    distinct_ids = {_stable_id(row) for row in rows if _stable_id(row)}
    if len(distinct_ids) == 1:
        return _latest(rows)
    return None


def expected_slot_counts(entries: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    """Conta slots esperados por data+componente para impedir fan-out de frequência."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for entry in entries:
        date = _day(entry)
        component = _component(entry)
        if date and component:
            counts[(date, component)] += 1
    return dict(counts)
