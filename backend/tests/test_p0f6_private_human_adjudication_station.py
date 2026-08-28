from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_p0f6_private_human_adjudication_station.py"
spec = importlib.util.spec_from_file_location("p0f6_station", SCRIPT)
assert spec and spec.loader
p0f6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f6)


def _packet() -> dict:
    units = [
        {
            "review_unit_id": "u-grade",
            "unit_type": "GRADE_FIELD_DECISION",
            "field_name": "b1",
            "student_id": "stu-1",
            "context": {"student_name": "Aluno Exemplo", "class_name": "8º A"},
            "source_actor": {"created_by": {"id": "usr-1", "name": "Prof A"}},
            "target_actor": {"created_by": {"id": "usr-2", "name": "Prof B"}},
            "source_value": 8.0,
            "target_value": 7.5,
            "decision_contract": {
                "status": "PENDING_HUMAN_DECISION",
                "allowed_decisions": list(p0f6.ALLOWED_DECISIONS),
                "automatic_recommendation": None,
                "decision": None,
                "decision_note": None,
            },
        },
        {
            "review_unit_id": "u-att",
            "unit_type": "ATTENDANCE_STUDENT_DECISION",
            "field_name": "records.status_or_dependency_id",
            "student_id": "stu-1",
            "context": {"student_name": "Aluno Exemplo", "date": "2026-05-02"},
            "source_actor": {},
            "target_actor": {},
            "source_value": [{"status": "present", "dependency_id": None}],
            "target_value": [{"status": "absent", "dependency_id": None}],
            "decision_contract": {
                "status": "PENDING_HUMAN_DECISION",
                "allowed_decisions": list(p0f6.ALLOWED_DECISIONS),
                "automatic_recommendation": None,
            },
        },
        {
            "review_unit_id": "u-learning",
            "unit_type": "PEDAGOGICAL_CONTENT_FIELD_DECISION",
            "field_name": "content",
            "student_id": None,
            "context": {"class_name": "8º A", "date": "2026-05-02"},
            "source_actor": {},
            "target_actor": {},
            "source_value": "Conteúdo source </script><script>alert(1)</script>",
            "target_value": "Conteúdo target",
            "decision_contract": {
                "status": "PENDING_HUMAN_DECISION",
                "allowed_decisions": list(p0f6.ALLOWED_DECISIONS),
                "automatic_recommendation": None,
            },
        },
    ]
    packet = {
        "phase": p0f6.P0F5_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "summary": {
            "review_units": 3,
            "pending_human_decisions": 3,
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
                    {"conflict_id": "c1", "collection": "grades", "review_units": [units[0]]},
                    {"conflict_id": "c2", "collection": "attendance", "review_units": [units[1]]},
                    {"conflict_id": "c3", "collection": "learning_objects", "review_units": [units[2]]},
                ],
            }
        ],
    }
    packet["manifest_sha256"] = p0f6.canonical_sha256(packet)
    return packet


def _raw(packet: dict) -> dict:
    return {
        "phase": p0f6.RAW_DECISION_PHASE,
        "manifest_version": 1,
        "source_p0f5_manifest_sha256": packet["manifest_sha256"],
        "station_phase": p0f6.STATION_PHASE,
        "reviewer": {
            "name": "Responsável Teste",
            "role": "Secretário Escolar",
            "identifier": "X-1",
            "authorized_acknowledgement": True,
        },
        "summary": {"review_units": 3, "decisions": 3},
        "decisions": [
            {"review_unit_id": "u-grade", "decision": "KEEP_SOURCE", "decision_note": "Conferido"},
            {"review_unit_id": "u-att", "decision": "KEEP_TARGET", "decision_note": None},
            {"review_unit_id": "u-learning", "decision": "MANUAL_RECONCILIATION", "decision_note": "Unificar os dois registros conforme ata."},
        ],
    }


def test_validate_packet_and_count_units():
    result = p0f6.validate_p0f5_packet(_packet())
    assert result["review_unit_count"] == 3
    assert set(result["review_units"]) == {"u-grade", "u-att", "u-learning"}


def test_packet_sha_is_fail_closed():
    packet = _packet()
    packet["summary"]["review_units"] = 999
    with pytest.raises(ValueError, match="MANIFEST_SHA256_MISMATCH"):
        p0f6.validate_p0f5_packet(packet)


def test_build_station_is_offline_and_escapes_script_payload(tmp_path: Path):
    packet = _packet()
    src = tmp_path / "packet.json"
    out = tmp_path / "station.html"
    src.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    result = p0f6.build_station(src, out)
    text = out.read_text(encoding="utf-8")

    assert result["status"] == "PASS"
    assert result["network_dependencies"] == 0
    assert result["output_file_mode"] == "0600"
    assert "Content-Security-Policy" in text
    assert "connect-src 'none'" in text
    assert "https://" not in text
    assert "http://" not in text
    assert "</script><script>alert(1)</script>" not in text
    assert "\\u003c/script\\u003e" in text


def test_raw_decisions_require_complete_exact_coverage():
    packet = _packet()
    validation = p0f6.validate_p0f5_packet(packet)
    raw = _raw(packet)
    raw["decisions"].pop()
    with pytest.raises(ValueError, match="MISSING_DECISIONS:1"):
        p0f6.validate_raw_decisions(packet, validation, raw)


def test_unknown_review_unit_is_rejected():
    packet = _packet()
    validation = p0f6.validate_p0f5_packet(packet)
    raw = _raw(packet)
    raw["decisions"][0]["review_unit_id"] = "unknown"
    with pytest.raises(ValueError, match="UNKNOWN_REVIEW_UNIT_ID"):
        p0f6.validate_raw_decisions(packet, validation, raw)


def test_manual_reconciliation_requires_note():
    packet = _packet()
    validation = p0f6.validate_p0f5_packet(packet)
    raw = _raw(packet)
    raw["decisions"][2]["decision_note"] = ""
    with pytest.raises(ValueError, match="MANUAL_RECONCILIATION_NOTE_REQUIRED"):
        p0f6.validate_raw_decisions(packet, validation, raw)


def test_seal_creates_private_complete_manifest(tmp_path: Path):
    packet = _packet()
    raw = _raw(packet)
    packet_path = tmp_path / "packet.json"
    raw_path = tmp_path / "decisions.json"
    out = tmp_path / "sealed.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    result = p0f6.seal_decisions(packet_path, raw_path, out)
    sealed = json.loads(out.read_text(encoding="utf-8"))

    assert result["status"] == "SEALED_COMPLETE_HUMAN_DECISIONS"
    assert result["decisions"] == 3
    assert result["output_file_mode"] == "0600"
    assert sealed["summary"]["complete_decision_coverage"] is True
    assert sealed["summary"]["pending_human_decisions"] == 0
    assert sealed["summary"]["database_mutation"] is False
    stored = sealed.pop("decision_manifest_sha256")
    assert stored == p0f6.canonical_sha256(sealed)


def test_script_has_no_database_or_apply_surface():
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "asynciomotorclient" not in lowered
    assert "mongo_url" not in lowered
    assert "--apply" not in lowered
    for token in (".update_one(", ".update_many(", ".delete_one(", ".delete_many(", ".insert_one(", ".bulk_write("):
        assert token not in source
