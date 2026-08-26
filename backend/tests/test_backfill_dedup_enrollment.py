"""Regressão: escritores legados de enrollment_number permanecem aposentados."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKFILL = REPO_ROOT / "backend" / "scripts" / "backfill_dedup_enrollment.py"
DIRECT_GENERATOR = REPO_ROOT / "generate_enrollment_numbers.py"

FORBIDDEN_WRITE_MARKERS = (
    "AsyncIOMotorClient",
    ".update_one(",
    ".update_many(",
    ".insert_one(",
    ".insert_many(",
    ".delete_one(",
    ".delete_many(",
    ".find_one_and_update(",
    ".replace_one(",
    ".bulk_write(",
    ".create_index(",
    "generate_enrollment_number(",
)


def _load(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_backfill_is_fail_closed_tombstone():
    mod = _load(BACKFILL, "retired_backfill_dedup_enrollment")
    assert mod.RETIREMENT_CODE == "LEGACY_ENROLLMENT_BACKFILL_RETIRED"
    assert mod.main() == 2


def test_direct_student_number_generator_is_fail_closed_tombstone():
    mod = _load(DIRECT_GENERATOR, "retired_generate_enrollment_numbers")
    assert mod.RETIREMENT_CODE == "LEGACY_ENROLLMENT_NUMBER_WRITER_RETIRED"
    assert mod.main() == 2


def test_retired_scripts_have_no_database_or_number_generation_write_path():
    for path in (BACKFILL, DIRECT_GENERATOR):
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_WRITE_MARKERS:
            assert marker not in source, f"{path}: marcador proibido ainda presente: {marker}"


def test_retirement_message_requires_governed_reconciliation():
    for path in (BACKFILL, DIRECT_GENERATOR):
        source = path.read_text(encoding="utf-8").lower()
        assert "reconciliação governada" in source
        assert "tombstone" in source
