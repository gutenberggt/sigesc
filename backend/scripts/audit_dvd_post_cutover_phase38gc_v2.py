"""38G-C v2 — auditoria pós-cutover DVD, estritamente READ-ONLY.

Corrige o contexto funcional do 38G-C original: para professores e demais
papéis escolares, reproduz o mesmo cálculo de role/school_ids do /auth/login,
com base em school_assignments ativos do ano de referência e fallback para
users.school_links. Nenhuma escrita é feita no MongoDB.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from pathlib import Path
import json
import os
import sys
from typing import Any, Mapping

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
from scripts.audit_dvd_post_cutover_phase38gc import (  # noqa: E402
    PostCutoverAuditError,
    assert_script_read_only as assert_original_script_read_only,
    schedule_collisions,
    validate_receipt,
    validate_slots,
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

LOTACAO_ROLES = frozenset({
    "professor", "secretario", "coordenador", "auxiliar_secretaria", "diretor"
})

FUNCAO_PRIORITY = {
    "diretor": 5,
    "coordenador": 4,
    "auxiliar_secretaria": 4,
    "secretario": 3,
    "professor": 2,
    "auxiliar": 1,
}


def assert_this_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    ]
    executable = "\n".join(executable_lines)
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise PostCutoverAuditError(f"READ_ONLY_GUARD_FAILED_V2 forbidden={forbidden}")


def _school_ids_from_links(links: Any) -> list[str]:
    result: list[str] = []
    for link in links or []:
        if isinstance(link, Mapping):
            school_id = link.get("school_id")
        else:
            school_id = getattr(link, "school_id", None)
        if school_id:
            result.append(str(school_id))
    return result


async def resolve_effective_login_users(
    db,
    *,
    teacher_ids: list[str],
    academic_year: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Reproduz o escopo efetivo do /auth/login para os usuários auditados."""
    users = await db.users.find(
        {"id": {"$in": teacher_ids}},
        {
            "_id": 0,
            "id": 1,
            "email": 1,
            "role": 1,
            "school_links": 1,
            "mantenedora_id": 1,
            "full_name": 1,
            "name": 1,
            "status": 1,
        },
    ).to_list(len(teacher_ids) + 20)
    raw_by_id = {str(row.get("id")): row for row in users if row.get("id")}
    if len(raw_by_id) != len(teacher_ids):
        raise PostCutoverAuditError(
            f"TEACHER_USER_RESOLUTION_MISMATCH expected={len(teacher_ids)} actual={len(raw_by_id)}"
        )

    emails = sorted({
        str(row.get("email") or "")
        for row in users
        if str(row.get("email") or "")
    })
    staff_docs = await db.staff.find(
        {"email": {"$in": emails}},
        {"_id": 0, "id": 1, "email": 1},
    ).to_list(len(emails) + 20) if emails else []
    staff_by_email = {
        str(row.get("email") or ""): row
        for row in staff_docs
        if row.get("email")
    }
    staff_ids = sorted({str(row.get("id")) for row in staff_docs if row.get("id")})

    lotacoes = await db.school_assignments.find(
        {
            "staff_id": {"$in": staff_ids},
            "status": "ativo",
            # Deliberadamente numérico: é exatamente o filtro do /auth/login.
            "academic_year": academic_year,
        },
        {"_id": 0, "staff_id": 1, "school_id": 1, "funcao": 1},
    ).to_list(max(100, len(staff_ids) * 20)) if staff_ids else []

    lotacoes_by_staff: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lot in lotacoes:
        if lot.get("staff_id"):
            lotacoes_by_staff[str(lot["staff_id"])].append(dict(lot))

    effective: dict[str, dict[str, Any]] = {}
    metrics = {
        "users_with_lotacao_scope": 0,
        "users_with_school_links_fallback": 0,
        "users_without_school_scope": 0,
        "effective_role_changed": 0,
    }

    for user_id, raw in raw_by_id.items():
        base_role = str(raw.get("role") or "")
        effective_role = base_role
        effective_links = list(raw.get("school_links") or [])
        used_lotacao = False

        if base_role in LOTACAO_ROLES:
            staff = staff_by_email.get(str(raw.get("email") or ""))
            lots = lotacoes_by_staff.get(str((staff or {}).get("id") or ""), [])
            if lots:
                used_lotacao = True
                highest_priority = FUNCAO_PRIORITY.get(base_role, 0)
                highest_role = base_role
                rebuilt_links = []
                for lot in lots:
                    funcao = str(lot.get("funcao") or "").lower()
                    priority = FUNCAO_PRIORITY.get(funcao, 0)
                    if priority > highest_priority:
                        highest_priority = priority
                        highest_role = funcao
                    rebuilt_links.append({
                        "school_id": lot.get("school_id"),
                        "role": funcao,
                    })
                effective_role = highest_role
                effective_links = rebuilt_links

        school_ids = _school_ids_from_links(effective_links)
        if used_lotacao:
            metrics["users_with_lotacao_scope"] += 1
        elif school_ids:
            metrics["users_with_school_links_fallback"] += 1
        else:
            metrics["users_without_school_scope"] += 1
        if effective_role != base_role:
            metrics["effective_role_changed"] += 1

        effective[user_id] = {
            "id": user_id,
            "email": raw.get("email"),
            "role": effective_role,
            "base_role": base_role,
            "school_ids": school_ids,
            "mantenedora_id": raw.get("mantenedora_id"),
            "full_name": raw.get("full_name") or raw.get("name"),
            "status": raw.get("status"),
        }

    return effective, metrics


async def audit(db, args) -> dict[str, Any]:
    assert_original_script_read_only()
    assert_this_script_read_only()

    backup = load_and_verify_backup(
        Path(args.backup_dir),
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_count=args.expected_count,
        expected_backup_sha256=args.expected_backup_sha256,
    )
    receipt = validate_receipt(
        Path(args.receipt),
        args.expected_manifest_sha256,
        args.expected_backup_sha256,
        args.expected_count,
    )
    manifest = list(backup["manifest"])
    ids = [str(row["id"]) for row in manifest]
    id_set = set(ids)
    manifest_by_id = {str(row["id"]): row for row in manifest}

    persisted = await db.teacher_class_assignments.find(
        {"id": {"$in": ids}}, {"_id": 0}
    ).to_list(args.expected_count + 20)
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

    expected_settings = {
        "enabled": True,
        "schema_version": 1,
        "profile": "regular",
        "student_scope": "all",
    }
    for assignment_id in ids:
        actual = by_id[assignment_id]
        proposed = manifest_by_id[assignment_id]
        if _canonical_json(_core(actual)) != _canonical_json(_core(proposed)):
            raise PostCutoverAuditError(f"CORE_MANIFEST_MISMATCH id={assignment_id}")
        if actual.get("deleted") is not False or actual.get("source") != "import" or actual.get("is_substitute") is not False:
            raise PostCutoverAuditError(f"STRUCTURAL_FLAGS_INVALID id={assignment_id}")
        if actual.get("valid_from") != args.reference_date or actual.get("valid_until") is not None:
            raise PostCutoverAuditError(f"VALIDITY_INVALID id={assignment_id}")
        if (actual.get("diary_settings") or {}) != expected_settings:
            raise PostCutoverAuditError(f"DIARY_SETTINGS_INVALID id={assignment_id}")
        validate_slots(actual)

    target_keys = [_target_key(row) for row in persisted]
    if len(target_keys) != len(set(target_keys)):
        raise PostCutoverAuditError("PERSISTED_TARGET_KEY_DUPLICATE")

    class_ids = sorted({str(row.get("class_id") or "") for row in manifest})
    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "education_level": 1,
            "nivel_ensino": 1,
            "grade_level": 1,
            "grade": 1,
            "atendimento_programa": 1,
            "shift": 1,
        },
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
    users_by_id, login_metrics = await resolve_effective_login_users(
        db,
        teacher_ids=teacher_ids,
        academic_year=int(args.reference_date[:4]),
    )

    access_ok = attendance_ok = grade_ok = auto_grade_ok = 0
    for assignment_id in ids:
        assignment = by_id[assignment_id]
        user = users_by_id[str(assignment["teacher_id"])]
        if user.get("role") not in PEDAGOGICAL_OWNER_ROLES:
            raise PostCutoverAuditError(
                "TEACHER_ROLE_NOT_PEDAGOGICAL "
                f"assignment={assignment_id} user={user.get('id')} "
                f"base_role={user.get('base_role')} effective_role={user.get('role')}"
            )
        if str(assignment.get("school_id") or "") not in set(user.get("school_ids") or []):
            raise PostCutoverAuditError(
                "LOGIN_SCHOOL_SCOPE_MISMATCH "
                f"assignment={assignment_id} teacher_id={user.get('id')} "
                f"assignment_school={assignment.get('school_id')} school_ids={user.get('school_ids')}"
            )

        try:
            for action in (
                DiaryAction.VIEW,
                DiaryAction.CONTENT,
                DiaryAction.ATTENDANCE,
                DiaryAction.GRADES,
            ):
                context = await authorize_assignment_access(
                    db,
                    user,
                    assignment_id,
                    action=action,
                    on_date=args.reference_date,
                    expected_class_id=str(assignment["class_id"]),
                    expected_component_id=str(assignment["component_id"]),
                    active_mantenedora_id=user.get("mantenedora_id"),
                )
                if not context.is_owner or context.management_override:
                    raise PostCutoverAuditError(f"OWNER_CONTEXT_INVALID assignment={assignment_id}")
            access_ok += 1

            attendance = await resolve_attendance_assignment(
                db,
                user,
                assignment_id,
                class_id=str(assignment["class_id"]),
                on_date=args.reference_date,
                active_mantenedora_id=user.get("mantenedora_id"),
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
                db,
                user,
                assignment_id,
                class_id=str(assignment["class_id"]),
                course_id=course_id,
                on_date=args.reference_date,
                active_mantenedora_id=user.get("mantenedora_id"),
            )
            if grade.assignment_id != assignment_id:
                raise PostCutoverAuditError(f"GRADE_RESOLUTION_MISMATCH assignment={assignment_id}")
            grade_ok += 1

            own_grade = await resolve_own_grade_assignment(
                db,
                user,
                class_id=str(assignment["class_id"]),
                course_id=course_id,
                on_date=args.reference_date,
                active_mantenedora_id=user.get("mantenedora_id"),
            )
            if own_grade is None or own_grade.assignment_id != assignment_id:
                raise PostCutoverAuditError(f"AUTO_GRADE_RESOLUTION_MISMATCH assignment={assignment_id}")
            auto_grade_ok += 1
        except (DiaryAssignmentAccessError, AttendanceAssignmentScopeError, GradeAssignmentScopeError) as exc:
            raise PostCutoverAuditError(
                f"FUNCTIONAL_ACCESS_FAILURE assignment={assignment_id} "
                f"teacher_id={user.get('id')} effective_role={user.get('role')} "
                f"school_ids={user.get('school_ids')} "
                f"code={getattr(exc, 'code', type(exc).__name__)} "
                f"message={getattr(exc, 'message', str(exc))}"
            ) from exc

    active_for_teachers = await db.teacher_class_assignments.find(
        {"teacher_id": {"$in": teacher_ids}, "deleted": {"$ne": True}},
        {"_id": 0},
    ).to_list(50000)
    collisions = schedule_collisions(active_for_teachers)
    if collisions:
        raise PostCutoverAuditError(
            f"SCHEDULE_COLLISIONS count={len(collisions)} first={collisions[0]}"
        )

    return {
        "status": "PASS",
        "mode": "38G_C_V2_POST_CUTOVER_READ_ONLY",
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
        "effective_login_scope": login_metrics,
        "manifest_sha256": args.expected_manifest_sha256,
        "backup_bundle_sha256": args.expected_backup_sha256,
        "receipt_sha256": receipt["receipt_sha256"],
        "mongo_writes": 0,
    }


def print_compact(r: Mapping[str, Any]) -> None:
    print("=== DVD 38G-C v2 — AUDITORIA POS-CUTOVER READ-ONLY ===")
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
    print("USERS_WITH_LOTACAO_SCOPE:", r["effective_login_scope"]["users_with_lotacao_scope"])
    print("USERS_WITH_SCHOOL_LINKS_FALLBACK:", r["effective_login_scope"]["users_with_school_links_fallback"])
    print("USERS_WITHOUT_SCHOOL_SCOPE:", r["effective_login_scope"]["users_without_school_scope"])
    print("EFFECTIVE_ROLE_CHANGED:", r["effective_login_scope"]["effective_role_changed"])
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
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("REPORT_JSON:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
