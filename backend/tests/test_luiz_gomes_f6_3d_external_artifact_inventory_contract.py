from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_external_artifact_inventory.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-external-artifact-inventory.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_search_roots_are_explicit_bounded_and_canonical_tree_excluded():
    src = read(RUNNER)
    assert "roots=(/root /opt /srv /var/backups)" in src
    assert "canonical_root='/root/sigesc-backups'" in src
    assert 'find "$root" -xdev -maxdepth 8' in src
    assert '-path "$canonical_root/*"' in src
    assert "count <= 200" in src


def test_candidate_patterns_cover_expected_historical_artifacts():
    src = read(RUNNER)
    for marker in (
        "*.archive.gz",
        "*.bson",
        "*.bson.gz",
        "*.dump",
        "*.dump.gz",
        "*sigesc*.tar.gz",
        "*mongo*.tar.gz",
        "*backup*.tar.gz",
        "*sigesc*.zip",
        "*mongo*.zip",
        "*backup*.zip",
    ):
        assert marker in src


def test_only_metadata_and_sanitized_fingerprint_are_emitted():
    src = read(RUNNER)
    assert "stat -Lc '%d:%i'" in src
    assert "stat -Lc '%Y'" in src
    assert "stat -Lc '%s'" in src
    assert "path_fingerprint" in src
    assert "filename_date" in src
    assert "mtime_date" in src
    assert "artifact_kind" in src
    assert "source_root" in src
    assert "F63D_PATHS_EMITTED=NO" in src
    point_line = [line for line in src.splitlines() if "F63D_POINT_JSON=" in line][0]
    assert '"path":' not in point_line
    assert '"basename":' not in point_line


def test_runner_never_reads_file_contents_or_accesses_mongo():
    src = read(RUNNER).lower()
    for forbidden in (
        "mongosh",
        "mongorestore",
        "docker exec",
        "docker run",
        "gzip -t",
        "sha256sum \"$candidate\"",
        "cat \"$candidate\"",
        "head \"$candidate\"",
        "tail \"$candidate\"",
        "strings \"$candidate\"",
    ):
        assert forbidden not in src
    assert "f63d_file_content_read=no" in src
    assert "f63d_mongo_accessed=no" in src
    assert "f63d_restore_executed=no" in src
    assert "f63d_filesystem_read_only=yes" in src


def test_workflow_is_owner_gated_sha_locked_and_fail_closed():
    src = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in src
    assert "LUIZ_GOMES_F6_3D_ARTIFACT_INVENTORY':'AUTHORIZED'" in src
    assert "INVENTORY_NONCANONICAL_HISTORICAL_ARTIFACTS_READ_ONLY" in src
    assert "TARGET_SHA" in src
    assert "EXPECTED_PRODUCTION_SHA" in src
    assert "TRACKING_ISSUE':'357'" in src
    assert "LUIZ_GOMES_F6_3D_MAIN_MOVED" in src
    assert "LUIZ_GOMES_F6_3D_PRODUCTION_MOVED" in src
    assert "EXTERNAL_ARTIFACT_INVENTORY_PROBE_ERROR" in src


def test_no_deploy_or_production_mutation_commands_in_runner():
    src = read(RUNNER).lower()
    for forbidden in (
        "git pull",
        "docker compose up",
        "docker stack deploy",
        "kubectl apply",
        "insertone(",
        "updateone(",
        "deleteone(",
        "delete_many",
        "rm -rf",
        "mv ",
        "cp ",
    ):
        assert forbidden not in src
