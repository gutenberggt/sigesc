import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f6_3_audit_log_recovery_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f6_3", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_scope_is_exact():
    assert mod.TARGET_CLASSES == ("8º ANO A", "9º ANO A")
    assert mod.START_DATE == "2026-02-01"
    assert mod.END_DATE == "2026-05-01"
    assert mod.CONTENT_COLLECTIONS == ("content_entries", "learning_objects")


def test_projection_does_not_read_pedagogical_plaintext():
    joined = "\n".join(mod.AUDIT_PROJECTION.keys())
    for field in mod.FORBIDDEN_AUDIT_FIELDS:
        assert field not in joined


def test_lesson_date_prefers_structured_extra_data():
    log = {
        "extra_data": {"date": "2026-03-12"},
        "description": "Criou conteúdo em 2026-04-01",
    }
    assert mod._lesson_date_from_log(log) == ("2026-03-12", "extra_data.date")


def test_lesson_date_can_fallback_to_description():
    log = {"description": "Criou conteúdo da turma 8º ANO A em 2026-04-22 (aula 2)"}
    assert mod._lesson_date_from_log(log) == ("2026-04-22", "description")


def test_event_context_strong_math_confirmation():
    log = {
        "action": "create",
        "collection": "content_entries",
        "user_id": "luiz-user",
        "timestamp": "2026-05-10T10:00:00+00:00",
        "extra_data": {
            "class_id": "class-8",
            "class_name": "8º ANO A",
            "date": "2026-02-10",
            "component_id": "math",
            "teacher_id": "luiz-user",
            "teacher_name": "Luiz Gomes dos Santos",
            "change_kind": "content_created",
        },
    }
    ctx = mod._event_context(
        log,
        target_classes={"8º ANO A": "class-8", "9º ANO A": "class-9"},
        course_by_id={"math": {"name": "Matemática"}},
        math_by_class={"8º ANO A": {"math"}, "9º ANO A": {"math"}},
        teacher_user_id="luiz-user",
    )
    assert ctx["evidence_strength"] == "STRONG_MATH_CONTEXT"
    assert ctx["math_component_match"] is True
    assert ctx["lesson_date"] == "2026-02-10"


def test_classification_requires_math_context_for_strong_confirmation():
    events = [{
        "action": "create",
        "change_kind": "content_created",
        "evidence_strength": "TARGET_CLASS_CONTENT_BY_LUIZ",
    }]
    assert mod._classify(events) == ["AUDIT_LOG_TARGET_CLASS_CONTENT_ACTIVITY_ONLY"]


def test_classification_confirms_create_in_math_context():
    events = [{
        "action": "create",
        "change_kind": "content_created",
        "evidence_strength": "STRONG_MATH_CONTEXT",
    }]
    assert mod._classify(events) == ["AUDIT_LOG_MATH_REGISTRATION_CONFIRMED"]


def test_month_counts_are_fixed():
    events = [
        {"lesson_date": "2026-02-10"},
        {"lesson_date": "2026-03-10"},
        {"lesson_date": "2026-03-11"},
        {"lesson_date": "2026-04-01"},
    ]
    assert mod._month_counts(events) == {"02": 1, "03": 2, "04": 1}
