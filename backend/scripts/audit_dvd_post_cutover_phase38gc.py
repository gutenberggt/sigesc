"""38G-C — auditoria pós-cutover DVD, estritamente READ-ONLY.

Valida cadeia criptográfica, persistência exata dos 228 vínculos, invariantes
estruturais, autorização funcional do proprietário, semântica REGULAR e colisões
de horário dos docentes afetados. Nenhuma escrita é feita no MongoDB.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts.apply_dvd_cutover_phase38g import (  # noqa: E402
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    DEFAULT_REFERENCE_DATE,
    _canonical_json,
    _core,
    _target_key,
    _verify_applied_docs,
    load_and_verify_backup,
)
from services.attendance_assignment_scope import (  # noqa: E402
    OFFICIAL_ATTENDANCE_COLLECTION,
    AttendanceAssignmentScopeError,
    resolve_attendance_assignment,
)
from services.diary_assignment_access import (  # noqa: E402
    DiaryAction,
    DiaryAssignmentAccessError,
    PEDAGOGICAL_OWNER_ROLES,
    authorize_assignment_access,
)
from services.diary_assignment_contract import (  # noqa: E402
    AttendanceMode,
    AttendancePurpose,
    DiaryProfile,
    StudentScope,
    is_class_in_scope,
)
from services.grade_assignment_scope import (  # noqa: E402
    GradeAssignmentScopeError,
    resolve_grade_assignment,
    resolve_own_grade_assignment,
)

load_dotenv(BACKEND_DIR / ".env")

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class PostCutoverAuditError(RuntimeError):
    pass


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    ]
    executable = "\n".join(executable_lines)
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise PostCutoverAuditError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def validate_receipt(path: Path, manifest_sha: str, backup_sha: str, count: int) -> dict[str, Any]:
    if not path.is_file():
        raise PostCutoverAuditError(f"APPLY_RECEIPT_MISSING path={path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    stored = str(doc.get("receipt_sha256") or "")
    payload = dict(doc)
    payload.pop("receipt_sha256", None)
    calculated = _sha256_value(payload)
    if stored != calculated:
        raise PostCutoverAuditError(f"APPLY_RECEIPT_HASH_MISMATCH stored={stored} calculated={calculated}")
    result = doc.get("result") or {}
    if doc.get("mode") != "APPLY" or result.get("state") not in {"applied", "already_applied"}:
        raise PostCutoverAuditError("APPLY_RECEIPT_MODE_OR_STATE_INVALID")
    if int(result.get("postcheck") or 0) != count:
        raise PostCutoverAuditError("APPLY_RECEIPT_POSTCHECK_MISMATCH")
    if result.get("state") == "applied" and int(result.get("inserted") or 0) != count:
        raise PostCutoverAuditError("APPLY_RECEIPT_INSERTED_MISMATCH")
    if str(doc.get("manifest_sha256") or "") != manifest_sha:
        raise PostCutoverAuditError("APPLY_RECEIPT_MANIFEST_HASH_MISMATCH")
    if str(doc.get("backup_bundle_sha256") or "") != backup_sha:
        raise PostCutoverAuditError("APPLY_RECEIPT_BACKUP_HASH_MISMATCH")
    if int(doc.get("expected_count") or 0) != count:
        raise PostCutoverAuditError("APPLY_RECEIPT_EXPECTED_COUNT_MISMATCH")
    return {"receipt_sha256": stored, "state": result.get("state"), "run_id": result.get("run_id")}


def validate_slots(doc: Mapping[str, Any]) -> None:
    slots = doc.get("weekly_slots")
    if not isinstance(slots, list) or not slots:
        raise PostCutoverAuditError(f"WEEKLY_SLOTS_INVALID id={doc.get('id')}")
    seen = set()
    for slot in slots:
        weekday = slot.get("weekday")
        aula = slot.get("aula_numero")
        start = str(slot.get("start_time") or "")
        end = str(slot.get("end_time") or "")
        if not isinstance(weekday, int) or not 1 <= weekday <= 7:
            raise PostCutoverAuditError(f"WEEKDAY_INVALID id={doc.get('id')} value={weekday}")
        if not isinstance(aula, int) or not 1 <= aula <= 12:
            raise PostCutoverAuditError(f"AULA_INVALID id={doc.get('id')} value={aula}")
        try:
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError as exc:
            raise PostCutoverAuditError(f"SLOT_TIME_INVALID id={doc.get('id')}") from exc
        if end <= start:
            raise PostCutoverAuditError(f"SLOT_RANGE_INVALID id={doc.get('id')}")
        key = (weekday, aula, start, end)
        if key in seen:
            raise PostCutoverAuditError(f"SLOT_DUPLICATE id={doc.get('id')} slot={key}")
        seen.add(key)


def periods_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    af, bf = str(a.get("valid_from") or ""), str(b.get("valid_from") or "")
    if not af or not bf:
        return False
    au, bu = str(a.get("valid_until") or "9999-12-31"), str(b.get("valid_until") or "9999-12-31")
    return max(af, bf) <= min(au, bu)


def slot_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if a.get("weekday") != b.get("weekday"):
        return False
    if a.get("aula_numero") == b.get("aula_numero"):
        return True
    return max(str(a.get("start_time") or ""), str(b.get("start_time") or "")) < min(
        str(a.get("end_time") or ""), str(b.get("end_time") or "")
    )


def schedule_collisions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_teacher: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("deleted") is not True and row.get("teacher_id"):
            by_teacher[str(row["teacher_id"])].append(row)
    collisions = []
    for teacher_id, items in by_teacher.items():
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if not periods_overlap(a, b):
                    continue
                if any(slot_overlap(sa, sb) for sa in (a.get("weekly_slots") or []) for sb in (b.get("weekly_slots") or [])):
                    collisions.append({
                        "teacher_id": teacher_id,
                        "assignment_a": a.get("id"), "class_a": a.get("class_id"), "component_a": a.get("component_id"),
                        "assignment_b": b.get("id"), "class_b": b.get("class_id"), "component_b": b.get("component_id"),
                    })
    return collisions


async def audit(db, args) -> dict[str, Any]:
    assert_script_read_only()
    backup = load_and_verify_backup(
        Path(args.backup_dir),
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_count=args.expected_count,
        expected_backup_sha256=args.expected_backup_sha256,
    )
    receipt = validate_receipt(Path(args.receipt), args.expected_manifest_sha256, args.expected_backup_sha256, args.expected_count)
    manifest = list(backup["manifest"])
    ids = [str(row["id"]) for row in manifest]
    id_set = set(ids)
    manifest_by_id = {str(row["id"]): row for row in manifest}

    persisted = await db.teacher_class_assignments.find({"id": {"$in": ids}}, {"_id": 0}).to_list(args.expected_count + 20)
    by_id = {str(row.get("id")): row for row in persisted if row.get("id")}
    if len(persisted) != args.expected_count or len(by_id) != args.expected_count or set(by_id) != id_set:
        raise PostCutoverAuditError(
            f"PERSISTED_SET_MISMATCH rows={len(persisted)} unique={len(by_id)} expected={args.expected_count}"
        )
    _verify_applied_docs(
        by_id,
        manifest,
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_backup_sha256=args.expected_backup_sha256,
    )

    phase_docs = await db.teacher_class_assignments.find(
        {
            "cutover_provenance.apply_phase": "38G-B",
            "cutover_provenance.manifest_sha256": args.expected_manifest_sha256,
            "cutover_provenance.backup_bundle_sha256": args.expected_backup_sha256,
        },
        {"_id": 0, "id": 1},
    ).to_list(args.expected_count + 100)
    phase_ids = {str(row.get("id") or "") for row in phase_docs}
    if len(phase_docs) != args.expected_count or phase_ids != id_set:
        raise PostCutoverAuditError(f"CUTOVER_PHASE_SCOPE_MISMATCH rows={len(phase_docs)}")

    expected_settings = {"enabled": True, "schema_version": 1, "profile": "regular", "student_scope": "all"}
    for assignment_id in ids:
        actual, proposed = by_id[assignment_id], manifest_by_id[assignment_id]
        if _canonical_json(_core(actual)) != _canonical_json(_core(proposed)):
            raise PostCutoverAuditError(f"CORE_MANIFEST_MISMATCH id={assignment_id}")
        if actual.get("deleted") is not False or actual.get("source") != "import" or actual.get("is_substitute") is not False:
            raise PostCutoverAuditError(f"STRUCTURAL_FLAGS_INVALID id={assignment_id}")
        if actual.get("valid_from") != args.reference_date or actual.get("valid_until") is not None:
            raise PostCutoverAuditError(f"VALIDITY_INVALID id={assignment_id}")
        if (actual.get("diary_settings") or {}) != expected_settings:
            raise PostCutoverAuditError(f"DIARY_SETTINGS_INVALID id={assignment_id}")
        validate_slots(actual)
    if len([_target_key(row) for row in persisted]) != len(set(_target_key(row) for row in persisted)):
        raise PostCutoverAuditError("PERSISTED_TARGET_KEY_DUPLICATE")

    class_ids = sorted({str(row.get("class_id") or "") for row in manifest})
    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {"_id": 0, "id": 1, "school_id": 1, "mantenedora_id": 1, "education_level": 1,
         "nivel_ensino": 1, "grade_level": 1, "grade": 1, "atendimento_programa": 1, "shift": 1},
    ).to_list(len(class_ids) + 20)
    classes_by_id = {str(row.get("id")): row for row in classes if row.get("id")}
    if len(classes_by_id) != len(class_ids):
        raise PostCutoverAuditError("CLASS_RESOLUTION_MISMATCH")
    for actual in persisted:
        klass = classes_by_id.get(str(actual.get("class_id") or ""))
        if not klass or not is_class_in_scope(klass):
            raise PostCutoverAuditError(f"CLASS_OUT_OF_SCOPE assignment={actual.get('id')}")
        if actual.get("school_id") != klass.get("school_id") or actual.get("mantenedora_id") != klass.get("mantenedora_id"):
            raise PostCutoverAuditError(f"CLASS_SCOPE_MISMATCH assignment={actual.get('id')}")

    teacher_ids = sorted({str(row.get("teacher_id") or "") for row in manifest})
    users = await db.users.find(
        {"id": {"$in": teacher_ids}},
        {"_id": 0, "id": 1, "role": 1, "school_ids": 1, "mantenedora_id": 1, "full_name": 1, "name": 1},
    ).to_list(len(teacher_ids) + 20)
    users_by_id = {str(row.get("id")): row for row in users if row.get("id")}
    if len(users_by_id) != len(teacher_ids):
        raise PostCutoverAuditError(f"TEACHER_USER_RESOLUTION_MISMATCH expected={len(teacher_ids)} actual={len(users_by_id)}")

    access_ok = attendance_ok = grade_ok = auto_grade_ok = 0
    for assignment_id in ids:
        assignment = by_id[assignment_id]
        user = users_by_id[str(assignment["teacher_id"])]
        if user.get("role") not in PEDAGOGICAL_OWNER_ROLES:
            raise PostCutoverAuditError(
                f"TEACHER_ROLE_NOT_PEDAGOGICAL assignment={assignment_id} role={user.get('role')}"
            )
        try:
            for action in (DiaryAction.VIEW, DiaryAction.CONTENT, DiaryAction.ATTENDANCE, DiaryAction.GRADES):
                context = await authorize_assignment_access(
                    db, user, assignment_id, action=action, on_date=args.reference_date,
                    expected_class_id=str(assignment["class_id"]),
                    expected_component_id=str(assignment["component_id"]),
                    active_mantenedora_id=user.get("mantenedora_id"),
                )
                if not context.is_owner or context.management_override:
                    raise PostCutoverAuditError(f"OWNER_CONTEXT_INVALID assignment={assignment_id}")
            access_ok += 1

            attendance = await resolve_attendance_assignment(
                db, user, assignment_id, class_id=str(assignment["class_id"]),
                on_date=args.reference_date, active_mantenedora_id=user.get("mantenedora_id"),
            )
            if (
                attendance.profile is not DiaryProfile.REGULAR
                or attendance.attendance_mode is not AttendanceMode.CLASS_DAILY
                or attendance.attendance_purpose is not AttendancePurpose.OFFICIAL
                or attendance.storage_collection != OFFICIAL_ATTENDANCE_COLLECTION
                or attendance.effective_course_id is not None
            ):
                raise PostCutoverAuditError(f"ATTENDANCE_SEMANTICS_INVALID assignment={assignment_id}")
            attendance_ok += 1

            course_id = str(assignment.get("component_id") or "")
            grade = await resolve_grade_assignment(
                db, user, assignment_id, class_id=str(assignment["class_id"]), course_id=course_id,
                on_date=args.reference_date, active_mantenedora_id=user.get("mantenedora_id"),
            )
            if grade.assignment_id != assignment_id:
                raise PostCutoverAuditError(f"GRADE_RESOLUTION_MISMATCH assignment={assignment_id}")
            grade_ok += 1

            own_grade = await resolve_own_grade_assignment(
                db, user, class_id=str(assignment["class_id"]), course_id=course_id,
                on_date=args.reference_date, active_mantenedora_id=user.get("mantenedora_id"),
            )
            if own_grade is None or own_grade.assignment_id != assignment_id:
                raise PostCutoverAuditError(f"AUTO_GRADE_RESOLUTION_MISMATCH assignment={assignment_id}")
            auto_grade_ok += 1
        except (DiaryAssignmentAccessError, AttendanceAssignmentScopeError, GradeAssignmentScopeError) as exc:
            raise PostCutoverAuditError(
                f"FUNCTIONAL_ACCESS_FAILURE assignment={assignment_id} code={getattr(exc, 'code', type(exc).__name__)} "
                f"message={getattr(exc, 'message', str(exc))}"
            ) from exc

    active_for_teachers = await db.teacher_class_assignments.find(
        {"teacher_id": {"$in": teacher_ids}, "deleted": {"$ne": True}}, {"_id": 0}
    ).to_list(50000)
    collisions = schedule_collisions(active_for_teachers)
    if collisions:
        raise PostCutoverAuditError(f"SCHEDULE_COLLISIONS count={len(collisions)} first={collisions[0]}")

    return {
        "status": "PASS",
        "mode": "38G_C_POST_CUTOVER_READ_ONLY",
        "expected": args.expected_count,
        "persisted": len(persisted),
        "unique_ids": len(by_id),
        "classes_in_scope": len(class_ids),
        "teachers_resolved": len(users_by_id),
        "owner_access_ok": access_ok,
        "attendance_scope_ok": attendance_ok,
        "grade_scope_ok": grade_ok,
        "auto_grade_resolution_ok": auto_grade_ok,
        "schedule_collisions": 0,
        "extra_38gb_docs": 0,
        "manifest_sha256": args.expected_manifest_sha256,
        "backup_bundle_sha256": args.expected_backup_sha256,
        "receipt_sha256": receipt["receipt_sha256"],
        "mongo_writes": 0,
    }


def print_compact(r: Mapping[str, Any]) -> None:
    print("=== DVD 38G-C — AUDITORIA POS-CUTOVER READ-ONLY ===")
    print("STATUS:", r["status"])
    print("ESPERADO:", r["expected"])
    print("PERSISTIDOS:", r["persisted"])
    print("UNIQUE_IDS:", r["unique_ids"])
    print("TURMAS_ESCOPO:", r["classes_in_scope"])
    print("PROFESSORES_RESOLVIDOS:", r["teachers_resolved"])
    print("OWNER_ACCESS_VIEW_CONTENT_ATTENDANCE_GRADES_OK:", f"{r['owner_access_ok']}/{r['expected']}")
    print("ATTENDANCE_REGULAR_CLASS_DAILY_OFFICIAL_OK:", f"{r['attendance_scope_ok']}/{r['expected']}")
    print("GRADE_SCOPE_OK:", f"{r['grade_scope_ok']}/{r['expected']}")
    print("AUTO_GRADE_RESOLUTION_OK:", f"{r['auto_grade_resolution_ok']}/{r['expected']}")
    print("SCHEDULE_COLLISIONS:", r["schedule_collisions"])
    print("EXTRA_38GB_DOCS:", r["extra_38gb_docs"])
    print("MANIFEST_SHA256:", r["manifest_sha256"])
    print("BACKUP_BUNDLE_SHA256:", r["backup_bundle_sha256"])
    print("APPLY_RECEIPT_SHA256:", r["receipt_sha256"])
    print("MONGO_WRITES: 0")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--expected-manifest-sha256", default=APPROVED_MANIFEST_SHA256)
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument("--expected-backup-sha256", default=APPROVED_BACKUP_BUNDLE_SHA256)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        report = await audit(client[os.environ["DB_NAME"]], args)
        print_compact(report)
        if args.json:
            path = Path(args.json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("REPORT_JSON:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
