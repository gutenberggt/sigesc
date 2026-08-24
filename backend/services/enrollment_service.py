"""Serviço canônico de matrículas do SIGESC.

Contrato arquitetural (Ago/2026):
- ``enrollments`` é a fonte canônica do vínculo aluno↔turma↔ano.
- ``students.class_id/school_id/status/enrollment_number`` são apenas uma projeção
  conveniente da MATRÍCULA REGULAR ativa (home class), nunca a fonte do vínculo.
- Matrículas especiais (AEE, recomposição e reforço) coexistem com a regular e
  NUNCA sobrescrevem a projeção de turma regular em ``students``.
- ``class_students`` é legado de leitura e não deve receber novas escritas.

O módulo não depende de FastAPI. Erros de domínio são convertidos em HTTP pelos
routers chamadores.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from utils.enrollment import generate_enrollment_number
from utils.text_normalize import normalize_input_fields


SPECIAL_PROGRAMS = frozenset({
    "aee",
    "recomposicao_aprendizagem",
    "reforco_escolar",
})

CANONICAL_STATUSES = frozenset({
    "active",
    "completed",
    "cancelled",
    "transferred",
    "relocated",
    "progressed",
    "dropout",
})

LEGACY_STATUS_MAP = {
    "inactive": "cancelled",
    "inativo": "cancelled",
    "deceased": "cancelled",
    "reclassified": "progressed",
}


class EnrollmentDomainError(Exception):
    """Erro base do domínio de matrículas."""


class EnrollmentValidationError(EnrollmentDomainError):
    """Dados estruturalmente inválidos ou referências inconsistentes."""


class EnrollmentConflictError(EnrollmentDomainError):
    """A operação violaria uma invariável de matrícula."""


class EnrollmentNotFoundError(EnrollmentDomainError):
    """Entidade necessária à operação não foi encontrada."""


def canonicalize_enrollment_status(value: Optional[str]) -> Optional[str]:
    """Normaliza status legado para o vocabulário canônico.

    Mantém ``None`` e rejeita valores desconhecidos para impedir que novos
    estados legados voltem a ser gravados no banco.
    """
    if value is None:
        return None
    normalized = str(value).strip().lower()
    normalized = LEGACY_STATUS_MAP.get(normalized, normalized)
    if normalized not in CANONICAL_STATUSES:
        raise EnrollmentValidationError(
            f"Status de matrícula inválido: {value!r}. Valores aceitos: "
            f"{', '.join(sorted(CANONICAL_STATUSES))}."
        )
    return normalized


def class_program(class_doc: Optional[dict]) -> str:
    """Retorna o programa especial normalizado da turma, se houver."""
    if not class_doc:
        return ""
    return str(class_doc.get("atendimento_programa") or "").strip().lower()


def is_special_class(class_doc: Optional[dict]) -> bool:
    return class_program(class_doc) in SPECIAL_PROGRAMS


async def _load_student(db, student_id: str) -> dict:
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise EnrollmentNotFoundError("Estudante não encontrado.")
    return student


async def _load_class(db, class_id: str) -> dict:
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise EnrollmentNotFoundError(f"Turma não encontrada (class_id={class_id}).")
    return class_doc


async def _load_school(db, school_id: str) -> dict:
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise EnrollmentNotFoundError(f"Escola não encontrada (school_id={school_id}).")
    return school


def _resolve_tenant_id(
    *,
    explicit_mantenedora_id: Optional[str],
    student: dict,
    school: dict,
    class_doc: dict,
) -> str:
    """Resolve tenant e falha se referências discordarem ou estiverem ausentes."""
    candidates = {
        str(v).strip()
        for v in (
            explicit_mantenedora_id,
            student.get("mantenedora_id"),
            school.get("mantenedora_id"),
            class_doc.get("mantenedora_id"),
        )
        if v is not None and str(v).strip()
    }
    if len(candidates) > 1:
        raise EnrollmentValidationError(
            "Inconsistência de mantenedora entre estudante, escola, turma e contexto da matrícula."
        )
    if not candidates:
        raise EnrollmentValidationError(
            "Não foi possível determinar a mantenedora da matrícula. "
            "Saneie estudante/escola/turma antes de efetivar o vínculo."
        )
    return next(iter(candidates))


async def _active_enrollments_for_year(db, student_id: str, academic_year: int) -> list[dict]:
    cursor = db.enrollments.find(
        {
            "student_id": student_id,
            "academic_year": academic_year,
            "status": "active",
        },
        {"_id": 0},
    )
    return await cursor.to_list(length=200)


def _sort_key(enrollment: dict) -> tuple:
    return (
        int(enrollment.get("academic_year") or 0),
        str(enrollment.get("enrollment_date") or ""),
        str(enrollment.get("created_at") or ""),
        str(enrollment.get("id") or ""),
    )


async def find_primary_active_enrollment(
    db,
    student_id: str,
    *,
    academic_year: Optional[int] = None,
) -> Optional[dict]:
    """Retorna a matrícula REGULAR ativa mais recente do estudante.

    Turmas especiais são deliberadamente ignoradas. Uma matrícula apontando para
    turma inexistente também não é promovida a ``home class``: esse caso deve ser
    tratado pela auditoria de integridade, não escondido por fallback.
    """
    query = {"student_id": student_id, "status": "active"}
    if academic_year is not None:
        query["academic_year"] = academic_year

    docs = await db.enrollments.find(query, {"_id": 0}).to_list(length=500)
    docs.sort(key=_sort_key, reverse=True)

    for enrollment in docs:
        class_id = enrollment.get("class_id")
        if not class_id:
            continue
        class_doc = await db.classes.find_one(
            {"id": class_id},
            {"_id": 0, "id": 1, "atendimento_programa": 1},
        )
        if class_doc and not is_special_class(class_doc):
            return enrollment
    return None


async def rebuild_student_home_projection(
    db,
    student_id: str,
    *,
    academic_year: Optional[int] = None,
    no_primary_status: Optional[str] = None,
) -> Optional[dict]:
    """Reconstrói a projeção de turma regular em ``students`` a partir de enrollments.

    Se não houver matrícula regular ativa, limpa apenas ``class_id``. O número de
    matrícula histórico não é apagado automaticamente. ``no_primary_status`` pode
    ser informado por fluxos que conhecem semanticamente o desligamento.
    """
    primary = await find_primary_active_enrollment(
        db, student_id, academic_year=academic_year
    )
    if primary:
        update = {
            "school_id": primary.get("school_id"),
            "class_id": primary.get("class_id"),
            "status": "active",
        }
        if primary.get("enrollment_number"):
            update["enrollment_number"] = primary.get("enrollment_number")
        if primary.get("mantenedora_id"):
            update["mantenedora_id"] = primary.get("mantenedora_id")
        result = await db.students.update_one({"id": student_id}, {"$set": update})
        if getattr(result, "matched_count", 1) == 0:
            raise EnrollmentNotFoundError(
                "Estudante deixou de existir durante a reconstrução da projeção de matrícula."
            )
        return primary

    update = {"class_id": None}
    if no_primary_status:
        update["status"] = no_primary_status
    result = await db.students.update_one({"id": student_id}, {"$set": update})
    if getattr(result, "matched_count", 1) == 0:
        raise EnrollmentNotFoundError(
            "Estudante deixou de existir durante a reconstrução da projeção de matrícula."
        )
    return None


async def _rollback_created_enrollment(db, enrollment_id: str) -> None:
    """Compensação best-effort quando a projeção do estudante falha."""
    try:
        await db.enrollments.delete_one({"id": enrollment_id})
    except Exception:
        # Preserva a exceção original. O auditor canônico detectará eventual
        # resíduo caso o próprio rollback encontre indisponibilidade do banco.
        pass


async def create_active_enrollment(
    db,
    *,
    student_id: str,
    school_id: str,
    class_id: str,
    academic_year: int,
    enrollment_date: Optional[str] = None,
    enrollment_number: Optional[str] = None,
    student_series: Optional[str] = None,
    course_ids: Optional[list[str]] = None,
    observations: Optional[str] = None,
    mantenedora_id: Optional[str] = None,
    source: str = "api",
    require_primary_for_special: bool = True,
) -> dict:
    """Cria uma matrícula ativa obedecendo às invariáveis canônicas.

    Regras:
    1. estudante, escola e turma precisam existir e ser coerentes;
    2. a turma deve pertencer à escola informada;
    3. tenant ausente/divergente é erro bloqueante;
    4. não há duas matrículas ativas na mesma turma/ano;
    5. só pode haver uma matrícula REGULAR ativa no mesmo ano;
    6. matrícula especial requer matrícula regular ativa (por padrão);
    7. somente matrícula REGULAR atualiza a projeção ``students.class_id``;
    8. falha na projeção regular compensa o insert de ``enrollments``.
    """
    if not student_id or not school_id or not class_id:
        raise EnrollmentValidationError("student_id, school_id e class_id são obrigatórios.")
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise EnrollmentValidationError("academic_year inválido.") from exc

    student = await _load_student(db, student_id)
    class_doc = await _load_class(db, class_id)
    school = await _load_school(db, school_id)

    if class_doc.get("school_id") != school_id:
        raise EnrollmentValidationError(
            "A turma selecionada não pertence à escola informada na matrícula."
        )

    resolved_tenant = _resolve_tenant_id(
        explicit_mantenedora_id=mantenedora_id,
        student=student,
        school=school,
        class_doc=class_doc,
    )

    special = is_special_class(class_doc)
    program = class_program(class_doc)
    active = await _active_enrollments_for_year(db, student_id, year)

    for existing in active:
        if existing.get("class_id") == class_id:
            raise EnrollmentConflictError(
                f"O estudante já possui matrícula ativa nesta turma no ano letivo {year}."
            )

    primary_regular = None
    for existing in active:
        existing_class = await db.classes.find_one(
            {"id": existing.get("class_id")},
            {"_id": 0, "id": 1, "name": 1, "atendimento_programa": 1},
        )
        if not existing_class:
            raise EnrollmentConflictError(
                "Existe matrícula ativa do estudante apontando para turma inexistente. "
                "Saneie o vínculo antes de criar outra matrícula."
            )
        if not is_special_class(existing_class):
            primary_regular = existing
            if not special:
                name = existing_class.get("name") or existing.get("class_id") or "N/A"
                raise EnrollmentConflictError(
                    f"O estudante já possui matrícula regular ativa na turma '{name}' "
                    f"no ano letivo {year}."
                )
            break

    if special and require_primary_for_special and not primary_regular:
        raise EnrollmentValidationError(
            f"Matrícula em '{program}' exige uma matrícula regular ativa no mesmo ano letivo."
        )

    number = str(enrollment_number or "").strip()
    if not number:
        number = await generate_enrollment_number(db, year)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "school_id": school_id,
        "class_id": class_id,
        "course_ids": list(course_ids or []),
        "academic_year": year,
        "enrollment_date": enrollment_date or now,
        "enrollment_number": number,
        "student_series": student_series or class_doc.get("grade_level"),
        "status": "active",
        "observations": observations,
        "mantenedora_id": resolved_tenant,
        "source": source,
        "created_at": now,
    }
    doc = normalize_input_fields(doc, "enrollments")

    try:
        await db.enrollments.insert_one(doc)
    except DuplicateKeyError as exc:
        raise EnrollmentConflictError(
            "A matrícula viola uma regra de unicidade (turma ativa ou número de matrícula)."
        ) from exc

    if not special:
        projection = {
            "school_id": school_id,
            "class_id": class_id,
            "status": "active",
            "enrollment_number": number,
            "mantenedora_id": resolved_tenant,
        }
        try:
            projection_result = await db.students.update_one(
                {"id": student_id}, {"$set": projection}
            )
            if getattr(projection_result, "matched_count", 1) == 0:
                raise EnrollmentNotFoundError(
                    "Estudante deixou de existir durante a efetivação da matrícula."
                )
        except Exception:
            await _rollback_created_enrollment(db, doc["id"])
            raise

    return {
        "enrollment": doc,
        "is_special": special,
        "program": program or "regular",
    }


async def cancel_active_enrollment(
    db,
    *,
    student_id: str,
    class_id: str,
    reason: str = "",
    cancelled_by: Optional[str] = None,
) -> dict:
    """Cancela o vínculo ativo mais recente e reconstrói a projeção regular."""
    enrollment = await db.enrollments.find_one(
        {"student_id": student_id, "class_id": class_id, "status": "active"},
        {"_id": 0},
        sort=[
            ("academic_year", -1),
            ("enrollment_date", -1),
            ("created_at", -1),
        ],
    )
    if not enrollment:
        raise EnrollmentNotFoundError(
            "Nenhuma matrícula ativa encontrada para este estudante nesta turma."
        )

    class_doc = await _load_class(db, class_id)
    special = is_special_class(class_doc)
    now = datetime.now(timezone.utc).isoformat()
    await db.enrollments.update_one(
        {"id": enrollment["id"]},
        {"$set": {
            "status": "cancelled",
            "cancellation_reason": reason or "",
            "cancellation_date": now,
            "cancelled_by": cancelled_by or "",
        }},
    )

    if not special:
        try:
            # Reconstrói contra TODOS os anos para não deixar um cancelamento
            # histórico sobrescrever uma matrícula regular ativa mais recente.
            await rebuild_student_home_projection(
                db,
                student_id,
                no_primary_status="cancelled",
            )
        except Exception:
            # Compensação: volta a matrícula ao estado ativo se a projeção falhar.
            try:
                await db.enrollments.update_one(
                    {"id": enrollment["id"]},
                    {
                        "$set": {"status": "active"},
                        "$unset": {
                            "cancellation_reason": "",
                            "cancellation_date": "",
                            "cancelled_by": "",
                        },
                    },
                )
            finally:
                raise

    return {
        "enrollment": enrollment,
        "is_special": special,
        "program": class_program(class_doc) or "regular",
        "cancelled_at": now,
    }
