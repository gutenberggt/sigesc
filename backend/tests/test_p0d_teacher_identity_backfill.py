from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import apply_teacher_identity_backfill_p0d as mod


def _proposal(index: int, *, tenant: str = "tenant-1") -> dict:
    proposal = {
        "operation": "BACKFILL_STAFF_USER_ID",
        "staff_id": f"staff-{index}",
        "expected_user_id_before": None,
        "target_user_id": f"user-{index}",
        "mantenedora_id": tenant,
        "evidence_method": "EXACT_PAIR_PLUS_EMAIL",
        "dvd_assignment_ids": [f"dvd-{index}"],
        "exact_pair_evidence": [
            {
                "class_id": f"class-{index}",
                "component_id": f"course-{index}",
                "legacy_staff_ids": [f"staff-{index}"],
            }
        ],
    }
    proposal["evidence_sha256"] = mod.base.manifest_sha256(proposal)
    return proposal


def _manifest(count: int = 2) -> dict:
    return {
        "phase": mod.APPROVED_MANIFEST_PHASE,
        "manifest_version": mod.APPROVED_MANIFEST_VERSION,
        "mode": "READ_ONLY_PREFLIGHT",
        "status": "PASS",
        "academic_year": 2026,
        "reference_date": "2026-08-27",
        "source_p0b_evidence_sha256": mod.APPROVED_SOURCE_P0B_SHA256,
        "semantic_partition": {
            "counts": {
                "LEGACY_MIGRATION_SYNTHETIC": 10,
                "LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED": 1,
                "OPERATIONAL_DVD": 5,
            },
            "remediation_gate": "PASS",
        },
        "summary": {
            "decision_counts": {
                "ALREADY_CANONICAL": mod.APPROVED_ALREADY_CANONICAL,
                "READY_SAFE": count,
            },
            "blocker_counts": {},
            "proposed_staff_user_id_backfills": count,
        },
        "proposals": [_proposal(i) for i in range(count)],
        "cases": [],
    }


def _pin_sample(monkeypatch, payload: dict) -> str:
    digest = mod.base.manifest_sha256(payload)
    monkeypatch.setattr(mod, "APPROVED_MANIFEST_SHA256", digest)
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", len(payload["proposals"]))
    return digest


def test_production_constants_are_pinned():
    assert mod.APPROVED_MANIFEST_SHA256 == (
        "68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a"
    )
    assert mod.APPROVED_SOURCE_P0B_SHA256 == (
        "519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be"
    )
    assert mod.APPROVED_READY_COUNT == 6
    assert mod.APPROVED_ALREADY_CANONICAL == 33
    assert mod.APPLY_CONFIRMATION == "APPLY-P0D-TEACHER-IDENTITY-6"
    assert mod.ROLLBACK_CONFIRMATION == "ROLLBACK-P0D-TEACHER-IDENTITY-6"


def test_manifest_loader_accepts_only_exact_approved_payload(tmp_path: Path, monkeypatch):
    payload = _manifest()
    digest = _pin_sample(monkeypatch, payload)
    path = tmp_path / "manifest.json"
    path.write_text(mod.json.dumps(payload), encoding="utf-8")

    loaded = mod.load_and_validate_manifest(path)

    assert mod.base.manifest_sha256(loaded) == digest
    assert len(loaded["proposals"]) == 2


def test_manifest_loader_rejects_proposal_evidence_drift(tmp_path: Path, monkeypatch):
    payload = _manifest()
    payload["proposals"][0]["evidence_sha256"] = "0" * 64
    _pin_sample(monkeypatch, payload)
    path = tmp_path / "manifest.json"
    path.write_text(mod.json.dumps(payload), encoding="utf-8")

    with pytest.raises(mod.P0DGateError, match="PROPOSAL_EVIDENCE_SHA_MISMATCH"):
        mod.load_and_validate_manifest(path)


def test_manifest_loader_rejects_nonempty_expected_before(tmp_path: Path, monkeypatch):
    payload = _manifest()
    payload["proposals"][0]["expected_user_id_before"] = "some-user"
    payload["proposals"][0].pop("evidence_sha256")
    payload["proposals"][0]["evidence_sha256"] = mod.base.manifest_sha256(
        payload["proposals"][0]
    )
    _pin_sample(monkeypatch, payload)
    path = tmp_path / "manifest.json"
    path.write_text(mod.json.dumps(payload), encoding="utf-8")

    with pytest.raises(mod.P0DGateError, match="PROPOSAL_EXPECTED_BEFORE_NOT_EMPTY"):
        mod.load_and_validate_manifest(path)


def test_cas_filter_preserves_missing_null_and_empty_distinction():
    missing = {
        "id": "s1",
        "mantenedora_id": "t1",
        "user_id_present": False,
        "user_id": None,
    }
    null = {
        "id": "s1",
        "mantenedora_id": "t1",
        "user_id_present": True,
        "user_id": None,
    }
    empty = {
        "id": "s1",
        "mantenedora_id": "t1",
        "user_id_present": True,
        "user_id": "",
    }

    assert mod._cas_before_filter(missing)["user_id"] == {"$exists": False}
    assert mod._cas_before_filter(null)["$and"] == [
        {"user_id": {"$exists": True}},
        {"user_id": None},
    ]
    assert mod._cas_before_filter(empty)["user_id"] == ""


def test_backup_round_trip_is_sealed_and_immutable(tmp_path: Path, monkeypatch):
    payload = _manifest()
    digest = _pin_sample(monkeypatch, payload)
    snapshot = [
        {
            "id": p["staff_id"],
            "mantenedora_id": p["mantenedora_id"],
            "user_id_present": False,
            "user_id": None,
            "target_user_id": p["target_user_id"],
            "proposal_evidence_sha256": p["evidence_sha256"],
        }
        for p in payload["proposals"]
    ]
    backup_dir = tmp_path / "backup"

    sealed = mod.write_backup_directory(
        backup_dir,
        manifest=payload,
        staff_snapshot=snapshot,
        live_manifest_sha256=digest,
    )
    loaded = mod.load_and_verify_backup(
        backup_dir,
        expected_backup_sha256=sealed["backup_bundle_sha256"],
    )

    assert loaded["backup_bundle_sha256"] == sealed["backup_bundle_sha256"]
    assert loaded["staff_before"] == snapshot

    with pytest.raises(mod.P0DGateError, match="BACKUP_DIR_ALREADY_EXISTS"):
        mod.write_backup_directory(
            backup_dir,
            manifest=payload,
            staff_snapshot=snapshot,
            live_manifest_sha256=digest,
        )


def test_backup_loader_detects_file_tamper(tmp_path: Path, monkeypatch):
    payload = _manifest()
    digest = _pin_sample(monkeypatch, payload)
    snapshot = [
        {
            "id": p["staff_id"],
            "mantenedora_id": p["mantenedora_id"],
            "user_id_present": False,
            "user_id": None,
            "target_user_id": p["target_user_id"],
            "proposal_evidence_sha256": p["evidence_sha256"],
        }
        for p in payload["proposals"]
    ]
    backup_dir = tmp_path / "backup"
    sealed = mod.write_backup_directory(
        backup_dir,
        manifest=payload,
        staff_snapshot=snapshot,
        live_manifest_sha256=digest,
    )
    (backup_dir / "staff_before.json").write_text("[]\n", encoding="utf-8")

    with pytest.raises(mod.P0DGateError, match="BACKUP_FILE_HASH_MISMATCH"):
        mod.load_and_verify_backup(
            backup_dir,
            expected_backup_sha256=sealed["backup_bundle_sha256"],
        )


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


def _matches(doc: dict, query: dict) -> bool:
    for key, expected in query.items():
        if key == "$and":
            if not all(_matches(doc, part) for part in expected):
                return False
            continue
        actual_present = key in doc
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif "$exists" in expected:
                if actual_present is not bool(expected["$exists"]):
                    return False
            else:
                raise AssertionError(f"unsupported query {expected}")
        elif actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, rows, *, fail_update_id=None):
        self.rows = [dict(row) for row in rows]
        self.fail_update_id = fail_update_id
        self.update_calls = []

    def find(self, query, _projection):
        return FakeCursor([row for row in self.rows if _matches(row, query)])

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        target_id = query.get("id")
        if target_id == self.fail_update_id:
            return SimpleNamespace(matched_count=0, modified_count=0)
        for row in self.rows:
            if _matches(row, query):
                before = dict(row)
                for key, value in (update.get("$set") or {}).items():
                    row[key] = value
                for key in (update.get("$unset") or {}):
                    row.pop(key, None)
                return SimpleNamespace(
                    matched_count=1,
                    modified_count=int(before != row),
                )
        return SimpleNamespace(matched_count=0, modified_count=0)


class FakeDB:
    def __init__(self, staff, users, *, fail_update_id=None):
        self.staff = FakeCollection(staff, fail_update_id=fail_update_id)
        self.users = FakeCollection(users)


def _fake_db(payload: dict, *, already=False, fail_update_id=None):
    staff = []
    users = []
    for proposal in payload["proposals"]:
        row = {
            "id": proposal["staff_id"],
            "mantenedora_id": proposal["mantenedora_id"],
            "cargo": "professor",
            "status": "ativo",
        }
        if already:
            row["user_id"] = proposal["target_user_id"]
        staff.append(row)
        users.append({
            "id": proposal["target_user_id"],
            "role": "professor",
            "mantenedora_id": proposal["mantenedora_id"],
        })
    return FakeDB(staff, users, fail_update_id=fail_update_id)


@pytest.mark.asyncio
async def test_inspect_live_state_distinguishes_ready_and_applied(monkeypatch):
    payload = _manifest()
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", 2)

    ready = await mod.inspect_live_state(_fake_db(payload), payload)
    applied = await mod.inspect_live_state(_fake_db(payload, already=True), payload)

    assert ready["state"] == "READY"
    assert ready["before_count"] == 2
    assert applied["state"] == "ALREADY_APPLIED"
    assert applied["target_count"] == 2


@pytest.mark.asyncio
async def test_inspect_live_state_rejects_foreign_user_link(monkeypatch):
    payload = _manifest()
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", 2)
    db = _fake_db(payload)
    db.staff.rows.append({
        "id": "foreign-staff",
        "user_id": payload["proposals"][0]["target_user_id"],
    })

    with pytest.raises(mod.P0DGateError, match="LIVE_TARGET_USER_ALREADY_LINKED_ELSEWHERE"):
        await mod.inspect_live_state(db, payload)


def _backup_for(payload: dict, db: FakeDB) -> dict:
    snapshot = []
    by_id = {row["id"]: row for row in db.staff.rows}
    for proposal in payload["proposals"]:
        snapshot.append(
            mod._snapshot_row(by_id[proposal["staff_id"]], proposal)
        )
    return {
        "manifest": payload,
        "staff_before": sorted(snapshot, key=lambda row: row["id"]),
        "backup_bundle_sha256": "b" * 64,
    }


@pytest.mark.asyncio
async def test_apply_changes_only_staff_user_id_with_cas(monkeypatch):
    payload = _manifest()
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", 2)
    db = _fake_db(payload)
    backup = _backup_for(payload, db)

    async def _ok(_db):
        return "approved"

    monkeypatch.setattr(mod, "assert_live_manifest_unchanged", _ok)

    changes = await mod.apply_backfills(db, backup)

    assert len(changes) == 2
    for proposal in payload["proposals"]:
        row = next(r for r in db.staff.rows if r["id"] == proposal["staff_id"])
        assert row["user_id"] == proposal["target_user_id"]
    assert all(set(update) == {"$set"} for _, update in db.staff.update_calls)
    assert all(set(update["$set"]) == {"user_id"} for _, update in db.staff.update_calls)


@pytest.mark.asyncio
async def test_apply_failure_compensates_prior_write(monkeypatch):
    payload = _manifest()
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", 2)
    second_id = payload["proposals"][1]["staff_id"]
    db = _fake_db(payload, fail_update_id=second_id)
    backup = _backup_for(payload, db)

    async def _ok(_db):
        return "approved"

    monkeypatch.setattr(mod, "assert_live_manifest_unchanged", _ok)

    with pytest.raises(mod.P0DGateError, match="APPLY_CAS_FAILED_COMPENSATED"):
        await mod.apply_backfills(db, backup)

    first = next(r for r in db.staff.rows if r["id"] == payload["proposals"][0]["staff_id"])
    assert "user_id" not in first


@pytest.mark.asyncio
async def test_rollback_restores_exact_missing_state(monkeypatch):
    payload = _manifest()
    monkeypatch.setattr(mod, "APPROVED_READY_COUNT", 2)
    before_db = _fake_db(payload)
    backup = _backup_for(payload, before_db)
    db = _fake_db(payload, already=True)

    changes = await mod.rollback_backfills(db, backup)

    assert len(changes) == 2
    assert all("user_id" not in row for row in db.staff.rows)


def test_script_is_default_dry_run_and_scope_is_staff_user_id_only():
    src = Path("scripts/apply_teacher_identity_backfill_p0d.py").read_text(
        encoding="utf-8"
    )
    assert "if not args.apply and not args.rollback:" in src
    assert "APPLY_CONFIRMATION_REQUIRED" in src
    assert "ROLLBACK_CONFIRMATION_REQUIRED" in src
    assert "db.staff.update_one(" in src
    assert "db.teacher_class_assignments.update" not in src
    assert "db.teacher_assignments.update" not in src
    assert ".update_many(" not in src
    assert ".delete_one(" not in src
    assert ".delete_many(" not in src
    assert ".insert_one(" not in src
    assert ".insert_many(" not in src
