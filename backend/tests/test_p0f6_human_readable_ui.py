from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_p0f6_private_human_adjudication_station_human_ui.py"
spec = importlib.util.spec_from_file_location("p0f6_human_ui", SCRIPT)
assert spec and spec.loader
p0f6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f6)


def _packet() -> dict:
    unit = {
        "review_unit_id": "u-learning",
        "unit_type": "PEDAGOGICAL_CONTENT_FIELD_DECISION",
        "field_name": "methodology",
        "student_id": None,
        "context": {
            "school_id": "school-1",
            "school_name": "Escola Exemplo",
            "class_id": "class-1",
            "class_name": "8º ANO A",
            "academic_year": 2026,
            "date": "2026-02-10",
            "period": None,
            "aula_numero": None,
            "student_name": None,
        },
        "source_actor": {"recorded_by": {"id": "usr-1", "name": "Professora A"}},
        "target_actor": {"recorded_by": {"id": "usr-1", "name": "Professora A"}},
        "source_value": "Aula dialogada.",
        "target_value": "Aula dialogada com conhecimentos prévios.",
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
                        "conflict_id": "c-learning",
                        "collection": "learning_objects",
                        "review_units": [unit],
                    }
                ],
            }
        ],
    }
    packet["manifest_sha256"] = p0f6.canonical_sha256(packet)
    return packet


def test_human_ui_preserves_contract_and_humanizes_visible_labels(tmp_path: Path):
    packet = _packet()
    src = tmp_path / "packet.json"
    out = tmp_path / "station.html"
    src.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    result = p0f6.build_station(src, out)
    text = out.read_text(encoding="utf-8")

    assert result["status"] == "PASS"
    assert result["human_ui_phase"] == p0f6.HUMAN_UI_PHASE
    assert result["human_readable_ui"] is True
    assert result["neutral_record_labels"] is True
    assert result["technical_contract_preserved"] is True
    assert result["database_mutation"] is False
    assert result["output_file_mode"] == "0600"

    assert "Componente curricular" in text
    assert "Tipo de registro" in text
    assert "Manter Registro 1" in text
    assert "Manter Registro 2" in text
    assert "Conciliar manualmente" in text
    assert "Quem registrou — Registro 1" in text
    assert "Quem registrou — Registro 2" in text
    assert "Registro 1 e Registro 2 são rótulos neutros" in text
    assert "Detalhes técnicos" in text

    # O contrato técnico continua no payload/JS, mas a renderização usa tradutores.
    assert "labelCollection(row.collection)" in text
    assert "labelUnitType(u.unit_type)" in text
    assert "labelField(u.field_name||u.unit_type)" in text
    assert "humanContext(u.context||{})" in text
    assert "humanValue(u.source_value,u.field_name)" in text
    assert "humanValue(u.target_value,u.field_name)" in text
    assert "KEEP_SOURCE" in text
    assert "KEEP_TARGET" in text
    assert "MANUAL_RECONCILIATION" in text


def test_human_ui_javascript_is_syntactically_valid(tmp_path: Path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")

    packet = _packet()
    src = tmp_path / "packet.json"
    out = tmp_path / "station.html"
    js = tmp_path / "inline.js"
    src.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    p0f6.build_station(src, out)
    text = out.read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", text, re.S)
    assert match
    js.write_text(match.group(1), encoding="utf-8")

    proc = subprocess.run(
        [node, "--check", str(js)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_humanization_is_fail_closed_when_expected_marker_moves():
    with pytest.raises(RuntimeError, match="P0F6_2_UI_PATTERN_PRELUDE_COUNT:0"):
        p0f6.humanize_generated_html("<html>estrutura inesperada</html>")


def test_script_has_no_database_or_apply_surface():
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
