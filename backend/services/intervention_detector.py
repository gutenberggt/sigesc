"""Compatibilidade do detector de Intervenções Curriculares.

S5.5 substitui o motor legado pela política institucional baseada exclusivamente
na Cobertura Curricular F5 e em dias letivos reais.

O nome público `run_intervention_detection` é preservado porque o router e o
scheduler existentes dependem dele. A implementação canônica vive em
`services.curriculum_coverage_alerts_s5`.
"""
from __future__ import annotations

from typing import Optional

from services.curriculum_coverage_alerts_s5 import (
    run_curriculum_coverage_alert_detection,
)


async def run_intervention_detection(
    db,
    academic_year: Optional[int] = None,
    *,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Executa a S5.5 preservando o contrato histórico do chamador."""
    return await run_curriculum_coverage_alert_detection(
        db,
        academic_year=academic_year,
        tenant_id=mantenedora_id,
    )
