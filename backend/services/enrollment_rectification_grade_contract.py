"""Contrato compartilhado F2.1B para fingerprint acadêmico de notas.

Não escreve no banco. Centraliza a projeção usada pelo dry-run e pelo primitivo
interno para que TOCTOU/CAS não dependam de updated_at nem de ordem de chaves.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

GRADE_VALUE_FIELDS = ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2", "recovery")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _academic_year(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def grade_academic_projection(grade: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if grade is None:
        return None
    return {
        "id": grade.get("id"),
        "mantenedora_id": grade.get("mantenedora_id"),
        "student_id": grade.get("student_id"),
        "class_id": grade.get("class_id"),
        "course_id": grade.get("course_id"),
        "academic_year": _academic_year(grade.get("academic_year")),
        "dependency_id": grade.get("dependency_id"),
        "values": {field: grade.get(field) for field in GRADE_VALUE_FIELDS},
        "grade_ownership": grade.get("grade_ownership") or {},
        "rectified_fields": grade.get("rectified_fields") or {},
    }


def grade_academic_fingerprint(grade: Mapping[str, Any] | None) -> str | None:
    projection = grade_academic_projection(grade)
    if projection is None:
        return None
    return hashlib.sha256(_canonical(projection).encode("utf-8")).hexdigest()


def migratable_grade_fields(grade: Mapping[str, Any]) -> list[str]:
    return [
        field for field in GRADE_VALUE_FIELDS
        if grade.get(field) not in (None, "", [], {})
    ]
