from pathlib import Path
import importlib.util
import sys


BACKEND = Path(__file__).parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SCRIPT = BACKEND / "scripts" / "p0_250_f2_8_global_dvd_reconciliation_audit.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_8", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(teacher, clazz, classification):
    return {
        "teacher_key": teacher,
        "class_key": clazz,
        "classification": classification,
        "invalid_reason_counts": {},
    }


def test_case_7_dvd_plus_2_legacy_is_generic_partial_cutover():
    rows = [row("t1", "c1", "CANONICAL_COVERED") for _ in range(7)]
    rows += [row("t1", "c1", "PARTIAL_CUTOVER_COMPONENT_MISSING") for _ in range(2)]

    analysis = module.summarize(rows)

    assert analysis["classification"] == "GLOBAL_DVD_PARTIAL_CUTOVER_PRESENT"
    assert analysis["teacher_class_classification_counts"]["PARTIAL_CUTOVER"] == 1
    assert analysis["canonical_component_pairs"] == 7
    assert analysis["unresolved_eligible_component_pairs"] == 2


def test_other_professor_6_dvd_plus_3_legacy_is_also_detected():
    rows = [row("t2", "c2", "CANONICAL_COVERED") for _ in range(6)]
    rows += [row("t2", "c2", "PARTIAL_CUTOVER_COMPONENT_MISSING") for _ in range(3)]

    analysis = module.summarize(rows)

    assert analysis["teacher_class_classification_counts"]["PARTIAL_CUTOVER"] == 1
    assert analysis["canonical_component_pairs"] == 6
    assert analysis["unresolved_eligible_component_pairs"] == 3


def test_full_canonical_group_is_clean():
    rows = [row("t1", "c1", "CANONICAL_COVERED") for _ in range(9)]

    analysis = module.summarize(rows)

    assert analysis["classification"] == "GLOBAL_DVD_RECONCILIATION_CLEAN"
    assert analysis["teacher_class_classification_counts"]["FULL_CANONICAL"] == 1
    assert analysis["unresolved_eligible_component_pairs"] == 0


def test_legacy_only_class_is_not_partial_without_any_canonical_component():
    rows = [row("t1", "c1", "LEGACY_ONLY_CLASS") for _ in range(9)]

    analysis = module.summarize(rows)

    assert analysis["classification"] == "GLOBAL_DVD_RECONCILIATION_REQUIRED"
    assert analysis["teacher_class_classification_counts"]["LEGACY_ONLY"] == 1


def test_duplicates_and_invalid_rows_require_review():
    rows = [
        row("t1", "c1", "CANONICAL_COVERED"),
        row("t1", "c1", "DVD_DUPLICATE_COVERAGE"),
        row("t2", "c2", "DVD_PRESENT_INVALID"),
    ]

    analysis = module.summarize(rows)

    assert analysis["teacher_class_classification_counts"]["REQUIRES_REVIEW"] == 2
    assert analysis["classification"] == "GLOBAL_DVD_RECONCILIATION_REQUIRED"


def test_out_of_scope_classes_do_not_count_as_dvd_gap():
    rows = [row("t1", "c1", "OUT_OF_DVD_SCOPE") for _ in range(4)]

    analysis = module.summarize(rows)

    assert analysis["dvd_eligible_component_pairs"] == 0
    assert analysis["teacher_class_classification_counts"]["OUT_OF_DVD_SCOPE"] == 1
    assert analysis["unresolved_eligible_component_pairs"] == 0


def test_mixed_global_population_preserves_all_group_states():
    rows = [row("a", "1", "CANONICAL_COVERED") for _ in range(9)]
    rows += [row("b", "2", "CANONICAL_COVERED") for _ in range(7)]
    rows += [row("b", "2", "PARTIAL_CUTOVER_COMPONENT_MISSING") for _ in range(2)]
    rows += [row("c", "3", "LEGACY_ONLY_CLASS") for _ in range(5)]
    rows += [row("d", "4", "OUT_OF_DVD_SCOPE") for _ in range(3)]

    analysis = module.summarize(rows)

    states = analysis["teacher_class_classification_counts"]
    assert states["FULL_CANONICAL"] == 1
    assert states["PARTIAL_CUTOVER"] == 1
    assert states["LEGACY_ONLY"] == 1
    assert states["OUT_OF_DVD_SCOPE"] == 1
    assert analysis["classification"] == "GLOBAL_DVD_PARTIAL_CUTOVER_PRESENT"
