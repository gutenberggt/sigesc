from pathlib import Path
import importlib.util
import sys

BACKEND = Path(__file__).parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SCRIPT = BACKEND / "scripts" / "p0_250_f2_9a_global_dvd_reconciliation_plan.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_9a", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def dvd_row(**overrides):
    row = {
        "valid_from": "2026-02-01",
        "valid_until": None,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "is_substitute": False,
        "grades_official_owner": True,
        "shift": "matutino",
    }
    row.update(overrides)
    return row


def decision(teacher, clazz, component, value, reasons=None, target=None):
    return {
        "teacher_key": teacher,
        "class_key": clazz,
        "component_key": component,
        "decision": value,
        "review_reasons": reasons or [],
        "target_assignment": target,
    }


def test_unique_template_is_derived_only_from_equal_effective_envelopes():
    first = dvd_row()
    second = dvd_row(
        diary_settings={"enabled": True, "profile": "regular"},
    )

    template, error = module.derive_unique_template([first, second])

    assert error is None
    assert template == {
        "valid_from": "2026-02-01",
        "valid_until": None,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "is_substitute": False,
        "grades_official_owner": True,
        "shift": "matutino",
    }


def test_legacy_only_without_canonical_sibling_requires_review_template():
    template, error = module.derive_unique_template([])

    assert template is None
    assert error == "NO_CANONICAL_TEMPLATE"


def test_different_profile_or_validity_is_ambiguous_and_never_guessed():
    regular = dvd_row()
    shared = dvd_row(
        diary_settings={
            "enabled": True,
            "schema_version": 1,
            "profile": "shared",
            "student_scope": "all",
        }
    )

    template, error = module.derive_unique_template([regular, shared])

    assert template is None
    assert error == "AMBIGUOUS_CANONICAL_TEMPLATE"


def test_unknown_diary_setting_field_blocks_automatic_template():
    row = dvd_row()
    row["diary_settings"]["future_flag"] = True

    template, error = module.derive_unique_template([row])

    assert template is None
    assert error == "UNSUPPORTED_TEMPLATE_FIELDS"


def test_target_assignment_id_and_payload_are_deterministic():
    template = module.derive_unique_template([dvd_row()])[0]
    kwargs = dict(
        tenant_id="tenant-1",
        school_id="school-1",
        teacher_id="user-1",
        class_id="class-1",
        component_id="course-1",
        academic_year=2026,
        template=template,
    )

    first = module.build_target_assignment(**kwargs)
    second = module.build_target_assignment(**kwargs)

    assert first == second
    assert first["id"] == second["id"]
    assert first["component_id"] == "course-1"
    assert first["teacher_id"] == "user-1"
    assert first["deleted"] is False


def test_component_identity_changes_target_id_without_name_mapping():
    template = module.derive_unique_template([dvd_row()])[0]
    common = dict(
        tenant_id="tenant-1",
        school_id="school-1",
        teacher_id="user-1",
        class_id="class-1",
        academic_year=2026,
        template=template,
    )

    a = module.build_target_assignment(component_id="course-A", **common)
    b = module.build_target_assignment(component_id="course-B", **common)

    assert a["id"] != b["id"]
    assert a["component_id"] != b["component_id"]


def test_generic_7_plus_2_population_produces_two_plan_operations():
    rows = [
        decision("t1", "c1", f"covered-{i}", "NOOP_ALREADY_CANONICAL")
        for i in range(7)
    ]
    rows += [
        decision("t1", "c1", f"missing-{i}", "PLAN_CREATE_CANONICAL_ASSIGNMENT")
        for i in range(2)
    ]

    analysis = module.summarize_decisions(rows)

    assert analysis["classification"] == "GLOBAL_DVD_RECONCILIATION_PLAN_READY"
    assert analysis["plan_create_count"] == 2
    assert analysis["teacher_class_state_counts"]["PLAN_READY"] == 1


def test_plan_plus_review_is_fail_closed_partial_review_required():
    rows = [
        decision("t1", "c1", "a", "PLAN_CREATE_CANONICAL_ASSIGNMENT"),
        decision(
            "t2",
            "c2",
            "b",
            "REQUIRES_REVIEW",
            ["NO_CANONICAL_TEMPLATE"],
        ),
    ]

    analysis = module.summarize_decisions(rows)

    assert analysis["classification"] == "GLOBAL_DVD_RECONCILIATION_PLAN_PARTIAL_REVIEW_REQUIRED"
    assert analysis["plan_complete_without_review"] is False
    assert analysis["review_reason_counts"]["NO_CANONICAL_TEMPLATE"] == 1


def test_decision_manifest_hash_is_order_independent_after_sorting():
    a = decision("t2", "c2", "x", "NOOP_ALREADY_CANONICAL")
    b = decision("t1", "c1", "y", "REQUIRES_REVIEW", ["NO_CANONICAL_TEMPLATE"])

    first = module._sha256_value(module._decision_manifest_rows([a, b]))
    second = module._sha256_value(module._decision_manifest_rows([b, a]))

    assert first == second
