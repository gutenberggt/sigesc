"""Contrato do boundary mínimo de leitura do Reporting de Conteúdo."""
from pathlib import Path
from types import SimpleNamespace

from services.content_reporting_structural_db import (
    REPORTING_CONTENT_PROJECTION,
    StructuralReportingDb,
    structural_reporting_db,
)


class InnerCollection:
    def __init__(self):
        self.calls = []

    def find(self, query, projection=None):
        self.calls.append((query, projection))
        return "cursor"


def test_allowlist_contem_apenas_metadados_estruturais_necessarios():
    required = {
        "id", "mantenedora_id", "academic_year", "class_id", "component_id",
        "course_id", "teacher_id", "recorded_by", "date", "number_of_classes",
        "created_at", "aula_numero", "deleted",
    }
    assert {key for key, enabled in REPORTING_CONTENT_PROJECTION.items() if enabled} == required
    for forbidden in (
        "content", "description", "objects", "skills", "observations",
        "curriculum_links", "student_id", "grades", "attendance",
    ):
        assert forbidden not in REPORTING_CONTENT_PROJECTION


def test_proxy_forca_allowlist_nas_duas_fontes_e_preserva_demais_colecoes():
    canonical = InnerCollection()
    legacy = InnerCollection()
    classes = object()
    inner = SimpleNamespace(
        content_entries=canonical,
        learning_objects=legacy,
        classes=classes,
    )
    wrapped = structural_reporting_db(inner)

    assert isinstance(wrapped, StructuralReportingDb)
    assert wrapped.classes is classes
    assert wrapped.content_entries.find({"x": 1}, {"_id": 0}) == "cursor"
    assert wrapped.learning_objects.find({"y": 2}, {"_id": 0, "content": 1}) == "cursor"
    assert canonical.calls[0][1] == REPORTING_CONTENT_PROJECTION
    assert legacy.calls[0][1] == REPORTING_CONTENT_PROJECTION


def test_proxy_e_idempotente():
    inner = SimpleNamespace(
        content_entries=InnerCollection(),
        learning_objects=InnerCollection(),
    )
    first = structural_reporting_db(inner)
    assert structural_reporting_db(first) is first


def test_dashboard_aplica_boundary_antes_do_read_model():
    source = Path("services/content_reporting_dashboard_s5.py").read_text(encoding="utf-8")
    assert "structural_reporting_db(db)" in source
    assert "list_reporting_content_shadow(\n        reporting_db," in source
    assert "resolve_content_reporting_cutover_scopes(\n        reporting_db," in source
