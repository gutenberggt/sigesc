"""Boundary de leitura mínima para consumidores institucionais de Conteúdo.

Os consumidores de reporting precisam apenas de metadados estruturais para
contagem, carga, atraso e deduplicação. Este proxy impede que o read model S1
carregue texto pedagógico ou outros campos desnecessários das duas fontes.
"""
from __future__ import annotations

from typing import Any


REPORTING_CONTENT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "mantenedora_id": 1,
    "academic_year": 1,
    "class_id": 1,
    "component_id": 1,
    "course_id": 1,
    "teacher_id": 1,
    "recorded_by": 1,
    "date": 1,
    "number_of_classes": 1,
    "created_at": 1,
    "aula_numero": 1,
    "deleted": 1,
}


class StructuralContentCollection:
    """Força projeção allow-list independentemente da projeção pedida pelo S1."""

    def __init__(self, inner: Any):
        self._inner = inner

    def find(self, query, _projection=None):
        return self._inner.find(query, REPORTING_CONTENT_PROJECTION)


class StructuralReportingDb:
    """Proxy transparente do DB, restringindo somente as coleções de conteúdo."""

    def __init__(self, inner: Any):
        self._inner = inner
        self.content_entries = StructuralContentCollection(inner.content_entries)
        self.learning_objects = StructuralContentCollection(inner.learning_objects)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def structural_reporting_db(db: Any) -> StructuralReportingDb:
    if isinstance(db, StructuralReportingDb):
        return db
    return StructuralReportingDb(db)
