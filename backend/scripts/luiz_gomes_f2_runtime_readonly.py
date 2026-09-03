#!/usr/bin/env python3
"""LUIZ-GOMES-F2 — paridade runtime legado, estritamente read-only.

Reutiliza o motor ANA-LUCIA-F2.1 já homologado, alterando apenas o alvo e
fortalecendo a resolução pela escola exata. Mede Mongo -> HTTP professor/gestão
para conteúdo e frequência sem ler attendance.records nem texto pedagógico.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts import ana_lucia_f2_1_runtime_legacy_audit as base

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Luiz Gomes dos Santos"
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_PAIRS: tuple[tuple[str, str], ...] = (
    ("6º ANO A", "Matemática"),
    ("6º ANO B", "Matemática"),
    ("7º ANO A", "Matemática"),
    ("7º ANO B", "Matemática"),
    ("8º ANO A", "Matemática"),
    ("9º ANO A", "Matemática"),
)


def _resolve_targets_exact_school(db, staff: dict[str, Any]) -> list[dict[str, Any]]:
    school_matches = [
        row for row in db.schools.find(
            {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
        )
        if base._norm(row.get("name")) == base._norm(TARGET_SCHOOL)
    ]
    if len(school_matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F2_TARGET_SCHOOL_MATCHES:{len(school_matches)}")
    school = school_matches[0]
    school_id = base._sid(school.get("id"))
    tenant_id = base._sid(school.get("mantenedora_id"))
    if not school_id or not tenant_id:
        raise RuntimeError("LUIZ_GOMES_F2_TARGET_SCHOOL_SCOPE_MISSING")

    legacy = list(db.teacher_assignments.find(
        {
            "staff_id": staff["id"],
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": {"$in": list(base.ACTIVE_STATUSES)},
        },
        {"_id": 0, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    class_ids = sorted({base._sid(row.get("class_id")) for row in legacy if base._sid(row.get("class_id"))})
    course_ids = sorted({base._sid(row.get("course_id")) for row in legacy if base._sid(row.get("course_id"))})

    classes = {
        base._sid(row.get("id")): row
        for row in db.classes.find(
            {"id": {"$in": class_ids}, "school_id": school_id},
            {
                "_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1,
                "academic_year": 1, "education_level": 1, "nivel_ensino": 1, "grade_level": 1,
            },
        )
        if base._sid(row.get("mantenedora_id")) == tenant_id
    }
    course_docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ):
        course_docs[base._sid(row.get("id"))].append(row)

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for class_name, component_name in TARGET_PAIRS:
        candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for assignment in legacy:
            class_id = base._sid(assignment.get("class_id"))
            course_id = base._sid(assignment.get("course_id"))
            class_doc = classes.get(class_id)
            if not class_doc or base._norm(class_doc.get("name")) != base._norm(class_name):
                continue
            if base._sid(assignment.get("school_id")) not in {"", school_id}:
                continue
            if base._sid(assignment.get("mantenedora_id")) not in {"", tenant_id}:
                continue
            docs = course_docs.get(course_id) or []
            scoped_docs = [
                row for row in docs
                if base._sid(row.get("mantenedora_id")) in {"", tenant_id}
            ]
            if base._norm(component_name) not in {base._norm(row.get("name")) for row in scoped_docs}:
                continue
            candidates.append((assignment, class_doc))

        if len(candidates) != 1:
            raise RuntimeError(
                f"LUIZ_GOMES_F2_TARGET_NOT_EXACT:{class_name}:{component_name}:{len(candidates)}"
            )
        assignment, class_doc = candidates[0]
        class_id = base._sid(assignment.get("class_id"))
        course_id = base._sid(assignment.get("course_id"))
        if (class_id, course_id) in seen:
            raise RuntimeError(f"LUIZ_GOMES_F2_DUPLICATE_TARGET:{class_name}:{component_name}")
        seen.add((class_id, course_id))
        out.append({
            "class": class_name,
            "component": component_name,
            "school": TARGET_SCHOOL,
            "class_id": class_id,
            "course_id": course_id,
            "tenant_id": tenant_id,
            "education_level": base._sid(class_doc.get("education_level") or class_doc.get("nivel_ensino")),
            "grade_level": base._sid(class_doc.get("grade_level")),
        })

    if len(out) != len(TARGET_PAIRS):
        raise RuntimeError(f"LUIZ_GOMES_F2_TARGET_COUNT:{len(out)}")
    return out


def run_live_audit() -> dict[str, Any]:
    # O motor base não mantém estado persistente; o patch existe apenas neste
    # processo efêmero e serve para reutilizar exatamente o contrato F2.1 já testado.
    base.ACADEMIC_YEAR = ACADEMIC_YEAR
    base.TEACHER_NAME = TEACHER_NAME
    base.TARGET_PAIRS = TARGET_PAIRS
    base._resolve_targets = _resolve_targets_exact_school
    result = base.run_live_audit()
    result["schema"] = "LUIZ_GOMES_F2_RUNTIME_READ_ONLY_V1"
    result["teacher"] = TEACHER_NAME
    result["target_school"] = TARGET_SCHOOL
    result["target_pair_count"] = len(TARGET_PAIRS)
    return result


if __name__ == "__main__":
    import json
    print("LUIZ_GOMES_F2_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
