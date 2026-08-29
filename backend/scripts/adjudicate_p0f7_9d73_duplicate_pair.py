"""P0-F7.9D7.3 - offline human adjudication and revised non-executable plan.

Consumes the sealed D4 plan, D7.1 collision report and the real D7.2 forensic
report. It never connects to a database or network and never executes writes.

D7.3 has two explicit human decisions:
1) which assignment survives the duplicate semantic pair;
2) which existing weekly workload value (from the pair) prevails.

If either decision is deferred, the manifest remains valid but the revised
execution plan stays blocked. If both are resolved, D7.3 emits an exact,
non-executable operation plan: 21 non-colliding course remaps, one duplicate
retirement by status, and one survivor consolidation update.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
D71_PHASE = "P0F7.9D7.1-INTRA-BATCH-COLLISION-PREFLIGHT-2026"
D72_PHASE = "P0F7.9D7.2-OFFLINE-DUPLICATE-PAIR-FORENSIC-2026"
D72_MODE = "LOCAL_OFFLINE_READ_ONLY_FORENSIC"
DECISION_PHASE = "P0F7.9D7.3-HUMAN-DUPLICATE-PAIR-DECISION-2026"
OUTPUT_PHASE = "P0F7.9D7.3-SEALED-DUPLICATE-PAIR-ADJUDICATION-2026"
OUTPUT_MODE = "LOCAL_OFFLINE_HUMAN_ADJUDICATION_NON_EXECUTABLE"

EXPECTED_PLAN_SHA256 = "6d39d8425c0555b36b69c8f5d00832fc8f93e1c4f38c35c0f29ea8e72fcf1312"
EXPECTED_D72_REPORT_SHA256 = "228e809edbe151797b055f12c467243e9b5db1db6bb64107a3f27fd83b1d7ea3"

EXPECTED_ENTRIES = 23
EXPECTED_SAFE = 21
EXPECTED_BLOCKED = 2
EXPECTED_GROUPS = 1
RETIRE_STATUS = "inativo"

SURVIVOR_SELECT = "SELECT_ASSIGNMENT"
SURVIVOR_DEFER = "DEFER"
WORKLOAD_SELECT = "SELECT_EXISTING_PAIR_VALUE"
WORKLOAD_DEFER = "DEFER"

FORBIDDEN_IMPORT_ROOTS = {
    "pymongo", "motor", "requests", "httpx", "subprocess", "paramiko", "fabric"
}
MUTATOR_METHOD_NAMES = {
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "bulk_write", "find_one_and_update"
}


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


def _unsigned_hash(payload: Mapping[str, Any], field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


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
    _private_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def assert_offline_only() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    mutation_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MUTATOR_METHOD_NAMES:
                mutation_calls.add(node.func.attr)
    forbidden = sorted(imported_roots & FORBIDDEN_IMPORT_ROOTS)
    if forbidden:
        raise RuntimeError(f"D73_OFFLINE_BOUNDARY_FAILED:{forbidden}")
    if mutation_calls:
        raise RuntimeError(f"D73_MUTATION_BOUNDARY_FAILED:{sorted(mutation_calls)}")


def validate_inputs(
    plan: Mapping[str, Any],
    d71: Mapping[str, Any],
    d72: Mapping[str, Any],
) -> dict[str, Any]:
    assert_offline_only()

    if (
        plan.get("phase") != PLAN_PHASE
        or plan.get("status") != "PASS"
        or plan.get("mode") != PLAN_MODE
    ):
        raise ValueError("P0F7_9D73_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if (
        not plan_sha
        or plan_sha != _unsigned_hash(plan, "plan_sha256")
        or plan_sha != EXPECTED_PLAN_SHA256
    ):
        raise ValueError("P0F7_9D73_PLAN_SHA_INVALID")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F7_9D73_PLAN_MUST_BE_NON_EXECUTABLE")
    entries = list(plan.get("entries") or [])
    if len(entries) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D73_PLAN_ENTRY_COUNT_INVALID")

    if d71.get("phase") != D71_PHASE or d71.get("status") != "PASS":
        raise ValueError("P0F7_9D73_D71_INVALID")
    d71_sha = _norm(d71.get("report_sha256"))
    if not d71_sha or d71_sha != _unsigned_hash(d71, "report_sha256"):
        raise ValueError("P0F7_9D73_D71_SHA_INVALID")
    if _norm(d71.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D73_D71_PLAN_CHAIN_MISMATCH")
    s71 = d71.get("summary") or {}
    if (
        int(s71.get("entries") or 0) != EXPECTED_ENTRIES
        or int(s71.get("safe_noncolliding") or 0) != EXPECTED_SAFE
        or int(s71.get("blocked_intra_batch") or 0) != EXPECTED_BLOCKED
        or int(s71.get("collision_groups") or 0) != EXPECTED_GROUPS
        or s71.get("execution_gate_open") is not False
    ):
        raise ValueError("P0F7_9D73_D71_PARTITION_INVALID")
    if s71.get("production_writes") is not False or s71.get("remediation_executed") is not False:
        raise ValueError("P0F7_9D73_D71_SAFETY_INVALID")

    safe = list(d71.get("safe_entries") or [])
    blocked = list(d71.get("blocked_entries") or [])
    if len(safe) != EXPECTED_SAFE or len(blocked) != EXPECTED_BLOCKED:
        raise ValueError("P0F7_9D73_D71_ENTRY_LISTS_INVALID")

    if (
        d72.get("phase") != D72_PHASE
        or d72.get("status") != "PASS"
        or d72.get("mode") != D72_MODE
    ):
        raise ValueError("P0F7_9D73_D72_INVALID")
    d72_sha = _norm(d72.get("report_sha256"))
    if not d72_sha or d72_sha != _unsigned_hash(d72, "report_sha256"):
        raise ValueError("P0F7_9D73_D72_SHA_INVALID")
    if d72_sha != EXPECTED_D72_REPORT_SHA256:
        raise ValueError("P0F7_9D73_D72_NOT_REAL_EXECUTED_REPORT")
    if _norm(d72.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D73_D72_PLAN_CHAIN_MISMATCH")
    if _norm(d72.get("source_d71_report_sha256")) != d71_sha:
        raise ValueError("P0F7_9D73_D72_D71_CHAIN_MISMATCH")

    pair = d72.get("pair") or {}
    summary72 = d72.get("summary") or {}
    adjudication = d72.get("adjudication_contract") or {}
    if pair.get("classification") != "ACTIVE_DUPLICATE_SEMANTIC_PAIR_REQUIRES_CONSOLIDATION":
        raise ValueError("P0F7_9D73_D72_CLASSIFICATION_INVALID")
    required_true = (
        "same_staff",
        "same_school",
        "same_class",
        "same_academic_year",
        "both_active",
        "weekly_workload_conflict",
    )
    if any(pair.get(field) is not True for field in required_true):
        raise ValueError("P0F7_9D73_D72_PAIR_INVARIANT_INVALID")
    if pair.get("substitution_present") is not False:
        raise ValueError("P0F7_9D73_D72_SUBSTITUTION_PRESENT")
    if (
        summary72.get("blocked_assignments") != EXPECTED_BLOCKED
        or summary72.get("collision_groups") != EXPECTED_GROUPS
        or summary72.get("semantic_pair_confirmed") is not True
        or summary72.get("survivor_decision_required") is not True
        or summary72.get("workload_decision_required") is not True
        or summary72.get("production_writes") is not False
        or summary72.get("database_mutation") is not False
        or summary72.get("remediation_executed") is not False
    ):
        raise ValueError("P0F7_9D73_D72_SUMMARY_INVALID")
    if (
        adjudication.get("automatic_survivor_selection") is not False
        or adjudication.get("automatic_workload_decision") is not False
        or adjudication.get("current_23_write_authorization_reusable") is not False
    ):
        raise ValueError("P0F7_9D73_D72_ADJUDICATION_CONTRACT_INVALID")

    pair_rows = list(pair.get("assignments") or [])
    if len(pair_rows) != EXPECTED_BLOCKED:
        raise ValueError("P0F7_9D73_D72_ASSIGNMENT_COUNT_INVALID")
    pair_by_id = {_norm(row.get("assignment_id")): row for row in pair_rows}
    if len(pair_by_id) != EXPECTED_BLOCKED or "" in pair_by_id:
        raise ValueError("P0F7_9D73_D72_ASSIGNMENT_IDS_INVALID")

    blocked_ids = {_norm(row.get("assignment_id")) for row in blocked}
    if set(pair_by_id) != blocked_ids:
        raise ValueError("P0F7_9D73_D72_BLOCKED_SET_MISMATCH")

    workloads = [row.get("weekly_workload") for row in pair_rows]
    normalized_workloads = {_norm(value) for value in workloads}
    if "" in normalized_workloads or len(normalized_workloads) != 2:
        raise ValueError("P0F7_9D73_D72_WORKLOAD_OPTIONS_INVALID")

    shared_target = pair.get("shared_target") or {}
    target_course_id = _norm(shared_target.get("course_id"))
    if not target_course_id:
        raise ValueError("P0F7_9D73_SHARED_TARGET_MISSING")
    blocked_targets = {_norm(row.get("target_course_id")) for row in blocked}
    if blocked_targets != {target_course_id}:
        raise ValueError("P0F7_9D73_SHARED_TARGET_CHAIN_MISMATCH")

    plan_by_id = {
        _norm(row.get("assignment_id")): row
        for row in entries
        if _norm(row.get("assignment_id"))
    }
    if len(plan_by_id) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D73_PLAN_ASSIGNMENT_SET_INVALID")
    for row in safe + blocked:
        aid = _norm(row.get("assignment_id"))
        plan_row = plan_by_id.get(aid)
        if not plan_row:
            raise ValueError(f"P0F7_9D73_ENTRY_NOT_IN_PLAN:{aid}")
        if _norm((plan_row.get("source") or {}).get("course_id")) != _norm(row.get("source_course_id")):
            raise ValueError(f"P0F7_9D73_SOURCE_CHAIN_MISMATCH:{aid}")
        if _norm((plan_row.get("target") or {}).get("course_id")) != _norm(row.get("target_course_id")):
            raise ValueError(f"P0F7_9D73_TARGET_CHAIN_MISMATCH:{aid}")

    return {
        "plan_sha256": plan_sha,
        "d71_sha256": d71_sha,
        "d72_sha256": d72_sha,
        "plan_by_id": plan_by_id,
        "safe_entries": sorted(safe, key=lambda row: int(row.get("ordinal") or 0)),
        "blocked_entries": sorted(blocked, key=lambda row: int(row.get("ordinal") or 0)),
        "pair_rows": sorted(pair_rows, key=lambda row: int(row.get("ordinal") or 0)),
        "pair_by_id": pair_by_id,
        "shared_target": shared_target,
        "workload_options": workloads,
        "class": d72.get("class") or {},
        "tenant": _norm(plan.get("mantenedora_id")),
        "academic_year": int(plan.get("academic_year") or 0),
    }


def build_decision_template(validated: Mapping[str, Any]) -> dict[str, Any]:
    pair_rows = validated["pair_rows"]
    return {
        "phase": DECISION_PHASE,
        "source_d72_report_sha256": validated["d72_sha256"],
        "responsible": "",
        "authority_confirmed": False,
        "survivor": {
            "decision": SURVIVOR_DEFER,
            "assignment_id": None,
            "justification": "",
        },
        "workload": {
            "decision": WORKLOAD_DEFER,
            "value": None,
            "justification": "",
        },
        "duplicate_retirement_confirmed": False,
        "allowed_survivor_assignment_ids": [row["assignment_id"] for row in pair_rows],
        "allowed_workload_values": validated["workload_options"],
        "production_write_authorized": False,
        "executor_authorized": False,
    }


def _esc(value: Any) -> str:
    return html.escape(_norm(value), quote=True)


def build_html(validated: Mapping[str, Any]) -> str:
    template = build_decision_template(validated)
    rows = validated["pair_rows"]
    shared = validated["shared_target"]
    class_info = validated["class"]
    payload = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    survivor_options = "\n".join(
        f"<option value='{_esc(row['assignment_id'])}'>"
        f"#{int(row.get('ordinal') or 0)} - {_esc(row.get('source_course_name'))} - "
        f"CH {_esc(row.get('weekly_workload'))}h - {_esc(row.get('assignment_id'))}"
        "</option>"
        for row in rows
    )
    workload_options = "\n".join(
        f"<option value='{_esc(v)}'>{_esc(v)}h/semana</option>"
        for v in validated["workload_options"]
    )
    cards = []
    for row in rows:
        audit = row.get("audit") or {}
        cards.append(
            "<section class='card'>"
            f"<h2>Registro #{int(row.get('ordinal') or 0)}</h2>"
            f"<p><b>assignment_id:</b> <code>{_esc(row.get('assignment_id'))}</code></p>"
            f"<p><b>Origem:</b> {_esc(row.get('source_course_name'))} "
            f"({_esc(row.get('source_course_level'))})</p>"
            f"<p><b>Carga semanal atual:</b> {_esc(row.get('weekly_workload'))}h</p>"
            f"<p><b>Status:</b> {_esc(row.get('status'))}</p>"
            f"<p><b>Criado:</b> {_esc(row.get('created_at'))} | "
            f"<b>Atualizado:</b> {_esc(row.get('updated_at'))}</p>"
            f"<p><b>Auditoria:</b> {_esc(audit.get('event_count'))} eventos; "
            f"primeiro {_esc(audit.get('first_event_at'))}; último {_esc(audit.get('last_event_at'))}</p>"
            f"<p><b>Slots do componente de origem:</b> {_esc(row.get('schedule_slots_for_source_course'))} "
            "(apenas evidência; não equivalem automaticamente a horas)</p>"
            "</section>"
        )
    cards_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P0-F7.9D7.3 - Adjudicação do par duplicado</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f5f6f8;color:#18202a;margin:0;padding:24px}}
main{{max-width:980px;margin:auto}} .card{{background:#fff;border:1px solid #d8dde6;border-radius:12px;padding:18px;margin:14px 0}}
.warn{{background:#fff7e8;border-left:4px solid #b7791f;padding:12px}} .ok{{background:#eef8f0;border-left:4px solid #4b8b57;padding:12px}}
label{{display:block;font-weight:650;margin:12px 0 5px}} input,select,textarea{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #b7c0cc;border-radius:8px;font:inherit}}
textarea{{min-height:86px}} input[type=checkbox]{{width:auto}} button{{margin-top:16px;padding:12px 18px;border:0;border-radius:9px;background:#243b53;color:#fff;font-weight:700}}
code{{word-break:break-all}} small{{color:#5e6c7b}}
</style></head><body><main>
<h1>P0-F7.9D7.3 - Adjudicação do par duplicado</h1>
<div class="ok"><b>D7.2 selada:</b> {_esc(validated["d72_sha256"])}</div>
<p><b>Turma:</b> {_esc(class_info.get("class_name"))} | <b>Ano:</b> {_esc(validated["academic_year"])}</p>
<p><b>Target compartilhado:</b> {_esc(shared.get("course_name"))} - <code>{_esc(shared.get("course_id"))}</code></p>
<div class="warn"><b>Regra:</b> nenhuma escolha é automática. O vínculo não sobrevivente será apenas planejado para inativação; hard delete continua proibido. Slots e carga anual não são convertidos automaticamente em carga semanal.</div>
{cards_html}
<section class="card">
<h2>Decisão humana</h2>
<label>Responsável institucional</label><input id="responsible" type="text">
<label><input id="authority" type="checkbox"> Confirmo que possuo autoridade institucional para esta adjudicação.</label>
<label>Survivor</label>
<select id="survivor"><option value="">Adiar decisão</option>{survivor_options}</select>
<label>Justificativa do survivor</label><textarea id="survivorJust"></textarea>
<label>Carga semanal consolidada</label>
<select id="workload"><option value="">Adiar decisão</option>{workload_options}</select>
<label>Justificativa da carga</label><textarea id="workloadJust"></textarea>
<label><input id="retire" type="checkbox"> Confirmo que, se um survivor for escolhido, o outro vínculo deve ser planejado para status '{_esc(RETIRE_STATUS)}', sem exclusão física.</label>
<button onclick="exportDecision()">Exportar decisão JSON</button>
<p><small>Este arquivo não executa banco, rede ou produção. A exportação continua com production_write_authorized=false e executor_authorized=false.</small></p>
</section>
<script>
const base={payload};
function exportDecision(){{
  const survivor=document.getElementById('survivor').value;
  const workload=document.getElementById('workload').value;
  const out=JSON.parse(JSON.stringify(base));
  out.responsible=document.getElementById('responsible').value.trim();
  out.authority_confirmed=document.getElementById('authority').checked;
  out.survivor.decision=survivor ? "{SURVIVOR_SELECT}" : "{SURVIVOR_DEFER}";
  out.survivor.assignment_id=survivor || null;
  out.survivor.justification=document.getElementById('survivorJust').value.trim();
  out.workload.decision=workload ? "{WORKLOAD_SELECT}" : "{WORKLOAD_DEFER}";
  out.workload.value=workload ? Number(workload) : null;
  out.workload.justification=document.getElementById('workloadJust').value.trim();
  out.duplicate_retirement_confirmed=document.getElementById('retire').checked;
  const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='p0f7_9d73-human-decision.json'; a.click(); URL.revokeObjectURL(a.href);
}}
</script></main></body></html>"""


def _value_matches(option: Any, chosen: Any) -> bool:
    return _norm(option) == _norm(chosen)


def validate_decision(
    decision: Mapping[str, Any],
    validated: Mapping[str, Any],
) -> dict[str, Any]:
    if decision.get("phase") != DECISION_PHASE:
        raise ValueError("P0F7_9D73_DECISION_PHASE_INVALID")
    if _norm(decision.get("source_d72_report_sha256")) != validated["d72_sha256"]:
        raise ValueError("P0F7_9D73_DECISION_D72_CHAIN_MISMATCH")
    responsible = _norm(decision.get("responsible"))
    if not responsible:
        raise ValueError("P0F7_9D73_RESPONSIBLE_REQUIRED")
    if decision.get("authority_confirmed") is not True:
        raise ValueError("P0F7_9D73_AUTHORITY_CONFIRMATION_REQUIRED")
    if decision.get("production_write_authorized") is not False:
        raise ValueError("P0F7_9D73_WRITE_AUTHORIZATION_FORBIDDEN")
    if decision.get("executor_authorized") is not False:
        raise ValueError("P0F7_9D73_EXECUTOR_AUTHORIZATION_FORBIDDEN")

    survivor = decision.get("survivor") or {}
    s_decision = survivor.get("decision")
    s_id = _norm(survivor.get("assignment_id"))
    s_just = _norm(survivor.get("justification"))
    allowed_ids = {_norm(row.get("assignment_id")) for row in validated["pair_rows"]}
    if s_decision not in {SURVIVOR_SELECT, SURVIVOR_DEFER}:
        raise ValueError("P0F7_9D73_SURVIVOR_DECISION_INVALID")
    if s_decision == SURVIVOR_SELECT:
        if s_id not in allowed_ids:
            raise ValueError("P0F7_9D73_SURVIVOR_NOT_IN_PAIR")
        if len(s_just) < 10:
            raise ValueError("P0F7_9D73_SURVIVOR_JUSTIFICATION_REQUIRED")
        if decision.get("duplicate_retirement_confirmed") is not True:
            raise ValueError("P0F7_9D73_RETIREMENT_CONFIRMATION_REQUIRED")
    else:
        if s_id:
            raise ValueError("P0F7_9D73_DEFERRED_SURVIVOR_MUST_HAVE_NO_ID")

    workload = decision.get("workload") or {}
    w_decision = workload.get("decision")
    w_value = workload.get("value")
    w_just = _norm(workload.get("justification"))
    if w_decision not in {WORKLOAD_SELECT, WORKLOAD_DEFER}:
        raise ValueError("P0F7_9D73_WORKLOAD_DECISION_INVALID")
    if w_decision == WORKLOAD_SELECT:
        if not any(_value_matches(option, w_value) for option in validated["workload_options"]):
            raise ValueError("P0F7_9D73_WORKLOAD_NOT_EXISTING_PAIR_VALUE")
        if len(w_just) < 10:
            raise ValueError("P0F7_9D73_WORKLOAD_JUSTIFICATION_REQUIRED")
    else:
        if w_value is not None:
            raise ValueError("P0F7_9D73_DEFERRED_WORKLOAD_MUST_HAVE_NO_VALUE")

    resolved = s_decision == SURVIVOR_SELECT and w_decision == WORKLOAD_SELECT
    return {
        "responsible": responsible,
        "survivor_decision": s_decision,
        "survivor_assignment_id": s_id or None,
        "survivor_justification": s_just,
        "workload_decision": w_decision,
        "workload_value": w_value if w_decision == WORKLOAD_SELECT else None,
        "workload_justification": w_just,
        "duplicate_retirement_confirmed": decision.get("duplicate_retirement_confirmed") is True,
        "fully_resolved": resolved,
    }


def _scope_from_plan(plan_row: Mapping[str, Any], tenant: str, year: int) -> dict[str, Any]:
    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "school_id": _norm(plan_row.get("school_id")),
        "class_id": _norm(plan_row.get("class_id")),
        "assignment_id": _norm(plan_row.get("assignment_id")),
    }


def build_revised_operations(
    validated: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not decision["fully_resolved"]:
        return []

    tenant = validated["tenant"]
    year = validated["academic_year"]
    plan_by_id = validated["plan_by_id"]
    operations: list[dict[str, Any]] = []

    for row in validated["safe_entries"]:
        aid = _norm(row.get("assignment_id"))
        plan_row = plan_by_id[aid]
        source = _norm((plan_row.get("source") or {}).get("course_id"))
        target = _norm((plan_row.get("target") or {}).get("course_id"))
        operations.append(
            {
                "operation_index": len(operations) + 1,
                "operation_type": "REMAP_COURSE",
                "scope": _scope_from_plan(plan_row, tenant, year),
                "cas_expected": {"status": "ativo_or_active", "course_id": source},
                "set_fields": {"course_id": target},
                "rollback_set_fields": {"course_id": source},
                "source_d4_ordinal": int(plan_row.get("ordinal") or 0),
            }
        )

    survivor_id = decision["survivor_assignment_id"]
    retire_id = next(
        aid for aid in validated["pair_by_id"] if aid != survivor_id
    )
    survivor_row = validated["pair_by_id"][survivor_id]
    retire_row = validated["pair_by_id"][retire_id]
    survivor_plan = plan_by_id[survivor_id]
    retire_plan = plan_by_id[retire_id]
    target = _norm(validated["shared_target"].get("course_id"))
    chosen_workload = decision["workload_value"]

    operations.append(
        {
            "operation_index": len(operations) + 1,
            "operation_type": "RETIRE_DUPLICATE_ASSIGNMENT",
            "scope": _scope_from_plan(retire_plan, tenant, year),
            "cas_expected": {
                "status": _norm(retire_row.get("status")),
                "course_id": _norm(retire_row.get("source_course_id")),
                "carga_horaria_semanal": retire_row.get("weekly_workload"),
            },
            "set_fields": {"status": RETIRE_STATUS},
            "rollback_set_fields": {"status": _norm(retire_row.get("status"))},
            "hard_delete": False,
            "source_d4_ordinal": int(retire_plan.get("ordinal") or 0),
        }
    )
    set_fields: dict[str, Any] = {"course_id": target}
    if not _value_matches(survivor_row.get("weekly_workload"), chosen_workload):
        set_fields["carga_horaria_semanal"] = chosen_workload

    rollback_fields: dict[str, Any] = {
        "course_id": _norm(survivor_row.get("source_course_id"))
    }
    if "carga_horaria_semanal" in set_fields:
        rollback_fields["carga_horaria_semanal"] = survivor_row.get("weekly_workload")

    operations.append(
        {
            "operation_index": len(operations) + 1,
            "operation_type": "CONSOLIDATE_SURVIVOR",
            "scope": _scope_from_plan(survivor_plan, tenant, year),
            "cas_expected": {
                "status": _norm(survivor_row.get("status")),
                "course_id": _norm(survivor_row.get("source_course_id")),
                "carga_horaria_semanal": survivor_row.get("weekly_workload"),
            },
            "set_fields": set_fields,
            "rollback_set_fields": rollback_fields,
            "shared_target_course_id": target,
            "source_d4_ordinal": int(survivor_plan.get("ordinal") or 0),
        }
    )

    if len(operations) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D73_REVISED_OPERATION_COUNT_INVALID")
    return operations


def seal(
    plan: Mapping[str, Any],
    d71: Mapping[str, Any],
    d72: Mapping[str, Any],
    human_decision: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_inputs(plan, d71, d72)
    decision = validate_decision(human_decision, validated)
    operations = build_revised_operations(validated, decision)

    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": OUTPUT_MODE,
        "sealed_plan_sha256": validated["plan_sha256"],
        "source_d71_report_sha256": validated["d71_sha256"],
        "source_d72_report_sha256": validated["d72_sha256"],
        "human_decision_sha256": _canonical_sha256(human_decision),
        "decision": {
            **decision,
            "responsible": decision["responsible"],
        },
        "pair_resolution": {
            "class": validated["class"],
            "survivor_assignment_id": decision["survivor_assignment_id"],
            "retired_assignment_id": (
                next(
                    (aid for aid in validated["pair_by_id"] if aid != decision["survivor_assignment_id"]),
                    None,
                )
                if decision["fully_resolved"]
                else None
            ),
            "retirement_status": RETIRE_STATUS if decision["fully_resolved"] else None,
            "shared_target_course_id": _norm(validated["shared_target"].get("course_id")),
            "selected_weekly_workload": decision["workload_value"],
            "hard_delete": False,
        },
        "revised_plan": {
            "ready": decision["fully_resolved"],
            "executable": False,
            "operation_count": len(operations),
            "operations": operations,
            "pair_ordering_rule": "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR",
            "rollback_order": "REVERSE_OPERATION_ORDER",
            "requires_fresh_last_mile_preflight": True,
            "requires_new_cas_dry_run": True,
            "requires_new_explicit_production_write_authorization": True,
            "old_23_write_authorization_reusable": False,
        },
        "summary": {
            "safe_noncolliding_operations": EXPECTED_SAFE if decision["fully_resolved"] else 0,
            "duplicate_retirement_operations": 1 if decision["fully_resolved"] else 0,
            "survivor_consolidation_operations": 1 if decision["fully_resolved"] else 0,
            "revised_document_updates": len(operations),
            "survivor_decision_resolved": decision["survivor_decision"] == SURVIVOR_SELECT,
            "workload_decision_resolved": decision["workload_decision"] == WORKLOAD_SELECT,
            "revised_plan_ready": decision["fully_resolved"],
            "production_write_authorized": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "safety": {
            "offline": True,
            "database_access": False,
            "network_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "hard_delete_allowed": False,
            "student_records_read": 0,
            "staff_id_exposed": False,
            "executor_authorized": False,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.9D7.3 duplicate pair adjudication")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build offline human decision station")
    build.add_argument("--plan", required=True, type=Path)
    build.add_argument("--d71-report", required=True, type=Path)
    build.add_argument("--d72-report", required=True, type=Path)
    build.add_argument("--html", required=True, type=Path)
    build.add_argument("--template-json", required=True, type=Path)

    seal_cmd = sub.add_parser("seal", help="Seal revised non-executable plan")
    seal_cmd.add_argument("--plan", required=True, type=Path)
    seal_cmd.add_argument("--d71-report", required=True, type=Path)
    seal_cmd.add_argument("--d72-report", required=True, type=Path)
    seal_cmd.add_argument("--decision", required=True, type=Path)
    seal_cmd.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = _load(args.plan)
    d71 = _load(args.d71_report)
    d72 = _load(args.d72_report)
    validated = validate_inputs(plan, d71, d72)

    if args.command == "build":
        _private_write(args.html, build_html(validated))
        _private_write_json(args.template_json, build_decision_template(validated))
        print("P0F7_9D73_STATION_BUILT=YES")
        print(f"D72_REPORT_SHA256={validated['d72_sha256']}")
        print(f"HTML={args.html}")
        print(f"TEMPLATE={args.template_json}")
        print("PRODUCTION_ACCESS=NO")
        print("DATABASE_MUTATION=NO")
        print("PRODUCTION_WRITES=NO")
        return

    report = seal(plan, d71, d72, _load(args.decision))
    _private_write_json(args.json, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D73_ADJUDICATION_SEAL=PASS")
    print(f"REPORT={args.json}")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("EXECUTOR_AUTHORIZED=NO")


if __name__ == "__main__":
    main()
