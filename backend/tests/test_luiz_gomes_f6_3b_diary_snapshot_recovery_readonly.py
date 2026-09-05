import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f6_3b_diary_snapshot_recovery_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f6_3b", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_scope_is_exact():
    assert mod.TARGET_CLASSES == ("8º ANO A", "9º ANO A")
    assert mod.START_DATE == "2026-02-01"
    assert mod.END_DATE == "2026-04-30"


def test_projection_excludes_sensitive_snapshot_payload():
    joined = "\n".join(mod.SNAPSHOT_PROJECTION.keys())
    for field in mod.FORBIDDEN_SNAPSHOT_FIELDS:
        assert field not in joined


def test_period_overlap():
    assert mod._overlaps_target("2026-01-01", "2026-02-10") is True
    assert mod._overlaps_target("2026-04-20", "2026-05-10") is True
    assert mod._overlaps_target("2026-05-01", "2026-05-31") is False


def test_entry_matches_luiz_math_by_ids():
    entry = {"component_id": "math", "teacher_id": "luiz"}
    assert mod._entry_is_luiz_math(entry, teacher_user_id="luiz", math_course_id="math") is True


def test_entry_matches_luiz_math_by_names():
    entry = {"component_name": "Matemática", "teacher_name": "Luiz Gomes dos Santos"}
    assert mod._entry_is_luiz_math(entry, teacher_user_id="luiz", math_course_id="math") is True


def test_content_entry_id_is_strongest_frozen_evidence():
    assert mod._content_evidence_strength({"content_entry_id": "x", "content_status": "missing"}) == "CONTENT_ENTRY_ID_FROZEN"


def test_nonmissing_content_status_is_secondary_frozen_evidence():
    assert mod._content_evidence_strength({"content_status": "published"}) == "CONTENT_STATUS_FROZEN"
    assert mod._content_evidence_strength({"content_status": "missing"}) == "NO_CONTENT_EVIDENCE"


def test_institutional_snapshot_classification_is_strong():
    evidence = [{"content_present": True, "institutional_snapshot": True}]
    assert mod._classify(1, evidence) == ["INSTITUTIONAL_DIARY_SNAPSHOT_MATH_CONTENT_CONFIRMED"]


def test_draft_snapshot_is_not_promoted_to_institutional():
    evidence = [{"content_present": True, "institutional_snapshot": False}]
    assert mod._classify(1, evidence) == ["DRAFT_DIARY_SNAPSHOT_MATH_CONTENT_EVIDENCE"]


def test_snapshot_without_content_does_not_claim_recovery():
    evidence = [{"content_present": False, "institutional_snapshot": True}]
    assert mod._classify(1, evidence) == ["DIARY_SNAPSHOT_MATH_EXPECTATION_WITHOUT_CONTENT"]


def test_no_snapshot_is_explicit():
    assert mod._classify(0, []) == ["NO_DIARY_SNAPSHOT_COVERING_TARGET_PERIOD"]
