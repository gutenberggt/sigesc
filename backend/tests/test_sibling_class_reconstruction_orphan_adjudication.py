from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
MIRROR = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_mirror_policy.py"
GLOBAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_global_ordinal_policy.py"
ORPHAN = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_orphan_adjudication.py"

ns = {"__name__": "r2c_test_module"}
for path in (BASE, MIRROR, GLOBAL, ORPHAN):
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)


def test_safe_attendance_meta_never_emits_ids_or_observation_text():
    row = {
        "id": "raw-id",
        "assignment_id": "raw-assignment",
        "date": "2026-04-30",
        "number_of_classes": 2,
        "period": "matutino",
        "aula_numero": 4,
        "version": 3,
        "observations": "texto que nao deve sair",
        "created_at": "2026-05-01T10:00:00",
        "updated_at": "2026-05-02T10:00:00",
    }
    safe = ns["_safe_attendance_meta"](row)
    assert safe == {
        "date": "2026-04-30",
        "number_of_classes": 2,
        "period_present": True,
        "aula_numero_present": True,
        "version": 3,
        "observations_present": True,
        "created_at_day": "2026-05-01",
        "updated_at_day": "2026-05-02",
    }
    assert "raw-id" not in repr(safe)
    assert "raw-assignment" not in repr(safe)
    assert "texto que nao deve sair" not in repr(safe)


def test_orphan_projection_explicitly_excludes_records():
    projection = ns["ORPHAN_ATTENDANCE_PROJECTION"]
    assert "records" not in projection
    assert projection.get("number_of_classes") == 1
    assert projection.get("aula_numero") == 1


def test_boundary_window_is_short_and_readonly_by_contract():
    assert ns["ORPHAN_DATE"] == "2026-04-30"
    assert ns["BOUNDARY_LOOKAHEAD_END"] == "2026-05-15"


def test_script_contains_no_mongo_write_primitives():
    source = ORPHAN.read_text(encoding="utf-8")
    for forbidden in (
        "insert_one(",
        "insert_many(",
        "update_one(",
        "update_many(",
        "replace_one(",
        "delete_one(",
        "delete_many(",
        "bulk_write(",
        "find_one_and_update(",
        "find_one_and_replace(",
        "find_one_and_delete(",
    ):
        assert forbidden not in source


def test_orphan_policy_never_reads_attendance_records():
    source = ORPHAN.read_text(encoding="utf-8")
    assert '"records"' not in source
    assert "['records']" not in source
    assert '["records"]' not in source


def test_classification_vocabulary_is_explicit_and_fail_closed():
    source = ORPHAN.read_text(encoding="utf-8")
    for token in (
        "ORPHAN_STATE_CHANGED_REVIEW_REQUIRED",
        "ORPHAN_ATTENDANCE_DUPLICATE_OR_AMBIGUOUS",
        "ORPHAN_BOUNDARY_SHIFT_NEXT_SOURCE_AVAILABLE",
        "ORPHAN_EXTRA_SESSION_METADATA_SUPPORTED",
        "ORPHAN_ADJUDICATION_INCONCLUSIVE",
    ):
        assert token in source
    assert "BLOCK_ORPHAN_ONLY" in source
