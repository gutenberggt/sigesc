#!/usr/bin/env python3
"""Reconcilia matrículas P0 de 2026 com data administrativa confirmada.

Uso deliberadamente restrito a casos em que a data administrativa original foi
confirmada fora do banco, mas a matrícula canônica está ausente.

Por padrão é READ-ONLY. Escrita exige simultaneamente:
    --apply --confirm-count N --confirm-token RECONCILE-P0-CONFIRMED-DATE-2026

A ferramenta:
- exige manifesto exclusivo de 2026;
- exige data ISO explícita via --confirmed-date;
- exige estudante ativo, turma regular de 2026, escola/tenant coerentes;
- exige número de matrícula existente e sem conflito;
- exige atividade acadêmica de 2026 na MESMA turma;
- exige que a data confirmada não seja posterior à primeira frequência;
- bloqueia qualquer caso que já possua documento em enrollments;
- cria somente via create_active_enrollment;
- grava source/observations de proveniência;
- não altera notas nem frequências.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.enrollment_service import (  # noqa: E402
    EnrollmentDomainError,
    create_active_enrollment,
    is_special_class,
)

YEAR = 2026
CONFIRM_TOKEN = "RECONCILE-P0-CONFIRMED-DATE-2026"
SOURCE = "repair:p0-enrollment-confirmed-date-2026"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _year_eq(value: Any) -> bool:
    return _norm(value) == str(YEAR)


def _active(value: Any) -> bool:
    return _norm(value).lower() == "active"


def parse_confirmed_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("--confirmed-date deve estar no formato YYYY-MM-DD.") from exc
    if parsed.year != YEAR:
        raise ValueError(f"--confirmed-date deve pertencer ao ano letivo {YEAR}.")
    return parsed.isoformat()


def load_manifest(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict):
        raise ValueError("Manifesto inválido: raiz deve ser objeto JSON.")
    ready = manifest.get("ready")
    quarantine = manifest.get("quarantine")
    if not isinstance(ready, list) or not isinstance(quarantine, list):
        raise ValueError("Manifesto inválido: campos ready/quarantine obrigatórios.")
    if _norm(manifest.get("year")) != str(YEAR):
        raise ValueError(f"Manifesto deve ser exclusivo do ano letivo {YEAR}.")
    return manifest


async def first_attendance_date(db, student_id: str, class_id: str) -> Optional[str]:
    docs = await db.attendance.find(
        {
            "class_id": class_id,
            "records": {"$elemMatch": {"student_id": student_id}},
            "$or": [
                {"academic_year": {"$in": [YEAR, str(YEAR)]}},
                {"date": {"$regex": f"^{YEAR}-"}},
            ],
        },
        {"_id": 0, "date": 1},
    ).sort("date", 1).limit(1).to_list(length=1)
    if not docs:
        return None
    value = _norm(docs[0].get("date"))
    return value[:10] if value else None


async def grade_count(db, student_id: str, class_id: str) -> int:
    return int(await db.grades.count_documents({
        "student_id": student_id,
        "class_id": class_id,
        "academic_year": {"$in": [YEAR, str(YEAR)]},
    }))


async def assess_candidate(
    db,
    row: dict[str, Any],
    confirmed_date: str,
) -> dict[str, Any]:
    sid = _norm(row.get("student_id"))
    blockers: list[str] = []

    student = await db.students.find_one({"id": sid}, {"_id": 0})
    if not student:
        return {"student_id": sid, "full_name": _norm(row.get("full_name")), "blockers": ["STUDENT_NOT_FOUND"]}

    if not _active(student.get("status")):
        blockers.append("STUDENT_NOT_ACTIVE")

    class_id = _norm(student.get("class_id"))
    expected_class_id = _norm(row.get("class_id"))
    if not class_id:
        blockers.append("STUDENT_CLASS_MISSING")
    if expected_class_id and class_id != expected_class_id:
        blockers.append("CLASS_CHANGED_SINCE_MANIFEST")

    class_doc = None
    if class_id:
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        blockers.append("CLASS_NOT_FOUND")
    else:
        if not _year_eq(class_doc.get("academic_year")):
            blockers.append("CLASS_NOT_2026")
        if is_special_class(class_doc):
            blockers.append("SPECIAL_CLASS")
        if _norm(class_doc.get("school_id")) != _norm(student.get("school_id")):
            blockers.append("SCHOOL_MISMATCH")
        tenants = {
            _norm(v)
            for v in (student.get("mantenedora_id"), class_doc.get("mantenedora_id"))
            if _norm(v)
        }
        if len(tenants) != 1:
            blockers.append("TENANT_MISMATCH_OR_MISSING")

    existing = await db.enrollments.find({"student_id": sid}, {"_id": 0}).to_list(length=100)
    if existing:
        blockers.append("ENROLLMENT_DOCUMENT_ALREADY_EXISTS")

    number = _norm(student.get("enrollment_number"))
    manifest_number = _norm(row.get("enrollment_number"))
    if not number:
        blockers.append("MISSING_ENROLLMENT_NUMBER")
    if manifest_number and number != manifest_number:
        blockers.append("ENROLLMENT_NUMBER_CHANGED_SINCE_MANIFEST")

    if number:
        same_students = await db.students.find(
            {"enrollment_number": number}, {"_id": 0, "id": 1}
        ).to_list(length=20)
        if any(_norm(x.get("id")) != sid for x in same_students):
            blockers.append("ENROLLMENT_NUMBER_DUPLICATED_IN_STUDENTS")

        same_enrollments = await db.enrollments.find(
            {"enrollment_number": number}, {"_id": 0, "student_id": 1}
        ).to_list(length=20)
        if any(_norm(x.get("student_id")) != sid for x in same_enrollments):
            blockers.append("ENROLLMENT_NUMBER_USED_BY_OTHER_STUDENT")

    direct_date = _norm(student.get("enrollment_date"))
    if direct_date:
        blockers.append("DIRECT_ENROLLMENT_DATE_NOW_PRESENT")

    first_att = None
    grades = 0
    if class_id:
        first_att = await first_attendance_date(db, sid, class_id)
        grades = await grade_count(db, sid, class_id)

    if not first_att and grades <= 0:
        blockers.append("NO_CURRENT_CLASS_ACADEMIC_ACTIVITY_2026")

    if first_att and confirmed_date > first_att:
        blockers.append("CONFIRMED_DATE_AFTER_FIRST_ATTENDANCE")

    return {
        "student_id": sid,
        "full_name": _norm(student.get("full_name") or row.get("full_name")),
        "student": student,
        "class_doc": class_doc or {},
        "first_attendance_date": first_att,
        "grade_count": grades,
        "confirmed_date": confirmed_date,
        "blockers": sorted(set(blockers)),
    }


def _write_receipt(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def _default_receipt() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"/tmp/sigesc_enrollment_p0_confirmed_date_{stamp}.json"


async def run(args: argparse.Namespace) -> int:
    confirmed_date = parse_confirmed_date(args.confirmed_date)
    manifest = load_manifest(args.manifest)
    rows = manifest["ready"]

    quarantine_ids = {
        _norm(x.get("student_id"))
        for x in manifest.get("quarantine", [])
        if isinstance(x, dict)
    }
    rows = [r for r in rows if _norm(r.get("student_id")) not in quarantine_ids]

    if args.apply:
        if args.confirm_token != CONFIRM_TOKEN:
            raise SystemExit(f"ABORTADO: --confirm-token deve ser exatamente {CONFIRM_TOKEN}")
        if args.confirm_count is None or args.confirm_count != len(rows):
            raise SystemExit(
                f"ABORTADO: --confirm-count={args.confirm_count!r} não corresponde ao manifesto ready={len(rows)}"
            )

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurada.")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    receipt_path = args.receipt or _default_receipt()
    receipt: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "year": YEAR,
        "confirmed_enrollment_date": confirmed_date,
        "date_provenance": "administrative_confirmation",
        "source": SOURCE,
        "manifest": args.manifest,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "created": [],
        "blocked": [],
    }

    try:
        assessments = [await assess_candidate(db, row, confirmed_date) for row in rows]
        blocked = [a for a in assessments if a["blockers"]]
        ready = [a for a in assessments if not a["blockers"]]

        print("SIGESC — RECONCILIAÇÃO P0 COM DATA CONFIRMADA")
        print("=" * 64)
        print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN / READ-ONLY'}")
        print(f"Data administrativa confirmada: {confirmed_date}")
        print(f"Manifesto ready considerado: {len(rows)}")
        print(f"READY: {len(ready)}")
        print(f"BLOCKED: {len(blocked)}")

        for item in blocked:
            receipt["blocked"].append({
                "student_id": item["student_id"],
                "full_name": item["full_name"],
                "blockers": item["blockers"],
            })
            print(
                f"BLOCKED | {item['student_id']} | {item['full_name']} | "
                f"{','.join(item['blockers'])}"
            )

        if blocked:
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_receipt(receipt_path, receipt)
            print(f"\nABORTADO: {len(blocked)} candidato(s) bloquearam o lote inteiro.")
            print(f"Recibo: {receipt_path}")
            return 2

        if not args.apply:
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_receipt(receipt_path, receipt)
            print("\nDRY-RUN concluído. Nenhuma alteração foi feita.")
            print(f"Recibo: {receipt_path}")
            return 0

        observations = (
            f"Reconstrução P0: enrollment_date {confirmed_date} confirmada "
            "administrativamente; não inferida por created_at, nota ou frequência."
        )

        for row in rows:
            current = await assess_candidate(db, row, confirmed_date)
            if current["blockers"]:
                receipt["blocked"].append({
                    "student_id": current["student_id"],
                    "full_name": current["full_name"],
                    "blockers": current["blockers"],
                    "stage": "pre_insert_revalidation",
                })
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise RuntimeError(
                    f"Revalidação falhou para {current['student_id']}; consulte {receipt_path}."
                )

            student = current["student"]
            class_doc = current["class_doc"]
            try:
                result = await create_active_enrollment(
                    db,
                    student_id=current["student_id"],
                    school_id=_norm(student.get("school_id")),
                    class_id=_norm(student.get("class_id")),
                    academic_year=YEAR,
                    enrollment_date=confirmed_date,
                    enrollment_number=_norm(student.get("enrollment_number")),
                    student_series=student.get("student_series") or class_doc.get("grade_level"),
                    observations=observations,
                    mantenedora_id=_norm(student.get("mantenedora_id")),
                    source=SOURCE,
                )
            except EnrollmentDomainError as exc:
                receipt["blocked"].append({
                    "student_id": current["student_id"],
                    "full_name": current["full_name"],
                    "blockers": [f"DOMAIN_ERROR:{type(exc).__name__}:{exc}"],
                    "stage": "create_active_enrollment",
                })
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise

            enrollment = result["enrollment"]
            receipt["created"].append({
                "student_id": current["student_id"],
                "full_name": current["full_name"],
                "enrollment_id": enrollment.get("id"),
                "class_id": enrollment.get("class_id"),
                "enrollment_number": enrollment.get("enrollment_number"),
                "enrollment_date": enrollment.get("enrollment_date"),
                "source": enrollment.get("source"),
            })
            _write_receipt(receipt_path, receipt)

        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_receipt(receipt_path, receipt)
        print(f"\nConcluído: {len(receipt['created'])} matrícula(s) criada(s).")
        print("Notas e frequências não foram alteradas.")
        print(f"Recibo: {receipt_path}")
        return 0
    finally:
        client.close()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--confirmed-date", required=True, help="Data administrativa confirmada YYYY-MM-DD.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-count", type=int, default=None)
    parser.add_argument("--confirm-token", default=None)
    parser.add_argument("--receipt", default=None)
    return parser.parse_args(argv)


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
