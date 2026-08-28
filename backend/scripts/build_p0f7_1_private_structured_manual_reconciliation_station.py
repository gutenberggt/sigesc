"""P0-F7.1 — estação privada OFFLINE para estruturar 8 reconciliações manuais.

Parte de P0-F5 + P0-F6 selado + P0-F7. Não acessa MongoDB, não recomenda
valores e não executa qualquer alteração. Nesta versão, aceita somente campos
textuais learning_objects.content e learning_objects.methodology.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
P0F6_PATH = SCRIPT_DIR / "build_p0f6_private_human_adjudication_station.py"
P0F7_PATH = SCRIPT_DIR / "audit_p0f7_sealed_decisions_execution_preflight.py"

PHASE_ID = "P0F7.1-STRUCTURED-MANUAL-RECONCILIATION-OFFLINE-2026"
RAW_PHASE = "P0F7.1-RAW-STRUCTURED-MANUAL-RECONCILIATIONS-2026"
SEALED_PHASE = "P0F7.1-SEALED-STRUCTURED-MANUAL-RECONCILIATIONS-2026"
MANIFEST_VERSION = 1
SUPPORTED_COLLECTION = "learning_objects"
SUPPORTED_FIELDS = {"content", "methodology"}

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def assert_offline_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"OFFLINE_READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"IMPORT_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def value_sha256(value: Any) -> str:
    return canonical_sha256({"value": value})


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def private_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    private_write_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    )


def verify_embedded_sha(payload: Mapping[str, Any], field: str, label: str) -> str:
    stored = str(payload.get(field) or "")
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    if canonical_sha256(canonical) != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def _packet_units(packet: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for case in packet.get("cases") or []:
        for conflict in case.get("conflicts") or []:
            for unit in conflict.get("review_units") or []:
                unit_id = str(unit.get("review_unit_id") or "")
                if not unit_id or unit_id in result:
                    raise ValueError("P0F5_REVIEW_UNIT_ID_INVALID")
                result[unit_id] = {
                    "group_number": case.get("group_number"),
                    "group_name": (case.get("identity") or {}).get("display_name"),
                    "collection": conflict.get("collection"),
                    "unit": unit,
                }
    return result


def validate_inputs(
    packet: Mapping[str, Any], sealed: Mapping[str, Any], preflight: Mapping[str, Any]
) -> dict[str, Any]:
    p0f7 = _load_module(P0F7_PATH, "p0f7_contract_for_p0f7_1")
    chain = p0f7.validate_chain(packet, sealed)
    preflight_sha = verify_embedded_sha(preflight, "manifest_sha256", "P0F7")

    if preflight.get("phase") != p0f7.PHASE_ID:
        raise ValueError("P0F7_PHASE_MISMATCH")
    if preflight.get("mode") != "READ_ONLY_SEALED_DECISIONS_EXECUTION_PREFLIGHT":
        raise ValueError("P0F7_MODE_MISMATCH")
    if preflight.get("status") != "PASS":
        raise ValueError("P0F7_STATUS_NOT_PASS")
    if preflight.get("source_p0f5_manifest_sha256") != chain["packet_sha256"]:
        raise ValueError("P0F7_SOURCE_P0F5_SHA_MISMATCH")
    if preflight.get("source_p0f6_decision_manifest_sha256") != chain["sealed_manifest_sha256"]:
        raise ValueError("P0F7_SOURCE_P0F6_SHA_MISMATCH")

    summary = preflight.get("summary") or {}
    safety = preflight.get("safety") or {}
    if int(summary.get("snapshot_drift_units") or 0) != 0:
        raise ValueError("P0F7_SNAPSHOT_DRIFT_PRESENT")
    if int(summary.get("missing_review_documents") or 0) != 0:
        raise ValueError("P0F7_MISSING_REVIEW_DOCUMENTS")
    if summary.get("p0f7_1_structured_manual_reconciliation_required") is not True:
        raise ValueError("P0F7_1_NOT_REQUIRED")
    if summary.get("database_mutation") is not False:
        raise ValueError("P0F7_DATABASE_MUTATION_INVALID")
    if safety.get("read_only") is not True or safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_SAFETY_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_EXECUTOR_AUTHORIZATION_INVALID")

    packet_units = _packet_units(packet)
    manual_ids = sorted(
        unit_id for unit_id, row in chain["decisions"].items()
        if row.get("decision") == "MANUAL_RECONCILIATION"
    )
    expected_count = int(summary.get("manual_reconciliation_units") or 0)
    if not manual_ids or len(manual_ids) != expected_count:
        raise ValueError("MANUAL_RECONCILIATION_COUNT_MISMATCH")

    blocker_ids = sorted(
        str(row.get("review_unit_id") or "")
        for row in preflight.get("blockers") or []
        if row.get("reason") == "MANUAL_RECONCILIATION_REQUIRES_STRUCTURED_VALUE"
    )
    if blocker_ids != manual_ids:
        raise ValueError("P0F7_MANUAL_BLOCKER_SET_MISMATCH")

    manual_units: list[dict[str, Any]] = []
    field_counts: Counter[str] = Counter()
    for unit_id in manual_ids:
        entry = packet_units.get(unit_id)
        if not entry:
            raise ValueError(f"MANUAL_UNIT_NOT_FOUND:{unit_id}")
        unit = entry["unit"]
        collection = str(entry.get("collection") or "")
        field = str(unit.get("field_name") or "")
        if collection != SUPPORTED_COLLECTION:
            raise ValueError(f"UNSUPPORTED_MANUAL_COLLECTION:{unit_id}:{collection}")
        if field not in SUPPORTED_FIELDS:
            raise ValueError(f"UNSUPPORTED_MANUAL_FIELD:{unit_id}:{field}")
        source_value, target_value = unit.get("source_value"), unit.get("target_value")
        if not isinstance(source_value, str) or not isinstance(target_value, str):
            raise ValueError(f"MANUAL_VALUES_MUST_BE_TEXT:{unit_id}")
        note = str(chain["decisions"][unit_id].get("decision_note") or "")
        if not note.strip():
            raise ValueError(f"MANUAL_NOTE_REQUIRED:{unit_id}")
        source_ids = [str(v) for v in unit.get("source_document_ids") or [] if v]
        target_ids = [str(v) for v in unit.get("target_document_ids") or [] if v]
        if len(source_ids) != 1 or len(target_ids) != 1:
            raise ValueError(f"MANUAL_DOCUMENT_MULTIPLICITY:{unit_id}")
        manual_units.append({
            "review_unit_id": unit_id,
            "group_number": entry.get("group_number"),
            "group_name": entry.get("group_name"),
            "collection": collection,
            "field_name": field,
            "context": unit.get("context") or {},
            "source_actor": unit.get("source_actor") or {},
            "target_actor": unit.get("target_actor") or {},
            "source_document_id": source_ids[0],
            "target_document_id": target_ids[0],
            "source_value": source_value,
            "target_value": target_value,
            "source_value_sha256": value_sha256(source_value),
            "target_value_sha256": value_sha256(target_value),
            "previous_decision_note": note,
            "previous_decision_note_sha256": value_sha256(note),
        })
        field_counts[field] += 1

    return {
        "p0f5_manifest_sha256": chain["packet_sha256"],
        "p0f6_decision_manifest_sha256": chain["sealed_manifest_sha256"],
        "p0f7_manifest_sha256": preflight_sha,
        "manual_units": manual_units,
        "manual_unit_count": len(manual_units),
        "field_counts": dict(sorted(field_counts.items())),
    }


def _safe_json_for_script(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )


def build_station_html(validation: Mapping[str, Any]) -> str:
    units_json = _safe_json_for_script(validation["manual_units"])
    meta_json = _safe_json_for_script({
        "phase": PHASE_ID,
        "raw_phase": RAW_PHASE,
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "manual_unit_count": validation["manual_unit_count"],
    })
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'">
<title>SIGESC P0-F7.1 — Conciliação manual estruturada</title>
<style>:root{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#171717;background:#f4f4f4}}body{{margin:0}}header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:14px 20px;z-index:2}}main{{max-width:1200px;margin:20px auto;padding:0 16px 80px}}.card{{background:#fff;border:1px solid #d8d8d8;border-radius:10px;padding:16px;margin:14px 0}}.warn{{background:#fff4ce;border-color:#e4b000}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}}.muted{{color:#666}}.pill{{display:inline-block;padding:3px 8px;border-radius:999px;background:#eee;margin-right:5px;font-size:12px}}pre{{white-space:pre-wrap;word-break:break-word;background:#f7f7f7;border:1px solid #ddd;padding:12px;border-radius:6px;max-height:320px;overflow:auto}}label{{display:block;font-weight:650;margin:8px 0 5px}}input,textarea{{width:100%;box-sizing:border-box;padding:9px;border:1px solid #999;border-radius:6px;background:#fff}}textarea.final{{min-height:150px}}button{{padding:10px 14px;border:1px solid #777;border-radius:6px;background:#fff;cursor:pointer}}button.primary{{background:#111;color:#fff;border-color:#111}}.done{{border-left:5px solid #16803b}}.pending{{border-left:5px solid #c17d00}}.progress{{font-weight:750}}details{{margin-top:10px}}</style></head>
<body><header><strong>SIGESC P0-F7.1 — Conciliação manual estruturada</strong><div class="muted">OFFLINE · nenhuma escrita no SIGESC</div><div class="progress" id="progress">0 / 0 conciliações estruturadas</div></header><main>
<section class="card warn"><strong>Regra de governança:</strong> nada é combinado ou recomendado automaticamente. Escreva o valor final que deverá prevalecer. Registro 1 e Registro 2 são rótulos neutros. A exportação ainda não autoriza execução no banco.</section>
<section class="card"><h2>Responsável pela conciliação</h2><div class="grid"><div><label>Nome</label><input id="reviewerName" autocomplete="off"></div><div><label>Função/cargo</label><input id="reviewerRole" autocomplete="off"></div><div><label>Identificador institucional (opcional)</label><input id="reviewerId" autocomplete="off"></div></div><label><input id="ack" type="checkbox" style="width:auto"> Confirmo que os valores finais abaixo foram definidos por decisão humana consciente e autorizada.</label></section>
<div id="units"></div><section class="card"><button class="primary" id="exportBtn">Exportar conciliações estruturadas JSON</button></section></main>
<script>'use strict';
const UNITS={units_json};const META={meta_json};const values=new Map();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const FIELD_LABELS={{content:'Conteúdo da aula',methodology:'Metodologia'}};
const formatDate=v=>{{const s=String(v||'');const m=s.match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/);return m?`${{m[3]}}/${{m[2]}}/${{m[1]}}`:s;}};
const humanContext=c=>{{c=c||{{}};const r=[];if(c.school_name)r.push('Escola: '+c.school_name);if(c.class_name)r.push('Turma: '+c.class_name);if(c.academic_year)r.push('Ano letivo: '+c.academic_year);if(c.date)r.push('Data: '+formatDate(c.date));if(c.period)r.push('Período: '+c.period);if(c.aula_numero!==null&&c.aula_numero!==undefined&&c.aula_numero!=='')r.push('Aula: '+c.aula_numero);return r.length?r.join('\\n'):'Contexto não informado';}};
const actorText=a=>{{a=a||{{}};const c=a.recorded_by||a.created_by||a.updated_by||a;if(c&&typeof c==='object'&&c.name)return c.name;if(a.name)return a.name;return 'Autoria não identificada';}};
function updateProgress(){{let n=0;for(const u of UNITS)if(String(values.get(u.review_unit_id)||'').trim())n++;document.getElementById('progress').textContent=`${{n}} / ${{UNITS.length}} conciliações estruturadas`;}}
function unitNode(u,i){{const el=document.createElement('section');el.className='card pending';el.innerHTML=`<div><span class="pill">${{esc(u.group_name)}}</span><span class="pill">Conteúdo pedagógico</span><span class="pill">${{esc(FIELD_LABELS[u.field_name]||u.field_name)}}</span></div><h3>Conciliação ${{i+1}} de ${{UNITS.length}}</h3><div class="grid"><div><strong>Contexto</strong><pre>${{esc(humanContext(u.context))}}</pre></div><div><strong>Quem registrou — Registro 1</strong><pre>${{esc(actorText(u.source_actor))}}</pre></div><div><strong>Quem registrou — Registro 2</strong><pre>${{esc(actorText(u.target_actor))}}</pre></div></div><div class="grid"><div><strong>Registro 1</strong><pre>${{esc(u.source_value)}}</pre></div><div><strong>Registro 2</strong><pre>${{esc(u.target_value)}}</pre></div></div><div><strong>Justificativa registrada anteriormente</strong><pre>${{esc(u.previous_decision_note)}}</pre></div><label>Valor final conciliado</label><textarea class="final" data-final placeholder="Escreva o texto final que deverá prevalecer. Nada será preenchido automaticamente."></textarea><details class="muted"><summary>Detalhes técnicos</summary><div>Identificador: ${{esc(u.review_unit_id)}}</div><div>Documento 1: ${{esc(u.source_document_id)}}</div><div>Documento 2: ${{esc(u.target_document_id)}}</div></details>`;const ta=el.querySelector('[data-final]');ta.addEventListener('input',()=>{{values.set(u.review_unit_id,ta.value);const ok=ta.value.trim().length>0;el.classList.toggle('done',ok);el.classList.toggle('pending',!ok);updateProgress();}});return el;}}
const container=document.getElementById('units');UNITS.forEach((u,i)=>container.appendChild(unitNode(u,i)));updateProgress();
document.getElementById('exportBtn').addEventListener('click',()=>{{const name=document.getElementById('reviewerName').value.trim(),role=document.getElementById('reviewerRole').value.trim(),identifier=document.getElementById('reviewerId').value.trim();if(!name||!role||!document.getElementById('ack').checked){{alert('Informe nome, função/cargo e confirme a declaração.');return;}}const missing=UNITS.filter(u=>!String(values.get(u.review_unit_id)||'').trim());if(missing.length){{alert(`Ainda existem ${{missing.length}} conciliações sem valor final.`);return;}}const rows=UNITS.map(u=>({{review_unit_id:u.review_unit_id,collection:u.collection,field_name:u.field_name,source_document_id:u.source_document_id,target_document_id:u.target_document_id,final_value:String(values.get(u.review_unit_id)),source_value_sha256:u.source_value_sha256,target_value_sha256:u.target_value_sha256,previous_decision_note_sha256:u.previous_decision_note_sha256}})).sort((a,b)=>a.review_unit_id.localeCompare(b.review_unit_id));const payload={{phase:META.raw_phase,manifest_version:1,source_p0f5_manifest_sha256:META.source_p0f5_manifest_sha256,source_p0f6_decision_manifest_sha256:META.source_p0f6_decision_manifest_sha256,source_p0f7_manifest_sha256:META.source_p0f7_manifest_sha256,station_phase:META.phase,exported_at:new Date().toISOString(),reviewer:{{name,role,identifier:identifier||null,authorized_acknowledgement:true}},summary:{{manual_units:UNITS.length,structured_values:rows.length}},reconciliations:rows}};const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='p0f7-1-manual-reconciliations.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}});
</script></body></html>'''


def build_station(packet_path: Path, sealed_path: Path, preflight_path: Path, output_path: Path) -> dict[str, Any]:
    assert_offline_read_only()
    validation = validate_inputs(load_json(packet_path), load_json(sealed_path), load_json(preflight_path))
    private_write_text(output_path, build_station_html(validation))
    return {
        "phase": PHASE_ID, "status": "PASS",
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "manual_units": validation["manual_unit_count"],
        "field_counts": validation["field_counts"],
        "output_file_mode": oct(output_path.stat().st_mode & 0o777)[2:].zfill(4),
        "network_dependencies": 0, "automatic_recommendation": False,
        "database_access": False, "database_mutation": False, "executor_authorized": False,
    }


def validate_raw(validation: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("phase") != RAW_PHASE or raw.get("station_phase") != PHASE_ID:
        raise ValueError("RAW_PHASE_MISMATCH")
    for key in ("source_p0f5_manifest_sha256", "source_p0f6_decision_manifest_sha256", "source_p0f7_manifest_sha256"):
        expected_key = key.replace("source_", "").replace("_sha256", "_sha256")
        expected = {
            "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
            "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
            "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        }[key]
        if raw.get(key) != expected:
            raise ValueError(f"RAW_CHAIN_MISMATCH:{key}")
    reviewer = raw.get("reviewer") or {}
    name, role = str(reviewer.get("name") or "").strip(), str(reviewer.get("role") or "").strip()
    if not name or not role or reviewer.get("authorized_acknowledgement") is not True:
        raise ValueError("REVIEWER_CONTRACT_INVALID")
    expected = {u["review_unit_id"]: u for u in validation["manual_units"]}
    seen: dict[str, dict[str, Any]] = {}
    for row in raw.get("reconciliations") or []:
        if not isinstance(row, Mapping):
            raise ValueError("RECONCILIATION_ROW_INVALID")
        unit_id = str(row.get("review_unit_id") or "")
        if unit_id in seen or unit_id not in expected:
            raise ValueError(f"RECONCILIATION_UNIT_INVALID:{unit_id}")
        unit = expected[unit_id]
        for key in ("collection", "field_name", "source_document_id", "target_document_id", "source_value_sha256", "target_value_sha256", "previous_decision_note_sha256"):
            if row.get(key) != unit.get(key):
                raise ValueError(f"RECONCILIATION_CONTRACT_MISMATCH:{unit_id}:{key}")
        final_value = row.get("final_value")
        if not isinstance(final_value, str) or not final_value.strip():
            raise ValueError(f"FINAL_VALUE_REQUIRED:{unit_id}")
        seen[unit_id] = {
            **{key: unit[key] for key in ("review_unit_id", "collection", "field_name", "source_document_id", "target_document_id", "source_value_sha256", "target_value_sha256", "previous_decision_note_sha256")},
            "final_value": final_value,
            "final_value_sha256": value_sha256(final_value),
        }
    if set(seen) != set(expected):
        raise ValueError(f"STRUCTURED_COVERAGE_MISMATCH:{len(seen)}!={len(expected)}")
    return {"reviewer": {"name": name, "role": role, "identifier": reviewer.get("identifier"), "authorized_acknowledgement": True}, "reconciliations": [seen[k] for k in sorted(seen)]}


def seal_reconciliations(packet_path: Path, sealed_path: Path, preflight_path: Path, reconciliations_path: Path, output_path: Path) -> dict[str, Any]:
    assert_offline_read_only()
    validation = validate_inputs(load_json(packet_path), load_json(sealed_path), load_json(preflight_path))
    validated = validate_raw(validation, load_json(reconciliations_path))
    counts = Counter(row["field_name"] for row in validated["reconciliations"])
    output: dict[str, Any] = {
        "phase": SEALED_PHASE, "manifest_version": MANIFEST_VERSION,
        "status": "SEALED_COMPLETE_STRUCTURED_MANUAL_RECONCILIATIONS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "reviewer": validated["reviewer"],
        "summary": {"manual_units": validation["manual_unit_count"], "structured_values": len(validated["reconciliations"]), "field_counts": dict(sorted(counts.items())), "complete_structured_coverage": True, "pending_structured_values": 0, "automatic_recommendation": False, "automatic_resolution": False, "database_access": False, "database_mutation": False},
        "safety": {"final_values_are_human_supplied": True, "no_automatic_combination": True, "no_database_access": True, "no_database_mutation": True, "not_authorization_for_executor": True},
        "reconciliations": validated["reconciliations"],
    }
    output["structured_reconciliation_manifest_sha256"] = canonical_sha256(output)
    private_write_json(output_path, output)
    return {"phase": SEALED_PHASE, "status": output["status"], "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"], "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"], "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"], "structured_values": len(validated["reconciliations"]), "field_counts": dict(sorted(counts.items())), "complete_structured_coverage": True, "structured_reconciliation_manifest_sha256": output["structured_reconciliation_manifest_sha256"], "output_file_mode": oct(output_path.stat().st_mode & 0o777)[2:].zfill(4), "database_access": False, "database_mutation": False, "executor_authorized": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.1 private/offline structured manual reconciliation")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--packet", required=True, type=Path); build.add_argument("--sealed", required=True, type=Path); build.add_argument("--preflight", required=True, type=Path); build.add_argument("--output", required=True, type=Path)
    seal = sub.add_parser("seal")
    seal.add_argument("--packet", required=True, type=Path); seal.add_argument("--sealed", required=True, type=Path); seal.add_argument("--preflight", required=True, type=Path); seal.add_argument("--reconciliations", required=True, type=Path); seal.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build":
        result = build_station(args.packet, args.sealed, args.preflight, args.output)
    else:
        result = seal_reconciliations(args.packet, args.sealed, args.preflight, args.reconciliations, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
