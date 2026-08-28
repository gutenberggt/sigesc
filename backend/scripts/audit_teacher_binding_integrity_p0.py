"""P0 Global — auditoria READ-ONLY de integridade Professor↔Turma↔Componente.

Cruza as representações concorrentes de vínculo docente e todas as referências
críticas a ``courses.id`` usadas por frequência, notas e conteúdos.

Não corrige, não migra e não infere vínculos. Casos ambíguos são classificados
para revisão, preservando a política fail-closed do SIGESC.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.course_reference_integrity import (  # noqa: E402
    COURSE_REFERENCE_SPECS,
    extract_reference_ids,
    reference_projection,
)

load_dotenv(BACKEND_DIR / ".env")

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _same_year(value: Any, year: int) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) == int(year)
    except (TypeError, ValueError):
        return False


def _active_temporal(row: Mapping[str, Any], reference_date: str) -> bool:
    if row.get("deleted") is True:
        return False
    valid_from = _norm(row.get("valid_from"))
    valid_until = _norm(row.get("valid_until"))
    if valid_from and valid_from > reference_date:
        return False
    if valid_until and valid_until < reference_date:
        return False
    return True


def _binding_key(staff_id: Any, class_id: Any, course_id: Any) -> Optional[tuple[str, str, str]]:
    staff = _norm(staff_id)
    klass = _norm(class_id)
    course = _norm(course_id)
    if not staff or not klass or not course:
        return None
    return staff, klass, course


def binding_state(present: set[str]) -> str:
    mapping = {
        frozenset({"legacy", "allocation", "dvd"}): "ALL_THREE_OK",
        frozenset({"legacy", "allocation"}): "LEGACY_AND_ALLOCATION_MISSING_DVD",
        frozenset({"legacy", "dvd"}): "LEGACY_AND_DVD_MISSING_ALLOCATION",
        frozenset({"allocation", "dvd"}): "ALLOCATION_AND_DVD_MISSING_LEGACY",
        frozenset({"legacy"}): "LEGACY_ONLY",
        frozenset({"allocation"}): "ALLOCATION_ONLY",
        frozenset({"dvd"}): "DVD_ONLY",
    }
    return mapping.get(frozenset(present), "UNKNOWN")


def build_identity_indexes(staff_rows: list[Mapping[str, Any]]) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, list[Mapping[str, Any]]]]:
    by_user_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_email: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in staff_rows:
        user_id = _norm(row.get("user_id"))
        email = _norm(row.get("email")).casefold()
        if user_id:
            by_user_id[user_id].append(row)
        if email:
            by_email[email].append(row)
    return by_user_id, by_email


def resolve_staff_identity(
    teacher_user_id: Any,
    *,
    user_by_id: Mapping[str, Mapping[str, Any]],
    staff_by_user_id: Mapping[str, list[Mapping[str, Any]]],
    staff_by_email: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[Optional[str], str]:
    """Resolve user→staff sem inferência por nome.

    Ordem: staff.user_id único; depois e-mail exato case-insensitive único.
    Ambiguidade ou ausência permanecem não resolvidas.
    """
    user_id = _norm(teacher_user_id)
    uid_matches = list(staff_by_user_id.get(user_id, []))
    if len(uid_matches) == 1:
        return _norm(uid_matches[0].get("id")) or None, "USER_ID"
    if len(uid_matches) > 1:
        return None, "AMBIGUOUS_USER_ID"

    user = user_by_id.get(user_id) or {}
    email = _norm(user.get("email")).casefold()
    email_matches = list(staff_by_email.get(email, [])) if email else []
    if len(email_matches) == 1:
        return _norm(email_matches[0].get("id")) or None, "EMAIL_FALLBACK"
    if len(email_matches) > 1:
        return None, "AMBIGUOUS_EMAIL"
    return None, "UNRESOLVED"


def _add_example(examples: dict[str, list[dict[str, Any]]], kind: str, item: dict[str, Any], limit: int) -> None:
    bucket = examples.setdefault(kind, [])
    if len(bucket) < limit:
        bucket.append(item)


async def _load_merge_provenance(db: Any) -> dict[str, str]:
    """Lê audit_logs antigos da consolidação e monta removed_id→kept_id."""
    result: dict[str, str] = {}
    cursor = db.audit_logs.find(
        {"collection": "courses", "extra_data.consolidated": {"$exists": True}},
        {"_id": 0, "extra_data.consolidated": 1},
    )
    async for row in cursor:
        consolidated = ((row.get("extra_data") or {}).get("consolidated") or [])
        for entry in consolidated:
            if not isinstance(entry, Mapping):
                continue
            kept = _norm(entry.get("kept_id"))
            for removed in entry.get("removed_ids") or []:
                removed_id = _norm(removed)
                if kept and removed_id:
                    result[removed_id] = kept
    return result


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    reference_date: str,
    mantenedora_id: Optional[str] = None,
    examples_limit: int = 50,
) -> dict[str, Any]:
    # Entidades de resolução.
    schools_query: dict[str, Any] = {}
    if mantenedora_id:
        schools_query["mantenedora_id"] = mantenedora_id
    schools = await db.schools.find(
        schools_query, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ).to_list(10000)
    school_by_id = {_norm(s.get("id")): s for s in schools if s.get("id")}
    school_ids = set(school_by_id)

    class_query: dict[str, Any] = {"academic_year": {"$in": [academic_year, str(academic_year)]}}
    if mantenedora_id:
        class_query["school_id"] = {"$in": sorted(school_ids)}
    classes = await db.classes.find(
        class_query,
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ).to_list(20000)
    class_by_id = {_norm(c.get("id")): c for c in classes if c.get("id")}
    class_ids = set(class_by_id)

    all_courses = await db.courses.find(
        {}, {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1}
    ).to_list(20000)
    course_by_id = {_norm(c.get("id")): c for c in all_courses if c.get("id")}
    merge_provenance = await _load_merge_provenance(db)

    users = await db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "mantenedora_id": 1}
    ).to_list(50000)
    user_by_id = {_norm(u.get("id")): u for u in users if u.get("id")}
    staff = await db.staff.find(
        {}, {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1, "full_name": 1, "mantenedora_id": 1}
    ).to_list(50000)
    staff_by_id = {_norm(s.get("id")): s for s in staff if s.get("id")}
    staff_by_user_id, staff_by_email = build_identity_indexes(staff)

    counters = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}

    # 1) Integridade de todas as referências a courses.id.
    for spec in COURSE_REFERENCE_SPECS:
        root = spec.field.split(".", 1)[0]
        cursor = db[spec.collection].find(
            {root: {"$exists": True}}, reference_projection(spec)
        )
        async for row in cursor:
            if not _same_year(row.get("academic_year"), academic_year):
                continue
            class_id = _norm(row.get("class_id"))
            if class_id:
                if class_id not in class_by_id:
                    # Se o documento declara explicitamente o ano alvo, ainda é útil
                    # para a auditoria; caso contrário pertence a outra turma/ano.
                    if row.get("academic_year") in (None, ""):
                        continue
                elif mantenedora_id:
                    klass = class_by_id[class_id]
                    school = school_by_id.get(_norm(klass.get("school_id")))
                    if not school or _norm(school.get("mantenedora_id")) != mantenedora_id:
                        continue
            elif mantenedora_id and _norm(row.get("mantenedora_id")) not in {"", mantenedora_id}:
                continue

            doc_tenant = _norm(row.get("mantenedora_id"))
            if not doc_tenant and class_id in class_by_id:
                klass = class_by_id[class_id]
                doc_tenant = _norm(klass.get("mantenedora_id"))
                if not doc_tenant:
                    school = school_by_id.get(_norm(klass.get("school_id")))
                    doc_tenant = _norm((school or {}).get("mantenedora_id"))

            for course_id in extract_reference_ids(row, spec.field):
                counters["COURSE_REFERENCES_AUDITED"] += 1
                course = course_by_id.get(course_id)
                if not course:
                    kind = "COURSE_MISSING_WITH_MERGE_PROVENANCE" if course_id in merge_provenance else "COURSE_MISSING"
                    counters[kind] += 1
                    _add_example(examples, kind, {
                        "collection": spec.collection,
                        "document_id": row.get("id"),
                        "class_id": row.get("class_id"),
                        "staff_id": row.get("staff_id"),
                        "teacher_id": row.get("teacher_id"),
                        "missing_course_id": course_id,
                        "canonical_candidate_id": merge_provenance.get(course_id),
                    }, examples_limit)
                    continue

                course_tenant = _norm(course.get("mantenedora_id"))
                if doc_tenant and course_tenant and doc_tenant != course_tenant:
                    counters["COURSE_TENANT_MISMATCH"] += 1
                    _add_example(examples, "COURSE_TENANT_MISMATCH", {
                        "collection": spec.collection,
                        "document_id": row.get("id"),
                        "course_id": course_id,
                        "document_mantenedora_id": doc_tenant,
                        "course_mantenedora_id": course_tenant,
                    }, examples_limit)

    # 2) Duplicidade nominal dentro do mesmo tenant (diagnóstico, nunca remapeia).
    duplicate_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for course in all_courses:
        tenant = _norm(course.get("mantenedora_id"))
        if mantenedora_id and tenant != mantenedora_id:
            continue
        key = (tenant, _norm(course.get("name")).casefold(), _norm(course.get("nivel_ensino")).casefold())
        duplicate_groups[key].append(course)
    for key, rows in duplicate_groups.items():
        if key[1] and len(rows) > 1:
            counters["DUPLICATE_COURSE_IDENTITY"] += 1
            _add_example(examples, "DUPLICATE_COURSE_IDENTITY", {
                "mantenedora_id": key[0] or None,
                "name": rows[0].get("name"),
                "nivel_ensino": rows[0].get("nivel_ensino"),
                "course_ids": sorted(_norm(r.get("id")) for r in rows),
            }, examples_limit)

    # 3) Cruzamento das três fontes de vínculo docente.
    legacy_query: dict[str, Any] = {
        "academic_year": {"$in": [academic_year, str(academic_year)]},
        "status": "ativo",
    }
    allocation_query = dict(legacy_query)
    if mantenedora_id:
        legacy_query["class_id"] = {"$in": sorted(class_ids)}
        allocation_query["class_id"] = {"$in": sorted(class_ids)}

    legacy = await db.teacher_assignments.find(
        legacy_query,
        {"_id": 0, "id": 1, "staff_id": 1, "class_id": 1, "course_id": 1, "mantenedora_id": 1},
    ).to_list(50000)
    allocations = await db.teacher_allocations.find(
        allocation_query,
        {"_id": 0, "id": 1, "staff_id": 1, "class_id": 1, "course_id": 1, "mantenedora_id": 1},
    ).to_list(50000)
    dvd_query: dict[str, Any] = {"deleted": {"$ne": True}, "class_id": {"$in": sorted(class_ids)}}
    dvd_rows = await db.teacher_class_assignments.find(
        dvd_query,
        {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1, "component_id": 1,
         "valid_from": 1, "valid_until": 1, "school_id": 1, "diary_settings": 1},
    ).to_list(50000)

    source_keys: dict[str, Counter[tuple[str, str, str]]] = {
        "legacy": Counter(), "allocation": Counter(), "dvd": Counter()
    }

    for row in legacy:
        key = _binding_key(row.get("staff_id"), row.get("class_id"), row.get("course_id"))
        if key:
            source_keys["legacy"][key] += 1

    for row in allocations:
        key = _binding_key(row.get("staff_id"), row.get("class_id"), row.get("course_id"))
        if key:
            source_keys["allocation"][key] += 1

    identity_resolution_counts = Counter()
    for row in dvd_rows:
        if not _active_temporal(row, reference_date):
            continue
        teacher_id = _norm(row.get("teacher_id"))
        staff_id, resolution = resolve_staff_identity(
            teacher_id,
            user_by_id=user_by_id,
            staff_by_user_id=staff_by_user_id,
            staff_by_email=staff_by_email,
        )
        identity_resolution_counts[resolution] += 1
        if not staff_id:
            counters["DVD_TEACHER_IDENTITY_UNRESOLVED"] += 1
            _add_example(examples, "DVD_TEACHER_IDENTITY_UNRESOLVED", {
                "assignment_id": row.get("id"),
                "teacher_id": teacher_id,
                "class_id": row.get("class_id"),
                "component_id": row.get("component_id"),
                "resolution": resolution,
            }, examples_limit)
            continue
        if not _norm(row.get("component_id")):
            counters["DVD_CLASS_WIDE_ASSIGNMENT"] += 1
            continue
        key = _binding_key(staff_id, row.get("class_id"), row.get("component_id"))
        if key:
            source_keys["dvd"][key] += 1

    for source, key_counts in source_keys.items():
        for key, count in key_counts.items():
            if count > 1:
                counters[f"DUPLICATE_BINDING_{source.upper()}"] += 1
                _add_example(examples, f"DUPLICATE_BINDING_{source.upper()}", {
                    "staff_id": key[0], "class_id": key[1], "course_id": key[2], "count": count
                }, examples_limit)

    all_keys = set().union(*(set(counter) for counter in source_keys.values()))
    binding_counts = Counter()
    for key in sorted(all_keys):
        present = {source for source, rows in source_keys.items() if key in rows}
        state = binding_state(present)
        binding_counts[state] += 1
        counters["BINDING_KEYS_AUDITED"] += 1
        if state != "ALL_THREE_OK":
            staff_row = staff_by_id.get(key[0]) or {}
            klass = class_by_id.get(key[1]) or {}
            course = course_by_id.get(key[2]) or {}
            _add_example(examples, state, {
                "staff_id": key[0],
                "teacher_name": staff_row.get("nome") or staff_row.get("full_name"),
                "class_id": key[1],
                "class_name": klass.get("name"),
                "course_id": key[2],
                "course_name": course.get("name"),
                "present_in": sorted(present),
                "course_exists": bool(course),
            }, examples_limit)

    risk_total = sum(
        count for name, count in counters.items()
        if name not in {"COURSE_REFERENCES_AUDITED", "BINDING_KEYS_AUDITED"}
    ) + sum(count for state, count in binding_counts.items() if state != "ALL_THREE_OK")

    return {
        "kind": "P0_GLOBAL_TEACHER_BINDING_INTEGRITY",
        "mode": "READ_ONLY",
        "academic_year": academic_year,
        "reference_date": reference_date,
        "mantenedora_id": mantenedora_id,
        "summary": {
            "schools_in_scope": len(schools),
            "classes_in_scope": len(classes),
            "courses_total": len(all_courses),
            "legacy_teacher_assignments": len(legacy),
            "teacher_allocations": len(allocations),
            "teacher_class_assignments_candidates": len(dvd_rows),
            "risk_signals_total": risk_total,
        },
        "counters": dict(sorted(counters.items())),
        "binding_state_counts": dict(sorted(binding_counts.items())),
        "identity_resolution_counts": dict(sorted(identity_resolution_counts.items())),
        "merge_provenance_entries": len(merge_provenance),
        "examples": examples,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="P0 Global READ-ONLY — vínculos docentes e componentes")
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--mantenedora-id", default=None)
    parser.add_argument("--examples-limit", type=int, default=50)
    parser.add_argument("--json", default=None, help="Arquivo opcional para preservar a evidência")
    args = parser.parse_args()

    assert_read_only()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        report = await collect_report(
            db,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            mantenedora_id=args.mantenedora_id,
            examples_limit=max(1, min(args.examples_limit, 500)),
        )
    finally:
        client.close()

    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(payload)
    if args.json:
        output = Path(args.json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
