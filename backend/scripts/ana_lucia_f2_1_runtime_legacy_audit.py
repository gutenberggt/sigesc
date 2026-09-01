#!/usr/bin/env python3
"""ANA-LUCIA-F2.1 — auditoria runtime legacy estritamente read-only.

Compara, para os 17 pares informados de Ana Lucia Faria Pinto/2026:
Mongo legado -> endpoints HTTP -> projeção que o frontend recebe.

Boundary:
- MongoDB somente leitura;
- HTTP somente GET;
- nenhum login; JWT efêmero criado em memória a partir de identidades existentes;
- nunca projeta/lê attendance.records;
- conteúdo pedagógico recebido por /learning-objects não é decodificado: apenas a
  cardinalidade estrutural do array JSON é contada em streaming;
- nenhum ID técnico, e-mail, PII de aluno ou texto pedagógico é emitido.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Ana Lucia Faria Pinto"
API_BASE = os.environ.get("ANA_LUCIA_F2_1_API_BASE", "http://127.0.0.1:8001/api").rstrip("/")
ACTIVE_STATUSES = ("ativo", "active")
TARGET_PAIRS: tuple[tuple[str, str], ...] = (
    ("6º ANO A", "Língua Inglesa"),
    ("6º ANO B", "Língua Inglesa"),
    ("6º ANO C", "Língua Inglesa"),
    ("6º ANO D", "Língua Inglesa"),
    ("9º ANO A", "Língua Inglesa"),
    ("9º ANO B", "Língua Inglesa"),
    ("9º ANO C", "Língua Inglesa"),
    ("9º ANO D", "Língua Inglesa"),
    ("3ª ETAPA", "Língua Inglesa"),
    ("4ª ETAPA", "Língua Inglesa"),
    ("6º ANO C", "Literatura e Redação"),
    ("6º ANO D", "Literatura e Redação"),
    ("7º ANO B", "Literatura e Redação"),
    ("7º ANO C", "Literatura e Redação"),
    ("9º ANO C", "Literatura e Redação"),
    ("7º ANO A", "Estudos Amazônicos"),
    ("8º ANO C", "Estudos Amazônicos"),
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _month(value: Any) -> int | None:
    raw = _sid(value)[:10]
    match = re.fullmatch(r"\d{4}-(\d{2})-\d{2}", raw)
    if not match:
        return None
    month = int(match.group(1))
    return month if 1 <= month <= 12 else None


def _year_scope() -> dict[str, Any]:
    return {
        "$or": [
            {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"date": {"$gte": f"{ACADEMIC_YEAR}-01-01", "$lte": f"{ACADEMIC_YEAR}-12-31"}},
        ]
    }


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1,
         "mantenedora_id": 1, "school_links": 1},
    ).limit(5))
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_1_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    if user.get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_1_TEACHER_ROLE:{user.get('role')}")

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    staff_rows = list(db.staff.find(
        {"$or": clauses},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
    ).limit(5))
    dedup = {_sid(row.get("id")): row for row in staff_rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_1_STAFF_MATCHES:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _management_identity(db) -> dict[str, Any]:
    rows = list(db.users.find(
        {"role": "super_admin"},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "mantenedora_id": 1},
    ).sort("id", 1).limit(1))
    if not rows:
        raise RuntimeError("ANA_LUCIA_F2_1_MANAGEMENT_IDENTITY_MISSING")
    return rows[0]


def _school_ids_for_professor(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> list[str]:
    rows = list(db.school_assignments.find(
        {"staff_id": staff["id"], "status": "ativo", "academic_year": ACADEMIC_YEAR},
        {"_id": 0, "school_id": 1},
    ))
    ids: list[str] = []
    for row in rows:
        value = _sid(row.get("school_id"))
        if value and value not in ids:
            ids.append(value)
    if ids:
        return ids
    for link in user.get("school_links") or []:
        if not isinstance(link, Mapping):
            continue
        value = _sid(link.get("school_id"))
        roles = link.get("roles") or ([link.get("role")] if link.get("role") else [])
        if value and (not roles or "professor" in roles) and value not in ids:
            ids.append(value)
    return ids


def _resolve_targets(db, staff: Mapping[str, Any]) -> list[dict[str, Any]]:
    legacy = list(db.teacher_assignments.find(
        {"staff_id": staff["id"], "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
         "status": {"$in": list(ACTIVE_STATUSES)}},
        {"_id": 0, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    class_ids = sorted({_sid(row.get("class_id")) for row in legacy if _sid(row.get("class_id"))})
    course_ids = sorted({_sid(row.get("course_id")) for row in legacy if _sid(row.get("course_id"))})
    classes = {
        _sid(row.get("id")): row
        for row in db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1,
             "academic_year": 1, "education_level": 1, "nivel_ensino": 1, "grade_level": 1},
        )
    }
    course_docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ):
        course_docs[_sid(row.get("id"))].append(row)
    school_ids = sorted({_sid(row.get("school_id")) for row in classes.values() if _sid(row.get("school_id"))})
    schools = {
        _sid(row.get("id")): row
        for row in db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
        )
    }

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for class_name, component_name in TARGET_PAIRS:
        candidates = []
        for assignment in legacy:
            class_id = _sid(assignment.get("class_id"))
            course_id = _sid(assignment.get("course_id"))
            class_doc = classes.get(class_id) or {}
            if _norm(class_doc.get("name")) != _norm(class_name):
                continue
            tenant_id = _sid(class_doc.get("mantenedora_id"))
            docs = course_docs.get(course_id) or []
            tenant_docs = [row for row in docs if not _sid(row.get("mantenedora_id")) or _sid(row.get("mantenedora_id")) == tenant_id]
            names = {_norm(row.get("name")) for row in (tenant_docs or docs)}
            if _norm(component_name) not in names:
                continue
            candidates.append((assignment, class_doc))
        if len(candidates) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_1_TARGET_NOT_EXACT:{class_name}:{component_name}:{len(candidates)}")
        assignment, class_doc = candidates[0]
        class_id = _sid(assignment.get("class_id"))
        course_id = _sid(assignment.get("course_id"))
        if (class_id, course_id) in seen:
            raise RuntimeError(f"ANA_LUCIA_F2_1_DUPLICATE_TARGET:{class_name}:{component_name}")
        seen.add((class_id, course_id))
        school = schools.get(_sid(class_doc.get("school_id"))) or {}
        tenant_id = _sid(class_doc.get("mantenedora_id") or school.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"ANA_LUCIA_F2_1_TARGET_TENANT_MISSING:{class_name}:{component_name}")
        out.append({
            "class": class_name,
            "component": component_name,
            "school": _sid(school.get("name")),
            "class_id": class_id,
            "course_id": course_id,
            "tenant_id": tenant_id,
            "education_level": _sid(class_doc.get("education_level") or class_doc.get("nivel_ensino")),
            "grade_level": _sid(class_doc.get("grade_level")),
        })
    if len(out) != 17:
        raise RuntimeError(f"ANA_LUCIA_F2_1_TARGET_COUNT:{len(out)}")
    return out


def _api_request(token: str, path: str, params=None, headers=None) -> urllib.request.Request:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    final_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sigesc-ana-lucia-f2-1-readonly-audit",
    }
    final_headers.update(headers or {})
    return urllib.request.Request(url, headers=final_headers, method="GET")


def _api_json(token: str, path: str, params=None, headers=None) -> dict[str, Any]:
    request = _api_request(token, path, params, headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
            return {"status": int(response.status), "data": payload}
    except urllib.error.HTTPError as exc:
        return {"status": int(exc.code), "data": None}


def _count_top_level_json_objects(stream) -> int:
    """Conta objetos do array JSON sem decodificar valores de campos."""
    in_string = False
    escaped = False
    array_started = False
    object_depth = 0
    count = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        for byte in chunk:
            if in_string:
                if escaped:
                    escaped = False
                elif byte == 92:  # backslash
                    escaped = True
                elif byte == 34:  # quote
                    in_string = False
                continue
            if byte == 34:
                in_string = True
                continue
            if not array_started:
                if byte == 91:  # [
                    array_started = True
                continue
            if byte == 123:  # {
                if object_depth == 0:
                    count += 1
                object_depth += 1
            elif byte == 125 and object_depth > 0:
                object_depth -= 1
    return count


def _api_array_count(token: str, path: str, params=None, headers=None) -> dict[str, Any]:
    request = _api_request(token, path, params, headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"status": int(response.status), "count": _count_top_level_json_objects(response)}
    except urllib.error.HTTPError as exc:
        return {"status": int(exc.code), "count": None}


def _api_status_only(token: str, path: str, params=None, headers=None) -> int:
    request = _api_request(token, path, params, headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _tenant_bucket(value: Any, tenant_id: str) -> str:
    raw = _sid(value)
    if not raw:
        return "missing"
    return "target" if raw == tenant_id else "other"


def _content_mongo(db, target: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(db.learning_objects.find(
        {"$and": [
            {"class_id": target["class_id"], "course_id": target["course_id"]},
            _year_scope(),
        ]},
        {"_id": 0, "date": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    tenant = Counter(_tenant_bucket(row.get("mantenedora_id"), target["tenant_id"]) for row in rows)
    year_types = Counter(
        "int" if row.get("academic_year") == ACADEMIC_YEAR else
        "string" if _sid(row.get("academic_year")) == str(ACADEMIC_YEAR) else "date_only_or_other"
        for row in rows
    )
    months: dict[str, dict[str, int]] = {}
    for row in rows:
        month = _month(row.get("date"))
        if month is None:
            continue
        key = str(month)
        months.setdefault(key, {"total": 0, "target_tenant": 0, "missing_tenant": 0, "api_eligible": 0})
        months[key]["total"] += 1
        bucket = _tenant_bucket(row.get("mantenedora_id"), target["tenant_id"])
        if bucket == "target":
            months[key]["target_tenant"] += 1
        elif bucket == "missing":
            months[key]["missing_tenant"] += 1
        if bucket == "target" and row.get("academic_year") == ACADEMIC_YEAR:
            months[key]["api_eligible"] += 1
    return {
        "total": len(rows),
        "target_tenant": tenant["target"],
        "missing_tenant": tenant["missing"],
        "other_tenant": tenant["other"],
        "academic_year_int": year_types["int"],
        "academic_year_string": year_types["string"],
        "date_only_or_other": year_types["date_only_or_other"],
        "months": months,
    }


def _attendance_mongo(db, target: Mapping[str, Any]) -> dict[str, Any]:
    collections = {}
    all_dates: set[str] = set()
    for name in ("attendance", "attendance_documentary"):
        rows = list(db[name].find(
            {"$and": [
                {"class_id": target["class_id"], "course_id": target["course_id"]},
                _year_scope(),
            ]},
            {"_id": 0, "date": 1, "academic_year": 1, "mantenedora_id": 1, "assignment_id": 1},
        ))
        tenant = Counter(_tenant_bucket(row.get("mantenedora_id"), target["tenant_id"]) for row in rows)
        unassigned = [row for row in rows if not _sid(row.get("assignment_id"))]
        dates = {_sid(row.get("date"))[:10] for row in rows if _sid(row.get("date"))}
        all_dates.update(dates)
        collections[name] = {
            "documents": len(rows),
            "unassigned": len(unassigned),
            "assigned": len(rows) - len(unassigned),
            "distinct_dates": len(dates),
            "target_tenant": tenant["target"],
            "missing_tenant": tenant["missing"],
            "other_tenant": tenant["other"],
            "academic_year_int": sum(1 for row in rows if row.get("academic_year") == ACADEMIC_YEAR),
            "academic_year_string": sum(1 for row in rows if _sid(row.get("academic_year")) == str(ACADEMIC_YEAR) and row.get("academic_year") != ACADEMIC_YEAR),
        }
    return {
        "collections": collections,
        "distinct_dates_all_collections": len(all_dates),
        "sentinel_date": min(all_dates) if all_dates else None,
    }


def _class_outside_dvd_scope(target: Mapping[str, Any]) -> bool:
    level = _norm(target.get("education_level"))
    class_name = _norm(target.get("class"))
    if level in {"fundamental_anos_finais", "eja_final"}:
        return True
    if any(token in class_name for token in ("6o ano", "7o ano", "8o ano", "9o ano", "3a etapa", "4a etapa")):
        return True
    return False


def classify_content(mongo: Mapping[str, Any], teacher_http: Mapping[str, Any], management_http: Mapping[str, Any], *, component_exposed: bool, content_diaries: int) -> str:
    if int(mongo.get("total") or 0) == 0:
        return "CONTENT_NO_LEGACY_RECORD"
    if not component_exposed:
        return "CONTENT_UI_COMPONENT_NOT_EXPOSED"
    if content_diaries:
        return "CONTENT_UNEXPECTED_CANONICAL_DIARY_PRESENT"
    if teacher_http.get("status") != 200:
        return "CONTENT_TEACHER_HTTP_BLOCKED"
    if management_http.get("status") != 200:
        return "CONTENT_MANAGEMENT_HTTP_BLOCKED"
    teacher_count = int(teacher_http.get("count") or 0)
    management_count = int(management_http.get("count") or 0)
    if teacher_count == 0 and management_count == 0 and int(mongo.get("missing_tenant") or 0) > 0 and int(mongo.get("target_tenant") or 0) == 0:
        return "CONTENT_TENANT_METADATA_GAP"
    if teacher_count == 0 and management_count == 0 and int(mongo.get("academic_year_string") or 0) > 0 and int(mongo.get("academic_year_int") or 0) == 0:
        return "CONTENT_ACADEMIC_YEAR_TYPE_GAP"
    if teacher_count != management_count:
        return "CONTENT_ROLE_HTTP_PARITY_GAP"
    if teacher_count == 0 and int(mongo.get("total") or 0) > 0:
        return "CONTENT_HTTP_ZERO_WITH_MONGO_RECORDS"
    return "CONTENT_REACHES_SCREEN"


def classify_attendance(mongo: Mapping[str, Any], teacher_dates: Mapping[str, Any], management_dates: Mapping[str, Any], *, component_exposed: bool, raw_dvd_year_rows: int, outside_dvd_scope: bool) -> str:
    official = (mongo.get("collections") or {}).get("attendance") or {}
    if int(official.get("documents") or 0) == 0:
        documentary = (mongo.get("collections") or {}).get("attendance_documentary") or {}
        if int(documentary.get("documents") or 0) > 0:
            return "ATTENDANCE_DOCUMENTARY_ONLY_NOT_IN_LEGACY_READER"
        return "ATTENDANCE_NO_LEGACY_RECORD"
    if not component_exposed:
        return "ATTENDANCE_UI_COMPONENT_NOT_EXPOSED"
    if outside_dvd_scope and raw_dvd_year_rows > 0 and teacher_dates.get("status") == 409:
        return "ATTENDANCE_RAW_DVD_YEAR_GUARD_OUT_OF_SCOPE"
    if teacher_dates.get("status") != 200:
        return "ATTENDANCE_TEACHER_HTTP_BLOCKED"
    if management_dates.get("status") != 200:
        return "ATTENDANCE_MANAGEMENT_HTTP_BLOCKED"
    if int(teacher_dates.get("count") or 0) != int(management_dates.get("count") or 0):
        return "ATTENDANCE_ROLE_HTTP_PARITY_GAP"
    if int(teacher_dates.get("count") or 0) == 0 and int(official.get("distinct_dates") or 0) > 0:
        return "ATTENDANCE_HTTP_ZERO_WITH_MONGO_RECORDS"
    return "ATTENDANCE_REACHES_SCREEN"


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_1_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    teacher, staff = _unique_teacher_identity(db)
    management = _management_identity(db)
    targets = _resolve_targets(db, staff)
    tenants = sorted({row["tenant_id"] for row in targets})
    if len(tenants) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_1_MULTIPLE_TARGET_TENANTS:{len(tenants)}")
    target_tenant = tenants[0]

    from auth_utils import create_access_token  # pylint: disable=import-outside-toplevel

    teacher_token = create_access_token({
        "sub": teacher["id"],
        "email": teacher.get("email"),
        "role": "professor",
        "school_ids": _school_ids_for_professor(db, teacher, staff),
        "mantenedora_id": teacher.get("mantenedora_id"),
    })
    management_token = create_access_token({
        "sub": management["id"],
        "email": management.get("email"),
        "role": "super_admin",
        "mantenedora_id": management.get("mantenedora_id"),
    })
    management_headers = {"X-Mantenedora-Id": target_tenant}

    teacher_turmas_result = _api_json(teacher_token, "/professor/turmas", {"academic_year": ACADEMIC_YEAR})
    teacher_diaries_result = _api_json(teacher_token, "/professor/diarios", {"academic_year": ACADEMIC_YEAR})
    turmas = teacher_turmas_result.get("data") if teacher_turmas_result.get("status") == 200 else []
    if not isinstance(turmas, list):
        turmas = []
    diary_items = ((teacher_diaries_result.get("data") or {}).get("items") or []) if teacher_diaries_result.get("status") == 200 else []

    public_pairs = []
    content_codes: Counter[str] = Counter()
    attendance_codes: Counter[str] = Counter()

    for target in targets:
        class_id = target["class_id"]
        course_id = target["course_id"]
        class_rows = [row for row in turmas if _sid(row.get("id")) == class_id]
        component_exposed = any(
            _sid(component.get("id")) == course_id
            for row in class_rows
            for component in (row.get("componentes") or [])
            if isinstance(component, Mapping)
        )
        content_diaries = sum(
            1 for item in diary_items
            if _sid(item.get("class_id")) == class_id
            and _sid(item.get("component_id")) == course_id
            and bool((item.get("capabilities") or {}).get("content_enabled"))
        )
        attendance_diaries = sum(
            1 for item in diary_items
            if _sid(item.get("class_id")) == class_id
            and (_sid(item.get("component_id")) == course_id or not _sid(item.get("component_id")))
            and bool((item.get("capabilities") or {}).get("attendance_enabled"))
        )

        content_mongo = _content_mongo(db, target)
        months = sorted(int(key) for key in content_mongo["months"])
        teacher_months: dict[str, Any] = {}
        management_months: dict[str, Any] = {}
        for month in months:
            params = {
                "class_id": class_id,
                "course_id": course_id,
                "academic_year": ACADEMIC_YEAR,
                "month": month,
            }
            teacher_months[str(month)] = _api_array_count(teacher_token, "/learning-objects", params)
            management_months[str(month)] = _api_array_count(
                management_token, "/learning-objects", params, management_headers
            )
        teacher_content = {
            "status": 200 if all(row.get("status") == 200 for row in teacher_months.values()) else next(
                (row.get("status") for row in teacher_months.values() if row.get("status") != 200), 200
            ),
            "count": sum(int(row.get("count") or 0) for row in teacher_months.values()),
            "months": teacher_months,
        }
        management_content = {
            "status": 200 if all(row.get("status") == 200 for row in management_months.values()) else next(
                (row.get("status") for row in management_months.values() if row.get("status") != 200), 200
            ),
            "count": sum(int(row.get("count") or 0) for row in management_months.values()),
            "months": management_months,
        }
        content_code = classify_content(
            content_mongo, teacher_content, management_content,
            component_exposed=component_exposed, content_diaries=content_diaries,
        )
        content_codes[content_code] += 1

        attendance_mongo = _attendance_mongo(db, target)
        params = {"class_id": class_id, "academic_year": ACADEMIC_YEAR, "course_id": course_id}
        teacher_dates_result = _api_json(teacher_token, "/attendance/dates-with-records", params)
        management_dates_result = _api_json(
            management_token, "/attendance/dates-with-records", params, management_headers
        )
        teacher_dates = {
            "status": teacher_dates_result["status"],
            "count": len((teacher_dates_result.get("data") or {}).get("dates") or []) if teacher_dates_result["status"] == 200 else None,
        }
        management_dates = {
            "status": management_dates_result["status"],
            "count": len((management_dates_result.get("data") or {}).get("dates") or []) if management_dates_result["status"] == 200 else None,
        }

        outside_scope = _class_outside_dvd_scope(target)
        raw_query = {
            "teacher_id": teacher["id"],
            "class_id": class_id,
            "diary_settings.enabled": True,
            "valid_from": {"$lte": f"{ACADEMIC_YEAR}-12-31"},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{ACADEMIC_YEAR}-01-01"}}],
        }
        raw_dvd_year_rows = db.teacher_class_assignments.count_documents(raw_query)

        sentinel = attendance_mongo.get("sentinel_date")
        teacher_by_class_status = None
        management_by_class_status = None
        if sentinel:
            by_params = {"course_id": course_id, "period": "regular"}
            teacher_by_class_status = _api_status_only(
                teacher_token, f"/attendance/by-class/{urllib.parse.quote(class_id)}/{sentinel}", by_params
            )
            management_by_class_status = _api_status_only(
                management_token,
                f"/attendance/by-class/{urllib.parse.quote(class_id)}/{sentinel}",
                by_params,
                management_headers,
            )

        attendance_code = classify_attendance(
            attendance_mongo, teacher_dates, management_dates,
            component_exposed=component_exposed,
            raw_dvd_year_rows=raw_dvd_year_rows,
            outside_dvd_scope=outside_scope,
        )
        attendance_codes[attendance_code] += 1

        public_pairs.append({
            "class": target["class"],
            "component": target["component"],
            "school": target["school"],
            "selection": {
                "professor_turmas_http_status": teacher_turmas_result["status"],
                "component_exposed": component_exposed,
                "professor_diarios_http_status": teacher_diaries_result["status"],
                "content_diaries": content_diaries,
                "attendance_diaries": attendance_diaries,
                "outside_dvd_v1_scope": outside_scope,
                "raw_enabled_dvd_year_rows_for_class": raw_dvd_year_rows,
            },
            "content": {
                "mongo": content_mongo,
                "professor_http": teacher_content,
                "management_http": management_content,
                "diagnosis": content_code,
            },
            "attendance": {
                "mongo": attendance_mongo,
                "professor_dates_http": teacher_dates,
                "management_dates_http": management_dates,
                "professor_by_class_status": teacher_by_class_status,
                "management_by_class_status": management_by_class_status,
                "diagnosis": attendance_code,
            },
        })

    return {
        "schema": "ANA_LUCIA_F2_1_RUNTIME_LEGACY_AUDIT_V1",
        "status": "PASS",
        "academic_year": ACADEMIC_YEAR,
        "teacher": TEACHER_NAME,
        "database_mutation": False,
        "production_writes": False,
        "mongo_reads_only": True,
        "http_methods": ["GET"],
        "login_endpoint_used": False,
        "attendance_records_read": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "pedagogical_text_decoded": False,
        "technical_ids_emitted": False,
        "target_pair_count": len(public_pairs),
        "summary": {
            "content_diagnoses": dict(sorted(content_codes.items())),
            "attendance_diagnoses": dict(sorted(attendance_codes.items())),
            "content_mongo_total": sum(int(row["content"]["mongo"]["total"]) for row in public_pairs),
            "attendance_official_documents_total": sum(int(row["attendance"]["mongo"]["collections"]["attendance"]["documents"]) for row in public_pairs),
            "attendance_documentary_documents_total": sum(int(row["attendance"]["mongo"]["collections"]["attendance_documentary"]["documents"]) for row in public_pairs),
            "pairs_with_raw_dvd_year_guard": sum(1 for row in public_pairs if row["selection"]["raw_enabled_dvd_year_rows_for_class"] > 0),
            "pairs_with_component_exposed": sum(1 for row in public_pairs if row["selection"]["component_exposed"]),
        },
        "pairs": public_pairs,
    }


if __name__ == "__main__":
    print("ANA_LUCIA_F2_1_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
