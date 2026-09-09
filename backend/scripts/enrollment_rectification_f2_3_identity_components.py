#!/usr/bin/env python3
"""F2.3 — diagnóstico criptográfico por componentes da identidade (read-only).

Executado via stdin dentro do backend de produção. Recebe somente hashes salted
independentes de nome, nascimento e CPF; nunca recebe nem emite os valores brutos.
A busca fica limitada às matrículas ativas do 6º ANO B da escola/ano autorizados.

Uma estudante só é resolvida quando um sinal forte/combinação inequívoca produz
cardinalidade 1 e todos os métodos únicos disponíveis concordam no mesmo registro.
Somente então o dry-run acadêmico canônico é invocado.

Não prepara, não executa, não faz rollback e não contém mutadores MongoDB.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3_COMPONENT_IDENTITY_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO B"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026
NAME_EDIT_ALPHABET = "abcdefghijklmnopqrstuvwxyz "


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(
        c for c in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(c)
    )
    return " ".join(text.casefold().strip().split())


def _normalize_birth_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def _cpf_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def component_hash(salt: str, kind: str, normalized_value: str) -> str:
    material = f"{salt}|{kind}|{normalized_value}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _one_edit_name_variants(value: Any) -> set[str]:
    source = _norm(value)
    if not source:
        return set()
    variants: set[str] = set()
    n = len(source)
    for i in range(n):
        variants.add(_norm(source[:i] + source[i + 1 :]))
    for i in range(n - 1):
        if source[i] != source[i + 1]:
            variants.add(_norm(source[:i] + source[i + 1] + source[i] + source[i + 2 :]))
    for i in range(n):
        for char in NAME_EDIT_ALPHABET:
            if char != source[i]:
                variants.add(_norm(source[:i] + char + source[i + 1 :]))
    for i in range(n + 1):
        for char in NAME_EDIT_ALPHABET:
            variants.add(_norm(source[:i] + char + source[i:]))
    variants.discard(source)
    variants.discard("")
    return variants


def _execution_flag_enabled() -> bool:
    return os.environ.get(
        "ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false"
    ).strip().lower() == "true"


def _code_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(i.get("code") or "UNKNOWN") for i in items).items()))


def _blocked(reason: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "BLOCKED",
        "reason": reason,
        **fields,
        "execution_flag_enabled": _execution_flag_enabled(),
        "database_mutation": False,
        "production_writes": False,
        "prepare_execution_called": False,
        "execute_called": False,
        "rollback_called": False,
        "feature_flag_modified": False,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
    }


def _safe_summary(
    dry_run: dict[str, Any], *, resolution_method: str,
    projection_matches_source: bool, diagnostic_counts: dict[str, Any]
) -> dict[str, Any]:
    blockers = list(dry_run.get("blockers") or [])
    warnings = list(dry_run.get("warnings") or [])
    grades = list(dry_run.get("grades_manifest") or [])
    attendance = list(dry_run.get("attendance_manifest") or [])
    documents = dry_run.get("documents") or {}
    return {
        "schema": SCHEMA,
        "status": "READY_FOR_REVIEW",
        "academic_year": ACADEMIC_YEAR,
        "school": TARGET_SCHOOL,
        "source_class": (dry_run.get("origin_class") or {}).get("name"),
        "destination_class": (dry_run.get("destination_class") or {}).get("name"),
        "identity_match_count": 1,
        "identity_resolution_method": resolution_method,
        "student_projection_matches_source": projection_matches_source,
        **diagnostic_counts,
        "contract_version": dry_run.get("contract_version"),
        "operation": dry_run.get("operation"),
        "can_execute_later": bool(dry_run.get("can_execute_later")),
        "execution_flag_enabled": _execution_flag_enabled(),
        "counts": dry_run.get("counts") or {},
        "grades_summary": {
            "documents": len(grades),
            "migratable_fields": sum(len(i.get("migratable_fields") or []) for i in grades),
            "destination_overlapping_fields": sum(len(i.get("overlapping_fields") or []) for i in grades),
            "metadata_conflicts": sum(len(i.get("destination_metadata_conflicts") or []) for i in grades),
        },
        "attendance_summary": {
            "student_records": len(attendance),
            "validated_source_records": sum(1 for i in attendance if i.get("validated")),
            "destination_overlap_total": sum(int(i.get("destination_overlap_count") or 0) for i in attendance),
        },
        "documents": {
            "coverage_complete": bool(documents.get("coverage_complete")),
            "tracked_total": int(documents.get("tracked_total") or 0),
            "coverage_gap_code": ((documents.get("coverage_gap") or {}).get("code")),
        },
        "blocker_code_counts": _code_counts(blockers),
        "warning_code_counts": _code_counts(warnings),
        "expected_postconditions": list(dry_run.get("expected_postconditions") or []),
        "dry_run_invoked": True,
        "database_mutation": False,
        "production_writes": False,
        "prepare_execution_called": False,
        "execute_called": False,
        "rollback_called": False,
        "feature_flag_modified": False,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
    }


def resolve_by_components(
    students: list[dict[str, Any]], *, salt: str,
    expected_name_hash: str, expected_dob_hash: str, expected_cpf_hash: str
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any]]:
    ids = {str(s.get("id") or ""): s for s in students if s.get("id")}
    name_ids: set[str] = set()
    edit_name_ids: set[str] = set()
    dob_ids: set[str] = set()
    cpf_ids: set[str] = set()

    for sid, student in ids.items():
        name = _norm(student.get("full_name"))
        dob = _normalize_birth_date(student.get("birth_date"))
        cpf = _cpf_digits(student.get("cpf"))
        if component_hash(salt, "name", name) == expected_name_hash:
            name_ids.add(sid)
        elif any(
            component_hash(salt, "name", variant) == expected_name_hash
            for variant in _one_edit_name_variants(name)
        ):
            edit_name_ids.add(sid)
        if component_hash(salt, "dob", dob) == expected_dob_hash:
            dob_ids.add(sid)
        if cpf and component_hash(salt, "cpf", cpf) == expected_cpf_hash:
            cpf_ids.add(sid)

    intersections = {
        "name_dob_count": len(name_ids & dob_ids),
        "name_cpf_count": len(name_ids & cpf_ids),
        "dob_cpf_count": len(dob_ids & cpf_ids),
        "one_edit_name_dob_count": len(edit_name_ids & dob_ids),
        "one_edit_name_cpf_count": len(edit_name_ids & cpf_ids),
    }
    counts: dict[str, Any] = {
        "candidate_count": len(ids),
        "name_exact_count": len(name_ids),
        "name_one_edit_count": len(edit_name_ids),
        "dob_exact_count": len(dob_ids),
        "cpf_exact_count": len(cpf_ids),
        **intersections,
    }

    methods: list[tuple[str, set[str]]] = [
        ("cpf_exact", cpf_ids),
        ("name_dob_exact", name_ids & dob_ids),
        ("name_cpf_exact", name_ids & cpf_ids),
        ("dob_cpf_exact", dob_ids & cpf_ids),
        ("one_edit_name_cpf", edit_name_ids & cpf_ids),
        ("one_edit_name_dob", edit_name_ids & dob_ids),
    ]
    unique_methods = [(name, values) for name, values in methods if len(values) == 1]
    if not unique_methods:
        return None, None, counts

    unique_ids = {next(iter(values)) for _, values in unique_methods}
    if len(unique_ids) != 1:
        counts["unique_method_count"] = len(unique_methods)
        counts["unique_method_agreement"] = False
        return None, "COMPONENT_SIGNAL_CONFLICT", counts

    resolved_id = next(iter(unique_ids))
    counts["unique_method_count"] = len(unique_methods)
    counts["unique_method_agreement"] = True
    resolution_method = "+".join(name for name, values in unique_methods if resolved_id in values)
    return ids[resolved_id], resolution_method, counts


async def run_live_resolution() -> dict[str, Any]:
    salt = os.environ.get("F2_3_COMPONENT_SALT", "").strip()
    name_hash = os.environ.get("F2_3_NAME_HASH", "").strip().lower()
    dob_hash = os.environ.get("F2_3_DOB_HASH", "").strip().lower()
    cpf_hash = os.environ.get("F2_3_CPF_HASH", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        raise RuntimeError("F2_3_COMPONENT_SALT_INVALID")
    for label, value in (("NAME", name_hash), ("DOB", dob_hash), ("CPF", cpf_hash)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise RuntimeError(f"F2_3_{label}_HASH_INVALID")

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        raise RuntimeError("F2_3_COMPONENT_DATABASE_ENV_MISSING")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
        school_matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
        if len(school_matches) != 1:
            return _blocked("SCHOOL_CARDINALITY_INVALID", school_match_count=len(school_matches))
        school = school_matches[0]
        tenant_id = str(school.get("mantenedora_id") or "")
        school_id = str(school.get("id") or "")
        if not tenant_id or not school_id:
            return _blocked("SCHOOL_IDENTITY_INCOMPLETE")

        classes = await db.classes.find(
            {"mantenedora_id": tenant_id, "school_id": school_id,
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(None)
        source = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
        destination = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
        if len(source) != 1 or len(destination) != 1:
            return _blocked("CLASS_CARDINALITY_INVALID",
                            source_class_match_count=len(source),
                            destination_class_match_count=len(destination))
        source_id = str(source[0].get("id") or "")
        destination_id = str(destination[0].get("id") or "")

        enrollments = await db.enrollments.find(
            {"mantenedora_id": tenant_id, "class_id": source_id,
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": "active"},
            {"_id": 0, "student_id": 1},
        ).to_list(None)
        candidate_ids = sorted({str(e.get("student_id")) for e in enrollments if e.get("student_id")})
        students = await db.students.find(
            {"mantenedora_id": tenant_id, "id": {"$in": candidate_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
        ).to_list(None)

        resolved, method, diagnostic = resolve_by_components(
            students, salt=salt, expected_name_hash=name_hash,
            expected_dob_hash=dob_hash, expected_cpf_hash=cpf_hash,
        )
        if resolved is None:
            reason = method or "COMPONENT_IDENTITY_NOT_UNIQUE"
            return _blocked(reason, **diagnostic)

        student_id = str(resolved.get("id") or "")
        projection_matches_source = str(resolved.get("class_id") or "") == source_id
        try:
            dry_run = await build_rectification_dry_run(
                db, student_id=student_id, destination_class_id=destination_id,
                tenant_id=tenant_id,
                actor={"id": "f2-3-component-identity-readonly", "role": "super_admin"},
            )
        except RectificationDryRunError as exc:
            return _blocked(
                "CANONICAL_DRY_RUN_ERROR", **diagnostic,
                identity_match_count=1, identity_resolution_method=method,
                student_projection_matches_source=projection_matches_source,
                dry_run_error_code=exc.code, dry_run_error_status=exc.status_code,
                dry_run_invoked=True,
            )
        return _safe_summary(
            dry_run, resolution_method=str(method),
            projection_matches_source=projection_matches_source,
            diagnostic_counts=diagnostic,
        )
    finally:
        client.close()


def main() -> None:
    result = asyncio.run(run_live_resolution())
    print("ENROLLMENT_RECTIFICATION_F2_3_COMPONENT_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
