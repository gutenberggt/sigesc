"""P0-F7.9D7.3.1 - policy-driven workload resolution for D7.3.

This offline adapter supersedes only the workload-choice portion of D7.3.
The duplicate survivor remains a human institutional decision, while weekly
workload is derived deterministically from the canonical curricular policy.

No database, network or production write surface exists here.
"""
from __future__ import annotations

import argparse
import ast
import html
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping

from utils.curricular_workload_policy import resolve_curricular_workload

ROOT = Path(__file__).resolve().parents[1]
D73_PATH = ROOT / "scripts" / "adjudicate_p0f7_9d73_duplicate_pair.py"
_spec = importlib.util.spec_from_file_location("p0f7_9d73_base", D73_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("D731_D73_IMPORT_SPEC_FAILED")
d73 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d73)

OUTPUT_POLICY_PHASE = "P0F7.9D7.3.1-CURRICULAR-WORKLOAD-POLICY-2026"
FORBIDDEN_IMPORT_ROOTS = {"pymongo", "motor", "requests", "httpx", "subprocess", "paramiko", "fabric"}
MUTATOR_METHOD_NAMES = {
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "bulk_write", "find_one_and_update",
}


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
    d73.assert_offline_only()
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    mutation_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MUTATOR_METHOD_NAMES:
                mutation_calls.add(node.func.attr)
    forbidden = sorted(imported & FORBIDDEN_IMPORT_ROOTS)
    if forbidden:
        raise RuntimeError(f"D731_OFFLINE_BOUNDARY_FAILED:{forbidden}")
    if mutation_calls:
        raise RuntimeError(f"D731_MUTATION_BOUNDARY_FAILED:{sorted(mutation_calls)}")


def validate_policy_inputs(plan, d71, d72) -> tuple[dict[str, Any], dict[str, Any]]:
    validated = d73.validate_inputs(plan, d71, d72)
    class_info = validated.get("class") or {}
    shared_target = validated.get("shared_target") or {}
    policy = resolve_curricular_workload(
        component_name=shared_target.get("course_name"),
        class_level=class_info.get("class_level") or class_info.get("education_level") or class_info.get("nivel_ensino"),
        class_series=class_info.get("series") or class_info.get("grade_level"),
    )
    if policy.get("applies") is not True:
        raise ValueError("P0F7_9D731_COMPONENT_OUTSIDE_CANONICAL_POLICY")

    canonical_weekly = policy.get("canonical_weekly_workload")
    if not any(d73._value_matches(option, canonical_weekly) for option in validated.get("workload_options") or []):
        raise ValueError("P0F7_9D731_CANONICAL_WEEKLY_NOT_PRESENT_IN_PAIR")
    return validated, policy


def _policy_justification(policy: Mapping[str, Any]) -> str:
    annual = policy.get("canonical_annual_workload")
    weekly = policy.get("canonical_weekly_workload")
    if policy.get("multigrade"):
        return (
            f"Política curricular institucional: multissérie usa a maior CH; "
            f"resultado canônico {annual}h anuais = {weekly}h semanais."
        )
    return f"Política curricular institucional: {annual}h anuais = {weekly}h semanais."


def build_decision_template(validated: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    template = d73.build_decision_template(validated)
    template["workload"] = {
        "decision": d73.WORKLOAD_SELECT,
        "value": policy["canonical_weekly_workload"],
        "justification": _policy_justification(policy),
    }
    template["workload_resolution"] = {
        "source": OUTPUT_POLICY_PHASE,
        "human_choice_required": False,
        "canonical_annual_workload": policy["canonical_annual_workload"],
        "canonical_weekly_workload": policy["canonical_weekly_workload"],
        "multigrade": policy["multigrade"],
        "multigrade_rule": policy["multigrade_rule"],
    }
    return template


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def build_html(validated: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    template = build_decision_template(validated, policy)
    rows = validated["pair_rows"]
    payload = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    survivor_options = "\n".join(
        f"<option value='{_esc(row.get('assignment_id'))}'>"
        f"#{int(row.get('ordinal') or 0)} - CH atual {_esc(row.get('weekly_workload'))}h - "
        f"{_esc(row.get('assignment_id'))}</option>"
        for row in rows
    )
    cards = "\n".join(
        "<section class='card'>"
        f"<h2>Registro #{int(row.get('ordinal') or 0)}</h2>"
        f"<p><b>assignment_id:</b> <code>{_esc(row.get('assignment_id'))}</code></p>"
        f"<p><b>Componente:</b> {_esc(row.get('source_course_name'))}</p>"
        f"<p><b>CH semanal atual:</b> {_esc(row.get('weekly_workload'))}h</p>"
        f"<p><b>Status:</b> {_esc(row.get('status'))}</p>"
        "</section>"
        for row in rows
    )
    series_text = ", ".join(str(v) for v in policy.get("series") or []) or "regra do nível"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P0-F7.9D7.3.1 - Adjudicação curricular</title>
<style>body{{font-family:system-ui;background:#f5f6f8;color:#18202a;margin:0;padding:24px}}main{{max-width:900px;margin:auto}}.card{{background:#fff;border:1px solid #d8dde6;border-radius:12px;padding:18px;margin:14px 0}}.policy{{background:#eef8f0;border-left:4px solid #4b8b57;padding:14px}}label{{display:block;font-weight:650;margin:12px 0 5px}}input,select,textarea{{width:100%;box-sizing:border-box;padding:10px}}input[type=checkbox]{{width:auto}}button{{margin-top:16px;padding:12px 18px}}code{{word-break:break-all}}</style>
</head><body><main>
<h1>P0-F7.9D7.3.1 - Adjudicação do par duplicado</h1>
<div class="policy"><b>Carga resolvida por política curricular:</b><br>
Componente: {_esc(policy.get('component'))}<br>
Nível: {_esc(policy.get('class_level'))}<br>
Séries/etapas: {_esc(series_text)}<br>
CH anual canônica: <b>{_esc(policy.get('canonical_annual_workload'))}h</b><br>
CH semanal canônica: <b>{_esc(policy.get('canonical_weekly_workload'))}h</b><br>
Regra multissérie: {_esc(policy.get('multigrade_rule'))}</div>
{cards}
<section class="card"><h2>Única decisão humana remanescente: survivor</h2>
<label>Responsável institucional</label><input id="responsible" type="text">
<label><input id="authority" type="checkbox"> Confirmo autoridade institucional para adjudicar qual registro sobreviverá.</label>
<label>Survivor</label><select id="survivor"><option value="">Adiar decisão</option>{survivor_options}</select>
<label>Justificativa institucional do survivor</label><textarea id="survivorJust"></textarea>
<label><input id="retire" type="checkbox"> Confirmo que o outro vínculo será planejado para status '{_esc(d73.RETIRE_STATUS)}', sem hard delete.</label>
<button onclick="exportDecision()">Exportar decisão JSON</button>
<p>A carga não é editável nesta estação. production_write_authorized=false e executor_authorized=false.</p>
</section>
<script>const base={payload};function exportDecision(){{const s=document.getElementById('survivor').value;const out=JSON.parse(JSON.stringify(base));out.responsible=document.getElementById('responsible').value.trim();out.authority_confirmed=document.getElementById('authority').checked;out.survivor.decision=s?"{d73.SURVIVOR_SELECT}":"{d73.SURVIVOR_DEFER}";out.survivor.assignment_id=s||null;out.survivor.justification=document.getElementById('survivorJust').value.trim();out.duplicate_retirement_confirmed=document.getElementById('retire').checked;const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='p0f7_9d731-human-survivor-decision.json';a.click();URL.revokeObjectURL(a.href);}}</script>
</main></body></html>"""


def seal(plan, d71, d72, decision: Mapping[str, Any]) -> dict[str, Any]:
    validated, policy = validate_policy_inputs(plan, d71, d72)
    workload = decision.get("workload") or {}
    if workload.get("decision") != d73.WORKLOAD_SELECT:
        raise ValueError("P0F7_9D731_WORKLOAD_MUST_BE_POLICY_SELECTED")
    if not d73._value_matches(workload.get("value"), policy["canonical_weekly_workload"]):
        raise ValueError("P0F7_9D731_WORKLOAD_POLICY_TAMPERED")

    report = d73.seal(plan, d71, d72, decision)
    report["curricular_workload_policy"] = {
        "phase": OUTPUT_POLICY_PHASE,
        "source": policy["source"],
        "version": policy["version"],
        "component": policy["component"],
        "class_level": policy["class_level"],
        "series": policy["series"],
        "per_series_annual_workload": policy["per_series_annual_workload"],
        "multigrade": policy["multigrade"],
        "multigrade_rule": policy["multigrade_rule"],
        "canonical_annual_workload": policy["canonical_annual_workload"],
        "canonical_weekly_workload": policy["canonical_weekly_workload"],
        "human_workload_choice_required": False,
    }
    report["summary"]["workload_resolution_source"] = "CURRICULAR_POLICY"
    report.pop("report_sha256", None)
    report["report_sha256"] = d73._canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.9D7.3.1 curricular workload policy adjudication")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "seal"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--plan", required=True, type=Path)
        cmd.add_argument("--d71-report", required=True, type=Path)
        cmd.add_argument("--d72-report", required=True, type=Path)
        if name == "build":
            cmd.add_argument("--html", required=True, type=Path)
            cmd.add_argument("--template-json", required=True, type=Path)
            cmd.add_argument("--policy-json", required=True, type=Path)
        else:
            cmd.add_argument("--decision", required=True, type=Path)
            cmd.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    assert_offline_only()
    args = parse_args()
    plan, d71, d72 = _load(args.plan), _load(args.d71_report), _load(args.d72_report)
    validated, policy = validate_policy_inputs(plan, d71, d72)
    if args.command == "build":
        _private_write(args.html, build_html(validated, policy))
        _private_write_json(args.template_json, build_decision_template(validated, policy))
        _private_write_json(args.policy_json, policy)
        print("P0F7_9D731_POLICY_STATION_BUILT=YES")
        print(f"CANONICAL_ANNUAL_WORKLOAD={policy['canonical_annual_workload']}")
        print(f"CANONICAL_WEEKLY_WORKLOAD={policy['canonical_weekly_workload']}")
        print(f"MULTIGRADE_RULE={policy['multigrade_rule']}")
        print("WORKLOAD_HUMAN_CHOICE_REQUIRED=NO")
        print("PRODUCTION_ACCESS=NO")
        print("DATABASE_MUTATION=NO")
        print("PRODUCTION_WRITES=NO")
        return
    report = seal(plan, d71, d72, _load(args.decision))
    _private_write_json(args.json, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D731_ADJUDICATION_SEAL=PASS")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("EXECUTOR_AUTHORIZED=NO")


if __name__ == "__main__":
    main()
