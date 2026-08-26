"""Generalização segura da ponte histórica de Frequência e Notas no DVD.

Mantém os adaptadores existentes como fallback conservador e substitui apenas a
função interna que revalida a origem legada. O runtime passa a aceitar as ondas
de cutover explicitamente aprovadas pelo serviço compartilhado, sem retrodatação
de ``valid_from`` e sem escrita em MongoDB.
"""

from __future__ import annotations

from services.diary_assignment_contract import AttendanceMode, AttendancePurpose
from services.dvd_cutover_legacy_provenance import (
    resolve_validated_cutover_legacy_assignment,
)


def install_dvd_historical_bridge_generalization(
    attendance_tabs_mod,
    grades_parity_mod,
) -> None:
    """Instala uma única política fail-closed nos dois consumidores históricos."""
    attendance_installed = getattr(
        attendance_tabs_mod,
        "_dvd_historical_cutover_generalization_installed",
        False,
    )
    grades_installed = getattr(
        grades_parity_mod,
        "_dvd_historical_cutover_generalization_installed",
        False,
    )
    if attendance_installed and grades_installed:
        return

    async def attendance_safe_cutover_legacy_assignment(db, context, academic_year):
        if context.attendance_mode is not AttendanceMode.CLASS_DAILY:
            return None
        if context.attendance_purpose is not AttendancePurpose.OFFICIAL:
            return None

        assignment = context.assignment
        return await resolve_validated_cutover_legacy_assignment(
            db,
            assignment,
            academic_year,
            expected_class_id=assignment.get("class_id"),
            expected_component_id=assignment.get("component_id"),
        )

    async def grades_safe_cutover_legacy_assignment(db, context, academic_year):
        assignment = context.assignment
        return await resolve_validated_cutover_legacy_assignment(
            db,
            assignment,
            academic_year,
            expected_class_id=context.class_id,
            expected_component_id=context.course_id,
        )

    attendance_tabs_mod._safe_cutover_legacy_assignment = (
        attendance_safe_cutover_legacy_assignment
    )
    grades_parity_mod._safe_cutover_legacy_assignment = (
        grades_safe_cutover_legacy_assignment
    )

    attendance_tabs_mod._dvd_historical_cutover_generalization_installed = True
    grades_parity_mod._dvd_historical_cutover_generalization_installed = True
