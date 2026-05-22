"""
Seed idempotente — Alocações Institucionais (Fase 4a).

Popula `teacher_class_assignments` para acelerar desenvolvimento e
testes manuais do calendário/PDF.

Estratégia:
  - Pega N turmas com alunos ativos (limite=5 por escola).
  - Para cada turma, gera 3 alocações sintéticas que imitam um cenário
    real de anos iniciais multi-professor:
        * Professor regente (Português + Matemática) — 4 slots Seg/Ter/Qua/Qui.
        * Professor de Arte — 1 slot Sex.
        * Professor de Ed. Física — 1 slot Qua.
  - Usuários professores são reaproveitados (pega 3 distintos do sistema).
  - `source='seed'` permite limpar com --undo.

Uso:
    cd /app/backend && python scripts/seed_teacher_class_assignments.py
    cd /app/backend && python scripts/seed_teacher_class_assignments.py --undo
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

SEED_SOURCE = "seed"
DEFAULT_VALID_FROM = "2026-02-01"


async def _connect():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


async def undo(db) -> dict:
    r = await db.teacher_class_assignments.delete_many({"source": SEED_SOURCE})
    return {"removed": r.deleted_count}


async def _pick_teachers(db, n=3) -> list:
    cursor = db.users.find(
        {"role": {"$in": ["professor", "coordenador"]}, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "school_id": 1},
    ).limit(n)
    teachers = await cursor.to_list(n)
    # Fallback: se não houver 3 professores, repetir
    while len(teachers) < n and teachers:
        teachers.append(teachers[0])
    return teachers


async def _pick_classes(db, per_school=5) -> list:
    # Agrupa turmas por escola e pega até N por escola
    cursor = db.classes.find(
        {"status": {"$in": [None, "active", "Ativa", "Ativo"]}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1},
    )
    by_school: dict = {}
    async for c in cursor:
        sid = c.get("school_id") or "_no_school"
        by_school.setdefault(sid, [])
        if len(by_school[sid]) < per_school:
            by_school[sid].append(c)
    flat = []
    for v in by_school.values():
        flat.extend(v)
    return flat


def _slots_regente() -> list:
    """Regente cobre Segunda-Quinta nas aulas 1 e 2 (geminadas)."""
    return [
        {"weekday": d, "aula_numero": n, "start_time": f"0{6+n}:00", "end_time": f"0{6+n}:50"}
        for d in (1, 2, 3, 4) for n in (1, 2)
    ]


def _slots_arte() -> list:
    return [{"weekday": 5, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}]


def _slots_edfis() -> list:
    return [{"weekday": 3, "aula_numero": 3, "start_time": "09:00", "end_time": "09:50"}]


def _build_doc(*, teacher, klass, component_id, slots, valid_from, source=SEED_SOURCE):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "teacher_id": teacher["id"],
        "teacher_name": teacher.get("full_name") or teacher.get("name"),
        "class_id": klass["id"],
        "class_name": klass["name"],
        "school_id": klass.get("school_id"),
        "component_id": component_id,
        "shift": "morning",
        "weekly_slots": slots,
        "valid_from": valid_from,
        "valid_until": None,
        "is_substitute": False,
        "source": source,
        "deleted": False,
        "created_at": now,
        "created_by": "seed-script",
        "updated_at": now,
        "updated_by": "seed-script",
    }


async def seed(db) -> dict:
    teachers = await _pick_teachers(db, 3)
    if len(teachers) < 1:
        return {"error": "Nenhum professor encontrado — abortando."}
    classes = await _pick_classes(db)
    if not classes:
        return {"error": "Nenhuma turma encontrada — abortando."}

    print(f"  Professores escolhidos: {len(teachers)}")
    for t in teachers:
        print(f"    - {t.get('full_name') or t.get('name')} ({t['id'][:8]})")
    print(f"  Turmas selecionadas: {len(classes)}")

    docs = []
    for k in classes:
        # Regente: teacher 0 — componentes "regente" (Português+Matemática inline)
        docs.append(_build_doc(
            teacher=teachers[0], klass=k,
            component_id="regente-fundamental",
            slots=_slots_regente(),
            valid_from=DEFAULT_VALID_FROM,
        ))
        # Arte: teacher 1
        if len(teachers) > 1:
            docs.append(_build_doc(
                teacher=teachers[1], klass=k,
                component_id="arte",
                slots=_slots_arte(),
                valid_from=DEFAULT_VALID_FROM,
            ))
        # Ed. Física: teacher 2
        if len(teachers) > 2:
            docs.append(_build_doc(
                teacher=teachers[2], klass=k,
                component_id="educacao-fisica",
                slots=_slots_edfis(),
                valid_from=DEFAULT_VALID_FROM,
            ))

    if not docs:
        return {"created": 0}
    await db.teacher_class_assignments.insert_many(docs)
    return {"created": len(docs)}


async def main(undo_mode: bool):
    db = await _connect()
    print("=" * 60)
    print("SEED — teacher_class_assignments (Fase 4a)")
    print(f"  MODE: {'UNDO' if undo_mode else 'APPLY (idempotente)'}")
    print("=" * 60)

    # Sempre limpa o que foi seedado antes (idempotência total)
    r_clean = await db.teacher_class_assignments.delete_many({"source": SEED_SOURCE})
    print(f"  Limpou {r_clean.deleted_count} seeds anteriores")

    if undo_mode:
        print("Feito (modo undo).")
        return

    result = await seed(db)
    print(f"  Resultado: {result}")
    print("Feito.")


if __name__ == "__main__":
    asyncio.run(main("--undo" in sys.argv))
