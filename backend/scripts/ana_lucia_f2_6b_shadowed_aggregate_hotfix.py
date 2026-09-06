#!/usr/bin/env python3
"""ANA-LUCIA-F2.6B — hotfix de adjudicação pré-escrita.

Este módulo NÃO escreve no MongoDB. Ele é instalado sobre o executor F2.6 e
corrige duas discrepâncias descobertas pela primeira execução, que abortou antes
do primeiro update_one:

1. distingue agregado legado isolado de agregado *shadowed* por todas as sessões
   exatas do mesmo dia, exigindo prova na grade `class_schedules`;
2. compara linhagem por arestas de cópia (141/140/1), preservando também a
   métrica distinta de 74 pais.

O executor F2.6 continua sendo o único escritor e continua alterando apenas
`course_id`, documento a documento, com CAS e rollback compensatório.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping


WEEKDAY_MAP = {
    "segunda": 1, "segunda-feira": 1, "seg": 1,
    "terca": 2, "terça": 2, "terca-feira": 2, "terça-feira": 2, "ter": 2,
    "quarta": 3, "quarta-feira": 3, "qua": 3,
    "quinta": 4, "quinta-feira": 4, "qui": 4,
    "sexta": 5, "sexta-feira": 5, "sex": 5,
    "sabado": 6, "sábado": 6, "sab": 6,
    "domingo": 7, "dom": 7,
}

EDGE_BASELINE = {
    "copied_candidate_documents": 141,
    "distinct_parent_ids": 74,
    "parent_in_candidate_edges": 140,
    "parent_missing_edges": 1,
}

AGGREGATE_BASELINE = {
    "incomplete_candidates": 4,
    "isolated_aggregate_cases": 2,
    "shadowed_aggregate_cases": 2,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm_day(value: Any) -> int | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw.isdigit():
        number = int(raw)
        return number if 1 <= number <= 7 else None
    return WEEKDAY_MAP.get(raw)


def _aula(value: Any) -> str:
    raw = _sid(value)
    if not raw:
        return ""
    try:
        number = int(raw)
        return str(number)
    except (TypeError, ValueError):
        return raw


def expected_schedule_aulas(
    schedule: Mapping[str, Any] | None,
    *,
    date: str,
    course_ids: set[str],
) -> set[str]:
    """Retorna aulas previstas na grade para data + qualquer identidade equivalente."""
    if not schedule or not date or not course_ids:
        return set()
    try:
        weekday = datetime.strptime(str(date)[:10], "%Y-%m-%d").isoweekday()
    except ValueError:
        return set()

    aulas: set[str] = set()
    for slot in schedule.get("schedule_slots") or []:
        if _sid(slot.get("course_id")) not in course_ids:
            continue
        if _norm_day(slot.get("day") or slot.get("weekday")) != weekday:
            continue
        aula = _aula(slot.get("slot_number") or slot.get("aula_numero"))
        if aula:
            aulas.add(aula)
    return aulas


def _group(rows: Iterable[Mapping[str, Any]], key_fn):
    groups: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    missing = 0
    for row in rows:
        key = key_fn(row)
        if key is None:
            missing += 1
        else:
            groups[key].append(row)
    return groups, missing


def validate_attendance_keys_with_schedule(
    base,
    db,
    source: list[Mapping[str, Any]],
    target: list[Mapping[str, Any]],
    *,
    legacy_id: str,
    current_id: str,
) -> dict[str, int]:
    """Valida as 4 chaves incompletas sem inventar `aula_numero`.

    Caso misto só é aceito como shadowed se:
    - houver exatamente um agregado;
    - não houver agregado/sessões na identidade de destino antes do remap;
    - as sessões numeradas da origem forem exatamente os slots previstos na grade;
    - `number_of_classes` do agregado coincidir com a quantidade de slots.
    """
    source_groups, source_missing = _group(source, base._attendance_key)
    target_groups, _ = _group(target, base._attendance_key)
    if any(len(rows) != 1 for rows in source_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6B_ATTENDANCE_SOURCE_DUPLICATE")
    if any(len(rows) != 1 for rows in target_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6B_ATTENDANCE_TARGET_DUPLICATE")
    if set(source_groups) & set(target_groups):
        raise RuntimeError("ANA_LUCIA_F2_6B_ATTENDANCE_TARGET_COLLISION")

    incomplete = [row for row in source if base._attendance_key(row) is None]
    if len(incomplete) != source_missing:
        raise RuntimeError("ANA_LUCIA_F2_6B_ATTENDANCE_KEY_ACCOUNTING")

    isolated = 0
    shadowed = 0
    for row in incomplete:
        if not _sid(row.get("class_id")) or not base._day(row.get("date")) or _sid(row.get("aula_numero")):
            raise RuntimeError("ANA_LUCIA_F2_6B_INCOMPLETE_KEY_NOT_LEGACY_AGGREGATE")
        agg = base._aggregate_key(row)
        if agg is None:
            raise RuntimeError("ANA_LUCIA_F2_6B_AGGREGATE_KEY_MISSING")

        source_same = [other for other in source if base._aggregate_key(other) == agg]
        target_same = [other for other in target if base._aggregate_key(other) == agg]
        source_aggregate = [other for other in source_same if not _sid(other.get("aula_numero"))]
        source_sessions = [other for other in source_same if _sid(other.get("aula_numero"))]
        target_aggregate = [other for other in target_same if not _sid(other.get("aula_numero"))]
        target_sessions = [other for other in target_same if _sid(other.get("aula_numero"))]

        if len(source_aggregate) != 1 or target_aggregate or target_sessions:
            raise RuntimeError("ANA_LUCIA_F2_6B_AGGREGATE_NOT_PRESERVABLE")

        if not source_sessions:
            isolated += 1
            continue

        schedule = db.class_schedules.find_one(
            {"class_id": _sid(row.get("class_id"))},
            {"_id": 0, "schedule_slots": 1},
        )
        expected = expected_schedule_aulas(
            schedule,
            date=base._day(row.get("date")),
            course_ids={legacy_id, current_id},
        )
        actual = {_aula(item.get("aula_numero")) for item in source_sessions if _aula(item.get("aula_numero"))}
        try:
            declared = int(row.get("number_of_classes") or 0)
        except (TypeError, ValueError):
            declared = 0

        if not expected:
            raise RuntimeError("ANA_LUCIA_F2_6B_SHADOWED_SCHEDULE_MISSING")
        if actual != expected:
            raise RuntimeError("ANA_LUCIA_F2_6B_SHADOWED_SESSION_SET_MISMATCH")
        if len(source_sessions) != len(expected):
            raise RuntimeError("ANA_LUCIA_F2_6B_SHADOWED_SESSION_COUNT_MISMATCH")
        if declared != len(expected):
            raise RuntimeError("ANA_LUCIA_F2_6B_SHADOWED_DECLARED_CLASS_COUNT_MISMATCH")
        shadowed += 1

    return {
        "incomplete_candidates": len(incomplete),
        "isolated_aggregate_cases": isolated,
        "shadowed_aggregate_cases": shadowed,
    }


def install(base) -> None:
    """Instala a política F2.6B sobre o módulo F2.6 sem adicionar mutadores."""
    base.BASELINE["copied_candidates"] = EDGE_BASELINE["copied_candidate_documents"]
    base.BASELINE["parent_in_candidate_set"] = EDGE_BASELINE["parent_in_candidate_edges"]
    base.BASELINE["parent_missing"] = EDGE_BASELINE["parent_missing_edges"]

    original_lineage = base._validate_lineage

    def validate_prewrite(db, state, context):
        learning = state["learning_candidates"]
        attendance = state["attendance_candidates"]
        target_learning = state["target_learning"]
        target_attendance = state["target_attendance"]

        if len(learning) != base.BASELINE["learning_candidates"]:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_LEARNING_BASELINE_DRIFT:{len(learning)}")
        if len(attendance) != base.BASELINE["attendance_candidates"]:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_ATTENDANCE_BASELINE_DRIFT:{len(attendance)}")
        if len(target_learning) != base.BASELINE["learning_target_existing"]:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_LEARNING_TARGET_DRIFT:{len(target_learning)}")
        if len(target_attendance) != base.BASELINE["attendance_target_existing"]:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_ATTENDANCE_TARGET_DRIFT:{len(target_attendance)}")
        if len(state["raw_attendance"]) != base.BASELINE["attendance_raw_legacy"]:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_ATTENDANCE_RAW_DRIFT:{len(state['raw_attendance'])}")
        if dict(state["learning_excluded"]):
            raise RuntimeError("ANA_LUCIA_F2_6B_UNEXPECTED_LEARNING_EXCLUSIONS")
        if dict(state["attendance_excluded"]) != {"NOT_ATTRIBUTABLE_TO_TEACHER": base.BASELINE["attendance_excluded_not_teacher"]}:
            raise RuntimeError("ANA_LUCIA_F2_6B_ATTENDANCE_EXCLUSIONS_DRIFT")
        if any(base._sid(row.get("assignment_id")) for row in [*learning, *attendance]):
            raise RuntimeError("ANA_LUCIA_F2_6B_ASSIGNMENT_BOUND_CANDIDATE")

        tenant_missing_learning = base._validate_tenant(learning, context["class_by_id"], context["tenant_id"])
        tenant_missing_attendance = base._validate_tenant(attendance, context["class_by_id"], context["tenant_id"])
        if tenant_missing_learning != 0 or tenant_missing_attendance != base.BASELINE["attendance_tenant_missing"]:
            raise RuntimeError("ANA_LUCIA_F2_6B_TENANT_ADJUDICATION_DRIFT")

        base._validate_learning_keys(learning, target_learning)
        aggregate = validate_attendance_keys_with_schedule(
            base,
            db,
            attendance,
            target_attendance,
            legacy_id=context["legacy_id"],
            current_id=context["current_id"],
        )
        if aggregate != AGGREGATE_BASELINE:
            raise RuntimeError(f"ANA_LUCIA_F2_6B_AGGREGATE_BASELINE_DRIFT:{aggregate}")

        lineage = original_lineage(db, learning, context["legacy_id"], context["current_id"])
        parent_ids = {
            base._sid(row.get("copied_from_id"))
            for row in learning
            if base._sid(row.get("copied_from_id"))
        }
        if lineage["copied_candidates"] != EDGE_BASELINE["copied_candidate_documents"]:
            raise RuntimeError("ANA_LUCIA_F2_6B_COPIED_EDGE_BASELINE_DRIFT")
        if len(parent_ids) != EDGE_BASELINE["distinct_parent_ids"]:
            raise RuntimeError("ANA_LUCIA_F2_6B_DISTINCT_PARENT_BASELINE_DRIFT")
        if lineage["parent_in_candidate_set"] != EDGE_BASELINE["parent_in_candidate_edges"]:
            raise RuntimeError("ANA_LUCIA_F2_6B_PARENT_EDGE_BASELINE_DRIFT")
        if lineage["parent_missing"] != EDGE_BASELINE["parent_missing_edges"]:
            raise RuntimeError("ANA_LUCIA_F2_6B_MISSING_PARENT_EDGE_DRIFT")

        lineage = dict(lineage)
        lineage["distinct_parent_ids"] = len(parent_ids)
        return {
            "learning_ids": base._candidate_ids(learning),
            "attendance_ids": base._candidate_ids(attendance),
            "lineage": lineage,
            "tenant_missing_attendance": tenant_missing_attendance,
            "legacy_aggregate_attendance": aggregate["incomplete_candidates"],
            "isolated_aggregate_attendance": aggregate["isolated_aggregate_cases"],
            "shadowed_aggregate_attendance": aggregate["shadowed_aggregate_cases"],
        }

    base._validate_prewrite = validate_prewrite
