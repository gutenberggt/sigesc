from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_p0f7_1_private_structured_manual_reconciliation_station.py"
P0F6_PATH = ROOT / "scripts" / "build_p0f6_private_human_adjudication_station.py"
P0F7_PATH = ROOT / "scripts" / "audit_p0f7_sealed_decisions_execution_preflight.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p0f71 = _load(SCRIPT, "p0f71_test")
p0f6 = _load(P0F6_PATH, "p0f6_for_p0f71_test")
p0f7 = _load(P0F7_PATH, "p0f7_for_p0f71_test")


def _unit(field: str = "methodology") -> dict:
    return {
        "review_unit_id": "manual-1",
        "unit_type": "PEDAGOGICAL_CONTENT_FIELD_DECISION",
        "field_name": field,
        "student_id": None,
        "context": {
            "school_name": "Escola Teste",
            "class_name": "8º ANO A",
            "academic_year": 2026,
            "date": "2026-05-04",
        },
        "source_document_ids": ["lo-source"],
        "target_document_ids": ["lo-target"],
        "source_actor": {"created_by": {"id": "u1", "name": "Docente 1"}},
        "target_actor": {"created_by": {"id": "u2", "name": "Docente 2"}},
        "source_value": "Metodologia do registro 1",
        "target_value": "Metodologia do registro 2",
        "decision_contract": {
            "status": "PENDING_HUMAN_DECISION",
            "allowed_decisions": ["KEEP_SOURCE", "KEEP_TARGET", "MANUAL_RECONCILIATION"],
            "automatic_recommendation": None,
            "decision": None,
            "decision_note": None,
        },
    }


def _packet(field: str = "methodology") -> dict:
    packet = {
        "phase": p0f6.P0F5_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "generated_at_utc": "2026-08-28T00:00:00+00:00",
        "academic_year": 2026,
        "mantenedora_id": "tenant-1",
        "source_p0f4_manifest_sha256": "p0f4",
        "summary": {
            "duplicate_identity_groups": 1,
            "p0f4_conflicts": 1,
            "conflicts_expanded": 1,
            "complete_conflict_coverage": True,
            "review_units": 1,
            "review_units_by_collection": {"learning_objects": 1},
            "review_units_by_type": {"PEDAGOGICAL_CONTENT_FIELD_DECISION": 1},
            "unresolved_review_conflicts": 0,
            "pending_human_decisions": 1,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {"automatic_recommendation": False, "automatic_resolution": False},
        "unresolved_conflicts": [],
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Ciências"},
            "source_id": "course-source",
            "target_id": "course-target",
            "p0f4_conflicts": 1,
            "review_units": 1,
            "conflicts": [{
                "conflict_id": "conflict-1",
                "collection": "learning_objects",
                "key_sha256": "key-1",
                "p0f3_classification": "PEDAGOGICAL_CONTENT_CONFLICT",
                "field_names": [field],
                "review_units": [_unit(field)],
                "expansion_error": None,
                "automatic_resolution": False,
            }],
            "automatic_resolution": False,
            "database_mutation": False,
        }],
    }
    packet["manifest_sha256"] = p0f6.canonical_sha256(packet)
    return packet


def _sealed(packet: dict) -> dict:
    sealed = {
        "phase": p0f6.SEALED_DECISION_PHASE,
        "manifest_version": 1,
        "status": "SEALED_COMPLETE_HUMAN_DECISIONS",
        "generated_at_utc": "2026-08-28T01:00:00+00:00",
        "source_p0f5_manifest_sha256": packet["manifest_sha256"],
        "source_review_unit_count": 1,
        "reviewer": {"name": "Responsável", "role": "Gestor", "identifier": None, "authorized_acknowledgement": True},
        "summary": {
            "decisions": 1,
            "decision_counts": {"MANUAL_RECONCILIATION": 1},
            "complete_decision_coverage": True,
            "pending_human_decisions": 0,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {
            "decision_values_are_human_supplied": True,
            "no_automatic_decision": True,
            "no_database_access": True,
            "no_database_mutation": True,
            "not_authorization_for_executor": True,
        },
        "decisions": [{
            "review_unit_id": "manual-1",
            "decision": "MANUAL_RECONCILIATION",
            "decision_note": "Combinar as informações pedagógicas sem perda de conteúdo.",
        }],
    }
    sealed["decision_manifest_sha256"] = p0f6.canonical_sha256(sealed)
    return sealed


def _p0f3() -> dict:
    empty = {"classifications": {}, "hard_conflicts": 0, "collision_items": 0}
    return {
        "phase": "P0F3-DUPLICATE-COURSE-SEMANTIC-COLLISION-READ-ONLY-2026",
        "status": "PASS",
        "summary": {"database_mutation": False},
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Ciências"},
            "source_id": "course-source",
            "target_id": "course-target",
            "reference_counts": {"learning_objects": {"course-source": 1, "course-target": 1}},
            "unsupported_reference_count": 0,
            "hard_conflicts": 1,
            "analyses": {
                "grades": dict(empty), "attendance": dict(empty),
                "learning_objects": {"classifications": {"PEDAGOGICAL_CONTENT_CONFLICT": 1}, "hard_conflicts": 1, "collision_items": 1},
                "teacher_assignments": dict(empty), "teacher_class_assignments": dict(empty),
                "class_schedules": {"same_day_slot_collisions": 0, "unresolved_slot_identities": 0, "hard_conflicts": 0, "collision_items": 0},
                "student_dependencies": dict(empty),
            },
        }],
    }


def _docs(field: str = "methodology") -> dict:
    source = {"id": "lo-source", "course_id": "course-source", "class_id": "class-1", "date": "2026-05-04", field: _unit(field)["source_value"]}
    target = {"id": "lo-target", "course_id": "course-target", "class_id": "class-1", "date": "2026-05-04", field: _unit(field)["target_value"]}
    return {"learning_objects": {"lo-source": source, "lo-target": target}}


def _artifacts(field: str = "methodology"):
    packet = _packet(field)
    sealed = _sealed(packet)
    preflight = p0f7.build_preflight(packet, sealed, _p0f3(), _docs(field))
    return packet, sealed, preflight


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_validates_exact_manual_chain_and_supported_field():
    packet, sealed, preflight = _artifacts()
    v = p0f71.validate_inputs(packet, sealed, preflight)
    assert v["manual_unit_count"] == 1
    assert v["field_counts"] == {"methodology": 1}
    assert v["manual_units"][0]["group_name"] == "Ciências"
    assert v["manual_units"][0]["previous_decision_note"]


def test_builds_private_human_station_and_javascript_parses(tmp_path: Path):
    packet, sealed, preflight = _artifacts()
    p, s, f = tmp_path / "p.json", tmp_path / "s.json", tmp_path / "f.json"
    out = tmp_path / "station.html"
    _write(p, packet); _write(s, sealed); _write(f, preflight)
    result = p0f71.build_station(p, s, f, out)
    html = out.read_text(encoding="utf-8")
    assert result["status"] == "PASS"
    assert result["database_access"] is False
    assert result["database_mutation"] is False
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert "Valor final conciliado" in html
    assert "Registro 1" in html and "Registro 2" in html
    assert "Justificativa registrada anteriormente" in html
    assert "Nada será preenchido automaticamente" in html
    assert "connect-src 'none'" in html
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match
    js = tmp_path / "station.js"
    js.write_text(match.group(1), encoding="utf-8")
    checked = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


def test_seals_human_structured_value_without_executor_authorization(tmp_path: Path):
    packet, sealed, preflight = _artifacts("content")
    validation = p0f71.validate_inputs(packet, sealed, preflight)
    unit = validation["manual_units"][0]
    raw = {
        "phase": p0f71.RAW_PHASE,
        "manifest_version": 1,
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "station_phase": p0f71.PHASE_ID,
        "reviewer": {"name": "Responsável", "role": "Gestor", "identifier": None, "authorized_acknowledgement": True},
        "reconciliations": [{
            "review_unit_id": unit["review_unit_id"],
            "collection": unit["collection"], "field_name": unit["field_name"],
            "source_document_id": unit["source_document_id"], "target_document_id": unit["target_document_id"],
            "source_value_sha256": unit["source_value_sha256"], "target_value_sha256": unit["target_value_sha256"],
            "previous_decision_note_sha256": unit["previous_decision_note_sha256"],
            "final_value": "Conteúdo final conciliado por decisão humana.",
        }],
    }
    p, s, f, r = tmp_path / "p.json", tmp_path / "s.json", tmp_path / "f.json", tmp_path / "r.json"
    out = tmp_path / "sealed.json"
    _write(p, packet); _write(s, sealed); _write(f, preflight); _write(r, raw)
    result = p0f71.seal_reconciliations(p, s, f, r, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "SEALED_COMPLETE_STRUCTURED_MANUAL_RECONCILIATIONS"
    assert result["structured_values"] == 1
    assert result["database_mutation"] is False
    assert result["executor_authorized"] is False
    assert payload["safety"]["final_values_are_human_supplied"] is True
    assert payload["safety"]["not_authorization_for_executor"] is True
    stored = payload.pop("structured_reconciliation_manifest_sha256")
    assert p0f71.canonical_sha256(payload) == stored
    assert oct(out.stat().st_mode & 0o777) == "0o600"


def test_rejects_blank_final_value():
    packet, sealed, preflight = _artifacts()
    validation = p0f71.validate_inputs(packet, sealed, preflight)
    unit = validation["manual_units"][0]
    raw = {
        "phase": p0f71.RAW_PHASE,
        "station_phase": p0f71.PHASE_ID,
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "reviewer": {"name": "R", "role": "G", "authorized_acknowledgement": True},
        "reconciliations": [{**{k: unit[k] for k in ("review_unit_id", "collection", "field_name", "source_document_id", "target_document_id", "source_value_sha256", "target_value_sha256", "previous_decision_note_sha256")}, "final_value": "   "}],
    }
    with pytest.raises(ValueError, match="FINAL_VALUE_REQUIRED"):
        p0f71.validate_raw(validation, raw)


def test_rejects_unsupported_manual_field():
    packet, sealed, preflight = _artifacts("resources")
    with pytest.raises(ValueError, match="UNSUPPORTED_MANUAL_FIELD"):
        p0f71.validate_inputs(packet, sealed, preflight)


def test_script_has_no_database_or_apply_surface():
    p0f71.assert_offline_read_only()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "AsyncIOMotorClient" not in source
    assert "MONGO_URL" not in source
    assert "--apply" not in source
    assert "motor.motor_asyncio" not in source
