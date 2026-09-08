"""Contratos S4 para execução real read-only do shadow institucional."""
from datetime import date
import ast
import json
from pathlib import Path

from scripts.content_reporting_shadow_s4_readonly import (
    BLOCKING_CLASSIFICATIONS,
    STRUCTURAL_CONTENT_PROJECTION,
    StructuralCollection,
    _classification_counts,
    _sanitize_report,
    _windows,
)


def test_windows_preservam_semantica_por_consumidor():
    windows = _windows("2026-09-07")
    assert windows["DIARY_DASHBOARD_CONTENT"] == {
        "start_date": "2026-01-01",
        "end_date": "2026-09-07",
    }
    assert windows["MONTHLY_REPORT"] == {
        "start_date": "2026-09-01",
        "end_date": "2026-09-07",
    }
    assert windows["PMPI_LESSONS"] == {
        "start_date": "2026-08-09",
        "end_date": "2026-09-07",
    }
    assert windows["PMPI_DELAY"] == windows["PMPI_LESSONS"]
    assert windows["PMPI_WORKLOAD"]["start_date"] == "2026-01-01"


class _InnerCollection:
    def __init__(self):
        self.calls = []

    def find(self, query, projection):
        self.calls.append((query, projection))
        return "cursor"


def test_structural_collection_ignora_projection_ampla_e_nao_le_texto():
    inner = _InnerCollection()
    wrapped = StructuralCollection(inner)
    assert wrapped.find({"class_id": "c1"}, {"_id": 0}) == "cursor"
    _, projection = inner.calls[0]
    assert projection == STRUCTURAL_CONTENT_PROJECTION
    for forbidden in ("content", "description", "objects", "skills", "observations"):
        assert forbidden not in projection


def test_sanitizer_remove_ids_brutos_e_preserva_fingerprints_metricas_e_reconciliacao():
    reconciliation = {
        "record_count_identity": {
            "legacy_record_count": 2,
            "canonical_record_count": 2,
            "canonical_shadow_count": 2,
            "legacy_excluded_post_cutover": 1,
            "legacy_duplicate_suppressed": 0,
            "projected_record_count": 3,
            "expected_record_count_delta": 1,
            "observed_record_count_delta": 1,
            "canonical_count_exact": True,
            "delta_exact": True,
            "exact": True,
        },
        "metric_net_delta": 1.0,
        "driver_count": 2,
    }
    report = {
        "consumer": "DIARY_DASHBOARD_CONTENT",
        "code_sha": "a" * 40,
        "generated_at": "2026-09-08T01:00:00Z",
        "report_sha256": "b" * 64,
        "scope": {
            "mantenedora_id": "tenant-secret",
            "academic_year": 2026,
            "class_ids": ["class-secret"],
            "component_ids": ["component-secret"],
            "start_date": "2026-01-01",
            "end_date": "2026-09-07",
        },
        "filters": {"reference_date": "2026-09-07"},
        "cutover": {
            "scope_count": 1,
            "sha256": "c" * 64,
            "scopes": [
                {
                    "class_id": "class-secret",
                    "component_id": "component-secret",
                    "valid_from": "2026-08-01",
                }
            ],
        },
        "metrics": [
            {
                "metric": "record_count",
                "legacy": 2,
                "projected": 3,
                "delta": 1,
                "classification": "EXPECTED_CANONICAL_GAIN",
                "explanation": "ganho esperado",
                "reconciliation": reconciliation,
            }
        ],
        "classifications": ["EXPECTED_CANONICAL_GAIN"],
        "shadow": {"canonical_count": 2, "tenant_mismatch_rejected": 0},
        "resolver_diagnostics": {"classes_considered": 1},
        "errors": [],
    }
    sanitized = _sanitize_report(report)
    raw = json.dumps(sanitized, ensure_ascii=False)
    assert "tenant-secret" not in raw
    assert "class-secret" not in raw
    assert "component-secret" not in raw
    assert sanitized["tenant_fp"]
    assert sanitized["cutover"]["scopes"][0]["class_fp"]
    assert sanitized["metrics"][0]["delta"] == 1
    assert sanitized["metrics"][0]["reconciliation"] == reconciliation


def test_classification_counts_nao_trata_divergencia_esperada_como_bloqueio():
    reports = [
        {
            "metrics": [
                {"classification": "MATCH"},
                {"classification": "EXPECTED_CANONICAL_GAIN"},
                {"classification": "PROVENANCE_INCOMPARABLE"},
            ],
            "classifications": [],
        },
        {"metrics": [], "classifications": ["SCOPE_ERROR"]},
    ]
    counts = _classification_counts(reports)
    assert counts["MATCH"] == 1
    assert counts["EXPECTED_CANONICAL_GAIN"] == 1
    assert counts["PROVENANCE_INCOMPARABLE"] == 1
    assert counts["SCOPE_ERROR"] == 1
    assert BLOCKING_CLASSIFICATIONS == {"UNEXPECTED_DIFFERENCE", "SCOPE_ERROR", "ERROR"}


def test_coletor_s4_e_estritamente_read_only_e_sem_http():
    path = Path("scripts/content_reporting_shadow_s4_readonly.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
    }
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden:
                hits.append(node.func.attr)
    assert hits == []
    assert "requests." not in source
    assert "httpx." not in source
    assert "students" not in source
    assert "enrollments" not in source


def test_referencia_de_calendario_do_contrato_e_valida():
    assert date.fromisoformat("2026-09-07").year == 2026
