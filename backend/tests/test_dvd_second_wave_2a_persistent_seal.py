from pathlib import Path

import pytest

from scripts.apply_dvd_second_wave_2a_persistent import (
    ACADEMIC_YEAR,
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    PERSISTENT_BACKUP_DIR,
    PERSISTENT_RECEIPT_DIR,
    REFERENCE_DATE,
    PersistentSealArgumentError,
    build_locked_argv,
    validate_runtime_args,
)


def test_persistent_production_seal_is_pinned():
    assert ACADEMIC_YEAR == 2026
    assert REFERENCE_DATE == "2026-08-18"
    assert APPROVED_READY_COUNT == 27
    assert APPROVED_MANIFEST_SHA256 == (
        "7ab088f1705c28894adadd4b9d294440cf07d77030ed6ae2d8af7435b043b546"
    )
    assert APPROVED_BACKUP_BUNDLE_SHA256 == (
        "4126da5a84ee2db2dd5071b58a9e019a04db56896c2ad4c24ba0474b0fd58620"
    )
    assert PERSISTENT_BACKUP_DIR == (
        "/data/sigesc-dvd-backups/dvd-second-wave-2a-preflight-v2"
    )
    assert PERSISTENT_RECEIPT_DIR.startswith("/data/sigesc-dvd-backups/")


def test_default_entrypoint_is_locked_dry_run():
    argv = build_locked_argv([])
    joined = " ".join(argv)
    assert "--academic-year 2026" in joined
    assert "--reference-date 2026-08-18" in joined
    assert f"--expected-count {APPROVED_READY_COUNT}" in joined
    assert f"--expected-manifest-sha256 {APPROVED_MANIFEST_SHA256}" in joined
    assert f"--expected-backup-sha256 {APPROVED_BACKUP_BUNDLE_SHA256}" in joined
    assert f"--backup-dir {PERSISTENT_BACKUP_DIR}" in joined
    assert f"--receipt-dir {PERSISTENT_RECEIPT_DIR}" in joined
    assert "--apply" not in argv
    assert "--rollback" not in argv


def test_only_mode_and_confirmation_can_be_forwarded():
    runtime = validate_runtime_args(
        ["--apply", "--confirm", "APPLY-DVD-SECOND-WAVE-2A-27"]
    )
    assert runtime == [
        "--apply",
        "--confirm",
        "APPLY-DVD-SECOND-WAVE-2A-27",
    ]

    runtime_equals = validate_runtime_args(
        ["--rollback", "--confirm=ROLLBACK-DVD-SECOND-WAVE-2A-27"]
    )
    assert runtime_equals[0] == "--rollback"


@pytest.mark.parametrize(
    "args",
    [
        ["--backup-dir", "/tmp/unsafe"],
        ["--expected-backup-sha256", "0" * 64],
        ["--expected-manifest-sha256", "0" * 64],
        ["--expected-count", "28"],
        ["--academic-year", "2027"],
        ["--reference-date", "2026-08-19"],
        ["--receipt-dir", "/tmp/receipts"],
        ["--tenant-id", "other"],
    ],
)
def test_authoritative_scope_cannot_be_overridden(args):
    with pytest.raises(PersistentSealArgumentError, match="SEALED_ARGUMENT_OVERRIDE"):
        validate_runtime_args(args)


def test_apply_and_rollback_cannot_be_combined():
    with pytest.raises(PersistentSealArgumentError, match="MUTUALLY_EXCLUSIVE"):
        validate_runtime_args(["--apply", "--rollback"])


def test_confirmation_requires_value():
    with pytest.raises(PersistentSealArgumentError, match="CONFIRM_VALUE_REQUIRED"):
        validate_runtime_args(["--apply", "--confirm"])


def test_wrapper_has_no_direct_mongo_mutators():
    src = Path("scripts/apply_dvd_second_wave_2a_persistent.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
    )
    assert not any(token in src for token in forbidden)
    assert "await implementation.main()" in src
