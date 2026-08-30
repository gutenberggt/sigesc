from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM_SCRIPT = ROOT / "scripts" / "build_p0f7_9d763_authorized_revised_executor_js.py"
FIXTURE_TEST = Path(__file__).with_name("test_p0f7_9d76_authorized_revised_executor.py")

_shim_spec = importlib.util.spec_from_file_location("p0f7_9d763_builder_test", SHIM_SCRIPT)
assert _shim_spec and _shim_spec.loader
shim = importlib.util.module_from_spec(_shim_spec)
_shim_spec.loader.exec_module(shim)

_fixture_spec = importlib.util.spec_from_file_location("p0f7_9d76_fixture_test", FIXTURE_TEST)
assert _fixture_spec and _fixture_spec.loader
fixtures = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(fixtures)


def _rehash(manifest: dict) -> dict:
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = shim.d761.d76._canonical_sha256(manifest)
    return manifest


def _real_status_manifest() -> dict:
    manifest = copy.deepcopy(fixtures._manifest())
    retire = manifest["operations"][21]
    retire["cas_expected"]["status"] = "ativo"
    retire["rollback_set_fields"]["status"] = "ativo"
    return _rehash(manifest)


def test_generated_writer_uses_mongosh_projection_second_argument() -> None:
    manifest = _real_status_manifest()
    js, metadata = shim.d761.d76.build_executor(
        manifest,
        "sigesc",
        authorized=True,
        expected_manifest_sha=manifest["manifest_sha256"],
    )

    assert metadata["executor_materialized"] is True
    assert "{projection:" not in js
    assert "{_id:0,id:1}" in js
    assert "{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}" in js
    assert "{_id:0,id:1,status:1,course_id:1,carga_horaria_semanal:1}" in js


def test_projection_fix_preserves_exact_sealed_retire_status() -> None:
    manifest = _real_status_manifest()
    js, _ = shim.d761.d76.build_executor(
        manifest,
        "sigesc",
        authorized=True,
        expected_manifest_sha=manifest["manifest_sha256"],
    )

    assert '"status":"ativo"' in js
    assert "targetDb.teacher_assignments.updateOne" in js
    assert "deleteOne" not in js
    assert "deleteMany" not in js


def test_projection_patch_is_complete_and_fail_closed() -> None:
    template = shim.d761.d76._JS_TEMPLATE
    assert "{projection:" not in template
    assert template.count("{_id:0,id:1}") == 1
    assert (
        template.count(
            "{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}"
        )
        == 4
    )
    assert (
        template.count(
            "{_id:0,id:1,status:1,course_id:1,carga_horaria_semanal:1}"
        )
        == 1
    )
