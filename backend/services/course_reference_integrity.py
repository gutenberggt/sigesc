"""Integridade referencial lógica de componentes curriculares.

O SIGESC usa MongoDB e, portanto, não dispõe de foreign keys físicas entre
``courses`` e os documentos pedagógicos. Este módulo centraliza as referências
que apontam para ``courses.id`` para que mutações destrutivas possam falhar
fechado e para que auditorias usem a mesma definição.

P0 Global (Ago/2026): nenhuma função deste módulo altera dados.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class CourseReferenceSpec:
    collection: str
    field: str
    label: str


# IMPORTANTE: adicionar aqui todo novo consumidor persistente de ``courses.id``.
# O campo pode ser escalar ou estar dentro de array (Mongo resolve dot notation).
COURSE_REFERENCE_SPECS: tuple[CourseReferenceSpec, ...] = (
    CourseReferenceSpec("teacher_assignments", "course_id", "alocação docente legada"),
    CourseReferenceSpec("teacher_allocations", "course_id", "alocação docente operacional"),
    CourseReferenceSpec("teacher_class_assignments", "component_id", "vínculo docente canônico/DVD"),
    CourseReferenceSpec("class_schedules", "schedule_slots.course_id", "grade de horário"),
    CourseReferenceSpec("grades", "course_id", "notas/conceitos"),
    CourseReferenceSpec("attendance", "course_id", "frequência"),
    CourseReferenceSpec("content_entries", "component_id", "registro de conteúdos"),
    CourseReferenceSpec("learning_objects", "course_id", "objetos de conhecimento legados"),
    CourseReferenceSpec("student_dependencies", "course_id", "dependências de estudos"),
)


def reference_query(spec: CourseReferenceSpec, course_id: str) -> dict[str, Any]:
    """Retorna a query Mongo que encontra documentos que referenciam course_id."""
    return {spec.field: course_id}


async def get_course_reference_counts(db: Any, course_id: str) -> dict[str, int]:
    """Conta referências persistentes ao componente, sem qualquer mutação."""
    counts: dict[str, int] = {}
    for spec in COURSE_REFERENCE_SPECS:
        counts[spec.collection] = await db[spec.collection].count_documents(
            reference_query(spec, course_id)
        )
    return counts


def blocking_course_references(counts: Mapping[str, int]) -> dict[str, int]:
    """Mantém apenas coleções com referências reais (> 0)."""
    return {name: int(count) for name, count in counts.items() if int(count or 0) > 0}


def extract_reference_ids(document: Mapping[str, Any], field: str) -> list[str]:
    """Extrai IDs referenciados de campo simples ou dot notation em array.

    É deliberadamente pequeno e determinístico para ser reutilizado pelo auditor
    P0 sem depender de agregações que poderiam esconder documentos inconsistentes.
    """
    parts = field.split(".")
    values: list[Any] = [document]
    for part in parts:
        next_values: list[Any] = []
        for value in values:
            if isinstance(value, Mapping):
                child = value.get(part)
                if isinstance(child, list):
                    next_values.extend(child)
                else:
                    next_values.append(child)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        child = item.get(part)
                        if isinstance(child, list):
                            next_values.extend(child)
                        else:
                            next_values.append(child)
        values = next_values

    result: list[str] = []
    for value in values:
        if isinstance(value, (str, int)):
            normalized = str(value).strip()
            if normalized:
                result.append(normalized)
    return result


def reference_projection(spec: CourseReferenceSpec) -> dict[str, int]:
    """Projeção mínima comum usada pelas auditorias globais."""
    root = spec.field.split(".", 1)[0]
    return {
        "_id": 0,
        "id": 1,
        root: 1,
        "mantenedora_id": 1,
        "school_id": 1,
        "class_id": 1,
        "academic_year": 1,
        "staff_id": 1,
        "teacher_id": 1,
        "status": 1,
        "deleted": 1,
    }


def all_reference_collections() -> Iterable[str]:
    return tuple(spec.collection for spec in COURSE_REFERENCE_SPECS)
