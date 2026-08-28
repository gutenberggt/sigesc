from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_p0f6_private_human_adjudication_station_hotfix.py"
)
spec = importlib.util.spec_from_file_location("p0f6_hotfix", SCRIPT)
assert spec and spec.loader
p0f6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f6)


def _packet() -> dict:
    unit = {
        "review_unit_id": "unit-1",
        "unit_type": "GRADE_FIELD_DECISION",
        "field_name": "b1",
        "student_id": "student-1",
        "context": {"student_name": "Aluno Teste", "class_name": "8º A"},
        "source_actor": {},
        "target_actor": {},
        "source_value": 8.0,
        "target_value": 7.5,
        "decision_contract": {
            "status": "PENDING_HUMAN_DECISION",
            "allowed_decisions": list(p0f6.ALLOWED_DECISIONS),
            "automatic_recommendation": None,
            "decision": None,
            "decision_note": None,
        },
    }
    packet = {
        "phase": p0f6.P0F5_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "summary": {
            "review_units": 1,
            "pending_human_decisions": 1,
            "complete_conflict_coverage": True,
            "unresolved_review_conflicts": 0,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "cases": [
            {
                "group_number": 1,
                "identity": {"display_name": "Ciências"},
                "conflicts": [
                    {
                        "conflict_id": "conflict-1",
                        "collection": "grades",
                        "review_units": [unit],
                    }
                ],
            }
        ],
    }
    packet["manifest_sha256"] = p0f6.canonical_sha256(packet)
    return packet


def test_hotfix_generates_javascript_that_node_can_parse(tmp_path: Path):
    packet = _packet()
    src = tmp_path / "packet.json"
    out = tmp_path / "station.html"
    src.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    result = p0f6.build_station(src, out)
    text = out.read_text(encoding="utf-8")

    assert result["status"] == "PASS"
    assert result["javascript_newline_escape_repaired"] is True
    assert result["output_file_mode"] == "0600"
    assert result["database_mutation"] is False

    # O HTML final deve conter backslash+n dentro da string JS, nunca newline físico.
    assert "JSON.stringify(payload,null,2)+'\\n'" in text
    assert "JSON.stringify(payload,null,2)+'\n'" not in text

    javascript = text.split("<script>", 1)[1].split("</script>", 1)[0]
    node = shutil.which("node")
    assert node is not None, "Node.js é obrigatório no guard P0-F6.1"
    checked = subprocess.run(
        [node, "--check"],
        input=javascript,
        text=True,
        capture_output=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


def test_hotfix_script_has_no_database_or_apply_surface():
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "asynciomotorclient" not in lowered
    assert "mongo_url" not in lowered
    assert "--apply" not in lowered
    for token in (
        ".update_one(",
        ".update_many(",
        ".delete_one(",
        ".delete_many(",
        ".insert_one(",
        ".bulk_write(",
    ):
        assert token not in source
