"""SSoT da prova histórica 38G-B para Notas/Conceitos no DVD.

Esta camada não escreve em ``grades`` nem altera ``teacher_class_assignments``.
Ela apenas revalida a continuidade pedagógica entre o vínculo DVD atual e a
``teacher_assignment`` legada indicada por ``cutover_provenance``.

A mesma prova é consumida por:
- projeção histórica/read-only de Notas;
- autorização estritamente retroativa de novos lançamentos pré-cutover;
- guards de regressão.

O ``valid_from`` persistido do DVD nunca é retrodatado. Escrita histórica só é
candidata quando o período pedagógico inteiro termina antes do ``valid_from``
técnico e o vínculo 38G-B permanece revalidável por professor, turma,
componente, ano e status.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Mapping, Optional


LEGACY_HISTORY_FLAG = "legacy_grade_history_read"
LEGACY_SOURCE_FLAG = "legacy_grade_source_assignment_id"
LEGACY_YEAR_FLAG = "legacy_grade_history_academic_year"

HISTORICAL_WRITE_FLAG = "historical_grade_write"
HISTORICAL_WRITE_SOURCE = "cutover_38g_b_legacy_assignment"
HISTORICAL_WRITE_SOURCE_FLAG = "historical_grade_source_legacy_assignment_id"
HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG = "historical_grade_authorized_from"
HISTORICAL_WRITE_PERIOD_FLAG = "historical_grade_period"
HISTORICAL_WRITE_PERIOD_START_FLAG = "historical_grade_period_start"
HISTORICAL_WRITE_PERIOD_END_FLAG = "historical_grade_period_end"


async def legacy_staff_matches_teacher(
    db,
    legacy: Mapping[str, Any],
    teacher_id: str,
) -> bool:
    """Confirma que o ``staff_id`` legado pertence ao mesmo usuário do DVD."""
    staff_id = legacy.get("staff_id")
    if not staff_id:
        return False

    staff = await db.staff.find_one(
        {"id": staff_id},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    if not staff:
        return False

    if staff.get("user_id"):
        return str(staff.get("user_id")) == str(teacher_id)

    email = str(staff.get("email") or "").strip()
    if not email:
        return False

    user = await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    return bool(user and str(user.get("id")) == str(teacher_id))


async def safe_cutover_legacy_assignment(
    db,
    context,
    academic_year: int,
) -> Optional[dict[str, Any]]:
    """Revalida a origem 38G-B sem transformar legado em nova autoridade.

    Retorna a ``teacher_assignment`` legada apenas quando:
    - ``apply_phase == 38G-B``;
    - ``apply_state == ACTIVATED``;
    - ``source_legacy_assignment_id`` existe;
    - turma, componente, ano e status coincidem;
    - o ``staff`` legado resolve para o mesmo ``teacher_id`` do DVD.
    """
    assignment = context.assignment
    provenance = assignment.get("cutover_provenance") or {}
    source_id = provenance.get("source_legacy_assignment_id")

    if (
        not source_id
        or provenance.get("apply_phase") != "38G-B"
        or provenance.get("apply_state") != "ACTIVATED"
    ):
        return None

    legacy = await db.teacher_assignments.find_one(
        {
            "id": source_id,
            "class_id": context.class_id,
            "course_id": context.course_id,
            "status": "ativo",
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {"_id": 0},
    )
    if not legacy:
        return None

    if not await legacy_staff_matches_teacher(
        db,
        legacy,
        str(assignment.get("teacher_id") or ""),
    ):
        return None

    return legacy


async def decorate_context_with_legacy_history(
    db,
    context,
    academic_year: int,
):
    """Marca contexto de leitura quando a continuidade 38G-B foi comprovada."""
    if context is None:
        return None

    legacy = await safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy:
        return context

    snapshot = dict(context.snapshot)
    snapshot[LEGACY_HISTORY_FLAG] = True
    snapshot[LEGACY_SOURCE_FLAG] = legacy.get("id")
    snapshot[LEGACY_YEAR_FLAG] = int(academic_year)
    return replace(context, snapshot=snapshot)


async def historical_grade_write_evidence(
    db,
    context,
    *,
    field: str,
    period_number: int,
    period: tuple[str, str],
) -> Optional[dict[str, Any]]:
    """Resolve evidência para uma escrita estritamente anterior ao cutover.

    Esta função não substitui RBAC, tenant, capability, shared owner nem escopo de
    estudante. Ela só pode ser chamada depois que o ``GradeAssignmentContext``
    vivo foi autorizado. Além disso:
    - exige propriedade pedagógica do assignment atual;
    - não atravessa ``valid_until``;
    - não libera período que apenas encoste/intersecte o ``valid_from``;
    - revalida a origem legada no ano institucional do período.
    """
    if not getattr(context.access, "is_owner", False):
        return None

    valid_from = str(context.assignment.get("valid_from") or "")[:10]
    valid_until = str(context.assignment.get("valid_until") or "")[:10] or None
    if not valid_from:
        return None
    if valid_until and valid_until < valid_from:
        return None

    start = str(period[0] or "")[:10]
    end = str(period[1] or "")[:10]
    if not start or not end or start > end:
        return None

    # Ponte estritamente retroativa: se o período encosta ou ultrapassa o
    # ``valid_from``, a regra normal de interseção deve decidir a autorização.
    if end >= valid_from:
        return None

    if len(start) < 4 or len(end) < 4 or start[:4] != end[:4]:
        return None
    try:
        academic_year = int(start[:4])
    except ValueError:
        return None

    legacy = await safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy:
        return None

    return {
        HISTORICAL_WRITE_FLAG: True,
        "historical_grade_write_source": HISTORICAL_WRITE_SOURCE,
        HISTORICAL_WRITE_SOURCE_FLAG: legacy.get("id"),
        HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG: valid_from,
        HISTORICAL_WRITE_PERIOD_FLAG: int(period_number),
        HISTORICAL_WRITE_PERIOD_START_FLAG: start,
        HISTORICAL_WRITE_PERIOD_END_FLAG: end,
        LEGACY_YEAR_FLAG: academic_year,
    }
