#!/usr/bin/env python3
"""Repara dois remanejamentos legados de 2026 com destino indevidamente `relocated`.

Escopo fechado e nominal:
- Aruna Chaves Alencar
- Ana Cecília da Silva Oliveira

Por padrão é READ-ONLY. Escrita exige simultaneamente:
    --apply --confirm-count 2 --confirm-token RECONCILE-P0-LEGACY-RELOCATION-2026

O reparo NÃO cria enrollment novo. Para cada caso ele:
- exige estudante ativo e projeção atual exatamente na turma destino auditada;
- exige enrollment de origem exatamente no status histórico auditado;
- exige enrollment de destino exatamente `relocated` e com o número legado esperado;
- exige que o número vigente em `students.enrollment_number` seja exclusivo;
- exige ausência de outra matrícula regular ativa em 2026;
- exige mantenedora presente e idêntica em estudante, turma origem e turma destino;
- revalida imediatamente antes de escrever;
- altera somente o enrollment de destino: status -> active, enrollment_number -> número vigente,
  previous_enrollment_number -> número legado do destino, source/proveniência e updated_at;
- preserva notas, frequências, histórico, turma, série, escola e student document.

A ferramenta é idempotente: após aplicação correta, os dois casos passam a
`ALREADY_CANONICAL`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

YEAR = 2026
CONFIRM_TOKEN = "RECONCILE-P0-LEGACY-RELOCATION-2026"
SOURCE = "repair:p0-legacy-relocation-2026"
SPECIAL_PROGRAMS = {"aee", "recomposicao_aprendizagem", "reforco_escolar"}

CASES = [
    {
        "student_id": "4cf4babd-39f0-4baf-aa22-d5a3369eed71",
        "full_name": "Aruna Chaves Alencar",
        "school_id": "1279c538-94c9-4c6b-a0de-994ed73c9f6f",
        "destination_class_id": "c05a4ec0-0876-4902-be59-5c40ae0b5923",
        "destination_enrollment_id": "576b0c48-fab0-44a5-8f9e-51d877438006",
        "destination_legacy_number": "202604793",
        "current_student_number": "202604733",
        "origin_class_id": "097d88de-6567-49d2-a014-936a0bb8cf39",
        "origin_enrollment_id": "d99b3f9d-1f16-4521-a118-e4122f98842b",
        "origin_status": "relocated",
        "origin_number": "202604613",
    },
    {
        "student_id": "e924c856-6c26-4bc8-b257-6400b68ec675",
        "full_name": "Ana Cecília da Silva Oliveira",
        "school_id": "891bae28-5919-437b-9907-6f030159b57a",
        "destination_class_id": "f1515648-06c2-4b10-9c3b-be40479e3959",
        "destination_enrollment_id": "53b8eff6-ede0-4c27-9178-cb6a49d9570c",
        "destination_legacy_number": "202607139",
        "current_student_number": "202604947",
        "origin_class_id": "1fb4740e-dbb2-48dc-bd88-a7e5cfd0a2d9",
        "origin_enrollment_id": "f4efad66-7dbf-48de-ae8e-35df11f90410",
        "origin_status": "cancelled",
        "origin_number": "202604531",
    },
]


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _year_eq(value: Any) -> bool:
    return _norm(value) == str(YEAR)


def _active(value: Any) -> bool:
    return _norm(value).lower() == "active"


def _special(class_doc: dict[str, Any] | None) -> bool:
    program = _norm((class_doc or {}).get("atendimento_programa")).lower()
    return program in SPECIAL_PROGRAMS


def assess_snapshot(
    *,
    case: dict[str, str],
    student: dict[str, Any] | None,
    destination: dict[str, Any] | None,
    origin: dict[str, Any] | None,
    destination_class: dict[str, Any] | None,
    origin_class: dict[str, Any] | None,
    same_student_number_students: list[dict[str, Any]],
    same_student_number_enrollments: list[dict[str, Any]],
    same_legacy_number_enrollments: list[dict[str, Any]],
    other_active_regular: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    sid = case["student_id"]

    if not student:
        return "BLOCKED", ["STUDENT_NOT_FOUND"]
    if _norm(student.get("id")) != sid:
        blockers.append("STUDENT_ID_DIVERGED")
    if not _active(student.get("status")):
        blockers.append("STUDENT_NOT_ACTIVE")
    if _norm(student.get("school_id")) != case["school_id"]:
        blockers.append("STUDENT_SCHOOL_CHANGED")
    if _norm(student.get("class_id")) != case["destination_class_id"]:
        blockers.append("STUDENT_CLASS_CHANGED")
    if _norm(student.get("enrollment_number")) != case["current_student_number"]:
        blockers.append("STUDENT_NUMBER_CHANGED")

    if not destination_class:
        blockers.append("DESTINATION_CLASS_NOT_FOUND")
    else:
        if _norm(destination_class.get("id")) != case["destination_class_id"]:
            blockers.append("DESTINATION_CLASS_LOOKUP_DIVERGED")
        if not _year_eq(destination_class.get("academic_year")):
            blockers.append("DESTINATION_CLASS_NOT_2026")
        if _special(destination_class):
            blockers.append("DESTINATION_CLASS_SPECIAL")
        if _norm(destination_class.get("school_id")) != case["school_id"]:
            blockers.append("DESTINATION_CLASS_SCHOOL_MISMATCH")

    if not origin_class:
        blockers.append("ORIGIN_CLASS_NOT_FOUND")
    else:
        if _norm(origin_class.get("id")) != case["origin_class_id"]:
            blockers.append("ORIGIN_CLASS_LOOKUP_DIVERGED")
        if not _year_eq(origin_class.get("academic_year")):
            blockers.append("ORIGIN_CLASS_NOT_2026")
        if _norm(origin_class.get("school_id")) != case["school_id"]:
            blockers.append("ORIGIN_CLASS_SCHOOL_MISMATCH")

    tenant_values = [
        _norm(student.get("mantenedora_id")),
        _norm((destination_class or {}).get("mantenedora_id")),
        _norm((origin_class or {}).get("mantenedora_id")),
    ]
    if any(not value for value in tenant_values) or len(set(tenant_values)) != 1:
        blockers.append("TENANT_MISMATCH_OR_MISSING")

    if not origin:
        blockers.append("ORIGIN_ENROLLMENT_NOT_FOUND")
    else:
        if _norm(origin.get("student_id")) != sid:
            blockers.append("ORIGIN_STUDENT_DIVERGED")
        if _norm(origin.get("class_id")) != case["origin_class_id"]:
            blockers.append("ORIGIN_CLASS_DIVERGED")
        if not _year_eq(origin.get("academic_year")):
            blockers.append("ORIGIN_YEAR_DIVERGED")
        if _norm(origin.get("status")).lower() != case["origin_status"]:
            blockers.append("ORIGIN_STATUS_CHANGED")
        if _norm(origin.get("enrollment_number")) != case["origin_number"]:
            blockers.append("ORIGIN_NUMBER_CHANGED")

    if not destination:
        blockers.append("DESTINATION_ENROLLMENT_NOT_FOUND")
    else:
        if _norm(destination.get("student_id")) != sid:
            blockers.append("DESTINATION_STUDENT_DIVERGED")
        if _norm(destination.get("class_id")) != case["destination_class_id"]:
            blockers.append("DESTINATION_CLASS_DIVERGED")
        if not _year_eq(destination.get("academic_year")):
            blockers.append("DESTINATION_YEAR_DIVERGED")

    foreign_students = [
        x for x in same_student_number_students if _norm(x.get("id")) != sid
    ]
    if foreign_students:
        blockers.append("CURRENT_NUMBER_USED_BY_OTHER_STUDENT")

    foreign_current_number_enrollments = [
        x for x in same_student_number_enrollments if _norm(x.get("student_id")) != sid
    ]
    if foreign_current_number_enrollments:
        blockers.append("CURRENT_NUMBER_USED_BY_OTHER_ENROLLMENT")

    foreign_legacy_number_enrollments = [
        x
        for x in same_legacy_number_enrollments
        if _norm(x.get("id")) != case["destination_enrollment_id"]
    ]
    if foreign_legacy_number_enrollments:
        blockers.append("LEGACY_DESTINATION_NUMBER_USED_ELSEWHERE")

    if other_active_regular:
        blockers.append("OTHER_ACTIVE_REGULAR_ENROLLMENT_EXISTS")

    already = False
    if destination:
        already = (
            _active(destination.get("status"))
            and _norm(destination.get("enrollment_number")) == case["current_student_number"]
            and _norm(destination.get("previous_enrollment_number"))
            == case["destination_legacy_number"]
            and _norm(destination.get("source")) == SOURCE
        )

    if already:
        if same_legacy_number_enrollments:
            blockers.append("LEGACY_DESTINATION_NUMBER_STILL_ACTIVE_AS_PRIMARY")
        return ("ALREADY_CANONICAL" if not blockers else "BLOCKED", sorted(set(blockers)))

    if destination:
        if _norm(destination.get("status")).lower() != "relocated":
            blockers.append("DESTINATION_STATUS_CHANGED")
        if _norm(destination.get("enrollment_number")) != case["destination_legacy_number"]:
            blockers.append("DESTINATION_NUMBER_CHANGED")
        if _norm(destination.get("previous_enrollment_number")):
            blockers.append("DESTINATION_PREVIOUS_NUMBER_ALREADY_SET")
        if _norm(destination.get("source")):
            blockers.append("DESTINATION_SOURCE_ALREADY_SET")

    return ("READY" if not blockers else "BLOCKED", sorted(set(blockers)))


async def _class_by_id(db, cid: str) -> dict[str, Any] | None:
    return await db.classes.find_one({"id": cid}, {"_id": 0})


async def assess_case(db, case: dict[str, str]) -> dict[str, Any]:
    sid = case["student_id"]
    student = await db.students.find_one({"id": sid}, {"_id": 0})
    destination = await db.enrollments.find_one(
        {"id": case["destination_enrollment_id"]}, {"_id": 0}
    )
    origin = await db.enrollments.find_one(
        {"id": case["origin_enrollment_id"]}, {"_id": 0}
    )
    destination_class = await _class_by_id(db, case["destination_class_id"])
    origin_class = await _class_by_id(db, case["origin_class_id"])

    same_students = await db.students.find(
        {"enrollment_number": case["current_student_number"]},
        {"_id": 0, "id": 1},
    ).to_list(length=20)
    same_current_enrollments = await db.enrollments.find(
        {"enrollment_number": case["current_student_number"]},
        {"_id": 0, "id": 1, "student_id": 1},
    ).to_list(length=20)
    same_legacy_enrollments = await db.enrollments.find(
        {"enrollment_number": case["destination_legacy_number"]},
        {"_id": 0, "id": 1, "student_id": 1},
    ).to_list(length=20)

    active_docs = await db.enrollments.find(
        {
            "student_id": sid,
            "status": "active",
            "academic_year": {"$in": [YEAR, str(YEAR)]},
            "id": {"$ne": case["destination_enrollment_id"]},
        },
        {"_id": 0},
    ).to_list(length=50)
    other_active_regular: list[dict[str, Any]] = []
    for doc in active_docs:
        cls = await _class_by_id(db, _norm(doc.get("class_id")))
        if cls and not _special(cls):
            other_active_regular.append(doc)

    disposition, blockers = assess_snapshot(
        case=case,
        student=student,
        destination=destination,
        origin=origin,
        destination_class=destination_class,
        origin_class=origin_class,
        same_student_number_students=same_students,
        same_student_number_enrollments=same_current_enrollments,
        same_legacy_number_enrollments=same_legacy_enrollments,
        other_active_regular=other_active_regular,
    )
    return {
        "student_id": sid,
        "full_name": case["full_name"],
        "disposition": disposition,
        "blockers": blockers,
    }


def _default_receipt() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"/tmp/sigesc_enrollment_p0_legacy_relocation_{stamp}.json"


def _write_receipt(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


async def run(args: argparse.Namespace) -> int:
    if args.apply:
        if args.confirm_count != len(CASES):
            raise SystemExit(
                f"ABORTADO: --confirm-count deve ser exatamente {len(CASES)}"
            )
        if args.confirm_token != CONFIRM_TOKEN:
            raise SystemExit(f"ABORTADO: --confirm-token deve ser exatamente {CONFIRM_TOKEN}")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurada.")

    receipt_path = args.receipt or _default_receipt()
    receipt: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "year": YEAR,
        "source": SOURCE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cases": [],
    }

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        assessments = [await assess_case(db, case) for case in CASES]
        ready = [x for x in assessments if x["disposition"] == "READY"]
        already = [x for x in assessments if x["disposition"] == "ALREADY_CANONICAL"]
        blocked = [x for x in assessments if x["disposition"] == "BLOCKED"]

        print("SIGESC — RECONCILIAÇÃO P0 DE REMANEJAMENTOS LEGADOS 2026")
        print("=" * 72)
        print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN / READ-ONLY'}")
        print(f"Casos considerados: {len(CASES)}")
        print(f"READY: {len(ready)}")
        print(f"ALREADY_CANONICAL: {len(already)}")
        print(f"BLOCKED: {len(blocked)}")

        for item in assessments:
            receipt["cases"].append(item)
            suffix = f" | {','.join(item['blockers'])}" if item["blockers"] else ""
            print(
                f"{item['disposition']} | {item['student_id']} | "
                f"{item['full_name']}{suffix}"
            )

        if blocked:
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_receipt(receipt_path, receipt)
            print(f"\nABORTADO: {len(blocked)} caso(s) bloquearam o lote inteiro.")
            print(f"Recibo: {receipt_path}")
            return 2

        if not args.apply:
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_receipt(receipt_path, receipt)
            print("\nDRY-RUN concluído. Nenhuma alteração foi feita.")
            print(f"Recibo: {receipt_path}")
            return 0

        applied: list[str] = []
        for case in CASES:
            current = await assess_case(db, case)
            if current["disposition"] == "ALREADY_CANONICAL":
                continue
            if current["disposition"] != "READY":
                receipt["cases"].append({**current, "stage": "pre_update_revalidation"})
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise RuntimeError(
                    f"Revalidação falhou para {current['student_id']}; consulte {receipt_path}."
                )

            now = datetime.now(timezone.utc).isoformat()
            result = await db.enrollments.update_one(
                {
                    "id": case["destination_enrollment_id"],
                    "student_id": case["student_id"],
                    "class_id": case["destination_class_id"],
                    "academic_year": {"$in": [YEAR, str(YEAR)]},
                    "status": "relocated",
                    "enrollment_number": case["destination_legacy_number"],
                    "$and": [
                        {
                            "$or": [
                                {"previous_enrollment_number": {"$exists": False}},
                                {"previous_enrollment_number": None},
                                {"previous_enrollment_number": ""},
                            ]
                        },
                        {
                            "$or": [
                                {"source": {"$exists": False}},
                                {"source": None},
                                {"source": ""},
                            ]
                        },
                    ],
                },
                {
                    "$set": {
                        "status": "active",
                        "enrollment_number": case["current_student_number"],
                        "previous_enrollment_number": case["destination_legacy_number"],
                        "source": SOURCE,
                        "repair_provenance": "forensic_audit_student_history_and_audit_logs",
                        "repair_applied_at": now,
                        "updated_at": now,
                    }
                },
            )
            if result.matched_count != 1 or result.modified_count != 1:
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise RuntimeError(
                    f"Update otimista não casou exatamente 1 documento para {case['student_id']}."
                )
            applied.append(case["student_id"])

        post = [await assess_case(db, case) for case in CASES]
        bad_post = [x for x in post if x["disposition"] != "ALREADY_CANONICAL"]
        receipt["postcondition"] = post
        receipt["applied_student_ids"] = applied
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_receipt(receipt_path, receipt)

        if bad_post:
            raise RuntimeError(
                f"Pós-condição falhou para {len(bad_post)} caso(s); consulte {receipt_path}."
            )

        print(f"\nConcluído: {len(applied)} remanejamento(s) reparado(s).")
        print("Nenhuma nota, frequência, turma, série ou student document foi alterado.")
        print(f"Recibo: {receipt_path}")
        return 0
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-count", type=int)
    parser.add_argument("--confirm-token")
    parser.add_argument("--receipt")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
