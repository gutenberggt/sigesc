import importlib.util
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_r1_0a_reconstructibility_preflight_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_r1_0a", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def classify(*, attendance=False, content=None, audit=None, snapshot=None):
    return mod._classify_day(
        attendance_anchor=attendance,
        content_states=Counter(content or {}),
        audit_states=Counter(audit or {}),
        snapshot_states=Counter(snapshot or {}),
    )


def test_attendance_anchor_only():
    assert classify(attendance=True) == (
        "ATTENDANCE_ANCHOR_ONLY",
        "math_attendance_attributable_to_luiz_without_content_evidence",
    )


def test_luiz_metadata_is_not_exact_recovery():
    classification, reason = classify(content={"LUIZ": 1})
    assert classification == "RECOVERABLE_METADATA_ONLY"
    assert "without_preserved_payload" in reason


def test_foreign_actor_fails_closed_as_conflict():
    assert classify(attendance=True, content={"FOREIGN": 1})[0] == "CONFLICTING_EVIDENCE"
    assert classify(snapshot={"FOREIGN": 1})[0] == "CONFLICTING_EVIDENCE"


def test_unattributed_snapshot_does_not_upgrade_recoverability():
    assert classify(attendance=True, snapshot={"UNATTRIBUTED": 1})[0] == "ATTENDANCE_ANCHOR_ONLY"
    assert classify(snapshot={"UNATTRIBUTED": 1})[0] == "NO_EVIDENCE"


def test_no_evidence():
    assert classify()[0] == "NO_EVIDENCE"


def test_projection_boundaries():
    assert "records" not in mod.ATTENDANCE_PROJECTION
    forbidden_payload = {"content", "methodology", "observations", "resources", "attendance_records"}
    assert not forbidden_payload.intersection(mod.CONTENT_PROJECTION)
    assert not forbidden_payload.intersection(mod.SNAPSHOT_PROJECTION)


def test_scope_is_surgical():
    assert mod.TARGET_CLASSES == ("8º ANO A", "9º ANO A")
    assert mod.TARGET_COMPONENT == "Matemática"
    assert mod.START_DATE == "2026-02-01"
    assert mod.END_DATE == "2026-05-01"


def test_static_source_has_no_mongo_mutators_or_student_stores():
    source = SCRIPT.read_text(encoding="utf-8")
    for token in (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
        "db.students", "db.enrollments", "db.grades",
    ):
        assert token not in source
