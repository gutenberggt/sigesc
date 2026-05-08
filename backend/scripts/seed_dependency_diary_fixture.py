"""
Seeder da fixture E2E `fixture_dependency_diary_v1`.

[Fev/2026] Ver /app/docs/DIARY_API_CONTRACT.md item 20.

Dataset CONGELADO para testes de regressão da Fase 2+ do Diário com Dependência.

Uso:
    cd /app/backend && python -m scripts.seed_dependency_diary_fixture

Idempotente: roda múltiplas vezes sem duplicar.
Identifica os documentos por IDs fixos (`fix_*`).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient


# ============================================================================
# IDs fixos da fixture — NÃO mudar (testes E2E dependem deles).
# ============================================================================
FIX = {
    "mantenedora": "fix_mant_v1",
    "school": "fix_sch_v1",
    "class": "fix_cl_v1",
    "course_mat": "fix_co_mat_v1",
    "course_pt": "fix_co_pt_v1",
    "students": {
        # 5 regulares
        "ana":   "fix_stu_ana",
        "bruno": "fix_stu_bruno",
        "carlos": "fix_stu_carlos",
        "diana": "fix_stu_diana",
        "eva":   "fix_stu_eva",
        # 2 com dep
        "felipe":   "fix_stu_felipe",
        "gabriela": "fix_stu_gabriela",
        # 1 só dep
        "heitor": "fix_stu_heitor",
        # 1 dep cancelada
        "ivo": "fix_stu_ivo",
        # 1 dep concluída
        "julia": "fix_stu_julia",
    },
    "deps": {
        "felipe_mat":   "fix_dep_felipe_mat",
        "gabriela_mat": "fix_dep_gabriela_mat",
        "heitor_mat":   "fix_dep_heitor_mat",
        "heitor_pt":    "fix_dep_heitor_pt",
        "ivo_cancelled":  "fix_dep_ivo_cancelled",
        "julia_completed": "fix_dep_julia_completed",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"[fixture] Conectado a {db_name}")

    # ----- Mantenedora com flags habilitadas -----
    await db.mantenedoras.update_one(
        {"id": FIX["mantenedora"]},
        {"$set": {
            "id": FIX["mantenedora"],
            "name": "Mantenedora Fixture v1",
            "aprovacao_com_dependencia": True,
            "max_componentes_dependencia": 5,
            "cursar_apenas_dependencia": True,
            "qtd_componentes_apenas_dependencia": 4,
            "updated_at": _now(),
        }},
        upsert=True,
    )

    # ----- Escola -----
    await db.schools.update_one(
        {"id": FIX["school"]},
        {"$set": {
            "id": FIX["school"], "name": "Escola Fixture v1",
            "mantenedora_id": FIX["mantenedora"],
        }},
        upsert=True,
    )

    # ----- Turma -----
    await db.classes.update_one(
        {"id": FIX["class"]},
        {"$set": {
            "id": FIX["class"], "name": "5º ano A (Fixture)",
            "school_id": FIX["school"], "mantenedora_id": FIX["mantenedora"],
            "series": "5º ano", "academic_year": 2026,
        }},
        upsert=True,
    )

    # ----- Componentes -----
    for cid, name in [(FIX["course_mat"], "Matemática"), (FIX["course_pt"], "Português")]:
        await db.courses.update_one(
            {"id": cid},
            {"$set": {
                "id": cid, "name": name, "carga_horaria": 80,
                "mantenedora_id": FIX["mantenedora"],
            }},
            upsert=True,
        )

    # ----- Alunos -----
    students_def = [
        ("ana",      "Ana da Silva",       "none"),
        ("bruno",    "Bruno Pereira",      "none"),
        ("carlos",   "Carlos Souza",       "none"),
        ("diana",    "Diana Lopes",        "none"),
        ("eva",      "Eva Martins",        "none"),
        ("felipe",   "Felipe Costa",       "with_dependency"),
        ("gabriela", "Gabriela Rocha",     "with_dependency"),
        ("heitor",   "Heitor Almeida",     "dependency_only"),
        ("ivo",      "Ivo Nascimento",     "with_dependency"),
        ("julia",    "Júlia Ferreira",     "with_dependency"),
    ]
    for key, name, mode in students_def:
        sid = FIX["students"][key]
        await db.students.update_one(
            {"id": sid},
            {"$set": {
                "id": sid, "full_name": name,
                "nome_busca": name.lower(),  # alimenta autocomplete
                "school_id": FIX["school"],
                "class_id": FIX["class"] if key not in ("heitor",) else None,
                "mantenedora_id": FIX["mantenedora"],
                "status": "active",
                "dependency_mode": mode,
            }},
            upsert=True,
        )

    # ----- Enrollments (regulares e with_dep) -----
    enrolled_keys = ["ana", "bruno", "carlos", "diana", "eva", "felipe", "gabriela", "ivo", "julia"]
    for key in enrolled_keys:
        sid = FIX["students"][key]
        await db.enrollments.update_one(
            {"student_id": sid, "class_id": FIX["class"], "academic_year": 2026},
            {"$set": {
                "student_id": sid, "class_id": FIX["class"], "academic_year": 2026,
                "school_id": FIX["school"], "mantenedora_id": FIX["mantenedora"],
                "status": "active",
            }},
            upsert=True,
        )

    # ----- Dependências -----
    deps_def = [
        # Felipe — Mat ativa
        ("felipe_mat", FIX["students"]["felipe"], FIX["course_mat"], "active", None, None),
        # Gabriela — Mat ativa
        ("gabriela_mat", FIX["students"]["gabriela"], FIX["course_mat"], "active", None, None),
        # Heitor — Mat + PT ativas (apenas dependência)
        ("heitor_mat", FIX["students"]["heitor"], FIX["course_mat"], "active", None, None),
        ("heitor_pt", FIX["students"]["heitor"], FIX["course_pt"], "active", None, None),
        # Ivo — cancelada
        ("ivo_cancelled", FIX["students"]["ivo"], FIX["course_mat"], "cancelled",
         None, "[fixture] cancelada para teste"),
        # Júlia — concluída
        ("julia_completed", FIX["students"]["julia"], FIX["course_mat"], "completed",
         7.5, "[fixture] concluída para teste"),
    ]
    for dkey, sid, cid, status, grade, reason in deps_def:
        did = FIX["deps"][dkey]
        await db.student_dependencies.update_one(
            {"id": did},
            {"$set": {
                "id": did, "student_id": sid,
                "school_id": FIX["school"], "class_id": FIX["class"],
                "course_id": cid, "academic_year": 2026,
                "origin_academic_year": 2025,
                "mantenedora_id": FIX["mantenedora"],
                "status": status,
                "status_reason": reason,
                "final_grade": grade,
                "completed_at": _now() if status in ("completed", "failed") else None,
            }},
            upsert=True,
        )

    # ----- Sumário -----
    counts = {
        "students": await db.students.count_documents({"mantenedora_id": FIX["mantenedora"]}),
        "deps_active": await db.student_dependencies.count_documents(
            {"mantenedora_id": FIX["mantenedora"], "status": "active"}
        ),
        "deps_total": await db.student_dependencies.count_documents(
            {"mantenedora_id": FIX["mantenedora"]}
        ),
        "enrollments": await db.enrollments.count_documents(
            {"mantenedora_id": FIX["mantenedora"]}
        ),
    }
    print(f"[fixture] OK — {counts}")

    expected = {"students": 10, "deps_active": 4, "deps_total": 6, "enrollments": 9}
    for k, v in expected.items():
        if counts[k] != v:
            print(f"[fixture] ⚠️  {k}={counts[k]} (esperado {v}) — pode haver dados antigos.")
    print("[fixture] Concluído. Dataset 'fixture_dependency_diary_v1' pronto.")


if __name__ == "__main__":
    asyncio.run(seed())
