#!/usr/bin/env python3
"""LUIZ-GOMES-F6.2 — linhagem histórica conclusiva, read-only.

Objetivo: adjudicar os conteúdos de Matemática de fev-abr/2026 de 8º A e 9º A
sem qualquer mutação. A fase cruza cinco fontes independentes:
1) proveniência global do ator Luiz em learning_objects, sem limitar turma/curso;
2) autoria explícita dos 209 registros candidatos encontrados na F6;
3) copied_from_id e digest criptográfico do payload pedagógico (plaintext nunca emitido);
4) audit_logs restritos a mudanças de course_id/class_id e nome/nível de courses;
5) cobertura de datas contra frequência de Matemática atribuível ao Luiz, sem records.

Acesso ao conteúdo pedagógico ocorre somente em memória para SHA-256 determinístico;
nenhum texto pedagógico é impresso, persistido ou incluído no artifact.
MongoDB é estritamente read-only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Luiz Gomes dos Santos"
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_COMPONENT = "Matemática"
TARGET_CLASSES = ("8º ANO A", "9º ANO A")
REFERENCE_CLASSES = ("6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B")
ALL_CLASSES = REFERENCE_CLASSES + TARGET_CLASSES
START_DATE = "2026-02-01"
END_DATE = "2026-05-01"
ACTIVE_STATUSES = {"ativo", "active"}
PEDAGOGICAL_FIELDS = ("content", "observations", "methodology", "resources", "number_of_classes")
ACTOR_FIELDS = ("recorded_by", "created_by", "updated_by", "teacher_id", "staff_id")

LEARNING_PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "course_id": 1,
    "component_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
    "copied_from_id": 1,
    "created_at": 1,
    "updated_at": 1,
    "mantenedora_id": 1,
    "content": 1,
    "observations": 1,
    "methodology": 1,
    "resources": 1,
    "number_of_classes": 1,
}
ATTENDANCE_PROJECTION = {
    "_id": 0,
    "class_id": 1,
    "course_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _fp(value: Any) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _date(value: Any) -> str | None:
    raw = _sid(value)[:10]
    return raw if re.fullmatch(r"2026-(0[2-4])-\d{2}", raw) else None


def _month(value: Any) -> str | None:
    day = _date(value)
    return day[5:7] if day else None


def _record_course_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


def _summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    dates = sorted({_date(row.get("date")) for row in values if _date(row.get("date"))})
    months = Counter(_month(row.get("date")) for row in values if _month(row.get("date")))
    return {
        "documents": len(values),
        "distinct_dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "months": {m: months.get(m, 0) for m in ("02", "03", "04")},
    }


def _teacher_attributed(row: Mapping[str, Any], actor_ids: set[str], assignment_ids: set[str]) -> bool:
    if any(_sid(row.get(field)) in actor_ids for field in ACTOR_FIELDS if _sid(row.get(field))):
        return True
    aid = _sid(row.get("assignment_id"))
    return bool(aid and aid in assignment_ids)


def _actor_category(row: Mapping[str, Any], actor_ids: set[str]) -> str:
    values = {_sid(row.get(field)) for field in ACTOR_FIELDS if _sid(row.get(field))}
    if values & actor_ids:
        return "LUIZ"
    if values:
        return "FOREIGN_ACTOR_PRESENT"
    return "NO_ACTOR_METADATA"


def _canon(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return value


def _payload_digest(row: Mapping[str, Any]) -> tuple[str | None, int]:
    payload = {field: _canon(row.get(field)) for field in PEDAGOGICAL_FIELDS}
    text_len = sum(len(v) for v in payload.values() if isinstance(v, str))
    if not any(v not in (None, "", [], {}) for v in payload.values()):
        return None, 0
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), text_len


def _resolve_teacher(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
    ).limit(20))
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_2_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    staff_rows = list(db.staff.find(
        {"user_id": _sid(user.get("id"))},
        {"_id": 0, "id": 1, "user_id": 1, "mantenedora_id": 1, "school_id": 1},
    ).limit(50))
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_F6_2_STAFF_NOT_FOUND")
    return user, staff_rows


def _resolve_school(db, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    matches = [
        row for row in db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1})
        if _norm(row.get("name")) == _norm(TARGET_SCHOOL)
    ]
    tenant_hints = {_sid(user.get("mantenedora_id")), *(_sid(r.get("mantenedora_id")) for r in staff_rows)}
    tenant_hints.discard("")
    if len(matches) > 1 and tenant_hints:
        matches = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_hints]
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_2_SCHOOL_MATCHES:{len(matches)}")
    return matches[0]


def _catalog(db, school_id: str, tenant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    classes = list(db.classes.find(
        {"school_id": school_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    classes = [r for r in classes if _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    class_by_id = {_sid(r.get("id")): r for r in classes if _sid(r.get("id"))}
    courses = list(db.courses.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1, "created_at": 1, "updated_at": 1},
    ))
    courses = [r for r in courses if _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    course_by_id = {_sid(r.get("id")): r for r in courses if _sid(r.get("id"))}
    return class_by_id, course_by_id


def _resolve_classes(class_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ALL_CLASSES:
        matches = [
            cid for cid, row in class_by_id.items()
            if _norm(row.get("name")) == _norm(name)
            and _sid(row.get("academic_year")) in {"", str(ACADEMIC_YEAR)}
        ]
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_2_CLASS_NOT_EXACT:{name}:{len(matches)}")
        out[name] = matches[0]
    return out


def _teacher_history(db, teacher_id: str, staff_ids: set[str], school_id: str, tenant_id: str):
    legacy = list(db.teacher_assignments.find(
        {"staff_id": {"$in": sorted(staff_ids)}, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1, "course_id": 1,
         "academic_year": 1, "status": 1, "mantenedora_id": 1, "created_at": 1, "updated_at": 1},
    ))
    legacy = [r for r in legacy if _sid(r.get("school_id")) in {"", school_id} and _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    dvd = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher_id},
        {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1, "component_id": 1, "course_id": 1,
         "school_id": 1, "mantenedora_id": 1, "valid_from": 1, "valid_until": 1, "deleted": 1},
    ))
    dvd = [r for r in dvd if _sid(r.get("school_id")) in {"", school_id} and _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    assignment_ids = {_sid(r.get("id")) for r in legacy + dvd if _sid(r.get("id"))}
    return legacy, dvd, assignment_ids


def _resolve_current_math(class_id: str, legacy: list[Mapping[str, Any]], course_by_id: Mapping[str, Mapping[str, Any]]) -> str:
    ids = []
    for row in legacy:
        if _sid(row.get("class_id")) != class_id or _norm(row.get("status")) not in ACTIVE_STATUSES:
            continue
        cid = _sid(row.get("course_id"))
        if cid and _norm((course_by_id.get(cid) or {}).get("name")) == _norm(TARGET_COMPONENT):
            ids.append(cid)
    unique = sorted(set(ids))
    if len(unique) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_2_CURRENT_MATH_NOT_EXACT:{_fp(class_id)}:{len(unique)}")
    return unique[0]


def _course_name_at_date(course_id: str, row_date: str, current_name: str, logs: list[Mapping[str, Any]]) -> tuple[str, bool]:
    relevant = []
    for log in logs:
        if _sid(log.get("document_id")) != course_id:
            continue
        changes = log.get("changes") or {}
        name_change = changes.get("name") if isinstance(changes, Mapping) else None
        if not isinstance(name_change, Mapping):
            continue
        ts = _sid(log.get("timestamp") or log.get("timestamp_utc"))[:10]
        if ts:
            relevant.append((ts, _sid(name_change.get("old")), _sid(name_change.get("new"))))
    inferred = current_name
    evidence = False
    for ts, old, new in sorted(relevant, reverse=True):
        if ts > row_date and new and _norm(inferred) == _norm(new):
            inferred = old or inferred
            evidence = True
    return inferred, evidence


def _audit_transition_to_math(row_id: str, candidate_course: str, current_math: str, logs: list[Mapping[str, Any]]) -> bool:
    for log in logs:
        if _sid(log.get("document_id")) != row_id:
            continue
        changes = log.get("changes") or {}
        cc = changes.get("course_id") if isinstance(changes, Mapping) else None
        if isinstance(cc, Mapping):
            old, new = _sid(cc.get("old")), _sid(cc.get("new"))
            if {old, new} == {candidate_course, current_math}:
                return True
        old = _sid((log.get("old_value") or {}).get("course_id"))
        new = _sid((log.get("new_value") or {}).get("course_id"))
        if {old, new} == {candidate_course, current_math}:
            return True
    return False


def _group_global_actor_rows(rows: list[Mapping[str, Any]], class_by_id, course_by_id) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(_sid(row.get("class_id")), _record_course_id(row))].append(row)
    result = []
    for (class_id, course_id), values in grouped.items():
        klass = class_by_id.get(class_id) or {}
        course = course_by_id.get(course_id) or {}
        result.append({
            "class_name": _sid(klass.get("name")) or "<unresolved>",
            "course_name": _sid(course.get("name")) or "<unresolved>",
            "class_fingerprint": _fp(class_id),
            "course_fingerprint": _fp(course_id),
            "summary": _summary(values),
        })
    return sorted(result, key=lambda r: (r["class_name"], r["course_name"]))


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_F6_2_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    user, staff_rows = _resolve_teacher(db)
    teacher_id = _sid(user.get("id"))
    staff_ids = {_sid(r.get("id")) for r in staff_rows if _sid(r.get("id"))}
    actor_ids = {teacher_id, *staff_ids}
    actor_ids.discard("")
    school = _resolve_school(db, user, staff_rows)
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))
    class_by_id, course_by_id = _catalog(db, school_id, tenant_id)
    class_ids = _resolve_classes(class_by_id)
    legacy, dvd, assignment_ids = _teacher_history(db, teacher_id, staff_ids, school_id, tenant_id)
    current_math = {name: _resolve_current_math(cid, legacy, course_by_id) for name, cid in class_ids.items()}

    all_six_rows = list(db.learning_objects.find(
        {"class_id": {"$in": list(class_ids.values())}, "date": {"$gte": START_DATE, "$lt": END_DATE}},
        LEARNING_PROJECTION,
    ))
    id_index = {_sid(r.get("id")): r for r in all_six_rows if _sid(r.get("id"))}

    # Proveniência global do Luiz, independentemente de turma/componente.
    global_actor_rows = list(db.learning_objects.find(
        {
            "date": {"$gte": START_DATE, "$lt": END_DATE},
            "$or": [{field: {"$in": sorted(actor_ids)}} for field in ACTOR_FIELDS],
        },
        LEARNING_PROJECTION,
    ))

    known_math_rows = []
    for row in all_six_rows:
        class_name = next((name for name, cid in class_ids.items() if cid == _sid(row.get("class_id"))), None)
        if class_name not in REFERENCE_CLASSES:
            continue
        if _record_course_id(row) != current_math[class_name]:
            continue
        if _teacher_attributed(row, actor_ids, assignment_ids):
            known_math_rows.append(row)

    target_candidates = []
    for row in all_six_rows:
        class_name = next((name for name, cid in class_ids.items() if cid == _sid(row.get("class_id"))), None)
        if class_name not in TARGET_CLASSES:
            continue
        if _record_course_id(row) == current_math[class_name]:
            continue
        target_candidates.append(row)

    parent_ids = {_sid(r.get("copied_from_id")) for r in target_candidates if _sid(r.get("copied_from_id"))}
    missing_parent_ids = sorted(pid for pid in parent_ids if pid not in id_index)
    if missing_parent_ids:
        parents = list(db.learning_objects.find({"id": {"$in": missing_parent_ids}}, LEARNING_PROJECTION))
        id_index.update({_sid(r.get("id")): r for r in parents if _sid(r.get("id"))})
    candidate_ids = {_sid(r.get("id")) for r in target_candidates if _sid(r.get("id"))}
    reverse_children = list(db.learning_objects.find({"copied_from_id": {"$in": sorted(candidate_ids)}}, LEARNING_PROJECTION)) if candidate_ids else []

    # Audit logs: somente metadados de identidade, nunca conteúdo pedagógico.
    course_ids = sorted({_record_course_id(r) for r in target_candidates if _record_course_id(r)} | set(current_math.values()))
    course_logs = list(db.audit_logs.find(
        {"collection": "courses", "document_id": {"$in": course_ids}},
        {"_id": 0, "document_id": 1, "action": 1, "timestamp": 1, "timestamp_utc": 1,
         "changes.name": 1, "changes.nivel_ensino": 1, "old_value.name": 1, "new_value.name": 1,
         "old_value.nivel_ensino": 1, "new_value.nivel_ensino": 1},
    )) if course_ids else []
    learning_logs = list(db.audit_logs.find(
        {"collection": "learning_objects", "document_id": {"$in": sorted(candidate_ids)}},
        {"_id": 0, "document_id": 1, "action": 1, "timestamp": 1, "timestamp_utc": 1,
         "changes.course_id": 1, "changes.class_id": 1,
         "old_value.course_id": 1, "new_value.course_id": 1,
         "old_value.class_id": 1, "new_value.class_id": 1,
         "old_value.date": 1, "new_value.date": 1},
    )) if candidate_ids else []

    # Índices de digest. O plaintext não sai deste processo.
    digest_to_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in all_six_rows:
        digest, _ = _payload_digest(row)
        if digest:
            digest_to_rows[digest].append(row)
    known_math_ids = {_sid(r.get("id")) for r in known_math_rows if _sid(r.get("id"))}
    known_math_digest_classes: dict[str, set[str]] = defaultdict(set)
    for row in known_math_rows:
        digest, _ = _payload_digest(row)
        if digest:
            known_math_digest_classes[digest].add(_sid(row.get("class_id")))

    reverse_by_parent: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in reverse_children:
        reverse_by_parent[_sid(row.get("copied_from_id"))].append(row)

    # Frequência Matemática por alvo, metadata-only.
    attendance_dates: dict[str, set[str]] = {}
    for class_name in TARGET_CLASSES:
        cid = class_ids[class_name]
        rows = list(db.attendance.find(
            {"class_id": cid, "course_id": current_math[class_name], "date": {"$gte": START_DATE, "$lt": END_DATE}},
            ATTENDANCE_PROJECTION,
        ))
        rows = [r for r in rows if _teacher_attributed(r, actor_ids, assignment_ids)]
        attendance_dates[class_name] = {_date(r.get("date")) for r in rows if _date(r.get("date"))}

    targets = []
    overall_codes = Counter()
    for class_name in TARGET_CLASSES:
        cid = class_ids[class_name]
        math_id = current_math[class_name]
        rows = [r for r in target_candidates if _sid(r.get("class_id")) == cid]
        actor_counts = Counter(_actor_category(r, actor_ids) for r in rows)
        confirmed = []
        evidence_counts = Counter()
        for row in rows:
            rid = _sid(row.get("id"))
            course_id = _record_course_id(row)
            row_date = _date(row.get("date")) or ""
            course = course_by_id.get(course_id) or {}
            digest, text_len = _payload_digest(row)

            direct_luiz = _actor_category(row, actor_ids) == "LUIZ"
            parent = id_index.get(_sid(row.get("copied_from_id")))
            copy_to_known_math = bool(parent and _sid(parent.get("id")) in known_math_ids)
            copy_from_candidate_to_known_math = any(_sid(ch.get("id")) in known_math_ids for ch in reverse_by_parent.get(rid, []))
            audit_transition = _audit_transition_to_math(rid, course_id, math_id, learning_logs)
            inferred_name, name_evidence = _course_name_at_date(course_id, row_date, _sid(course.get("name")), course_logs)
            historical_name_math = bool(name_evidence and _norm(inferred_name) == _norm(TARGET_COMPONENT))

            strong_digest = False
            if digest and text_len >= 24 and len(known_math_digest_classes.get(digest, set())) >= 2:
                external_nonmath = []
                for peer in digest_to_rows.get(digest, []):
                    peer_class = _sid(peer.get("class_id"))
                    peer_course = _record_course_id(peer)
                    peer_name = next((n for n, pcid in class_ids.items() if pcid == peer_class), None)
                    if peer_name in TARGET_CLASSES and peer_course != current_math[peer_name]:
                        continue
                    if peer_name in REFERENCE_CLASSES and peer_course == current_math[peer_name]:
                        continue
                    external_nonmath.append(peer)
                strong_digest = not external_nonmath

            flags = {
                "DIRECT_LUIZ_ACTOR": direct_luiz,
                "COPY_LINEAGE_TO_KNOWN_MATH": copy_to_known_math or copy_from_candidate_to_known_math,
                "AUDIT_COURSE_ID_TRANSITION_WITH_MATH": audit_transition,
                "CATALOG_NAME_RECONSTRUCTS_TO_MATH": historical_name_math,
                "STRONG_DIGEST_MATCHES_MATH_IN_2PLUS_REFERENCE_CLASSES": strong_digest,
            }
            for key, value in flags.items():
                if value:
                    evidence_counts[key] += 1
            is_confirmed = any(flags.values())
            if is_confirmed:
                confirmed.append({
                    "date": row_date,
                    "course_name_now": _sid(course.get("name")) or "<unresolved>",
                    "course_fingerprint": _fp(course_id),
                    "payload_digest_fingerprint": digest[:12] if digest else None,
                    "evidence": sorted(k for k, v in flags.items() if v),
                })

        confirmed_dates = [r["date"] for r in confirmed if r["date"]]
        date_counts = Counter(confirmed_dates)
        expected = attendance_dates[class_name]
        exact_one_per_expected = bool(expected) and set(confirmed_dates) == expected and all(date_counts[d] == 1 for d in expected)
        codes = []
        if exact_one_per_expected:
            codes.append("CONCLUSIVE_HISTORICAL_MATH_SET_IDENTIFIED")
        elif confirmed:
            codes.append("PARTIAL_HISTORICAL_MATH_SET_IDENTIFIED")
        else:
            codes.append("NO_CONCLUSIVE_HISTORICAL_MATH_MATCH")
        if actor_counts.get("LUIZ", 0):
            codes.append("DIRECT_LUIZ_MISBINDING_CONFIRMED")
        if actor_counts.get("FOREIGN_ACTOR_PRESENT", 0) == len(rows) and rows:
            codes.append("ALL_OTHER_COURSE_ROWS_HAVE_FOREIGN_ACTOR_METADATA")
        if not known_math_rows:
            codes.append("NO_REFERENCE_MATH_ROWS_ATTRIBUTED_TO_LUIZ")
        for code in codes:
            overall_codes[code] += 1
        targets.append({
            "class": class_name,
            "candidate_rows": len(rows),
            "actor_partition": dict(sorted(actor_counts.items())),
            "math_attendance_dates": len(expected),
            "confirmed_math_rows": len(confirmed),
            "confirmed_math_distinct_dates": len(set(confirmed_dates)),
            "full_attendance_date_coverage": exact_one_per_expected,
            "evidence_counts": dict(sorted(evidence_counts.items())),
            "classification": codes,
            "confirmed": sorted(confirmed, key=lambda r: (r["date"], r["course_name_now"])),
        })

    # Sinal global: Luiz encontrado fora das seis turmas/componente esperado.
    global_groups = _group_global_actor_rows(global_actor_rows, class_by_id, course_by_id)
    expected_pairs = {(class_ids[n], current_math[n]) for n in ALL_CLASSES}
    unexpected_global = [
        r for r in global_actor_rows
        if (_sid(r.get("class_id")), _record_course_id(r)) not in expected_pairs
    ]
    if unexpected_global:
        overall_codes["LUIZ_ATTRIBUTED_CONTENT_OUTSIDE_EXPECTED_MATH_PAIRS"] += 1

    return {
        "schema": "LUIZ_GOMES_F6_2_LINEAGE_CONTENT_DIGEST_READ_ONLY_V1",
        "status": "PASS",
        "academic_year": ACADEMIC_YEAR,
        "period": {"start": START_DATE, "end_exclusive": END_DATE},
        "teacher": TEACHER_NAME,
        "school": TARGET_SCHOOL,
        "reference_math_rows": len(known_math_rows),
        "global_luiz_attributed_learning_objects": _summary(global_actor_rows),
        "global_luiz_groups": global_groups,
        "unexpected_global_luiz_rows": _summary(unexpected_global),
        "course_audit_log_count": len(course_logs),
        "learning_object_identity_audit_log_count": len(learning_logs),
        "targets": targets,
        "summary": {"classification_counts": dict(sorted(overall_codes.items()))},
        "mongo_reads_only": True,
        "http_methods": [],
        "database_mutation": False,
        "production_writes": False,
        "attendance_records_read": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "pedagogical_plaintext_emitted": False,
        "pedagogical_payload_hashed_in_memory": True,
        "technical_ids_emitted": False,
    }


if __name__ == "__main__":
    print("LUIZ_GOMES_F6_2_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
