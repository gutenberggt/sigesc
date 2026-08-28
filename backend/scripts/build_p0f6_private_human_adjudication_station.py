"""P0-F6 — estação privada OFFLINE de adjudicação humana para conflitos P0-F5.

Este utilitário NÃO acessa MongoDB e NÃO executa qualquer decisão. Ele possui dois
subcomandos estritamente locais:

* ``build``: valida o pacote privado P0-F5 e gera um HTML autocontido/offline,
  gravado com permissão 0600. O HTML permite que um responsável humano registre
  KEEP_SOURCE, KEEP_TARGET ou MANUAL_RECONCILIATION sem recomendação automática.
* ``seal``: valida o JSON de decisões exportado pelo HTML contra o pacote P0-F5,
  exige cobertura exata de todas as unidades e produz um manifesto de decisões
  selado por SHA-256, também 0600.

Nenhum dos modos altera dados do SIGESC. Um eventual executor de banco deve ser
uma fase distinta, com preflight, CI e autorização humana específica.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping

P0F5_PHASE = "P0F5-DUPLICATE-COURSE-HUMAN-REVIEW-PACKET-READ-ONLY-2026"
STATION_PHASE = "P0F6-PRIVATE-HUMAN-ADJUDICATION-STATION-OFFLINE-2026"
RAW_DECISION_PHASE = "P0F6-HUMAN-ADJUDICATION-RAW-DECISIONS-2026"
SEALED_DECISION_PHASE = "P0F6-HUMAN-ADJUDICATION-DECISIONS-SEALED-2026"
MANIFEST_VERSION = 1

ALLOWED_DECISIONS = (
    "KEEP_SOURCE",
    "KEEP_TARGET",
    "MANUAL_RECONCILIATION",
)


def canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def verify_embedded_sha(payload: Mapping[str, Any], field: str = "manifest_sha256") -> str:
    stored = str(payload.get(field) or "")
    if not stored:
        raise ValueError(f"MISSING_{field.upper()}")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = canonical_sha256(canonical)
    if stored != actual:
        raise ValueError(f"{field.upper()}_MISMATCH")
    return stored


def iter_review_units(packet: Mapping[str, Any]):
    for case in packet.get("cases") or []:
        for conflict in case.get("conflicts") or []:
            for unit in conflict.get("review_units") or []:
                yield case, conflict, unit


def validate_p0f5_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    if packet.get("phase") != P0F5_PHASE:
        raise ValueError("P0F5_PHASE_MISMATCH")
    if packet.get("status") != "PASS":
        raise ValueError("P0F5_STATUS_NOT_PASS")

    packet_sha = verify_embedded_sha(packet)
    summary = packet.get("summary") or {}
    if summary.get("complete_conflict_coverage") is not True:
        raise ValueError("P0F5_CONFLICT_COVERAGE_INCOMPLETE")
    if int(summary.get("unresolved_review_conflicts") or 0) != 0:
        raise ValueError("P0F5_HAS_UNRESOLVED_REVIEW_CONFLICTS")

    units: dict[str, dict[str, Any]] = {}
    group_counts: Counter[str] = Counter()
    collection_counts: Counter[str] = Counter()
    for case, conflict, unit in iter_review_units(packet):
        unit_id = str(unit.get("review_unit_id") or "")
        if not unit_id:
            raise ValueError("P0F5_REVIEW_UNIT_WITHOUT_ID")
        if unit_id in units:
            raise ValueError(f"P0F5_DUPLICATE_REVIEW_UNIT_ID:{unit_id}")
        contract = unit.get("decision_contract") or {}
        if contract.get("status") != "PENDING_HUMAN_DECISION":
            raise ValueError(f"P0F5_UNIT_NOT_PENDING:{unit_id}")
        allowed = set(contract.get("allowed_decisions") or [])
        if set(ALLOWED_DECISIONS) - allowed:
            raise ValueError(f"P0F5_DECISION_CONTRACT_INCOMPLETE:{unit_id}")
        if contract.get("automatic_recommendation") is not None:
            raise ValueError(f"P0F5_AUTOMATIC_RECOMMENDATION_PRESENT:{unit_id}")
        units[unit_id] = {
            "group_number": case.get("group_number"),
            "group_name": (case.get("identity") or {}).get("display_name"),
            "collection": conflict.get("collection"),
            "conflict_id": conflict.get("conflict_id"),
            "unit": unit,
        }
        group_counts[str(case.get("group_number"))] += 1
        collection_counts[str(conflict.get("collection"))] += 1

    expected = int(summary.get("review_units") or 0)
    pending = int(summary.get("pending_human_decisions") or 0)
    if expected <= 0 or len(units) != expected:
        raise ValueError(f"P0F5_REVIEW_UNIT_COUNT_MISMATCH:{len(units)}!={expected}")
    if pending != expected:
        raise ValueError("P0F5_PENDING_COUNT_MISMATCH")

    return {
        "packet_sha256": packet_sha,
        "review_units": units,
        "review_unit_count": expected,
        "group_counts": dict(sorted(group_counts.items())),
        "collection_counts": dict(sorted(collection_counts.items())),
    }


def _safe_json_for_script(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return (
        rendered.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_station_html(packet: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    packet_json = _safe_json_for_script(packet)
    metadata_json = _safe_json_for_script({
        "station_phase": STATION_PHASE,
        "raw_decision_phase": RAW_DECISION_PHASE,
        "source_p0f5_manifest_sha256": validation["packet_sha256"],
        "review_unit_count": validation["review_unit_count"],
        "allowed_decisions": list(ALLOWED_DECISIONS),
    })

    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'\">
<title>SIGESC P0-F6 — Adjudicação Humana Offline</title>
<style>
:root{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#161616;background:#f4f4f4}}
body{{margin:0}} header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:14px 20px;z-index:2}}
main{{max-width:1200px;margin:20px auto;padding:0 16px 80px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}}
.card{{background:#fff;border:1px solid #d8d8d8;border-radius:10px;padding:14px;margin:12px 0}} .muted{{color:#666}} .warn{{background:#fff4ce;border:1px solid #e4b000}}
label{{display:block;font-weight:600;margin:8px 0 4px}} input,select,textarea{{width:100%;box-sizing:border-box;padding:8px;border:1px solid #aaa;border-radius:6px;background:#fff}}
textarea{{min-height:88px}} button{{padding:9px 12px;border:1px solid #888;border-radius:6px;background:#fff;cursor:pointer}} button.primary{{background:#111;color:#fff;border-color:#111}}
button.selected{{outline:3px solid #111}} pre{{white-space:pre-wrap;word-break:break-word;background:#f7f7f7;border:1px solid #ddd;padding:10px;border-radius:6px;max-height:260px;overflow:auto}}
.unit{{border-left:5px solid #aaa}} .unit.decided{{border-left-color:#16803b}} .pill{{display:inline-block;padding:3px 7px;border-radius:999px;background:#eee;margin-right:5px;font-size:12px}}
.progress{{font-weight:700}} .actions{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}} .hidden{{display:none!important}}
@media print{{header,.no-print{{display:none}} main{{margin:0;max-width:none}}}}
</style>
</head>
<body>
<header>
  <div><strong>SIGESC P0-F6 — Estação privada de adjudicação humana</strong></div>
  <div class=\"muted\">OFFLINE · sem recomendações automáticas · nenhuma escrita no SIGESC</div>
  <div class=\"progress\" id=\"progress\">0 / 0 decisões</div>
</header>
<main>
<section class=\"card warn\">
<strong>Regra de governança:</strong> esta tela apenas registra decisões de um responsável autorizado. Ela não recomenda qual lado deve prevalecer e não altera o banco de dados.
</section>
<section class=\"card\">
<h2>Responsável pela adjudicação</h2>
<div class=\"grid\">
<div><label>Nome</label><input id=\"reviewerName\" autocomplete=\"off\"></div>
<div><label>Função/cargo</label><input id=\"reviewerRole\" autocomplete=\"off\"></div>
<div><label>Identificador institucional (opcional)</label><input id=\"reviewerId\" autocomplete=\"off\"></div>
</div>
<label>Declaração</label>
<input id=\"ack\" type=\"checkbox\" style=\"width:auto\"> Confirmo que sou responsável autorizado para revisar estes registros e que cada escolha abaixo é uma decisão humana.
</section>
<section class=\"card no-print\">
<div class=\"grid\">
<div><label>Grupo</label><select id=\"filterGroup\"><option value=\"\">Todos</option></select></div>
<div><label>Coleção</label><select id=\"filterCollection\"><option value=\"\">Todas</option></select></div>
<div><label>Situação</label><select id=\"filterStatus\"><option value=\"\">Todas</option><option value=\"pending\">Pendentes</option><option value=\"decided\">Decididas</option></select></div>
</div>
<div class=\"actions\"><button id=\"applyFilters\">Aplicar filtros</button><button id=\"exportBtn\" class=\"primary\">Exportar decisões JSON</button></div>
</section>
<div id=\"units\"></div>
</main>
<script>
'use strict';
const PACKET={packet_json};
const META={metadata_json};
const decisions=new Map();
const flattened=[];
for(const c of (PACKET.cases||[])){{
  for(const conflict of (c.conflicts||[])){{
    for(const unit of (conflict.review_units||[])){{
      flattened.push({{group_number:c.group_number,group_name:(c.identity||{{}}).display_name,collection:conflict.collection,conflict_id:conflict.conflict_id,unit}});
    }}
  }}
}}
if(flattened.length!==META.review_unit_count){{document.body.innerHTML='<main><h1>ERRO: contagem de unidades divergente</h1></main>';throw new Error('count mismatch')}}
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c]));
const pretty=v=>JSON.stringify(v,null,2);
const unitNode=(row)=>{{
  const u=row.unit; const id=u.review_unit_id;
  const el=document.createElement('section'); el.className='card unit'; el.dataset.id=id; el.dataset.group=String(row.group_number); el.dataset.collection=row.collection;
  el.innerHTML=`<div><span class=\"pill\">${{esc(row.group_name||row.group_number)}}</span><span class=\"pill\">${{esc(row.collection)}}</span><span class=\"pill\">${{esc(u.unit_type)}}</span></div>
  <h3>${{esc(u.field_name||u.unit_type)}}</h3>
  <div class=\"grid\"><div><strong>Contexto</strong><pre>${{esc(pretty(u.context||{{}}))}}</pre></div><div><strong>Origem/autoria SOURCE</strong><pre>${{esc(pretty(u.source_actor||{{}}))}}</pre></div><div><strong>Origem/autoria TARGET</strong><pre>${{esc(pretty(u.target_actor||{{}}))}}</pre></div></div>
  <div class=\"grid\"><div><strong>Valor SOURCE</strong><pre>${{esc(pretty(u.source_value))}}</pre></div><div><strong>Valor TARGET</strong><pre>${{esc(pretty(u.target_value))}}</pre></div></div>
  <div class=\"actions\"><button data-choice=\"KEEP_SOURCE\">Manter SOURCE</button><button data-choice=\"KEEP_TARGET\">Manter TARGET</button><button data-choice=\"MANUAL_RECONCILIATION\">Reconciliação manual</button><button data-choice=\"CLEAR\">Limpar</button></div>
  <label>Justificativa / observação da decisão</label><textarea data-note placeholder=\"Obrigatória para Reconciliação manual; recomendada nos demais casos.\"></textarea>
  <div class=\"muted\">review_unit_id: ${{esc(id)}}</div>`;
  const note=el.querySelector('[data-note]');
  el.querySelectorAll('button[data-choice]').forEach(btn=>btn.addEventListener('click',()=>{{
    const choice=btn.dataset.choice;
    if(choice==='CLEAR'){{decisions.delete(id);note.value='';el.classList.remove('decided');el.querySelectorAll('button[data-choice]').forEach(b=>b.classList.remove('selected'));updateProgress();return;}}
    decisions.set(id,{{decision:choice,decision_note:note.value}}); el.classList.add('decided'); el.querySelectorAll('button[data-choice]').forEach(b=>b.classList.toggle('selected',b.dataset.choice===choice)); updateProgress();
  }}));
  note.addEventListener('input',()=>{{if(decisions.has(id)){{const d=decisions.get(id);d.decision_note=note.value;decisions.set(id,d)}}}});
  return el;
}};
const container=document.getElementById('units'); flattened.forEach(r=>container.appendChild(unitNode(r)));
const groups=[...new Map(flattened.map(r=>[String(r.group_number),r.group_name||r.group_number])).entries()];
for(const [v,t] of groups){{const o=document.createElement('option');o.value=v;o.textContent=t;document.getElementById('filterGroup').appendChild(o)}}
for(const v of [...new Set(flattened.map(r=>r.collection))].sort()){{const o=document.createElement('option');o.value=v;o.textContent=v;document.getElementById('filterCollection').appendChild(o)}}
function updateProgress(){{document.getElementById('progress').textContent=`${{decisions.size}} / ${{flattened.length}} decisões`;}}
function applyFilters(){{const g=document.getElementById('filterGroup').value,c=document.getElementById('filterCollection').value,s=document.getElementById('filterStatus').value;document.querySelectorAll('.unit').forEach(el=>{{const decided=decisions.has(el.dataset.id);const ok=(!g||el.dataset.group===g)&&(!c||el.dataset.collection===c)&&(!s||(s==='decided'&&decided)||(s==='pending'&&!decided));el.classList.toggle('hidden',!ok)}})}}
document.getElementById('applyFilters').addEventListener('click',applyFilters);
document.getElementById('exportBtn').addEventListener('click',()=>{{
  const name=document.getElementById('reviewerName').value.trim(),role=document.getElementById('reviewerRole').value.trim(),identifier=document.getElementById('reviewerId').value.trim();
  if(!name||!role||!document.getElementById('ack').checked){{alert('Informe nome, função/cargo e confirme a declaração.');return;}}
  if(decisions.size!==flattened.length){{alert(`Ainda existem ${{flattened.length-decisions.size}} decisões pendentes.`);return;}}
  for(const [id,d] of decisions){{if(d.decision==='MANUAL_RECONCILIATION'&&!String(d.decision_note||'').trim()){{alert('Toda reconciliação manual exige justificativa. Unidade: '+id);return;}}}}
  const payload={{phase:META.raw_decision_phase,manifest_version:1,source_p0f5_manifest_sha256:META.source_p0f5_manifest_sha256,station_phase:META.station_phase,exported_at:new Date().toISOString(),reviewer:{{name,role,identifier:identifier||null,authorized_acknowledgement:true}},summary:{{review_units:flattened.length,decisions:decisions.size}},decisions:[...decisions.entries()].map(([review_unit_id,d])=>({{review_unit_id,decision:d.decision,decision_note:d.decision_note||null}})).sort((a,b)=>a.review_unit_id.localeCompare(b.review_unit_id))}};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='p0f6-human-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}});
updateProgress();
</script>
</body>
</html>"""


def build_station(packet_path: Path, output_path: Path) -> dict[str, Any]:
    packet = load_json(packet_path)
    validation = validate_p0f5_packet(packet)
    html_text = build_station_html(packet, validation)
    private_write_text(output_path, html_text)
    return {
        "phase": STATION_PHASE,
        "status": "PASS",
        "source_p0f5_manifest_sha256": validation["packet_sha256"],
        "review_units": validation["review_unit_count"],
        "output_file_mode": oct(output_path.stat().st_mode & 0o777)[2:].zfill(4),
        "network_dependencies": 0,
        "automatic_recommendation": False,
        "database_mutation": False,
    }


def validate_raw_decisions(
    packet: Mapping[str, Any],
    validation: Mapping[str, Any],
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    if raw.get("phase") != RAW_DECISION_PHASE:
        raise ValueError("RAW_DECISION_PHASE_MISMATCH")
    if raw.get("source_p0f5_manifest_sha256") != validation["packet_sha256"]:
        raise ValueError("RAW_DECISION_SOURCE_PACKET_SHA_MISMATCH")
    reviewer = raw.get("reviewer") or {}
    if not str(reviewer.get("name") or "").strip():
        raise ValueError("REVIEWER_NAME_REQUIRED")
    if not str(reviewer.get("role") or "").strip():
        raise ValueError("REVIEWER_ROLE_REQUIRED")
    if reviewer.get("authorized_acknowledgement") is not True:
        raise ValueError("REVIEWER_AUTHORIZATION_ACK_REQUIRED")

    expected_units = validation["review_units"]
    seen: dict[str, dict[str, Any]] = {}
    for row in raw.get("decisions") or []:
        if not isinstance(row, Mapping):
            raise ValueError("DECISION_ROW_MUST_BE_OBJECT")
        unit_id = str(row.get("review_unit_id") or "")
        if not unit_id:
            raise ValueError("DECISION_WITHOUT_REVIEW_UNIT_ID")
        if unit_id in seen:
            raise ValueError(f"DUPLICATE_DECISION:{unit_id}")
        if unit_id not in expected_units:
            raise ValueError(f"UNKNOWN_REVIEW_UNIT_ID:{unit_id}")
        decision = str(row.get("decision") or "")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"INVALID_DECISION:{unit_id}:{decision}")
        note = row.get("decision_note")
        if decision == "MANUAL_RECONCILIATION" and not str(note or "").strip():
            raise ValueError(f"MANUAL_RECONCILIATION_NOTE_REQUIRED:{unit_id}")
        seen[unit_id] = {
            "review_unit_id": unit_id,
            "decision": decision,
            "decision_note": note,
        }

    missing = sorted(set(expected_units) - set(seen))
    if missing:
        raise ValueError(f"MISSING_DECISIONS:{len(missing)}")
    if len(seen) != validation["review_unit_count"]:
        raise ValueError("DECISION_COUNT_MISMATCH")

    return {
        "reviewer": {
            "name": str(reviewer.get("name")).strip(),
            "role": str(reviewer.get("role")).strip(),
            "identifier": reviewer.get("identifier"),
            "authorized_acknowledgement": True,
        },
        "decisions": [seen[k] for k in sorted(seen)],
    }


def seal_decisions(packet_path: Path, decisions_path: Path, output_path: Path) -> dict[str, Any]:
    packet = load_json(packet_path)
    validation = validate_p0f5_packet(packet)
    raw = load_json(decisions_path)
    validated = validate_raw_decisions(packet, validation, raw)
    counts = Counter(row["decision"] for row in validated["decisions"])

    sealed: dict[str, Any] = {
        "phase": SEALED_DECISION_PHASE,
        "manifest_version": MANIFEST_VERSION,
        "status": "SEALED_COMPLETE_HUMAN_DECISIONS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_p0f5_manifest_sha256": validation["packet_sha256"],
        "source_review_unit_count": validation["review_unit_count"],
        "reviewer": validated["reviewer"],
        "summary": {
            "decisions": len(validated["decisions"]),
            "decision_counts": dict(sorted(counts.items())),
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
        "decisions": validated["decisions"],
    }
    sealed["decision_manifest_sha256"] = canonical_sha256(sealed)
    private_write_json(output_path, sealed)
    return {
        "phase": SEALED_DECISION_PHASE,
        "status": sealed["status"],
        "source_p0f5_manifest_sha256": validation["packet_sha256"],
        "decisions": len(validated["decisions"]),
        "decision_counts": dict(sorted(counts.items())),
        "complete_decision_coverage": True,
        "decision_manifest_sha256": sealed["decision_manifest_sha256"],
        "output_file_mode": oct(output_path.stat().st_mode & 0o777)[2:].zfill(4),
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F6 offline human adjudication station")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Gerar HTML privado/offline a partir do P0-F5")
    build.add_argument("--packet", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)

    seal = sub.add_parser("seal", help="Validar decisões humanas e gerar manifesto selado")
    seal.add_argument("--packet", required=True, type=Path)
    seal.add_argument("--decisions", required=True, type=Path)
    seal.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build":
        result = build_station(args.packet, args.output)
    else:
        result = seal_decisions(args.packet, args.decisions, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
