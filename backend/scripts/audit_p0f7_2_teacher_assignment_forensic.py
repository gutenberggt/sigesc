"""P0-F7.2 — forense READ-ONLY do blocker de teacher_assignments.

Valida P0-F5 -> P0-F6 -> P0-F7, localiza o grupo que possui
TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED e expande os pares divergentes de
teacher_assignments com contexto humano e proveniência segura. Não decide qual
registro prevalece e não altera o banco.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
P0F3_PATH = SCRIPT_DIR / "audit_duplicate_course_semantic_collision_p0f3.py"
P0F7_PATH = SCRIPT_DIR / "audit_p0f7_sealed_decisions_execution_preflight.py"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F7.2-TEACHER-ASSIGNMENT-FORENSIC-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

HUMAN_FIELD_LABELS = {
    "school_id": "Escola",
    "carga_horaria_semanal": "Carga horária semanal",
    "is_substituicao": "É substituição",
    "substituted_staff_id": "Professor substituído",
    "data_inicio_substituicao": "Início da substituição",
    "data_fim_substituicao": "Fim da substituição",
}


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"IMPORT_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _verify_embedded_sha(payload: Mapping[str, Any], field: str, label: str) -> str:
    stored = str(payload.get(field) or "")
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def validate_artifacts(
    packet: Mapping[str, Any], sealed: Mapping[str, Any], preflight: Mapping[str, Any],
    group_name: str,
) -> dict[str, Any]:
    p0f7 = _load_module(P0F7_PATH, "p0f7_contract_for_p0f7_2")
    chain = p0f7.validate_chain(packet, sealed)
    preflight_sha = _verify_embedded_sha(preflight, "manifest_sha256", "P0F7")
    if preflight.get("phase") != p0f7.PHASE_ID or preflight.get("status") != "PASS":
        raise ValueError("P0F7_CONTRACT_MISMATCH")
    if preflight.get("source_p0f5_manifest_sha256") != chain["packet_sha256"]:
        raise ValueError("P0F7_SOURCE_P0F5_SHA_MISMATCH")
    if preflight.get("source_p0f6_decision_manifest_sha256") != chain["sealed_manifest_sha256"]:
        raise ValueError("P0F7_SOURCE_P0F6_SHA_MISMATCH")
    safety = preflight.get("safety") or {}
    if safety.get("read_only") is not True or safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_SAFETY_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_EXECUTOR_AUTHORIZATION_INVALID")

    cases = [
        case for case in packet.get("cases") or []
        if str((case.get("identity") or {}).get("display_name") or "").casefold()
        == group_name.casefold()
    ]
    if len(cases) != 1:
        raise ValueError(f"GROUP_CASE_COUNT_INVALID:{len(cases)}")
    case = cases[0]
    source_id, target_id = str(case.get("source_id") or ""), str(case.get("target_id") or "")
    if not source_id or not target_id:
        raise ValueError("GROUP_SOURCE_TARGET_MISSING")

    blockers = [
        row for row in preflight.get("blockers") or []
        if row.get("reason") == "TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED"
        and str(row.get("group_name") or "").casefold() == group_name.casefold()
    ]
    if len(blockers) != 1:
        raise ValueError(f"TEACHER_BLOCKER_COUNT_INVALID:{len(blockers)}")
    blocker = blockers[0]
    expected_count = int(blocker.get("count") or 0)
    expected_classification = str(blocker.get("classification") or "")
    if expected_count <= 0 or not expected_classification:
        raise ValueError("TEACHER_BLOCKER_CONTRACT_INVALID")

    return {
        "p0f5_manifest_sha256": chain["packet_sha256"],
        "p0f6_decision_manifest_sha256": chain["sealed_manifest_sha256"],
        "p0f7_manifest_sha256": preflight_sha,
        "group_name": group_name,
        "mantenedora_id": (case.get("identity") or {}).get("mantenedora_id"),
        "source_id": source_id,
        "target_id": target_id,
        "expected_count": expected_count,
        "expected_classification": expected_classification,
    }


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _same_year(value: Any, academic_year: int) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) == int(academic_year)
    except (TypeError, ValueError):
        return False


def _active(value: Any) -> bool:
    return _norm(value).casefold() in {"ativo", "active"}


def _group_assignments(rows: list[Mapping[str, Any]]) -> dict[tuple[str, str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not _active(row.get("status")):
            continue
        key = (_norm(row.get("staff_id")), _norm(row.get("class_id")), _norm(row.get("academic_year")))
        grouped[key].append(row)
    return grouped


def build_divergent_pairs(
    source_rows: list[Mapping[str, Any]], target_rows: list[Mapping[str, Any]],
    p0f3: Any,
) -> list[dict[str, Any]]:
    smap, tmap = _group_assignments(source_rows), _group_assignments(target_rows)
    result: list[dict[str, Any]] = []
    for key in sorted(set(smap) & set(tmap)):
        srows, trows = smap[key], tmap[key]
        fields: list[str] = []
        if len(srows) != 1 or len(trows) != 1:
            classification = "MULTIPLICITY_REQUIRES_REVIEW"
        else:
            source, target = srows[0], trows[0]
            if source.get("is_substituicao") is True or target.get("is_substituicao") is True:
                classification = "SUBSTITUTION_COEXISTENCE_REQUIRES_REVIEW"
            else:
                cmp = p0f3.compare_sparse_fields(source, target, p0f3.TA_COMPARE_FIELDS)
                fields = cmp["conflicts"] + cmp["complementary"]
                classification = (
                    "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW"
                    if fields else "EXACT_ACTIVE_ASSIGNMENT_DUPLICATE"
                )
        if "REQUIRES_REVIEW" not in classification:
            continue
        result.append({
            "natural_key": {"staff_id": key[0], "class_id": key[1], "academic_year": key[2]},
            "classification": classification,
            "field_names": fields,
            "source_rows": [dict(row) for row in srows],
            "target_rows": [dict(row) for row in trows],
        })
    return result


def _safe_assignment_view(row: Mapping[str, Any], actor_names: Mapping[str, str]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "school_id": row.get("school_id"),
        "carga_horaria_semanal": row.get("carga_horaria_semanal"),
        "is_substituicao": row.get("is_substituicao"),
        "substituted_staff_id": row.get("substituted_staff_id"),
        "data_inicio_substituicao": row.get("data_inicio_substituicao"),
        "data_fim_substituicao": row.get("data_fim_substituicao"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "created_by": {
            "id": row.get("created_by"),
            "name": actor_names.get(_norm(row.get("created_by"))),
        } if row.get("created_by") else None,
        "updated_by": {
            "id": row.get("updated_by"),
            "name": actor_names.get(_norm(row.get("updated_by"))),
        } if row.get("updated_by") else None,
    }


def _audit_summary(events: list[Mapping[str, Any]], actor_names: Mapping[str, str]) -> dict[str, Any]:
    def ts(row: Mapping[str, Any]) -> str:
        return _norm(row.get("timestamp_utc") or row.get("timestamp"))
    ordered = sorted(events, key=ts)
    actions = Counter(_norm(row.get("action") or row.get("operation") or "unknown") for row in ordered)
    actors = []
    for row in ordered:
        actor_id = _norm(row.get("user_id") or ((row.get("user") or {}).get("id")))
        if actor_id and actor_id not in [a["id"] for a in actors]:
            actors.append({"id": actor_id, "name": actor_names.get(actor_id)})
    return {
        "event_count": len(ordered),
        "first_event_at": ts(ordered[0]) if ordered else None,
        "last_event_at": ts(ordered[-1]) if ordered else None,
        "action_counts": dict(sorted(actions.items())),
        "actors": actors,
    }


async def collect_report(
    db: Any, *, packet_path: Path, sealed_path: Path, preflight_path: Path,
    academic_year: int, group_name: str,
) -> dict[str, Any]:
    assert_read_only()
    packet, sealed, preflight = _load_json(packet_path), _load_json(sealed_path), _load_json(preflight_path)
    validation = validate_artifacts(packet, sealed, preflight, group_name)
    p0f3 = _load_module(P0F3_PATH, "p0f3_for_p0f7_2")
    p0f3.assert_read_only()

    pair_ids = [validation["source_id"], validation["target_id"]]
    query: dict[str, Any] = {"course_id": {"$in": pair_ids}}
    if validation.get("mantenedora_id"):
        query["mantenedora_id"] = validation["mantenedora_id"]
    rows = await db.teacher_assignments.find(query, {"_id": 0}).to_list(10000)
    rows = [row for row in rows if _same_year(row.get("academic_year"), academic_year)]
    source_rows = [row for row in rows if _norm(row.get("course_id")) == validation["source_id"]]
    target_rows = [row for row in rows if _norm(row.get("course_id")) == validation["target_id"]]
    pairs = build_divergent_pairs(source_rows, target_rows, p0f3)

    matching = [row for row in pairs if row["classification"] == validation["expected_classification"]]
    if len(matching) != validation["expected_count"]:
        raise RuntimeError(
            f"LIVE_TEACHER_BLOCKER_COUNT_MISMATCH:{len(matching)}!={validation['expected_count']}"
        )
    unexpected = [row for row in pairs if row["classification"] != validation["expected_classification"]]
    if unexpected:
        raise RuntimeError(f"UNEXPECTED_TEACHER_REVIEW_CLASSIFICATIONS:{len(unexpected)}")

    staff_ids: set[str] = set()
    class_ids: set[str] = set()
    assignment_ids: set[str] = set()
    actor_ids: set[str] = set()
    for pair in matching:
        staff_ids.add(pair["natural_key"]["staff_id"])
        class_ids.add(pair["natural_key"]["class_id"])
        for row in pair["source_rows"] + pair["target_rows"]:
            if _norm(row.get("id")):
                assignment_ids.add(_norm(row.get("id")))
            if _norm(row.get("substituted_staff_id")):
                staff_ids.add(_norm(row.get("substituted_staff_id")))
            for field in ("created_by", "updated_by"):
                if _norm(row.get(field)):
                    actor_ids.add(_norm(row.get(field)))

    staff_rows = await db.staff.find({"id": {"$in": sorted(staff_ids)}}, {"_id": 0, "id": 1, "nome": 1, "name": 1, "full_name": 1, "user_id": 1}).to_list(len(staff_ids) + 20)
    staff = {str(row.get("id")): row for row in staff_rows if row.get("id")}
    class_rows = await db.classes.find({"id": {"$in": sorted(class_ids)}}, {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1}).to_list(len(class_ids) + 20)
    classes = {str(row.get("id")): row for row in class_rows if row.get("id")}
    school_ids = {_norm(row.get("school_id")) for row in class_rows if _norm(row.get("school_id"))}
    school_rows = await db.schools.find({"id": {"$in": sorted(school_ids)}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(school_ids) + 20)
    schools = {str(row.get("id")): row for row in school_rows if row.get("id")}

    audit_rows = await db.audit_logs.find(
        {"collection": "teacher_assignments", "document_id": {"$in": sorted(assignment_ids)}},
        {"_id": 0, "document_id": 1, "action": 1, "operation": 1, "timestamp": 1, "timestamp_utc": 1, "user_id": 1, "user.id": 1},
    ).to_list(1000)
    for row in audit_rows:
        actor_id = _norm(row.get("user_id") or ((row.get("user") or {}).get("id")))
        if actor_id:
            actor_ids.add(actor_id)
    user_rows = await db.users.find({"id": {"$in": sorted(actor_ids)}}, {"_id": 0, "id": 1, "full_name": 1, "name": 1}).to_list(len(actor_ids) + 20)
    actor_names = {str(row.get("id")): str(row.get("full_name") or row.get("name") or "") for row in user_rows if row.get("id")}
    audit_by_doc: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in audit_rows:
        if _norm(row.get("document_id")):
            audit_by_doc[_norm(row.get("document_id"))].append(row)

    cases: list[dict[str, Any]] = []
    field_counts: Counter[str] = Counter()
    for index, pair in enumerate(matching, 1):
        key = pair["natural_key"]
        teacher = staff.get(key["staff_id"], {})
        class_row = classes.get(key["class_id"], {})
        school = schools.get(_norm(class_row.get("school_id")), {})
        source = pair["source_rows"][0]
        target = pair["target_rows"][0]
        fields = list(pair["field_names"])
        field_counts.update(fields)
        cases.append({
            "case_number": index,
            "classification": pair["classification"],
            "teacher": {"staff_id": key["staff_id"], "name": teacher.get("full_name") or teacher.get("nome") or teacher.get("name")},
            "class": {"class_id": key["class_id"], "name": class_row.get("name"), "academic_year": class_row.get("academic_year") or key["academic_year"]},
            "school": {"school_id": class_row.get("school_id"), "name": school.get("name")},
            "divergent_fields": fields,
            "divergent_field_labels": [HUMAN_FIELD_LABELS.get(field, field) for field in fields],
            "source_assignment": _safe_assignment_view(source, actor_names),
            "target_assignment": _safe_assignment_view(target, actor_names),
            "source_audit": _audit_summary(audit_by_doc.get(_norm(source.get("id")), []), actor_names),
            "target_audit": _audit_summary(audit_by_doc.get(_norm(target.get("id")), []), actor_names),
            "automatic_recommendation": False,
            "human_decision_required": True,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_TEACHER_ASSIGNMENT_FORENSIC",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "group_name": validation["group_name"],
        "source_course_id": validation["source_id"],
        "target_course_id": validation["target_id"],
        "source_p0f5_manifest_sha256": validation["p0f5_manifest_sha256"],
        "source_p0f6_decision_manifest_sha256": validation["p0f6_decision_manifest_sha256"],
        "source_p0f7_manifest_sha256": validation["p0f7_manifest_sha256"],
        "summary": {
            "expected_blocker_count": validation["expected_count"],
            "documented_cases": len(cases),
            "classification": validation["expected_classification"],
            "divergent_field_counts": dict(sorted(field_counts.items())),
            "complete_blocker_coverage": len(cases) == validation["expected_count"],
            "human_decisions_required": len(cases),
            "automatic_recommendation": False,
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "contains_student_data": False,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "automatic_remap": False,
            "automatic_merge": False,
            "automatic_delete": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": cases,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "group_name": report.get("group_name"),
        "summary": report.get("summary"),
        "cases": [
            {
                "case_number": row.get("case_number"),
                "teacher_name": (row.get("teacher") or {}).get("name"),
                "class_name": (row.get("class") or {}).get("name"),
                "school_name": (row.get("school") or {}).get("name"),
                "divergent_fields": row.get("divergent_fields"),
                "divergent_field_labels": row.get("divergent_field_labels"),
                "source_assignment": row.get("source_assignment"),
                "target_assignment": row.get("target_assignment"),
                "source_audit": row.get("source_audit"),
                "target_audit": row.get("target_audit"),
            }
            for row in report.get("cases") or []
        ],
        "manifest_sha256": report.get("manifest_sha256"),
        "student_data_printed": False,
        "automatic_recommendation": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.2 teacher assignment forensic read-only")
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--sealed", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--group-name", required=True)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    args = parse_args()
    mongo_url, db_name = os.getenv("MONGO_URL"), os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(
            client[db_name], packet_path=args.packet, sealed_path=args.sealed,
            preflight_path=args.preflight, academic_year=args.academic_year,
            group_name=args.group_name,
        )
    finally:
        client.close()
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
