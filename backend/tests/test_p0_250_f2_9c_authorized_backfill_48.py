from __future__ import annotations

import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path

import pytest

_pymongo = types.ModuleType("pymongo")
_pymongo.MongoClient = object
sys.modules.setdefault("pymongo", _pymongo)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p0_250_f2_9c_authorized_backfill_48.py"
spec = importlib.util.spec_from_file_location("f29c", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _get(doc, dotted):
    value = doc
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _match_value(actual, expected):
    if isinstance(expected, dict) and any(str(key).startswith("$") for key in expected):
        for op, value in expected.items():
            if op == "$ne":
                if actual == value:
                    return False
            elif op == "$in":
                if actual not in value:
                    return False
            elif op == "$lte":
                if actual is None or actual > value:
                    return False
            elif op == "$gte":
                if actual is None or actual < value:
                    return False
            else:
                raise AssertionError(f"unsupported operator {op}")
        return True
    return actual == expected


def _match(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_match(doc, branch) for branch in expected):
                return False
            continue
        if not _match_value(_get(doc, key), expected):
            return False
    return True


class Result:
    def __init__(self, *, inserted_id=None, deleted_count=0):
        self.inserted_id = inserted_id
        self.deleted_count = deleted_count


class Collection:
    def __init__(self, docs=None, fail_insert_at=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.fail_insert_at = fail_insert_at
        self.insert_calls = 0
        self.delete_calls = 0
        self._next = 1

    def count_documents(self, query):
        return sum(1 for doc in self.docs if _match(doc, query))

    def find_one(self, query):
        for doc in self.docs:
            if _match(doc, query):
                return deepcopy(doc)
        return None

    def insert_one(self, document):
        self.insert_calls += 1
        if self.fail_insert_at == self.insert_calls:
            raise RuntimeError("simulated_insert_failure")
        candidate = deepcopy(document)
        candidate["_id"] = f"oid-{self._next}"
        self._next += 1
        self.docs.append(candidate)
        return Result(inserted_id=candidate["_id"])

    def delete_one(self, query):
        self.delete_calls += 1
        for index, doc in enumerate(self.docs):
            if _match(doc, query):
                del self.docs[index]
                return Result(deleted_count=1)
        return Result(deleted_count=0)


class DB:
    def __init__(
        self,
        teacher_assignments,
        teacher_class_assignments=None,
        fail_insert_at=None,
    ):
        self.teacher_assignments = Collection(teacher_assignments)
        self.teacher_class_assignments = Collection(
            teacher_class_assignments,
            fail_insert_at=fail_insert_at,
        )


def target(i):
    return {
        "id": f"target-{i}",
        "teacher_id": f"teacher-{i}",
        "class_id": f"class-{i}",
        "component_id": f"component-{i}",
        "school_id": f"school-{i}",
        "mantenedora_id": "tenant-1",
        "deleted": False,
        "valid_from": "2026-01-01",
        "valid_until": None,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "is_substitute": False,
        "grades_official_owner": False,
    }


def operation(i):
    target_doc = target(i)
    target_hash = mod.sha256_value(target_doc)
    return {
        "ordinal": i,
        "operation": "INSERT_TEACHER_CLASS_ASSIGNMENT",
        "source_legacy_key": {
            "staff_id": f"staff-{i}",
            "class_id": f"class-{i}",
            "course_id": f"component-{i}",
            "academic_year": 2026,
            "active_statuses": ["ativo", "active"],
        },
        "target_assignment": target_doc,
        "target_assignment_sha256": target_hash,
        "sealed_preconditions": {
            "source_legacy_count": 1,
            "target_id_count": 0,
            "other_teacher_official_grade_owner_count": 0,
            "reference_date": "2026-08-31",
            "must_reappear_identically_in_f2_9a_plan_before_apply": True,
        },
        "rollback_contract": {
            "mode": "DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH",
            "target_assignment_id": target_doc["id"],
            "target_assignment_sha256": target_hash,
        },
    }


def source_doc(i):
    return {
        "staff_id": f"staff-{i}",
        "class_id": f"class-{i}",
        "course_id": f"component-{i}",
        "academic_year": 2026,
        "status": "ativo",
    }


def fake_manifest(count=2):
    operations = [operation(i) for i in range(1, count + 1)]
    targets = [op["target_assignment"] for op in operations]
    core = {
        "schema": mod.SEALED_PRIVATE_SCHEMA,
        "phase": mod.SEALED_PHASE_ID,
        "mode": mod.SEALED_MODE,
        "status": "PASS",
        "database_mutation": False,
        "production_database_writes": False,
        "automatic_apply_authorized": False,
        "source": {
            "f2_9a_main_sha": mod.SOURCE_F2_9A_MAIN_SHA,
            "academic_year": 2026,
            "reference_date": "2026-08-31",
            "plan_sha256": mod.SOURCE_F2_9A_PLAN_SHA256,
        },
        "expected_target_count": count,
        "operations": operations,
        "sealed_targets_sha256": mod.sha256_value(targets),
        "sealed_operations_sha256": mod.sha256_value(operations),
    }
    return {
        **core,
        "sealed_bundle_sha256": mod.sha256_value(core),
    }


def test_manifest_validation_accepts_exact_chain_and_rejects_drift():
    manifest = fake_manifest()
    ops = mod.validate_sealed_manifest(
        manifest,
        expected_target_count=2,
        expected_targets_sha256=manifest["sealed_targets_sha256"],
        expected_operations_sha256=manifest["sealed_operations_sha256"],
        expected_bundle_sha256=manifest["sealed_bundle_sha256"],
    )
    assert len(ops) == 2

    tampered = deepcopy(manifest)
    tampered["operations"][0]["target_assignment"]["school_id"] = "tampered"
    with pytest.raises(mod.F29CExecutionError):
        mod.validate_sealed_manifest(
            tampered,
            expected_target_count=2,
            expected_targets_sha256=manifest["sealed_targets_sha256"],
            expected_operations_sha256=manifest["sealed_operations_sha256"],
            expected_bundle_sha256=manifest["sealed_bundle_sha256"],
        )


def test_apply_inserts_and_verifies_exact_documents():
    ops = [operation(1), operation(2)]
    db = DB([source_doc(1), source_doc(2)])
    result = mod.apply_validated_operations(db, ops)

    assert result["inserted_count"] == 2
    assert result["verified_count"] == 2
    assert db.teacher_class_assignments.insert_calls == 2
    assert db.teacher_class_assignments.delete_calls == 0
    assert db.teacher_class_assignments.count_documents({"id": "target-1"}) == 1
    assert db.teacher_class_assignments.count_documents({"id": "target-2"}) == 1


def test_apply_rolls_back_exact_prior_inserts_on_failure():
    ops = [operation(1), operation(2)]
    db = DB([source_doc(1), source_doc(2)], fail_insert_at=2)

    with pytest.raises(mod.F29CExecutionError) as exc:
        mod.apply_validated_operations(db, ops)

    assert "EXECUTION_FAILED_ROLLED_BACK" in str(exc.value)
    assert db.teacher_class_assignments.count_documents({"id": "target-1"}) == 0
    assert db.teacher_class_assignments.count_documents({"id": "target-2"}) == 0
    assert db.teacher_class_assignments.delete_calls == 1


def test_live_reseal_must_be_canonically_identical(monkeypatch):
    manifest = fake_manifest()
    monkeypatch.setattr(mod, "EXPECTED_BUNDLE_SHA256", manifest["sealed_bundle_sha256"])
    mod.validate_live_reseal(manifest, deepcopy(manifest))

    changed = deepcopy(manifest)
    changed["mode"] = "changed"
    with pytest.raises(mod.F29CExecutionError):
        mod.validate_live_reseal(manifest, changed)


def test_authorization_is_fail_closed_before_database_access():
    with pytest.raises(mod.F29CExecutionError) as exc:
        mod.run_authorized_backfill(
            {},
            explicit_authorization=False,
            authorization_marker="",
            live_reseal_factory=None,
            db=None,
        )
    assert str(exc.value) == "EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED"


def _patch_fake_contract(monkeypatch, manifest):
    monkeypatch.setattr(mod, "EXPECTED_TARGET_COUNT", 2)
    monkeypatch.setattr(
        mod,
        "EXPECTED_TARGETS_SHA256",
        manifest["sealed_targets_sha256"],
    )
    monkeypatch.setattr(
        mod,
        "EXPECTED_OPERATIONS_SHA256",
        manifest["sealed_operations_sha256"],
    )
    monkeypatch.setattr(
        mod,
        "EXPECTED_BUNDLE_SHA256",
        manifest["sealed_bundle_sha256"],
    )
    monkeypatch.setattr(mod, "AUTHORIZATION_MARKER", "AUTHORIZED-TEST")


def test_top_level_requires_identical_live_reseal_before_first_write(monkeypatch):
    manifest = fake_manifest()
    _patch_fake_contract(monkeypatch, manifest)
    db = DB([source_doc(1), source_doc(2)])
    calls = {"reseal": 0}

    def reseal():
        calls["reseal"] += 1
        return deepcopy(manifest)

    result = mod.run_authorized_backfill(
        manifest,
        explicit_authorization=True,
        authorization_marker="AUTHORIZED-TEST",
        live_reseal_factory=reseal,
        db=db,
    )

    assert calls["reseal"] == 1
    assert result["public"]["classification"] == "F2_9C_48_TARGETS_APPLIED_AND_VERIFIED"
    assert result["public"]["new_writes"] == 2
    assert result["public"]["verified_count"] == 2


def test_top_level_is_idempotent_when_all_targets_are_exact(monkeypatch):
    manifest = fake_manifest()
    _patch_fake_contract(monkeypatch, manifest)
    existing = [target(1), target(2)]
    db = DB(
        [source_doc(1), source_doc(2)],
        teacher_class_assignments=existing,
    )

    def reseal_must_not_run():
        raise AssertionError("reseal must not run on exact replay")

    result = mod.run_authorized_backfill(
        manifest,
        explicit_authorization=True,
        authorization_marker="AUTHORIZED-TEST",
        live_reseal_factory=reseal_must_not_run,
        db=db,
    )

    assert result["public"]["classification"] == "F2_9C_48_TARGETS_ALREADY_APPLIED_EXACT"
    assert result["public"]["new_writes"] == 0
    assert result["public"]["verified_count"] == 2
