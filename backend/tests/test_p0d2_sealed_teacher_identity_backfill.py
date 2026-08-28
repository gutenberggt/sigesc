from argparse import Namespace
from pathlib import Path

import pytest

from scripts import apply_teacher_identity_backfill_p0d2_sealed as sealed


def _args(tmp_path: Path, **overrides):
    values = {
        "backup_dir": str(tmp_path / "backup"),
        "receipt_dir": str(tmp_path / "receipts"),
        "apply": False,
        "rollback": False,
        "confirm": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_production_seal_constants_are_pinned():
    assert sealed.APPROVED_READY_COUNT == 6
    assert sealed.APPROVED_MANIFEST_SHA256 == (
        "68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a"
    )
    assert sealed.APPROVED_SOURCE_P0B_SHA256 == (
        "519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be"
    )
    assert sealed.APPROVED_BACKUP_BUNDLE_SHA256 == (
        "fac42381eb1d702002334be1e25d06ade594bf6376125a5008d09b995c7cc100"
    )
    assert sealed.APPLY_CONFIRMATION == "APPLY-P0D-TEACHER-IDENTITY-6"
    assert sealed.ROLLBACK_CONFIRMATION == "ROLLBACK-P0D-TEACHER-IDENTITY-6"


def test_seal_matches_p0d1_implementation_contract():
    sealed.assert_implementation_contract()


def test_build_implementation_args_locks_manifest_and_backup_hash(tmp_path: Path):
    args = _args(
        tmp_path,
        apply=True,
        confirm=sealed.APPLY_CONFIRMATION,
    )
    built = sealed.build_implementation_args(args)

    assert built.manifest == str(tmp_path / "backup" / "manifest.json")
    assert built.backup_dir == str(tmp_path / "backup")
    assert built.receipt_dir == str(tmp_path / "receipts")
    assert built.expected_backup_sha256 == sealed.APPROVED_BACKUP_BUNDLE_SHA256
    assert built.apply is True
    assert built.rollback is False
    assert built.confirm == sealed.APPLY_CONFIRMATION


def test_cli_does_not_expose_manifest_or_hash_override():
    with pytest.raises(SystemExit):
        sealed.parse_args([
            "--backup-dir",
            "/tmp/backup",
            "--manifest",
            "/tmp/other.json",
        ])

    with pytest.raises(SystemExit):
        sealed.parse_args([
            "--backup-dir",
            "/tmp/backup",
            "--expected-backup-sha256",
            "0" * 64,
        ])


def test_default_mode_is_verify_only():
    args = sealed.parse_args(["--backup-dir", "/tmp/backup"])
    assert args.apply is False
    assert args.rollback is False
    assert args.confirm is None


def test_wrapper_has_no_direct_database_mutators():
    source = Path(
        "scripts/apply_teacher_identity_backfill_p0d2_sealed.py"
    ).read_text(encoding="utf-8")

    for token in (
        ".update_one(",
        ".update_many(",
        ".insert_one(",
        ".insert_many(",
        ".delete_one(",
        ".delete_many(",
        ".replace_one(",
        ".bulk_write(",
    ):
        assert token not in source


@pytest.mark.asyncio
async def test_verify_only_ready_revalidates_live_manifest(monkeypatch, tmp_path: Path):
    manifest = {"proposals": [{"staff_id": "staff-1"}]}

    def fake_load(backup_dir, *, expected_backup_sha256):
        assert backup_dir == tmp_path
        assert expected_backup_sha256 == sealed.APPROVED_BACKUP_BUNDLE_SHA256
        return {"manifest": manifest}

    async def fake_inspect(db, received_manifest):
        assert db == "db"
        assert received_manifest is manifest
        return {"state": "READY"}

    called = {"live": 0}

    async def fake_live(db):
        assert db == "db"
        called["live"] += 1
        return sealed.APPROVED_MANIFEST_SHA256

    monkeypatch.setattr(sealed.implementation, "load_and_verify_backup", fake_load)
    monkeypatch.setattr(sealed.implementation, "inspect_live_state", fake_inspect)
    monkeypatch.setattr(
        sealed.implementation,
        "assert_live_manifest_unchanged",
        fake_live,
    )

    result = await sealed.verify_only("db", tmp_path)

    assert result["status"] == "PASS"
    assert result["mode"] == "VERIFY_ONLY"
    assert result["database_mutation"] is False
    assert result["live_state"] == "READY"
    assert result["live_manifest_sha256"] == sealed.APPROVED_MANIFEST_SHA256
    assert result["backup_bundle_sha256"] == sealed.APPROVED_BACKUP_BUNDLE_SHA256
    assert called["live"] == 1


@pytest.mark.asyncio
async def test_verify_only_already_applied_does_not_require_old_live_manifest(
    monkeypatch,
    tmp_path: Path,
):
    manifest = {"proposals": [{"staff_id": "staff-1"}]}

    monkeypatch.setattr(
        sealed.implementation,
        "load_and_verify_backup",
        lambda backup_dir, expected_backup_sha256: {"manifest": manifest},
    )

    async def fake_inspect(db, received_manifest):
        assert received_manifest is manifest
        return {"state": "ALREADY_APPLIED"}

    async def forbidden_live_check(db):
        raise AssertionError("old live manifest must not be required after apply")

    monkeypatch.setattr(sealed.implementation, "inspect_live_state", fake_inspect)
    monkeypatch.setattr(
        sealed.implementation,
        "assert_live_manifest_unchanged",
        forbidden_live_check,
    )

    result = await sealed.verify_only("db", tmp_path)

    assert result["status"] == "PASS"
    assert result["live_state"] == "ALREADY_APPLIED"
    assert result["live_manifest_sha256"] is None
    assert result["database_mutation"] is False


def test_apply_and_rollback_are_mutually_exclusive(tmp_path: Path):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    args = _args(tmp_path, apply=True, rollback=True)

    with pytest.raises(sealed.P0D2SealError, match="APPLY_ROLLBACK_MUTUALLY_EXCLUSIVE"):
        import asyncio

        asyncio.run(sealed.run(args))
