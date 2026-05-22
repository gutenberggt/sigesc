"""
Legacy Content Bridge — camada de compatibilidade (Fev/2026).

Quando uma turma NÃO possui lançamentos em `content_entries` (modelo novo),
este serviço lê de `learning_objects` (modelo legacy) e devolve documentos
no shape esperado pelo Diário.

Espelha exatamente o Legacy Schedule Bridge (services/legacy_schedule_bridge.py):
  - Read-only. Não move dados.
  - Modelo novo SEMPRE TEM PRIORIDADE absoluta.
  - Sem merge, sem sincronização, sem repair.
  - Marca saída com `source="legacy_content_bridge"` e `synthetic_validity=True`.

Mapeamento learning_objects → content_entries:
  course_id           → component_id (e course_id preservado)
  recorded_by         → teacher_id
  content             → content
  methodology         → methodology
  observations        → observations
  number_of_classes   → number_of_classes (campo extra; usado por fan-out)
  status              → "published" (legacy já consolidado)
  version             → 1
  deleted             → False
  aula_numero         → None (legacy não tem; fan-out flexível resolve)

ALCANCE: usado em
  - `routers/calendar_diary_state.py` (UI operacional)
  - `services/diary_snapshot_service.py` (snapshot imutável)
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


async def build_content_entries_from_legacy(
    db, *, class_id: str, dates_in_range: Iterable[str],
) -> list[dict]:
    """Constrói lista de content_entries sintéticos a partir de learning_objects.

    Args:
      db: motor database handle.
      class_id: ID da turma.
      dates_in_range: iterable de datas ISO (yyyy-mm-dd) do período.

    Returns:
      Lista no shape esperado pelo Diário. Vazia se não há learning_objects.
    """
    dates_list = list(dates_in_range)
    if not class_id or not dates_list:
        return []

    cursor = db.learning_objects.find(
        {"class_id": class_id, "date": {"$in": dates_list}},
        {"_id": 0},
    )
    raw_docs = await cursor.to_list(5000)
    if not raw_docs:
        return []

    bridged: list[dict] = []
    for lo in raw_docs:
        course_id = lo.get("course_id")
        bridged.append({
            "id": lo["id"],
            "class_id": lo.get("class_id"),
            "date": lo.get("date"),
            "academic_year": lo.get("academic_year"),
            "mantenedora_id": lo.get("mantenedora_id"),
            "aula_numero": None,
            "component_id": course_id,
            "course_id": course_id,
            "teacher_id": lo.get("recorded_by"),
            "status": "published",
            "version": 1,
            "deleted": False,
            "content": lo.get("content"),
            "methodology": lo.get("methodology"),
            "observations": lo.get("observations"),
            "resources": lo.get("resources"),
            "number_of_classes": lo.get("number_of_classes"),
            "created_by": lo.get("recorded_by"),
            "created_at": lo.get("created_at"),
            "updated_at": lo.get("updated_at"),
            # Marcadores institucionais
            "source": "legacy_content_bridge",
            "synthetic_validity": True,
        })

    logger.info(
        "[legacy_content_bridge] legacy_content_bridge_used=True "
        "class_id=%s docs_built=%d",
        class_id, len(bridged),
    )

    return bridged
