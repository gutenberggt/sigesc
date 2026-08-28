from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preflight_teacher_identity_remediation_p0c.py"
SPEC = importlib.util.spec_from_file_location("p0c_teacher_identity_preflight", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def test_script_has_no_apply_mode_and_static_read_only_guard():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--apply" not in source
    MOD.assert_read_only()


def test_select_structural_staff_requires_unanimous_exact_pairs():
    staff_id, status = MOD.select_structural_staff([{"staff-1"}, {"staff-1"}, {"staff-1"}])
    assert staff_id == "staff-1"
    assert status == "EXACT_PAIR_UNANIMOUS"


def test_select_structural_staff_rejects_missing_pair():
    staff_id, status = MOD.select_structural_staff([{"staff-1"}, set()])
    assert staff_id is None
    assert status == "PAIR_MISSING"


def test_select_structural_staff_rejects_ambiguous_pair():
    staff_id, status = MOD.select_structural_staff([{"staff-1", "staff-2"}])
    assert staff_id is None
    assert status == "PAIR_AMBIGUOUS"


def test_select_structural_staff_rejects_conflicting_singletons():
    staff_id, status = MOD.select_structural_staff([{"staff-1"}, {"staff-2"}])
    assert staff_id is None
    assert status == "PAIR_CONFLICT"


def test_select_structural_staff_rejects_class_wide_only():
    staff_id, status = MOD.select_structural_staff([])
    assert staff_id is None
    assert status == "NO_COMPONENT_EVIDENCE"


def test_email_is_never_sufficient_without_structural_evidence():
    user = {"id": "user-1", "email": "Professor@Example.com"}
    users_by_email = {"professor@example.com": [user]}
    staff = {"id": "staff-1", "email": "professor@example.com"}
    staff_by_email = {"professor@example.com": [staff]}

    signal, staff_id = MOD.email_signal(
        user,
        users_by_email=users_by_email,
        staff_by_email=staff_by_email,
        structural_staff_id=None,
    )
    assert signal == "UNIQUE_EMAIL_MATCH"
    assert staff_id == "staff-1"
    # A decisão continua sem permissão porque o par turma+componente não existe.
    assert MOD.decision_bucket(structural_status="NO_COMPONENT_EVIDENCE", blockers=[]) == "NEEDS_REVIEW"


def test_email_conflict_blocks_structural_candidate():
    user = {"id": "user-1", "email": "professor@example.com"}
    users_by_email = {"professor@example.com": [user]}
    staff_by_email = {"professor@example.com": [{"id": "staff-email"}]}
    signal, staff_id = MOD.email_signal(
        user,
        users_by_email=users_by_email,
        staff_by_email=staff_by_email,
        structural_staff_id="staff-structural",
    )
    assert signal == "EMAIL_STRUCTURAL_CONFLICT"
    assert staff_id == "staff-email"


def test_absent_user_tenant_can_be_derived_from_single_staff_class_tenant():
    blockers = MOD.classify_blockers(
        user_id="user-1",
        user={"id": "user-1", "role": "professor", "mantenedora_id": None},
        staff={
            "id": "staff-1",
            "cargo": "professor",
            "status": "ativo",
            "user_id": None,
            "mantenedora_id": "tenant-1",
        },
        class_tenants={"tenant-1"},
        staff_by_user_id={},
        email_evidence="NO_STAFF_EMAIL_MATCH",
    )
    assert blockers == []


def test_explicit_tenant_mismatch_is_fail_closed():
    blockers = MOD.classify_blockers(
        user_id="user-1",
        user={"id": "user-1", "role": "professor", "mantenedora_id": "tenant-2"},
        staff={
            "id": "staff-1",
            "cargo": "professor",
            "status": "ativo",
            "user_id": None,
            "mantenedora_id": "tenant-1",
        },
        class_tenants={"tenant-1"},
        staff_by_user_id={},
        email_evidence="NO_STAFF_EMAIL_MATCH",
    )
    assert "USER_STAFF_TENANT_MISMATCH" in blockers
    assert "USER_CLASS_TENANT_MISMATCH" in blockers


def test_foreign_staff_user_link_blocks_candidate():
    blockers = MOD.classify_blockers(
        user_id="user-1",
        user={"id": "user-1", "role": "professor"},
        staff={
            "id": "staff-1",
            "cargo": "professor",
            "status": "ativo",
            "user_id": "user-other",
            "mantenedora_id": "tenant-1",
        },
        class_tenants={"tenant-1"},
        staff_by_user_id={},
        email_evidence="NO_STAFF_EMAIL_MATCH",
    )
    assert "STAFF_ALREADY_LINKED_TO_OTHER_USER" in blockers


def test_manifest_hash_is_deterministic_for_key_order():
    a = {"b": 2, "a": {"y": 2, "x": 1}}
    b = {"a": {"x": 1, "y": 2}, "b": 2}
    assert MOD.manifest_sha256(a) == MOD.manifest_sha256(b)


def test_ready_safe_requires_exact_pair_and_no_blockers():
    assert MOD.decision_bucket(
        structural_status="EXACT_PAIR_UNANIMOUS",
        blockers=[],
    ) == "READY_SAFE"
    assert MOD.decision_bucket(
        structural_status="EXACT_PAIR_UNANIMOUS",
        blockers=["STAFF_ALREADY_LINKED_TO_OTHER_USER"],
    ) == "BLOCKED"
