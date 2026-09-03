from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f2_runtime_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_target_contract_is_exact_school_six_math_pairs():
    assert mod.ACADEMIC_YEAR == 2026
    assert mod.TEACHER_NAME == "Luiz Gomes dos Santos"
    assert mod.TARGET_SCHOOL == "E M E I E F Jose Pereira Barbosa"
    assert len(mod.TARGET_PAIRS) == 6
    assert [name for name, _ in mod.TARGET_PAIRS] == [
        "6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"
    ]
    assert all(component == "Matemática" for _, component in mod.TARGET_PAIRS)


def test_reuses_homologated_f2_1_runtime_engine():
    assert mod.base.__name__ == "ana_lucia_f2_1_runtime_engine"
    assert callable(mod.base.classify_content)
    assert callable(mod.base.classify_attendance)


def test_runtime_engine_classifies_content_http_parity():
    mongo = {
        "total": 10,
        "target_tenant": 10,
        "missing_tenant": 0,
        "academic_year_int": 10,
        "academic_year_string": 0,
    }
    result = mod.base.classify_content(
        mongo,
        {"status": 200, "count": 10},
        {"status": 200, "count": 10},
        component_exposed=True,
        content_diaries=0,
    )
    assert result == "CONTENT_REACHES_SCREEN"


def test_runtime_engine_classifies_attendance_http_zero_gap():
    mongo = {
        "collections": {
            "attendance": {"documents": 10, "distinct_dates": 5},
            "attendance_documentary": {"documents": 0},
        }
    }
    result = mod.base.classify_attendance(
        mongo,
        {"status": 200, "count": 0},
        {"status": 200, "count": 0},
        component_exposed=True,
        raw_dvd_year_rows=0,
        outside_dvd_scope=True,
    )
    assert result == "ATTENDANCE_HTTP_ZERO_WITH_MONGO_RECORDS"


def test_runtime_engine_classifies_role_parity_gap():
    mongo = {
        "collections": {
            "attendance": {"documents": 10, "distinct_dates": 5},
            "attendance_documentary": {"documents": 0},
        }
    }
    result = mod.base.classify_attendance(
        mongo,
        {"status": 200, "count": 3},
        {"status": 200, "count": 5},
        component_exposed=True,
        raw_dvd_year_rows=0,
        outside_dvd_scope=True,
    )
    assert result == "ATTENDANCE_ROLE_HTTP_PARITY_GAP"
