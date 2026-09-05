from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3c_1_documented_baseline_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3c_backup_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3c-1-documented-baseline.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_baseline_identity_is_exact_and_documented():
    src = read(RUNNER)
    assert "database/sigesc-full-20260819T140519Z.archive.gz" in src
    assert "f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a" in src
    assert "expected_image='mongo:7'" in src
    assert "gzip -t" in src
    assert "sha256sum" in src
    assert "F63C1_BASELINE_PROVENANCE=DOCUMENTED_PRE_DVD_BASELINE" in src


def test_restore_is_never_directed_at_production_mongo():
    src = read(RUNNER)
    assert '--network none' in src
    assert 'dst=/backup,readonly' in src
    assert 'dst=/forensic/probe.js,readonly' in src
    assert 'docker exec "$drill" mongorestore' in src
    assert 'docker exec "$mongo_container" mongorestore' not in src
    assert "PRODUCTION_DATABASE_TOUCHED=NO" in src
    assert "TEMP_RESTORE_NETWORK=none" in src
    assert "TEMP_RESTORE_PORTS=none" in src
    assert "BACKUP_MOUNT=read_only" in src


def test_namespace_allowlist_excludes_sensitive_student_domains():
    src = read(RUNNER)
    expected = {
        "users", "staff", "schools", "classes", "courses",
        "teacher_assignments", "teacher_class_assignments",
        "learning_objects", "content_entries", "audit_logs",
    }
    restored = set(re.findall(r"--nsInclude=sigesc\.([A-Za-z0-9_]+)", src))
    assert restored == expected
    for forbidden in ("students", "enrollments", "attendance", "grades"):
        assert f"--nsInclude=sigesc.{forbidden}" not in src


def test_reuses_metadata_only_probe_and_never_emits_plaintext():
    probe = read(PROBE)
    assert "LUIZ_GOMES_F6_3C_BACKUP_POINT_METADATA_V2" in probe
    assert "pedagogical_plaintext_emitted: false" in probe
    assert "pedagogical_payload_boolean_only: true" in probe
    for forbidden in (
        "content: 1", "methodology: 1", "observations: 1", "resources: 1",
        "records: 1", "student_id: 1",
    ):
        assert forbidden not in probe


def test_runner_has_cleanup_on_error_and_success():
    src = read(RUNNER)
    assert "trap cleanup EXIT" in src
    assert 'docker rm -f "$drill"' in src
    assert 'rm -f "$probe_host"' in src
    assert "TEMP_CONTAINERS_CLEANED=YES" in src


def test_workflow_is_exact_sha_owner_gated():
    src = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in src
    assert "LUIZ_GOMES_F6_3C_1_BASELINE':'AUTHORIZED'" in src
    assert "RESTORE_DOCUMENTED_20260819_BASELINE_IN_ISOLATED_TEMP_MONGO" in src
    assert "TARGET_SHA" in src
    assert "EXPECTED_PRODUCTION_SHA" in src
    assert "TRACKING_ISSUE':'357'" in src
    assert "LUIZ_GOMES_F6_3C_1_MAIN_MOVED" in src
    assert "LUIZ_GOMES_F6_3C_1_PRODUCTION_MOVED" in src


def test_probe_error_is_inconclusive_not_negative():
    src = read(WORKFLOW)
    assert "DOCUMENTED_BASELINE_PROBE_ERROR" in src
    assert "status='INCONCLUSIVE'" in src
    assert "DOCUMENTED_BASELINE_NO_RECOVERABLE_LUIZ_MATH" in src
    assert "if not complete:" in src


def test_no_deploy_or_database_write_commands():
    combined = (read(RUNNER) + "\n" + read(PROBE) + "\n" + read(WORKFLOW)).lower()
    for forbidden in (
        "git pull", "docker compose up", "docker stack deploy", "kubectl apply",
        "insertone(", "insert_many", "updateone(", "updatemany(",
        "deleteone(", "delete_many", "replaceone(",
    ):
        assert forbidden not in combined
