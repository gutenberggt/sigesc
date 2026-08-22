"""Auditoria read-only dos horários de Planos/Atendimentos AEE de 2026.

Não executa insert/update/delete. Lista intervalos inválidos, fora da janela
06:00–22:00, invertidos, durações suspeitas (>4h) e divergências entre a duração
armazenada e a duração cronológica esperada.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import os

from motor.motor_asyncio import AsyncIOMotorClient

from aee_v2.time_integrity import classify_time_interval


def _pair(doc):
    return (
        str(doc.get("horario_inicio") or "").strip() or "-",
        str(doc.get("horario_fim") or "").strip() or "-",
    )


def _fmt_issues(result):
    return ", ".join(issue["code"] for issue in result["issues"]) or "OK"


async def main(year: int):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "sigesc_db")]

    planos = await db.planos_aee.find(
        {"academic_year": year},
        {
            "_id": 0,
            "id": 1,
            "student_id": 1,
            "school_id": 1,
            "status": 1,
            "horario_inicio": 1,
            "horario_fim": 1,
            "dias_atendimento": 1,
        },
    ).to_list(None)

    plan_ids = [p.get("id") for p in planos if p.get("id")]
    atendimentos = await db.atendimentos_aee.find(
        {
            "$or": [
                {"academic_year": year},
                {"plano_aee_id": {"$in": plan_ids}},
            ]
        },
        {
            "_id": 0,
            "id": 1,
            "plano_aee_id": 1,
            "student_id": 1,
            "school_id": 1,
            "academic_year": 1,
            "data": 1,
            "horario_inicio": 1,
            "horario_fim": 1,
            "duracao_minutos": 1,
        },
    ).to_list(None)

    student_ids = {
        str(doc.get("student_id"))
        for doc in [*planos, *atendimentos]
        if doc.get("student_id")
    }
    students = {}
    if student_ids:
        docs = await db.students.find(
            {"id": {"$in": list(student_ids)}},
            {"_id": 0, "id": 1, "full_name": 1},
        ).to_list(None)
        students = {str(d.get("id")): d.get("full_name") or "N/A" for d in docs}

    school_ids = {
        str(doc.get("school_id"))
        for doc in [*planos, *atendimentos]
        if doc.get("school_id")
    }
    schools = {}
    if school_ids:
        docs = await db.schools.find(
            {"id": {"$in": list(school_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(None)
        schools = {str(d.get("id")): d.get("name") or "N/A" for d in docs}

    plan_pairs = Counter(_pair(p) for p in planos)
    attendance_pairs = Counter(_pair(a) for a in atendimentos)

    flagged_plans = []
    for plano in planos:
        result = classify_time_interval(
            plano.get("horario_inicio"),
            plano.get("horario_fim"),
        )
        if result["issues"]:
            flagged_plans.append((plano, result))

    flagged_attendances = []
    for atendimento in atendimentos:
        result = classify_time_interval(
            atendimento.get("horario_inicio"),
            atendimento.get("horario_fim"),
            stored_duration=atendimento.get("duracao_minutos"),
        )
        if result["issues"]:
            flagged_attendances.append((atendimento, result))

    print("=" * 78)
    print(f" AEE — AUDITORIA TEMPORAL READ-ONLY — {year}")
    print("=" * 78)
    print(f"Planos analisados       : {len(planos)}")
    print(f"Atendimentos analisados : {len(atendimentos)}")
    print(f"Planos com alerta       : {len(flagged_plans)}")
    print(f"Atendimentos com alerta : {len(flagged_attendances)}")

    print("\nPARES DE HORÁRIO — PLANOS")
    for pair, count in sorted(plan_pairs.items()):
        print(f"  {pair[0]} -> {pair[1]} : {count}")

    print("\nPARES DE HORÁRIO — ATENDIMENTOS")
    for pair, count in sorted(attendance_pairs.items()):
        print(f"  {pair[0]} -> {pair[1]} : {count}")

    if flagged_plans:
        print("\n" + "=" * 78)
        print(" PLANOS COM ALERTA")
        print("=" * 78)
        for plano, result in flagged_plans:
            sid = str(plano.get("student_id") or "")
            school_id = str(plano.get("school_id") or "")
            print(
                f"plano={plano.get('id')} | estudante={students.get(sid, sid or 'N/A')} | "
                f"escola={schools.get(school_id, school_id or 'N/A')} | "
                f"dias={plano.get('dias_atendimento')} | "
                f"{plano.get('horario_inicio')} -> {plano.get('horario_fim')} | "
                f"issues={_fmt_issues(result)}"
            )

    if flagged_attendances:
        print("\n" + "=" * 78)
        print(" ATENDIMENTOS COM ALERTA")
        print("=" * 78)
        for atendimento, result in flagged_attendances:
            sid = str(atendimento.get("student_id") or "")
            school_id = str(atendimento.get("school_id") or "")
            print(
                f"atendimento={atendimento.get('id')} | plano={atendimento.get('plano_aee_id')} | "
                f"estudante={students.get(sid, sid or 'N/A')} | "
                f"escola={schools.get(school_id, school_id or 'N/A')} | data={atendimento.get('data')} | "
                f"{atendimento.get('horario_inicio')} -> {atendimento.get('horario_fim')} | "
                f"duracao_salva={atendimento.get('duracao_minutos')} | "
                f"duracao_esperada={result.get('duration_minutes')} | issues={_fmt_issues(result)}"
            )

    print("\n" + "=" * 78)
    print(" SOMENTE LEITURA — NENHUM INSERT / UPDATE / DELETE EXECUTADO")
    print("=" * 78)
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    asyncio.run(main(args.year))
