import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f6_4_math_without_teacher_filter_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f6_4", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_scope_is_exact():
    assert mod.ACADEMIC_YEAR == 2026
    assert mod.TARGET_CLASSES == ("8º ANO A", "9º ANO A")
    assert mod.TARGET_COMPONENT == "Matemática"
    assert mod.START_DATE == "2026-02-01"
    assert mod.END_DATE == "2026-05-01"


def test_primary_selection_does_not_filter_teacher():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'collection.find({"class_id": class_id}, ROW_PROJECTION)' in source
    assert "# Autoria é resolvida somente DEPOIS da seleção acima." in source
    selection = source.split("# CRÍTICO: seleção por turma, data e identidade Matemática; nenhum filtro docente.", 1)[1]
    selection = selection.split("# Autoria é resolvida somente DEPOIS da seleção acima.", 1)[0]
    for field in mod.ACTOR_FIELDS:
        assert f'"{field}"' not in selection
    assert '"assignment_id"' not in selection


def test_actor_partition_can_detect_missing_binding():
    actor_ids = {"teacher-x", "staff-x"}
    assignment_ids = {"assignment-x"}
    assert mod._actor_category({}, actor_ids, assignment_ids) == "NO_ACTOR_OR_ASSIGNMENT_METADATA"
    assert mod._actor_category({"recorded_by": "teacher-x"}, actor_ids, assignment_ids) == "LUIZ_EXPLICIT_ACTOR"
    assert mod._actor_category({"assignment_id": "assignment-x"}, actor_ids, assignment_ids) == "LUIZ_ASSIGNMENT_ONLY"
    assert mod._actor_category({"teacher_id": "other"}, actor_ids, assignment_ids) == "OTHER_EXPLICIT_ACTOR"
    assert mod._actor_category({"assignment_id": "other"}, actor_ids, assignment_ids) == "OTHER_OR_UNKNOWN_ASSIGNMENT_ONLY"
    assert mod._actor_category(
        {"teacher_id": "other", "assignment_id": "assignment-x"}, actor_ids, assignment_ids
    ) == "FOREIGN_EXPLICIT_ACTOR_WITH_LUIZ_ASSIGNMENT"


def test_period_supports_string_and_datetime():
    from datetime import datetime

    assert mod._in_period({"date": "2026-02-01"})
    assert mod._in_period({"date": datetime(2026, 4, 30, 12, 0)})
    assert not mod._in_period({"date": "2026-01-31"})
    assert not mod._in_period({"date": "2026-05-01"})


def test_projection_excludes_pedagogical_and_student_payloads():
    forbidden = {
        "content", "methodology", "observations", "resources", "records",
        "student_id", "enrollment_id", "grade", "score",
    }
    assert not (forbidden & set(mod.ROW_PROJECTION))


def test_output_contract_declares_strict_boundaries():
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        '"selection_teacher_filter_used": False',
        '"pedagogical_plaintext_read": False',
        '"pedagogical_plaintext_emitted": False',
        '"attendance_read": False',
        '"attendance_records_read": False',
        '"student_data_read": False',
        '"grades_read": False',
        '"technical_ids_emitted": False',
        '"database_mutation": False',
        '"production_writes": False',
    ):
        assert marker in source
