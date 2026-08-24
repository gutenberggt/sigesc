"""Auditoria READ-ONLY da fonte canônica de matrículas.

Uso no backend/container de produção:

    python scripts/audit_enrollment_canonical.py
    python scripts/audit_enrollment_canonical.py --json

Requer MONGO_URL e DB_NAME. O script executa somente leituras (find/count) e não
altera nenhum documento. A saída usa IDs, sem nomes/CPF, para reduzir exposição
de dados pessoais em logs operacionais.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter, defaultdict

from motor.motor_asyncio import AsyncIOMotorClient


SPECIAL_PROGRAMS = {
    "aee",
    "recomposicao_aprendizagem",
    "reforco_escolar",
}
LEGACY_STATUSES = {"inactive", "inativo", "deceased", "reclassified"}


def _program(cls: dict | None) -> str:
    return str((cls or {}).get("atendimento_programa") or "").strip().lower()


def _is_special(cls: dict | None) -> bool:
    return _program(cls) in SPECIAL_PROGRAMS


def _sort_key(enr: dict) -> tuple:
    return (
        int(enr.get("academic_year") or 0),
        str(enr.get("enrollment_date") or ""),
        str(enr.get("created_at") or ""),
        str(enr.get("id") or ""),
    )


async def audit(db) -> dict:
    students = await db.students.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "status": 1,
            "school_id": 1,
            "class_id": 1,
            "enrollment_number": 1,
            "mantenedora_id": 1,
        },
    ).to_list(length=None)
    enrollments = await db.enrollments.find({}, {"_id": 0}).to_list(length=None)
    classes = await db.classes.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "academic_year": 1,
            "atendimento_programa": 1,
            "mantenedora_id": 1,
        },
    ).to_list(length=None)

    students_by_id = {s.get("id"): s for s in students if s.get("id")}
    classes_by_id = {c.get("id"): c for c in classes if c.get("id")}

    active = [e for e in enrollments if str(e.get("status") or "").lower() == "active"]
    regular_active = []
    special_active = []
    broken_active_class = []
    for e in active:
        cls = classes_by_id.get(e.get("class_id"))
        if not cls:
            broken_active_class.append(e)
        elif _is_special(cls):
            special_active.append(e)
        else:
            regular_active.append(e)

    regular_by_student: dict[str, list[dict]] = defaultdict(list)
    regular_by_student_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for e in regular_active:
        sid = e.get("student_id")
        if not sid:
            continue
        regular_by_student[sid].append(e)
        regular_by_student_year[(sid, int(e.get("academic_year") or 0))].append(e)

    multiple_regular_same_year = {
        f"{sid}:{year}": [e.get("id") for e in docs]
        for (sid, year), docs in regular_by_student_year.items()
        if len(docs) > 1
    }

    projection_mismatch = []
    active_student_without_regular = []
    for s in students:
        if str(s.get("status") or "").lower() != "active":
            continue
        sid = s.get("id")
        regs = regular_by_student.get(sid, [])
        if not regs:
            active_student_without_regular.append(sid)
            continue
        primary = sorted(regs, key=_sort_key, reverse=True)[0]
        if s.get("class_id") != primary.get("class_id"):
            projection_mismatch.append({
                "student_id": sid,
                "students_class_id": s.get("class_id"),
                "canonical_class_id": primary.get("class_id"),
                "enrollment_id": primary.get("id"),
                "academic_year": primary.get("academic_year"),
            })

    orphan_active_student = [
        e.get("id") for e in active if e.get("student_id") not in students_by_id
    ]
    school_mismatch = []
    tenant_mismatch = []
    for e in active:
        cls = classes_by_id.get(e.get("class_id"))
        if cls and e.get("school_id") != cls.get("school_id"):
            school_mismatch.append(e.get("id"))
        tenant_values = {
            str(v).strip()
            for v in (
                e.get("mantenedora_id"),
                (cls or {}).get("mantenedora_id"),
                (students_by_id.get(e.get("student_id")) or {}).get("mantenedora_id"),
            )
            if v is not None and str(v).strip()
        }
        if len(tenant_values) > 1:
            tenant_mismatch.append(e.get("id"))

    status_counts = Counter(str(e.get("status") or "__missing__").lower() for e in enrollments)
    legacy_status_counts = {
        key: count for key, count in status_counts.items() if key in LEGACY_STATUSES
    }
    special_program_counts = Counter(
        _program(classes_by_id.get(e.get("class_id"))) for e in special_active
    )

    # Mede o bug histórico da conversão de pré-matrícula: registros já marcados
    # como convertidos cujo estudante não possui qualquer enrollment.
    converted_pre = await db.pre_matriculas.find(
        {"status": "convertida"},
        {"_id": 0, "id": 1, "converted_student_id": 1, "converted_enrollment_id": 1},
    ).to_list(length=None)
    enrollment_student_ids = {e.get("student_id") for e in enrollments if e.get("student_id")}
    converted_without_enrollment = [
        {
            "pre_matricula_id": p.get("id"),
            "student_id": p.get("converted_student_id"),
        }
        for p in converted_pre
        if p.get("converted_student_id")
        and p.get("converted_student_id") not in enrollment_student_ids
    ]

    class_students_count = await db.class_students.count_documents({})

    return {
        "mode": "READ_ONLY",
        "canonical_source": "enrollments",
        "totals": {
            "students": len(students),
            "students_active": sum(
                1 for s in students if str(s.get("status") or "").lower() == "active"
            ),
            "enrollments": len(enrollments),
            "enrollments_active": len(active),
            "regular_active": len(regular_active),
            "special_active": len(special_active),
            "class_students_legacy": class_students_count,
            "converted_pre_matriculas": len(converted_pre),
        },
        "special_programs": dict(sorted(special_program_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "legacy_status_counts": legacy_status_counts,
        "issues": {
            "active_student_without_regular_enrollment": len(active_student_without_regular),
            "students_projection_mismatch": len(projection_mismatch),
            "multiple_regular_active_same_year": len(multiple_regular_same_year),
            "active_enrollment_missing_class": len(broken_active_class),
            "active_enrollment_missing_student": len(orphan_active_student),
            "active_enrollment_school_class_mismatch": len(school_mismatch),
            "active_enrollment_tenant_mismatch": len(tenant_mismatch),
            "enrollments_missing_mantenedora_id": sum(
                1 for e in enrollments if not e.get("mantenedora_id")
            ),
            "active_students_missing_mantenedora_id": sum(
                1
                for s in students
                if str(s.get("status") or "").lower() == "active"
                and not s.get("mantenedora_id")
            ),
            "converted_pre_matricula_without_enrollment": len(converted_without_enrollment),
        },
        "samples": {
            "active_student_without_regular_enrollment": active_student_without_regular[:50],
            "students_projection_mismatch": projection_mismatch[:50],
            "multiple_regular_active_same_year": dict(
                list(multiple_regular_same_year.items())[:50]
            ),
            "active_enrollment_missing_class": [e.get("id") for e in broken_active_class[:50]],
            "active_enrollment_missing_student": orphan_active_student[:50],
            "active_enrollment_school_class_mismatch": school_mismatch[:50],
            "active_enrollment_tenant_mismatch": tenant_mismatch[:50],
            "converted_pre_matricula_without_enrollment": converted_without_enrollment[:50],
        },
    }


def _human(report: dict) -> str:
    lines = [
        "SIGESC — AUDITORIA CANÔNICA DE MATRÍCULAS (READ-ONLY)",
        "=" * 60,
        "Fonte canônica pretendida: enrollments",
        "",
        "TOTAIS",
    ]
    for key, value in report["totals"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "PROBLEMAS"])
    for key, value in report["issues"].items():
        marker = "OK" if value == 0 else "ATENÇÃO"
        lines.append(f"- [{marker}] {key}: {value}")
    lines.extend(["", "STATUS LEGADOS"])
    if report["legacy_status_counts"]:
        for key, value in report["legacy_status_counts"].items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- nenhum")
    lines.extend(["", "MATRÍCULAS ESPECIAIS ATIVAS"])
    if report["special_programs"]:
        for key, value in report["special_programs"].items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- nenhuma")
    lines.append("")
    lines.append("Use --json para obter amostras por ID e saída estruturada.")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurada")

    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await audit(client[db_name])
        if args.as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print(_human(report))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
