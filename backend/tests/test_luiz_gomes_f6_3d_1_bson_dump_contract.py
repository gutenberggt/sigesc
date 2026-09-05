from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3c_backup_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-1-bson-dump.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_selection_is_single_group_pre_0819_and_coherent():
    src = read(RUNNER)
    assert "2026-08-18" in src
    assert "required=(users schools classes courses learning_objects)" in src
    assert '"${#eligible[@]}" -eq 1' in src
    assert "spread <= 600" in src
    assert "structural_only_ad_hoc_bson_dump" in src
    assert "F63D1_GROUP_SELECTION=PASS" in src


def test_canonical_tree_is_excluded_and_source_is_read_only():
    src = read(RUNNER)
    assert "canonical_root='/root/sigesc-backups'" in src
    assert '-path "$canonical_root/*"' in src
    assert "F63D1_CANONICAL_BACKUP_TREE_EXCLUDED=YES" in src
    assert "dst=/dump,readonly" in src
    assert "F63D1_SOURCE_FILES_MUTATED=NO" in src


def test_restore_is_network_isolated_and_collection_allowlisted():
    src = read(RUNNER)
    assert "--network none" in src
    assert "TEMP_RESTORE_NETWORK=none" in src
    assert "TEMP_RESTORE_PORTS=none" in src
    assert "PRODUCTION_DATABASE_TOUCHED=NO" in src
    assert "mongorestore --quiet --stopOnError --db sigesc --collection" in src
    for forbidden in (
        "students",
        "enrollments",
        "attendance",
        "grades",
        "attendance_documentary",
    ):
        assert forbidden not in src


def test_probe_does_not_emit_sensitive_academic_plaintext():
    probe = read(PROBE)
    for banned in (
        "content: 1",
        "methodology: 1",
        "observations: 1",
        "records: 1",
        "student_id: 1",
    ):
        assert banned not in probe
    assert "payload_present" in probe
    assert "pedagogical_plaintext_emitted: false" in probe


def test_workflow_is_owner_gated_exact_sha_and_fail_closed():
    wf = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in wf
    assert "LUIZ_GOMES_F6_3D_1_BSON_DUMP':'AUTHORIZED'" in wf
    assert "RESTORE_20260818_ADHOC_BSON_IN_ISOLATED_TEMP_MONGO" in wf
    assert "TARGET_SHA" in wf
    assert "EXPECTED_PRODUCTION_SHA" in wf
    assert "TRACKING_ISSUE':'357'" in wf
    assert "LUIZ_GOMES_F6_3D_1_MAIN_MOVED" in wf
    assert "LUIZ_GOMES_F6_3D_1_PRODUCTION_MOVED" in wf
    assert "BSON_DUMP_PROBE_ERROR" in wf


def test_no_deploy_or_data_mutation_path():
    combined = (read(RUNNER) + "\n" + read(WORKFLOW)).lower()
    for forbidden in (
        "git pull",
        "docker compose up",
        "docker stack deploy",
        "kubectl apply",
        "insertone(",
        "updateone(",
        "deleteone(",
        "delete_many",
        "rm -rf /root/sigesc-backups",
    ):
        assert forbidden not in combined
