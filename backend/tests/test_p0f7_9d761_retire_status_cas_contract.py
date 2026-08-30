from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIM_SCRIPT = ROOT / "scripts" / "build_p0f7_9d761_authorized_revised_executor_js.py"
VALIDATOR_SCRIPT = ROOT / "scripts" / "validate_p0f7_9d76_execution_receipt_offline.py"
FIXTURE_TEST = Path(__file__).with_name("test_p0f7_9d76_authorized_revised_executor.py")

_shim_spec = importlib.util.spec_from_file_location("p0f7_9d761_builder_test", SHIM_SCRIPT)
assert _shim_spec and _shim_spec.loader
shim = importlib.util.module_from_spec(_shim_spec)
_shim_spec.loader.exec_module(shim)

_validator_spec = importlib.util.spec_from_file_location(
    "p0f7_9d762_receipt_validator_test", VALIDATOR_SCRIPT
)
assert _validator_spec and _validator_spec.loader
validator = importlib.util.module_from_spec(_validator_spec)
_validator_spec.loader.exec_module(validator)

_fixture_spec = importlib.util.spec_from_file_location("p0f7_9d76_fixture_test", FIXTURE_TEST)
assert _fixture_spec and _fixture_spec.loader
fixtures = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(fixtures)


def _rehash(manifest: dict) -> dict:
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = shim.d76._canonical_sha256(manifest)
    return manifest


def test_exact_active_retire_status_from_real_sealed_contract_is_accepted() -> None:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "active"
    retire["rollback_set_fields"]["status"] = "active"
    _rehash(manifest)

    js, metadata = shim.d76.build_executor(
        manifest,
        "sigesc",
        authorized=True,
        expected_manifest_sha=manifest["manifest_sha256"],
    )

    assert metadata["executor_materialized"] is True
    assert metadata["production_write_authorized"] is True
    assert '"status":"active"' in js
    assert '"status":"ativo_or_active"' in js  # other operations may retain the legacy alias


def test_exact_ativo_retire_status_is_accepted_and_preserved() -> None:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "ativo"
    retire["rollback_set_fields"]["status"] = "ativo"
    _rehash(manifest)

    ctx = shim.d76.validate_manifest(
        manifest,
        expected_manifest_sha=manifest["manifest_sha256"],
    )
    assert ctx["operations"][21]["cas_expected"]["status"] == "ativo"


def test_non_active_retire_status_remains_fail_closed() -> None:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "inativo"
    retire["rollback_set_fields"]["status"] = "inativo"
    _rehash(manifest)

    with pytest.raises(ValueError, match="RETIRE_STATUS_CAS_INVALID"):
        shim.d76.validate_manifest(
            manifest,
            expected_manifest_sha=manifest["manifest_sha256"],
        )


def test_exact_status_requires_exact_rollback_status() -> None:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "active"
    retire["rollback_set_fields"]["status"] = "ativo"
    _rehash(manifest)

    with pytest.raises(ValueError, match="RETIRE_ROLLBACK_STATUS_MISMATCH"):
        shim.d76.validate_manifest(
            manifest,
            expected_manifest_sha=manifest["manifest_sha256"],
        )


def test_receipt_validator_uses_same_exact_status_contract() -> None:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "active"
    retire["rollback_set_fields"]["status"] = "active"
    _rehash(manifest)

    ctx = validator.builder.validate_manifest(
        manifest,
        expected_manifest_sha=manifest["manifest_sha256"],
    )

    assert ctx["operations"][21]["cas_expected"]["status"] == "active"
    assert validator.builder is not shim
