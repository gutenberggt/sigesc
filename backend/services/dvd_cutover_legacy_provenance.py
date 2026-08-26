"""Validação fail-closed da origem legada de cutovers DVD.

A vigência técnica de ``teacher_class_assignments.valid_from`` não deve ser
retrodatada para representar lotação pedagógica anterior ao cutover. Quando um
consumidor precisa apresentar histórico anterior a essa fronteira técnica, este
serviço permite usar a origem legada apenas como prova de continuidade, sem
alterar qualquer documento.

A fase de cutover é somente um gate inicial. A autorização histórica exige,
adicionalmente:
- ``apply_state=ACTIVATED``;
- ``source_legacy_assignment_id``;
- vínculo legado ativo no ano letivo;
- mesma turma e mesmo componente;
- identidade staff -> user revalidada, com fallback legado por e-mail.

Qualquer divergência retorna ``None``. Este módulo é estritamente READ-ONLY.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional


APPROVED_HISTORICAL_CUTOVER_PHASES = frozenset({
    "38G-B",
    "SECOND_WAVE_2A-B",
    "SECOND_WAVE_2B",
    "SECOND_WAVE_2C",
    "SECOND_WAVE_2D_J",
})


def is_approved_historical_cutover(assignment: Mapping[str, Any]) -> bool:
    """Aceita somente cutover conhecido, ativado e com origem legada explícita."""
    provenance = assignment.get("cutover_provenance") or {}
    return bool(
        provenance.get("source_legacy_assignment_id")
        and provenance.get("apply_state") == "ACTIVATED"
        and provenance.get("apply_phase") in APPROVED_HISTORICAL_CUTOVER_PHASES
    )


async def _legacy_staff_matches_teacher(
    db,
    legacy: Mapping[str, Any],
    teacher_id: str,
) -> bool:
    staff_id = legacy.get("staff_id")
    if not staff_id or not teacher_id:
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


async def resolve_validated_cutover_legacy_assignment(
    db,
    assignment: Mapping[str, Any],
    academic_year: int,
    *,
    expected_class_id: Optional[str] = None,
    expected_component_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Revalida a origem legada sem alterar a vigência ou autoria do DVD.

    ``expected_class_id`` e ``expected_component_id`` permitem que cada domínio
    use o próprio contexto já autorizado como âncora. Se o contexto divergir dos
    campos persistidos no assignment, a revalidação falha fechado. Retorna o
    documento legado somente quando toda a cadeia de proveniência é consistente.
    """
    if not is_approved_historical_cutover(assignment):
        return None

    provenance = assignment.get("cutover_provenance") or {}
    source_id = provenance.get("source_legacy_assignment_id")
    assignment_class_id = assignment.get("class_id")
    assignment_component_id = assignment.get("component_id")

    if expected_class_id is not None and expected_class_id != assignment_class_id:
        return None
    if (
        expected_component_id is not None
        and expected_component_id != assignment_component_id
    ):
        return None

    class_id = assignment_class_id
    component_id = assignment_component_id
    if not source_id or not class_id:
        return None

    legacy = await db.teacher_assignments.find_one(
        {
            "id": source_id,
            "class_id": class_id,
            "course_id": component_id,
            "status": "ativo",
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {"_id": 0},
    )
    if not legacy:
        return None

    teacher_id = str(assignment.get("teacher_id") or "")
    if not await _legacy_staff_matches_teacher(db, legacy, teacher_id):
        return None

    return legacy
