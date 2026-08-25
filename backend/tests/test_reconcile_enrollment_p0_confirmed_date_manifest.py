import json

import pytest

from scripts.reconcile_enrollment_p0_confirmed_date_2026 import load_manifest


def test_manifest_requires_ready_quarantine_and_2026(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"year": 2026, "ready": [], "quarantine": []}), encoding="utf-8")
    manifest = load_manifest(str(path))
    assert manifest["year"] == 2026


def test_manifest_rejects_other_year(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"year": 2025, "ready": [], "quarantine": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(str(path))
