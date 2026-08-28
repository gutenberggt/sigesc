from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_p0f7_4_curricular_compatibility.py"
spec = importlib.util.spec_from_file_location("p0f74", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_read_only_guard_passes():
    mod.assert_read_only()


def test_exact_level_match():
    assert mod.classify_level_compatibility("fundamental_anos_finais", "fundamental_anos_finais") == "EXACT_LEVEL_MATCH"


def test_eja_final_vs_fundamental_is_mismatch():
    assert mod.classify_level_compatibility("eja_final", "fundamental_anos_finais") == "LEVEL_MISMATCH"


def test_eja_final_accepts_broad_eja_only_as_review():
    assert mod.classify_level_compatibility("eja_final", "eja") == "BROAD_EJA_MATCH_REQUIRES_REVIEW"


def test_eja_vs_eja_final_is_specialized_review():
    assert mod.classify_level_compatibility("eja", "eja_final") == "SPECIALIZED_EJA_MATCH_REQUIRES_REVIEW"


def test_missing_class_level_is_unknown():
    assert mod.classify_level_compatibility(None, "fundamental_anos_finais") == "UNKNOWN_CLASS_LEVEL"


def test_missing_course_level_is_unknown():
    assert mod.classify_level_compatibility("eja_final", None) == "UNKNOWN_COURSE_LEVEL"


def test_explicit_class_level_prefers_education_level():
    row = {"education_level": "eja_final", "nivel_ensino": "fundamental_anos_finais"}
    assert mod._explicit_class_level(row) == "eja_final"


def test_explicit_class_level_falls_back_to_nivel_ensino():
    row = {"education_level": None, "nivel_ensino": "fundamental_anos_finais"}
    assert mod._explicit_class_level(row) == "fundamental_anos_finais"


def test_safe_course_does_not_expose_tenant_or_student_data():
    row = {
        "id": "c1", "name": "Geografia", "nivel_ensino": "eja_final",
        "grade_levels": ["3ª Etapa"], "workload": 120,
        "carga_horaria_por_serie": {"3ª Etapa": 120}, "active": True,
        "created_at": "2026-01-01", "mantenedora_id": "secret",
        "student_id": "forbidden",
    }
    out = mod._safe_course(row)
    assert out["course_id"] == "c1"
    assert "mantenedora_id" not in out
    assert "student_id" not in out


def test_phase_id_is_stable():
    assert mod.PHASE_ID == "P0F7.4-CURRICULAR-COMPATIBILITY-READ-ONLY-2026"


def test_no_apply_argument_surface():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--apply" not in source
    assert "production_writes_executed\": False" in source
