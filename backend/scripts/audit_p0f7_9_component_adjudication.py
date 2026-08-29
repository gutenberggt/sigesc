"""P0-F7.9 — adjudicação humana offline de componente curricular.

Consome exclusivamente os relatórios privados P0-F7.5 e P0-F7.8.2 já coletados.
Não possui cliente MongoDB, SSH, Docker, HTTP ou superfície de escrita em produção.
A divergência de carga semanal (2h x 3h) é deliberadamente fora do escopo.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping

PHASE_ID = "P0F7.9-HUMAN-COMPONENT-ADJUDICATION-2026"
P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
P0F782_PHASE = "P0F7.8.2-OFFLINE-SNAPSHOT-REEVALUATION-2026"
MANIFEST_VERSION = 1
EXPECTED_CASES = 3

CASE1_POLICY = "STRONG_CURRICULAR_PREFERENCE_SOURCE"
CASE2_POLICY = "BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION"
CASE3_POLICY = "BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION"

DECISION_SELECT_ALTERNATIVE = "SELECT_ALTERNATIVE_CANDIDATE"
DECISION_SELECT_SOURCE = "SELECT_SOURCE"
DECISION_SELECT_TARGET = "SELECT_TARGET"
DECISION_DEFER = "DEFER_FOR_CURRICULAR_SCOPE_REVIEW"

FORBIDDEN_RUNTIME_TOKENS = (
    "motor.", "pymongo", "AsyncIOMotorClient", "MongoClient(",
    "subprocess.", "docker exec", "ssh ", "scp ", "requests.", "httpx.",
)
MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _verify_embedded_sha(payload: Mapping[str, Any], field: str, label: str) -> str:
    stored = _norm(payload.get(field))
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def _private_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _private_write(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")


def assert_offline_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = [token for token in FORBIDDEN_RUNTIME_TOKENS if token in source]
    mutators = [token for token in MUTATOR_TOKENS if token in source]
    if forbidden:
        raise RuntimeError(f"OFFLINE_BOUNDARY_FAILED:{forbidden}")
    if mutators:
        raise RuntimeError(f"READ_ONLY_BOUNDARY_FAILED:{mutators}")
    if "--apply" in source or "--rollback" in source:
        raise RuntimeError("EXECUTOR_SURFACE_FORBIDDEN")


def validate_inputs(
    p0f75: Mapping[str, Any], p0f782: Mapping[str, Any]
) -> dict[str, Any]:
    assert_offline_only()
    sha75 = _verify_embedded_sha(p0f75, "manifest_sha256", "P0F7_5")
    sha782 = _verify_embedded_sha(p0f782, "manifest_sha256", "P0F7_8_2")

    if p0f75.get("phase") != P0F75_PHASE or p0f75.get("status") != "PASS":
        raise ValueError("P0F7_5_INVALID")
    if p0f782.get("phase") != P0F782_PHASE or p0f782.get("status") != "PASS":
        raise ValueError("P0F7_8_2_INVALID")
    if _norm(p0f782.get("source_p0f7_5_manifest_sha256")) != sha75:
        raise ValueError("P0F7_8_2_CHAIN_MISMATCH")

    summary = p0f782.get("summary") or {}
    if summary.get("documented_cases") != EXPECTED_CASES:
        raise ValueError("P0F7_8_2_CASE_COUNT_INVALID")
    if summary.get("snapshot_drift_cases") != 0:
        raise ValueError("P0F7_8_2_SNAPSHOT_DRIFT_PRESENT")
    if summary.get("automatic_course_mutations") != 0:
        raise ValueError("P0F7_8_2_AUTOMATIC_COURSE_MUTATION_PRESENT")
    if summary.get("automatic_workload_decisions") != 0:
        raise ValueError("P0F7_8_2_AUTOMATIC_WORKLOAD_DECISION_PRESENT")
    if summary.get("database_mutation") is not False:
        raise ValueError("P0F7_8_2_DATABASE_MUTATION_INVALID")
    if p0f782.get("database_mutation") is not False:
        raise ValueError("P0F7_8_2_TOP_LEVEL_MUTATION_INVALID")
    if p0f782.get("executor_authorized") is not False:
        raise ValueError("P0F7_8_2_EXECUTOR_FLAG_INVALID")

    cases782 = {int(row.get("case_number") or 0): row for row in (p0f782.get("cases") or [])}
    cases75 = {int(row.get("case_number") or 0): row for row in (p0f75.get("cases") or [])}
    if sorted(cases782) != [1, 2, 3] or sorted(cases75) != [1, 2, 3]:
        raise ValueError("CASE_SET_INVALID")

    expected_policies = {1: CASE1_POLICY, 2: CASE2_POLICY, 3: CASE3_POLICY}
    for number, expected in expected_policies.items():
        row = cases782[number]
        if row.get("snapshot_drift") is not False:
            raise ValueError(f"CASE_{number}_DRIFT_INVALID")
        policy = (row.get("pair_policy") or {}).get("state")
        if policy != expected:
            raise ValueError(f"CASE_{number}_POLICY_MISMATCH:{policy}")
        if row.get("automatic_course_mutation") is not False:
            raise ValueError(f"CASE_{number}_AUTOMATIC_MUTATION_INVALID")
        if row.get("automatic_workload_decision") is not False:
            raise ValueError(f"CASE_{number}_WORKLOAD_DECISION_INVALID")
        if row.get("executor_authorized") is not False:
            raise ValueError(f"CASE_{number}_EXECUTOR_FLAG_INVALID")

    case1 = cases782[1]
    if (case1.get("pair_policy") or {}).get("curricular_preference") != "source":
        raise ValueError("CASE_1_SOURCE_PREFERENCE_NOT_CONFIRMED")
    if (case1.get("pair_policy") or {}).get("component_adjudication_required") is not False:
        raise ValueError("CASE_1_UNEXPECTED_ADJUDICATION_REQUIREMENT")

    for number in (2, 3):
        if (cases782[number].get("pair_policy") or {}).get("component_adjudication_required") is not True:
            raise ValueError(f"CASE_{number}_ADJUDICATION_REQUIREMENT_MISSING")

    return {
        "p0f7_5_sha": sha75,
        "p0f7_8_2_sha": sha782,
        "cases75": cases75,
        "cases782": cases782,
    }


def _course_id(case: Mapping[str, Any], side: str) -> str:
    return _norm((case.get(side) or {}).get("course_id"))


def decision_contract(validated: Mapping[str, Any]) -> dict[str, Any]:
    cases = validated["cases782"]
    case2_candidates = [
        _norm(row.get("course_id"))
        for row in (cases[2].get("alternative_exact_level_candidates") or [])
        if _norm(row.get("course_id"))
    ]
    if not case2_candidates:
        raise ValueError("CASE_2_ALTERNATIVE_CANDIDATE_MISSING")

    return {
        "case_1": {
            "locked_outcome": "TECHNICAL_SOURCE_PREFERENCE",
            "selected_course_id": _course_id(cases[1], "source"),
            "human_decision_required": False,
        },
        "case_2": {
            "allowed_decisions": [DECISION_SELECT_ALTERNATIVE, DECISION_DEFER],
            "allowed_course_ids": case2_candidates,
            "human_decision_required": True,
        },
        "case_3": {
            "allowed_decisions": [DECISION_SELECT_SOURCE, DECISION_SELECT_TARGET, DECISION_DEFER],
            "source_course_id": _course_id(cases[3], "source"),
            "target_course_id": _course_id(cases[3], "target"),
            "human_decision_required": True,
        },
        "workload_decision_allowed": False,
        "executor_authorized": False,
    }


def _classification_label(value: Any) -> str:
    labels = {
        "LEVEL_MISMATCH": "Nível de ensino incompatível",
        "LEVEL_MATCH_NO_SERIES_SCOPE": "Nível compatível, mas sem escopo explícito de séries",
        "EXPLICIT_SERIES_FULL_MATCH": "Cobertura explícita completa das séries",
        "PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW": "Cobertura explícita parcial — requer revisão",
        "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW": "Conflito de escopo de séries — requer revisão",
    }
    raw = _norm(value)
    return labels.get(raw, raw or "Não informado")


def _identity_label(case75: Mapping[str, Any]) -> str:
    identity = case75.get("identity_evidence_from_p0f7_3") or {}
    raw = _norm(identity.get("classification"))
    if raw == "IDENTITY_EVIDENCE_LEANS_TARGET":
        return "A evidência histórica de identidade tende ao Registro 2; isso é evidência, não decisão automática."
    return raw or "Sem classificação adicional de identidade."


def _build_view_model(validated: Mapping[str, Any]) -> dict[str, Any]:
    cases782 = validated["cases782"]
    cases75 = validated["cases75"]
    case1, case2, case3 = cases782[1], cases782[2], cases782[3]
    contract = decision_contract(validated)

    def base(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "case_number": row.get("case_number"),
            "teacher_name": row.get("teacher_name"),
            "school_name": row.get("school_name"),
            "class_name": row.get("class_name"),
            "class_level": row.get("class_level"),
            "class_series": row.get("class_series") or [],
            "source": row.get("source") or {},
            "target": row.get("target") or {},
        }

    c1 = base(case1)
    c1["technical_outcome"] = contract["case_1"]

    c2 = base(case2)
    c2["alternatives"] = case2.get("alternative_exact_level_candidates") or []
    c2["identity_context"] = _identity_label(cases75[2])

    c3 = base(case3)
    c3["identity_context"] = _identity_label(cases75[3])

    return {
        "phase": PHASE_ID,
        "source_p0f7_5_manifest_sha256": validated["p0f7_5_sha"],
        "source_p0f7_8_2_manifest_sha256": validated["p0f7_8_2_sha"],
        "case1": c1,
        "case2": c2,
        "case3": c3,
        "contract": contract,
    }


def _esc(value: Any) -> str:
    return html.escape(_norm(value), quote=True)


def build_html(validated: Mapping[str, Any]) -> str:
    vm = _build_view_model(validated)
    c1, c2, c3 = vm["case1"], vm["case2"], vm["case3"]
    payload = json.dumps(vm, ensure_ascii=False).replace("</", "<\\/")

    alt_cards = []
    for alt in c2["alternatives"]:
        alt_cards.append(
            f"<div class='candidate'><strong>Componente alternativo</strong>"
            f"<div>{_esc(_classification_label(alt.get('curricular_classification')))}</div>"
            f"<details><summary>Detalhes técnicos</summary><code>{_esc(alt.get('course_id'))}</code>"
            f"<div>Rank curricular: {_esc(alt.get('curricular_rank'))}</div></details></div>"
        )
    alt_html = "".join(alt_cards)

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P0-F7.9 — Adjudicação de Componente Curricular</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f5f6f8;color:#18202a;margin:0;padding:24px}}
main{{max-width:980px;margin:auto}} .card{{background:white;border:1px solid #d8dde6;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 1px 3px #0001}}
h1{{font-size:26px}} h2{{font-size:20px;margin-top:0}} .ok{{background:#eef8f0;border-left:4px solid #4b8b57;padding:12px}} .warn{{background:#fff7e8;border-left:4px solid #b7791f;padding:12px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} .candidate{{border:1px solid #ccd3dd;border-radius:10px;padding:12px;margin:10px 0}} label{{display:block;margin:10px 0;font-weight:600}}
select,textarea,input[type=text]{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #b7c0cc;border-radius:8px;font:inherit}} textarea{{min-height:90px}} button{{padding:12px 18px;border:0;border-radius:9px;background:#243b53;color:white;font-weight:700;cursor:pointer}}
small,.muted{{color:#5e6c7b}} code{{word-break:break-all}} details{{margin-top:8px}} .footer{{margin-top:20px;font-size:13px;color:#5e6c7b}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}} body{{padding:12px}}}}
</style></head><body><main>
<h1>P0-F7.9 — Adjudicação de Componente Curricular</h1>
<div class="ok"><strong>Estação offline.</strong> Nenhum acesso ao servidor, MongoDB, notas, frequência ou estudantes. Esta etapa não decide carga horária e não autoriza executor.</div>

<section class="card"><h2>Caso 1 — {_esc(c1['class_name'])}</h2>
<p><strong>{_esc(c1['school_name'])}</strong> · {_esc(c1['teacher_name'])}</p>
<div class="ok">A política curricular já produziu preferência técnica pelo <strong>Registro 1 (source)</strong>, com rank 3 contra rank 2. Não há adjudicação humana de componente neste caso.</div>
<details><summary>Detalhes técnicos</summary>
<div>Registro 1: <code>{_esc(c1['source'].get('course_id'))}</code> — {_esc(_classification_label(c1['source'].get('curricular_classification')))}</div>
<div>Registro 2: <code>{_esc(c1['target'].get('course_id'))}</code> — {_esc(_classification_label(c1['target'].get('curricular_classification')))}</div>
</details><p class="muted">A preferência técnica não é autorização para alterar o banco.</p></section>

<section class="card" data-case="2"><h2>Caso 2 — {_esc(c2['class_name'])}</h2>
<p><strong>{_esc(c2['school_name'])}</strong> · {_esc(c2['teacher_name'])}</p>
<div class="warn">Os dois componentes atualmente vinculados são incompatíveis com o nível EJA Final. Existe candidato de mesmo nome e nível compatível, mas sem escopo explícito de séries. Exige decisão institucional.</div>
<p class="muted">{_esc(c2['identity_context'])}</p>{alt_html}
<label>Decisão
<select id="decision-2"><option value="">Selecione...</option><option value="{DECISION_SELECT_ALTERNATIVE}">Selecionar o componente alternativo compatível com EJA Final</option><option value="{DECISION_DEFER}">Adiar e exigir revisão curricular cadastral</option></select></label>
<label>Justificativa institucional<textarea id="justification-2" placeholder="Explique a decisão sem tratar 2h/3h nesta etapa."></textarea></label>
</section>

<section class="card" data-case="3"><h2>Caso 3 — {_esc(c3['class_name'])}</h2>
<p><strong>{_esc(c3['school_name'])}</strong> · {_esc(c3['teacher_name'])}</p>
<div class="warn">Registro 1 e Registro 2 permanecem no mesmo nível de revisão curricular. Não existe preferência curricular forte entre eles.</div>
<p class="muted">{_esc(c3['identity_context'])}</p>
<div class="grid"><div class="candidate"><strong>Registro 1 (source)</strong><div>{_esc(_classification_label(c3['source'].get('curricular_classification')))}</div><details><summary>Detalhes técnicos</summary><code>{_esc(c3['source'].get('course_id'))}</code></details></div>
<div class="candidate"><strong>Registro 2 (target)</strong><div>{_esc(_classification_label(c3['target'].get('curricular_classification')))}</div><details><summary>Detalhes técnicos</summary><code>{_esc(c3['target'].get('course_id'))}</code></details></div></div>
<label>Decisão
<select id="decision-3"><option value="">Selecione...</option><option value="{DECISION_SELECT_SOURCE}">Selecionar Registro 1</option><option value="{DECISION_SELECT_TARGET}">Selecionar Registro 2</option><option value="{DECISION_DEFER}">Adiar e exigir revisão curricular cadastral</option></select></label>
<label>Justificativa institucional<textarea id="justification-3" placeholder="Explique a decisão sem tratar 2h/3h nesta etapa."></textarea></label>
</section>

<section class="card"><h2>Responsável pela adjudicação</h2>
<label>Nome do responsável<input id="responsible" type="text" autocomplete="off"></label>
<label><input id="authority" type="checkbox"> Confirmo que possuo autoridade institucional para registrar estas decisões de componente curricular.</label>
<button id="export">Exportar decisões P0-F7.9</button>
<p id="status" class="muted"></p></section>
<div class="footer">Carga semanal 2h × 3h permanece explicitamente fora do escopo. O JSON exportado não executa nem autoriza qualquer alteração.</div>
<script id="vm" type="application/json">{payload}</script>
<script>
const VM=JSON.parse(document.getElementById('vm').textContent);
function val(id){{return document.getElementById(id).value.trim();}}
function buildDecision(n){{
 const decision=val('decision-'+n), justification=val('justification-'+n);
 if(!decision) throw new Error('Caso '+n+': selecione uma decisão.');
 if(!justification) throw new Error('Caso '+n+': informe a justificativa.');
 let selected_course_id=null;
 if(n===2 && decision==='{DECISION_SELECT_ALTERNATIVE}') selected_course_id=VM.contract.case_2.allowed_course_ids[0];
 if(n===3 && decision==='{DECISION_SELECT_SOURCE}') selected_course_id=VM.contract.case_3.source_course_id;
 if(n===3 && decision==='{DECISION_SELECT_TARGET}') selected_course_id=VM.contract.case_3.target_course_id;
 return {{case_number:n,decision,selected_course_id,justification}};
}}
document.getElementById('export').addEventListener('click',()=>{{
 try{{
  const responsible=val('responsible'); if(!responsible) throw new Error('Informe o responsável.');
  if(!document.getElementById('authority').checked) throw new Error('Confirme a autoridade institucional.');
  const out={{phase:VM.phase,source_p0f7_8_2_manifest_sha256:VM.source_p0f7_8_2_manifest_sha256,responsible,authority_confirmed:true,decisions:[buildDecision(2),buildDecision(3)],workload_decision_performed:false,executor_authorized:false}};
  const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}}), url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url;a.download='p0f7_9-decisions.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.getElementById('status').textContent='Decisões exportadas. Ainda não há autorização de executor.';
 }}catch(e){{document.getElementById('status').textContent=e.message;}}
}});
</script></main></body></html>"""


def validate_human_decisions(
    validated: Mapping[str, Any], decisions: Mapping[str, Any]
) -> list[dict[str, Any]]:
    contract = decision_contract(validated)
    if decisions.get("phase") != PHASE_ID:
        raise ValueError("DECISIONS_PHASE_MISMATCH")
    if _norm(decisions.get("source_p0f7_8_2_manifest_sha256")) != validated["p0f7_8_2_sha"]:
        raise ValueError("DECISIONS_SOURCE_SHA_MISMATCH")
    if not _norm(decisions.get("responsible")):
        raise ValueError("RESPONSIBLE_REQUIRED")
    if decisions.get("authority_confirmed") is not True:
        raise ValueError("AUTHORITY_CONFIRMATION_REQUIRED")
    if decisions.get("workload_decision_performed") is not False:
        raise ValueError("WORKLOAD_DECISION_FORBIDDEN_IN_P0F7_9")
    if decisions.get("executor_authorized") is not False:
        raise ValueError("EXECUTOR_AUTHORIZATION_FORBIDDEN_IN_P0F7_9")

    rows = decisions.get("decisions") or []
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("EXACTLY_TWO_HUMAN_DECISIONS_REQUIRED")
    by_case = {int(row.get("case_number") or 0): row for row in rows if isinstance(row, Mapping)}
    if sorted(by_case) != [2, 3]:
        raise ValueError("DECISION_CASE_SET_MUST_BE_2_AND_3")

    sealed: list[dict[str, Any]] = []
    for number in (2, 3):
        row = by_case[number]
        decision = _norm(row.get("decision"))
        justification = _norm(row.get("justification"))
        selected = _norm(row.get("selected_course_id")) or None
        if not justification:
            raise ValueError(f"CASE_{number}_JUSTIFICATION_REQUIRED")

        if number == 2:
            allowed = set(contract["case_2"]["allowed_decisions"])
            if decision not in allowed:
                raise ValueError("CASE_2_DECISION_NOT_ALLOWED")
            if decision == DECISION_SELECT_ALTERNATIVE:
                if selected not in set(contract["case_2"]["allowed_course_ids"]):
                    raise ValueError("CASE_2_SELECTED_COURSE_NOT_ALLOWED")
            elif selected is not None:
                raise ValueError("CASE_2_DEFER_MUST_NOT_SELECT_COURSE")
        else:
            allowed = set(contract["case_3"]["allowed_decisions"])
            if decision not in allowed:
                raise ValueError("CASE_3_DECISION_NOT_ALLOWED")
            expected = None
            if decision == DECISION_SELECT_SOURCE:
                expected = contract["case_3"]["source_course_id"]
            elif decision == DECISION_SELECT_TARGET:
                expected = contract["case_3"]["target_course_id"]
            if expected is not None and selected != expected:
                raise ValueError("CASE_3_SELECTED_COURSE_MISMATCH")
            if decision == DECISION_DEFER and selected is not None:
                raise ValueError("CASE_3_DEFER_MUST_NOT_SELECT_COURSE")

        sealed.append({
            "case_number": number,
            "decision": decision,
            "selected_course_id": selected,
            "justification": justification,
        })
    return sealed


def seal_manifest(
    validated: Mapping[str, Any], decisions: Mapping[str, Any]
) -> dict[str, Any]:
    sealed_decisions = validate_human_decisions(validated, decisions)
    contract = decision_contract(validated)
    case1 = validated["cases782"][1]
    manifest: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "OFFLINE_HUMAN_COMPONENT_ADJUDICATION",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_p0f7_5_manifest_sha256": validated["p0f7_5_sha"],
        "source_p0f7_8_2_manifest_sha256": validated["p0f7_8_2_sha"],
        "responsible": _norm(decisions.get("responsible")),
        "authority_confirmed": True,
        "technical_outcomes": [{
            "case_number": 1,
            "policy_state": CASE1_POLICY,
            "outcome": "TECHNICAL_SOURCE_PREFERENCE",
            "selected_course_id": contract["case_1"]["selected_course_id"],
            "source_curricular_rank": (case1.get("source") or {}).get("curricular_rank"),
            "target_curricular_rank": (case1.get("target") or {}).get("curricular_rank"),
            "human_component_adjudication_required": False,
            "automatic_database_action": False,
        }],
        "human_decisions": sealed_decisions,
        "summary": {
            "technical_component_outcomes": 1,
            "human_component_decisions": 2,
            "deferred_component_cases": sum(1 for row in sealed_decisions if row["decision"] == DECISION_DEFER),
            "workload_decisions": 0,
            "database_access": False,
            "database_mutation": False,
            "executor_authorizations": 0,
        },
        "safety": {
            "offline": True,
            "read_only": True,
            "database_access": False,
            "production_access": False,
            "contains_student_identifiers": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "workload_decision_performed": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "executor_authorized": False,
            "not_authorization_for_executor": True,
        },
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.9 offline component adjudication")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--series", required=True, type=Path)
    build.add_argument("--reevaluation", required=True, type=Path)
    build.add_argument("--html", required=True, type=Path)

    seal = sub.add_parser("seal")
    seal.add_argument("--series", required=True, type=Path)
    seal.add_argument("--reevaluation", required=True, type=Path)
    seal.add_argument("--decisions", required=True, type=Path)
    seal.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    assert_offline_only()
    args = parse_args()
    p0f75 = _load_json(args.series)
    p0f782 = _load_json(args.reevaluation)
    validated = validate_inputs(p0f75, p0f782)

    if args.command == "build":
        _private_write(args.html, build_html(validated))
        print(f"P0F7_9_STATION_BUILT=YES path={args.html}")
        print("PRODUCTION_ACCESS=NO")
        print("WORKLOAD_DECISION=NO")
        print("EXECUTOR_AUTHORIZED=NO")
        return

    decisions = _load_json(args.decisions)
    manifest = seal_manifest(validated, decisions)
    _private_write_json(args.json_path, manifest)
    print("P0F7_9_DECISIONS_SEALED=YES")
    print(f"REPORT={args.json_path}")
    print(f"MANIFEST_SHA256={manifest['manifest_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("EXECUTOR_AUTHORIZED=NO")


if __name__ == "__main__":
    main()
