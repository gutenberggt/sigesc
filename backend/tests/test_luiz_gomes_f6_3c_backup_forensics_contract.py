from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3c_backup_probe.js"
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3c_retained_backup_runner.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3c-retained-backup-forensics.yml"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_probe_scope_is_exact_and_metadata_only():
    src = text(PROBE)
    assert '"Luiz Gomes dos Santos"' in src
    assert '"E M E I E F Jose Pereira Barbosa"' in src
    assert '["8º ANO A", "9º ANO A"]' in src
    assert 'const START = "2026-02-01"' in src
    assert 'const END = "2026-05-01"' in src
    assert 'LUIZ_GOMES_F6_3C_BACKUP_POINT_METADATA_V2' in src

    # O plaintext pode ser consultado apenas pelo motor Mongo para produzir
    # payload_present; jamais deve ser projetado/emitido para o shell/artifact.
    for forbidden_projection in (
        "content: 1",
        "methodology: 1",
        "observations: 1",
        "resources: 1",
        "records: 1",
        "student_id: 1",
    ):
        assert forbidden_projection not in src
    assert "payload_present" in src
    assert '"$content"' in src
    assert '"$methodology"' in src
    assert '"$observations"' in src
    assert "pedagogical_plaintext_emitted: false" in src
    assert "pedagogical_payload_boolean_only: true" in src
    assert "attendance_records_read: false" in src
    assert "student_data_read: false" in src
    assert "technical_ids_emitted: false" in src


def test_probe_requires_payload_for_strong_recovery_classification():
    src = text(PROBE)
    assert "luiz_math_payload_rows" in src
    assert "luiz_math_rows_without_payload" in src
    assert "RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED" in src
    assert "LUIZ_MATH_ROWS_PRESENT_WITHOUT_PAYLOAD" in src
    strong = src.index('classification = "RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED"')
    payload_guard = src.rfind("luizMathPayloadTotal > 0", 0, strong)
    assert payload_guard >= 0


def test_runner_deduplicates_by_physical_inode_not_checksum():
    src = text(RUNNER)
    assert "stat -Lc '%d:%i'" in src
    assert "path_by_inode" in src
    assert "sha_by_inode" in src
    assert "path_by_sha" not in src
    assert "gzip -t" in src
    assert "sha256sum" in src
    assert "F63C_HARDLINK_SHA_INCONSISTENT" in src


def test_runner_validates_provenance_before_restore():
    src = text(RUNNER)
    restore_at = src.index('docker exec "$drill" mongorestore')
    for marker in (
        'grep -Fq "$mongo_name" "$meta_sidecar"',
        'grep -Fq "$mongo_image" "$meta_sidecar"',
        "F63C_PROVENANCE_CONTAINER_FAIL",
        "F63C_PROVENANCE_IMAGE_FAIL",
    ):
        assert marker in src
        if marker.startswith("grep"):
            assert src.index(marker) < restore_at


def test_runner_restores_only_allowlisted_collections_in_isolated_container():
    src = text(RUNNER)
    assert '--network none' in src
    assert 'dst=/backup,readonly' in src
    assert 'dst=/forensic/probe.js,readonly' in src
    assert 'docker exec "$drill" mongorestore' in src
    assert 'docker exec "$mongo_container" mongorestore' not in src

    allowed = {
        "users",
        "staff",
        "schools",
        "classes",
        "courses",
        "teacher_assignments",
        "teacher_class_assignments",
        "learning_objects",
        "content_entries",
        "audit_logs",
    }
    restored = set(re.findall(r"--nsInclude=sigesc\.([A-Za-z0-9_]+)", src))
    assert restored == allowed
    for forbidden in ("students", "enrollments", "attendance", "grades"):
        assert f"--nsInclude=sigesc.{forbidden}" not in src


def test_runner_cleanup_and_production_boundary_are_explicit():
    src = text(RUNNER)
    assert "trap cleanup_all EXIT" in src
    assert 'docker rm -f "$drill"' in src
    assert "PRODUCTION_DATABASE_TOUCHED=NO" in src
    assert "TEMP_RESTORE_NETWORK=none" in src
    assert "TEMP_RESTORE_PORTS=none" in src
    assert "BACKUP_MOUNT=read_only" in src
    assert "TEMP_CONTAINERS_CLEANED=YES" in src


def test_workflow_is_owner_gated_and_sha_locked():
    src = text(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in src
    assert "LUIZ_GOMES_F6_3C_BACKUP_FORENSICS':'AUTHORIZED'" in src
    assert "RESTORE_RETAINED_BACKUPS_IN_ISOLATED_TEMP_MONGO" in src
    assert "TARGET_SHA" in src
    assert "EXPECTED_PRODUCTION_SHA" in src
    assert "/branches/main" in src
    assert "/branches/production" in src
    assert "LUIZ_GOMES_F6_3C_MAIN_MOVED" in src
    assert "LUIZ_GOMES_F6_3C_PRODUCTION_MOVED" in src
    assert "TRACKING_ISSUE':'357'" in src


def test_workflow_never_maps_probe_failure_to_negative_data_conclusion():
    src = text(WORKFLOW)
    assert "status='INCONCLUSIVE'" in src
    assert "classification='BACKUP_FORENSICS_PROBE_ERROR'" in src
    assert "NO_RECOVERABLE_LUIZ_MATH_IN_ALL_RETAINED_BACKUPS" in src
    inconclusive_at = src.index("classification='BACKUP_FORENSICS_PROBE_ERROR'")
    negative_at = src.index("classification='NO_RECOVERABLE_LUIZ_MATH_IN_ALL_RETAINED_BACKUPS'")
    assert inconclusive_at < negative_at
    assert "if not complete:" in src


def test_runtime_artifact_is_structured_and_raw_log_is_deleted():
    src = text(WORKFLOW)
    assert "evidence/runtime.json" in src
    assert "raw.unlink()" in src
    assert "operational_markers" in src
    assert "pedagogical_plaintext_emitted" in src
    assert "pedagogical_payload_boolean_only" in src
    assert "technical_ids_emitted" in src
    assert "Upload metadata-only forensic evidence" in src


def test_no_deploy_or_production_database_write_commands_exist():
    combined = "\n".join((text(PROBE), text(RUNNER), text(WORKFLOW))).lower()
    for forbidden in (
        "git pull",
        "docker compose up",
        "docker stack deploy",
        "kubectl apply",
        "delete_many",
        "deleteone(",
        "insertone(",
        "insert_many",
        "updateone(",
        "updatemany(",
        "replaceone(",
    ):
        assert forbidden not in combined
