"""
Seed idempotente — Frequência <75% para alunos de Bolsa Família.

Objetivo: popular dados realistas para validar visualmente o
mini-dashboard executivo do Acompanhamento BF
(/admin/bolsa-familia), ascendendo os chips "abaixo de 75%" e
"sem motivo informado" e habilitando o filtro de drill-down.

O que faz:
  1. Garante um calendário letivo global para 2026 (school_id=None) — se
     não existir, cria um (4 bimestres cobrindo Fev → Dez).
  2. Seleciona deterministicamente ~30% dos alunos BF ativos
     (`benefits` Bolsa Família) ordenados por nome — paridade visual.
  3. Para cada aluno selecionado, cria documentos `attendance` em 8 dias
     úteis de Março/2026 com `status='F'` — o suficiente para derrubar
     a frequência abaixo de 75% (~63%).
  4. Para a METADE dos selecionados, escreve um `bolsa_familia_tracking`
     com `reason_id` (1º motivo MEC válido), para diferenciar os chips
     "below" vs "missing" no dashboard.

Idempotência: todos os documentos criados pelo seed carregam o flag
`_seed_bf_test: 'frequency_below_75'`. Re-execução remove tudo que tem
esse flag antes de re-inserir.

Uso:
    cd /app/backend && python scripts/seed_test_bf_attendance.py
    cd /app/backend && python scripts/seed_test_bf_attendance.py --undo
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

SEED_TAG = "frequency_below_75"
ACADEMIC_YEAR = 2026

# Dias úteis de Março/2026 escolhidos como faltas (8 dias).
MARCH_2026_ABSENCE_DATES = [
    "2026-03-02", "2026-03-03", "2026-03-04",
    "2026-03-09", "2026-03-10", "2026-03-16",
    "2026-03-17", "2026-03-23",
]

DEFAULT_CALENDAR_2026 = {
    "id": "cal-2026-global-seed",
    "ano_letivo": ACADEMIC_YEAR,
    "school_id": None,
    "bimestre_1_inicio": "2026-02-02",
    "bimestre_1_fim": "2026-04-17",
    "bimestre_2_inicio": "2026-04-20",
    "bimestre_2_fim": "2026-07-03",
    "bimestre_3_inicio": "2026-08-03",
    "bimestre_3_fim": "2026-10-16",
    "bimestre_4_inicio": "2026-10-19",
    "bimestre_4_fim": "2026-12-18",
}


async def _connect():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


async def undo(db) -> dict:
    """Remove tudo que esse seed criou. Não toca em dados reais."""
    att = await db.attendance.delete_many({"_seed_bf_test": SEED_TAG})
    track = await db.bolsa_familia_tracking.delete_many({"_seed_bf_test": SEED_TAG})
    # Calendário só removemos se foi nosso (id começa com cal-2026-global-seed)
    cal = await db.calendario_letivo.delete_many({"id": DEFAULT_CALENDAR_2026["id"]})
    return {
        "attendance_removed": att.deleted_count,
        "tracking_removed": track.deleted_count,
        "calendar_removed": cal.deleted_count,
    }


async def ensure_calendar(db) -> str:
    """Cria/garante calendário 2026 global. Não sobrescreve calendário
    existente NÃO-seed (respeita dados reais)."""
    existing = await db.calendario_letivo.find_one(
        {"ano_letivo": ACADEMIC_YEAR, "school_id": None}, {"_id": 0, "id": 1}
    )
    if existing:
        return f"already_exists ({existing.get('id')})"
    await db.calendario_letivo.insert_one({**DEFAULT_CALENDAR_2026})
    return "created"


async def pick_target_students(db) -> list:
    """Retorna ~30% dos alunos BF ativos ordenados deterministicamente."""
    cursor = db.students.find(
        {
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]},
        },
        {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1},
    ).sort("full_name", 1)
    all_bf = await cursor.to_list(10000)
    if not all_bf:
        return []
    target_count = max(2, len(all_bf) * 30 // 100)
    return all_bf[:target_count]


async def first_active_reason_id(db) -> str:
    r = await db.attendance_frequency_reasons.find_one(
        {"active": True, "mec_version": "4.2"},
        {"_id": 0, "id": 1},
        sort=[("mec_group_code", 1), ("mec_subcode", 1)],
    )
    return r["id"] if r else None


async def seed_absences(db, target_students: list) -> dict:
    """Cria attendance docs com status='F' nas datas pré-definidas."""
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for s in target_students:
        sid = s["id"]
        cid = s.get("class_id")
        if not cid:
            continue
        for date_str in MARCH_2026_ABSENCE_DATES:
            doc = {
                "id": str(uuid.uuid4()),
                "academic_year": ACADEMIC_YEAR,
                "date": date_str,
                "class_id": cid,
                "course_id": None,
                "period": "regular",
                "attendance_type": "by_class_seed",
                "records": [{"student_id": sid, "status": "F"}],
                "observations": "[SEED] Frequência <75% para validação UX BF",
                "number_of_classes": 1,
                "created_at": now_iso,
                "_seed_bf_test": SEED_TAG,
            }
            await db.attendance.insert_one(doc)
            inserted += 1
    return {"attendance_docs_created": inserted}


async def seed_trackings(db, target_students: list, reason_id: str) -> dict:
    """Atribui reason_id (motivo MEC) para METADE dos alunos selecionados.

    Resultado esperado:
      - 1ª metade do grupo → tem motivo (não aparece no chip "sem motivo")
      - 2ª metade → sem motivo (aparece em "below" E em "sem motivo")
    """
    if not reason_id:
        return {"tracking_docs_created": 0, "skipped": "no_mec_reason_available"}
    half = len(target_students) // 2
    created = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for s in target_students[:half]:
        doc = {
            "student_id": s["id"],
            "school_id": s.get("school_id"),
            "month": "3",
            "academic_year": ACADEMIC_YEAR,
            "reason_id": reason_id,
            "notes": "[SEED] motivo atribuído para validar chip 'below' sem 'missing'",
            "updated_at": now_iso,
            "saved_by_role": "seed_script",
            "saved_by_user_id": None,
            "_seed_bf_test": SEED_TAG,
        }
        await db.bolsa_familia_tracking.update_one(
            {
                "student_id": s["id"],
                "school_id": s.get("school_id"),
                "month": "3",
                "academic_year": ACADEMIC_YEAR,
            },
            {"$set": doc},
            upsert=True,
        )
        created += 1
    return {"tracking_docs_created": created}


async def main(undo_mode: bool):
    db = await _connect()
    if undo_mode:
        result = await undo(db)
        print("[undo]", result)
        return

    # Sempre limpa antes (idempotência total)
    await undo(db)

    cal_status = await ensure_calendar(db)
    target_students = await pick_target_students(db)
    if not target_students:
        print("[seed] Nenhum aluno BF encontrado no banco. Abortando.")
        return
    reason_id = await first_active_reason_id(db)
    abs_result = await seed_absences(db, target_students)
    track_result = await seed_trackings(db, target_students, reason_id)

    print("[seed] OK")
    print("  Calendário 2026:", cal_status)
    print(f"  Alunos selecionados ({len(target_students)}):")
    for s in target_students:
        print(f"    - {s['full_name']} ({s['id']})")
    print("  Resultado:", {**abs_result, **track_result})
    print()
    print("Acesse /admin/bolsa-familia e selecione a escola correspondente")
    print("(ou 'Todas as Escolas') no Mês Inicial=Fev e Mês Final=Mar.")
    print("Espere ver os chips 'abaixo de 75%' e 'sem motivo informado' acesos.")


if __name__ == "__main__":
    undo_mode = "--undo" in sys.argv
    asyncio.run(main(undo_mode))
