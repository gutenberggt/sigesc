#!/usr/bin/env python3
"""Reconciliação P0 de matrículas canônicas ausentes em 2026.

Ferramenta deliberadamente conservadora para reparar SOMENTE estudantes que:
- constam no manifesto READ-ONLY como `ready`;
- permanecem ativos e projetados na mesma turma regular de 2026;
- não possuem outro documento em `enrollments` (salvo execução idempotente já concluída);
- possuem número de matrícula preservável e não conflitante;
- possuem evidência acadêmica (nota ou frequência) NA MESMA turma em 2026;
- possuem escola/mantenedora/turma coerentes;
- possuem data de matrícula comprovável em `students.enrollment_date` ou histórico.

Por padrão é READ-ONLY. Escrita exige simultaneamente:
    --apply --confirm-count N --confirm-token RECONCILE-P0-2026

Exemplo de prévia:
    python scripts/reconcile_enrollment_p0_2026.py \
      --manifest /tmp/sigesc_enrollment_p0_repair_readiness.json

Execução real (somente após revisão/PR/deploy):
    python scripts/reconcile_enrollment_p0_2026.py \
      --manifest /tmp/sigesc_enrollment_p0_repair_readiness.json \
      --apply --confirm-count 108 --confirm-token RECONCILE-P0-2026

A ferramenta NÃO trata:
- ONLY_NON_ACTIVE_ENROLLMENTS;
- ACTIVE_SPECIAL_ONLY/AEE;
- duplicidade cadastral;
- matrículas órfãs ou turmas inexistentes;
- qualquer caso presente em `quarantine`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient

# Permite execução direta em /app/backend/scripts.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.enrollment_service import (  # noqa: E402
    EnrollmentDomainError,
    create_active_enrollment,
    is_special_class,
)

YEAR = 2026
CONFIRM_TOKEN = "RECONCILE-P0-2026"
SOURCE = "repair:p0-enrollment-reconcile-2026"


@dataclass
class Assessment:
    student_id: str
    full_name: str
    disposition: str
    blockers: list[str]
    student: dict[str, Any]
    class_doc: dict[str, Any]
    enrollment_date: Optional[str]
    grade_count: int
    attendance_count: int
    existing_exact_enrollment: Optional[dict[str, Any]] = None

    @property
    def ready(self) -> bool:
        return self.disposition == "READY" and not self.blockers


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _year_eq(value: Any, year: int = YEAR) -> bool:
    return _norm(value) == str(year)


def _active(value: Any) -> bool:
    return _norm(value).lower() == "active"


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


def evaluate_snapshot(
    *,
    manifest_row: dict[str, Any],
    student: Optional[dict[str, Any]],
    class_doc: Optional[dict[str, Any]],
    enrollment_docs: list[dict[str, Any]],
    same_number_student_ids: list[str],
    same_number_enrollment_student_ids: list[str],
    grade_count: int,
    attendance_count: int,
    enrollment_date: Optional[str],
) -> tuple[str, list[str], Optional[dict[str, Any]]]:
    """Avalia um candidato sem alterar banco; usada também nos testes."""
    blockers: list[str] = []
    sid = _norm(manifest_row.get("student_id"))
    expected_class_id = _norm(manifest_row.get("class_id"))

    if not sid:
        return "BLOCKED", ["MANIFEST_STUDENT_ID_MISSING"], None
    if not student:
        return "BLOCKED", ["STUDENT_NOT_FOUND"], None
    if _norm(student.get("id")) != sid:
        blockers.append("STUDENT_ID_DIVERGED")
    if not _active(student.get("status")):
        blockers.append("STUDENT_NOT_ACTIVE")

    current_class_id = _norm(student.get("class_id"))
    if not current_class_id:
        blockers.append("STUDENT_CLASS_MISSING")
    if expected_class_id and current_class_id != expected_class_id:
        blockers.append("CLASS_CHANGED_SINCE_MANIFEST")

    if not class_doc:
        blockers.append("CLASS_NOT_FOUND")
    else:
        if _norm(class_doc.get("id")) != current_class_id:
            blockers.append("CLASS_LOOKUP_DIVERGED")
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

    number = _norm(student.get("enrollment_number"))
    manifest_number = _norm(manifest_row.get("enrollment_number"))
    if not number:
        blockers.append("MISSING_ENROLLMENT_NUMBER")
    if manifest_number and number != manifest_number:
        blockers.append("ENROLLMENT_NUMBER_CHANGED_SINCE_MANIFEST")

    foreign_students = [x for x in same_number_student_ids if _norm(x) and _norm(x) != sid]
    if foreign_students:
        blockers.append("ENROLLMENT_NUMBER_DUPLICATED_IN_STUDENTS")
    foreign_enrollments = [x for x in same_number_enrollment_student_ids if _norm(x) and _norm(x) != sid]
    if foreign_enrollments:
        blockers.append("ENROLLMENT_NUMBER_USED_BY_OTHER_STUDENT")

    exact = None
    for e in enrollment_docs:
        if (
            _active(e.get("status"))
            and _year_eq(e.get("academic_year"))
            and _norm(e.get("class_id")) == current_class_id
        ):
            exact = e
            break

    if exact:
        if _norm(exact.get("enrollment_number")) != number:
            blockers.append("EXISTING_CANONICAL_NUMBER_MISMATCH")
        if blockers:
            return "BLOCKED", sorted(set(blockers)), exact
        return "ALREADY_CANONICAL", [], exact

    if enrollment_docs:
        blockers.append("ENROLLMENT_DOCUMENT_ALREADY_EXISTS")

    # P0: atividade acadêmica deve comprovar a MESMA turma atual.
    if int(grade_count or 0) <= 0 and int(attendance_count or 0) <= 0:
        blockers.append("NO_CURRENT_CLASS_ACADEMIC_ACTIVITY_2026")

    if not _norm(enrollment_date):
        blockers.append("MISSING_ENROLLMENT_DATE_EVIDENCE")

    return ("READY" if not blockers else "BLOCKED"), sorted(set(blockers)), exact


async def resolve_enrollment_date(db, student: dict[str, Any], class_id: str) -> Optional[str]:
    direct = _norm(student.get("enrollment_date"))
    if direct:
        return direct

    # Prefere eventos explicitamente ligados à turma atual.
    history = await db.student_history.find_one(
        {
            "student_id": student.get("id"),
            "$or": [
                {"class_id": class_id},
                {"new_class_id": class_id},
            ],
            "action_type": {"$in": ["matricula", "remanejamento", "relocated"]},
        },
        {"_id": 0, "action_date": 1},
        sort=[("action_date", -1)],
    )
    if history and history.get("action_date"):
        return str(history["action_date"])
    return None


async def academic_activity_counts(db, student_id: str, class_id: str) -> tuple[int, int]:
    grades = await db.grades.count_documents(
        {
            "student_id": student_id,
            "class_id": class_id,
            "academic_year": {"$in": [YEAR, str(YEAR)]},
        }
    )
    attendance = await db.attendance.count_documents(
        {
            "class_id": class_id,
            "records": {"$elemMatch": {"student_id": student_id}},
            "$or": [
                {"academic_year": {"$in": [YEAR, str(YEAR)]}},
                {"date": {"$regex": f"^{YEAR}-"}},
            ],
        }
    )
    return int(grades), int(attendance)


async def assess_candidate(db, row: dict[str, Any]) -> Assessment:
    sid = _norm(row.get("student_id"))
    student = await db.students.find_one({"id": sid}, {"_id": 0})
    class_doc: dict[str, Any] = {}
    class_id = _norm((student or {}).get("class_id"))
    if class_id:
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0}) or {}

    enrollment_docs = await db.enrollments.find(
        {"student_id": sid}, {"_id": 0}
    ).to_list(length=100)

    number = _norm((student or {}).get("enrollment_number"))
    same_student_ids: list[str] = []
    same_enrollment_student_ids: list[str] = []
    if number:
        same_students = await db.students.find(
            {"enrollment_number": number}, {"_id": 0, "id": 1}
        ).to_list(length=20)
        same_student_ids = [_norm(x.get("id")) for x in same_students]

        same_enrollments = await db.enrollments.find(
            {"enrollment_number": number}, {"_id": 0, "student_id": 1}
        ).to_list(length=20)
        same_enrollment_student_ids = [_norm(x.get("student_id")) for x in same_enrollments]

    grade_count = 0
    attendance_count = 0
    enrollment_date = None
    if student and class_id:
        grade_count, attendance_count = await academic_activity_counts(db, sid, class_id)
        enrollment_date = await resolve_enrollment_date(db, student, class_id)

    disposition, blockers, exact = evaluate_snapshot(
        manifest_row=row,
        student=student,
        class_doc=class_doc,
        enrollment_docs=enrollment_docs,
        same_number_student_ids=same_student_ids,
        same_number_enrollment_student_ids=same_enrollment_student_ids,
        grade_count=grade_count,
        attendance_count=attendance_count,
        enrollment_date=enrollment_date,
    )

    return Assessment(
        student_id=sid,
        full_name=_norm((student or {}).get("full_name") or row.get("full_name")),
        disposition=disposition,
        blockers=blockers,
        student=student or {},
        class_doc=class_doc,
        enrollment_date=enrollment_date,
        grade_count=grade_count,
        attendance_count=attendance_count,
        existing_exact_enrollment=exact,
    )


def _receipt_path(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"/tmp/sigesc_enrollment_p0_reconcile_receipt_{stamp}.json"


def _write_receipt(path: str, receipt: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2, default=str)


async def run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    rows = manifest["ready"]

    # Nunca inclui quarentena, mesmo se o manifesto estiver adulterado de forma simples.
    quarantine_ids = {
        _norm(x.get("student_id")) for x in manifest.get("quarantine", []) if isinstance(x, dict)
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
    receipt_path = _receipt_path(args.receipt)
    receipt: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "year": YEAR,
        "source": SOURCE,
        "manifest": args.manifest,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "created": [],
        "already_canonical": [],
        "blocked": [],
    }

    try:
        assessments: list[Assessment] = []
        for row in rows:
            assessments.append(await assess_candidate(db, row))

        blocked = [a for a in assessments if a.disposition == "BLOCKED"]
        already = [a for a in assessments if a.disposition == "ALREADY_CANONICAL"]
        ready = [a for a in assessments if a.ready]

        print("SIGESC — RECONCILIAÇÃO P0 DE MATRÍCULAS 2026")
        print("=" * 64)
        print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN / READ-ONLY'}")
        print(f"Manifesto ready considerado: {len(rows)}")
        print(f"READY: {len(ready)}")
        print(f"ALREADY_CANONICAL: {len(already)}")
        print(f"BLOCKED: {len(blocked)}")

        for a in blocked:
            item = {
                "student_id": a.student_id,
                "full_name": a.full_name,
                "blockers": a.blockers,
            }
            receipt["blocked"].append(item)
            print(f"BLOCKED | {a.student_id} | {a.full_name} | {','.join(a.blockers)}")

        for a in already:
            receipt["already_canonical"].append({
                "student_id": a.student_id,
                "full_name": a.full_name,
                "enrollment_id": (a.existing_exact_enrollment or {}).get("id"),
            })

        # Fail-closed: nenhum write se UMA linha mudou desde o manifesto.
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

        # APPLY: revalida cada caso imediatamente antes do insert.
        for row in rows:
            sid = _norm(row.get("student_id"))
            current = await assess_candidate(db, row)
            if current.disposition == "ALREADY_CANONICAL":
                continue
            if not current.ready:
                receipt["blocked"].append({
                    "student_id": current.student_id,
                    "full_name": current.full_name,
                    "blockers": current.blockers,
                    "stage": "pre_insert_revalidation",
                })
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise RuntimeError(
                    f"Revalidação falhou para {sid}; lote interrompido. Consulte {receipt_path}."
                )

            student = current.student
            class_doc = current.class_doc
            try:
                result = await create_active_enrollment(
                    db,
                    student_id=sid,
                    school_id=_norm(student.get("school_id")),
                    class_id=_norm(student.get("class_id")),
                    academic_year=YEAR,
                    enrollment_date=current.enrollment_date,
                    enrollment_number=_norm(student.get("enrollment_number")),
                    student_series=student.get("student_series") or class_doc.get("grade_level"),
                    mantenedora_id=_norm(student.get("mantenedora_id")),
                    source=SOURCE,
                )
            except EnrollmentDomainError as exc:
                receipt["blocked"].append({
                    "student_id": sid,
                    "full_name": current.full_name,
                    "blockers": [f"DOMAIN_ERROR:{type(exc).__name__}:{exc}"],
                    "stage": "create_active_enrollment",
                })
                receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
                _write_receipt(receipt_path, receipt)
                raise

            enrollment = result["enrollment"]
            receipt["created"].append({
                "student_id": sid,
                "full_name": current.full_name,
                "enrollment_id": enrollment.get("id"),
                "class_id": enrollment.get("class_id"),
                "academic_year": enrollment.get("academic_year"),
                "enrollment_number": enrollment.get("enrollment_number"),
                "source": enrollment.get("source"),
            })
            # Persistência incremental do recibo permite auditoria mesmo em falha intermediária.
            _write_receipt(receipt_path, receipt)

        # Pós-condição: todos os itens do manifesto agora devem ser canônicos ou já canônicos.
        post_blocked = []
        for row in rows:
            after = await assess_candidate(db, row)
            if after.disposition != "ALREADY_CANONICAL":
                post_blocked.append({
                    "student_id": after.student_id,
                    "full_name": after.full_name,
                    "disposition": after.disposition,
                    "blockers": after.blockers,
                })

        receipt["postcondition_failures"] = post_blocked
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_receipt(receipt_path, receipt)

        if post_blocked:
            print(f"\nERRO: pós-condição falhou para {len(post_blocked)} estudante(s).")
            print(f"Recibo: {receipt_path}")
            return 3

        print(f"\nConcluído: {len(receipt['created'])} matrícula(s) criada(s).")
        print(f"Já canônicas: {len(already)}")
        print("Notas e frequências não foram alteradas.")
        print(f"Recibo: {receipt_path}")
        return 0
    finally:
        client.close()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Manifesto JSON READ-ONLY aprovado.")
    parser.add_argument("--apply", action="store_true", help="Habilita escrita; ausente = dry-run.")
    parser.add_argument("--confirm-count", type=int, default=None)
    parser.add_argument("--confirm-token", default=None)
    parser.add_argument("--receipt", default=None, help="Caminho opcional para recibo JSON.")
    return parser.parse_args(argv)


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
