from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3c_2_backup_inventory.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3c-2-backup-inventory.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_inventory_is_recursive_physical_and_bounded():
    src = read(RUNNER)
    assert "find \"$backup_root\" -xdev -maxdepth 6" in src
    assert "stat -Lc '%d:%i'" in src
    assert "F63C2_PHYSICAL_ARCHIVE_COUNT" in src
    assert "count <= 100" in src


def test_inventory_emits_only_sanitized_metadata():
    src = read(RUNNER)
    assert "filename_date" in src
    assert "mtime_date" in src
    assert "size_bytes" in src
    assert "source_class" in src
    assert "sha_sidecar" in src
    assert "metadata_sidecar" in src
    assert "F63C2_PATHS_EMITTED=NO" in src
    assert 'printf \'F63C2_POINT_JSON=' in src
    # rel/base são usados internamente, mas não aparecem no JSON emitido.
    json_printf = [line for line in src.splitlines() if "F63C2_POINT_JSON=" in line][0]
    assert "rel" not in json_printf
    assert "base" not in json_printf


def test_inventory_never_accesses_mongo_or_restores():
    src = read(RUNNER).lower()
    for forbidden in ("mongosh", "mongorestore", "mongo_container", "docker exec", "docker run"):
        assert forbidden not in src
    assert "f63c2_mongo_accessed=no" in src
    assert "f63c2_restore_executed=no" in src
    assert "f63c2_filesystem_read_only=yes" in src


def test_workflow_is_owner_gated_and_sha_locked():
    src = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in src
    assert "LUIZ_GOMES_F6_3C_2_BACKUP_INVENTORY':'AUTHORIZED'" in src
    assert "INVENTORY_BACKUP_ARCHIVES_READ_ONLY" in src
    assert "TARGET_SHA" in src
    assert "EXPECTED_PRODUCTION_SHA" in src
    assert "TRACKING_ISSUE':'357'" in src
    assert "LUIZ_GOMES_F6_3C_2_MAIN_MOVED" in src
    assert "LUIZ_GOMES_F6_3C_2_PRODUCTION_MOVED" in src


def test_workflow_has_inconclusive_probe_error_taxonomy():
    src = read(WORKFLOW)
    assert "BACKUP_INVENTORY_PROBE_ERROR" in src
    assert "status='INCONCLUSIVE'" in src
    assert "BACKUP_INVENTORY_COMPLETED" in src


def test_no_deploy_or_mutation_commands():
    combined = (read(RUNNER) + "\n" + read(WORKFLOW)).lower()
    for forbidden in (
        "git pull", "docker compose up", "docker stack deploy", "kubectl apply",
        "mongorestore", "insertone(", "updateone(", "deleteone(", "delete_many",
        "rm -rf /root/sigesc-backups",
    ):
        assert forbidden not in combined
