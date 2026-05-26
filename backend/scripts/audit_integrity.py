"""
[Fase 1 — Diagnóstico Global] Auditoria de integridade institucional do SIGESC.

Roda 15 queries agregadas para mensurar o passivo de inconsistências
em toda a rede. NÃO altera dados — apenas leitura.

Uso:
    cd /app/backend && set -a && source .env && set +a && python3 scripts/audit_integrity.py
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL ou DB_NAME ausente no ambiente.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print("=" * 70)
    print(f"  AUDITORIA DE INTEGRIDADE — SIGESC (DB: {db_name})")
    print("=" * 70)

    # =========================================================
    # MATRÍCULAS / ALUNOS
    # =========================================================
    print("\n[1] MATRÍCULAS / ALUNOS")
    print("-" * 70)

    total_active = await db.students.count_documents({"status": "active"})
    print(f"  Total alunos ativos                            : {total_active:>6}")

    # 1.1 sem turma
    sem_turma = await db.students.count_documents({
        "status": "active",
        "$or": [{"class_id": None}, {"class_id": ""}, {"class_id": {"$exists": False}}],
    })
    print(f"  → 1.1  Ativos sem turma (class_id nulo)         : {sem_turma:>6}")

    # 1.2 turma inexistente (class_id aponta pra turma que não existe)
    pipeline = [
        {"$match": {"status": "active", "class_id": {"$nin": [None, ""]}}},
        {"$lookup": {"from": "classes", "localField": "class_id",
                     "foreignField": "id", "as": "_c"}},
        {"$match": {"_c": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.students.aggregate(pipeline).to_list(1)
    turma_inexist = r[0]["n"] if r else 0
    print(f"  → 1.2  Ativos com turma INEXISTENTE              : {turma_inexist:>6}")

    # 1.3 turma de outra escola
    pipeline = [
        {"$match": {"status": "active", "class_id": {"$nin": [None, ""]}}},
        {"$lookup": {"from": "classes", "localField": "class_id",
                     "foreignField": "id", "as": "_c"}},
        {"$unwind": "$_c"},
        {"$match": {"$expr": {"$ne": ["$school_id", "$_c.school_id"]}}},
        {"$count": "n"},
    ]
    r = await db.students.aggregate(pipeline).to_list(1)
    turma_outra = r[0]["n"] if r else 0
    print(f"  → 1.3  Ativos com turma de OUTRA escola          : {turma_outra:>6}")

    # 1.4 sem escola
    sem_escola = await db.students.count_documents({
        "status": "active",
        "$or": [{"school_id": None}, {"school_id": ""}, {"school_id": {"$exists": False}}],
    })
    print(f"  → 1.4  Ativos sem escola (school_id nulo)        : {sem_escola:>6}")

    # 1.5 escola inexistente
    pipeline = [
        {"$match": {"status": "active", "school_id": {"$nin": [None, ""]}}},
        {"$lookup": {"from": "schools", "localField": "school_id",
                     "foreignField": "id", "as": "_s"}},
        {"$match": {"_s": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.students.aggregate(pipeline).to_list(1)
    esc_inexist = r[0]["n"] if r else 0
    print(f"  → 1.5  Ativos com ESCOLA inexistente             : {esc_inexist:>6}")

    # 1.6 student_series vazio
    sem_serie = await db.students.count_documents({
        "status": "active",
        "$or": [{"student_series": None}, {"student_series": ""},
                {"student_series": {"$exists": False}}],
    })
    print(f"  → 1.6  Ativos com student_series VAZIO           : {sem_serie:>6}")

    # 1.7 duplicidade de matrícula ativa (mesmo student_id ↑1)
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$student_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "total"},
    ]
    r = await db.enrollments.aggregate(pipeline).to_list(1)
    dup_matr = r[0]["total"] if r else 0
    print(f"  → 1.7  Alunos com 2+ matrículas ATIVAS           : {dup_matr:>6}")

    # 1.8 disabilities[] com duplicatas
    pipeline = [
        {"$match": {"disabilities": {"$exists": True, "$ne": []}}},
        {"$addFields": {
            "_unique_count": {"$size": {"$setUnion": ["$disabilities", []]}},
            "_total_count": {"$size": "$disabilities"},
        }},
        {"$match": {"$expr": {"$lt": ["$_unique_count", "$_total_count"]}}},
        {"$count": "n"},
    ]
    r = await db.students.aggregate(pipeline).to_list(1)
    dup_dis = r[0]["n"] if r else 0
    print(f"  → 1.8  Alunos com disabilities[] DUPLICADAS      : {dup_dis:>6}")

    # =========================================================
    # AEE
    # =========================================================
    print("\n[2] AEE")
    print("-" * 70)

    total_planos = await db.planos_aee.count_documents({})
    total_atend = await db.atendimentos_aee.count_documents({})
    print(f"  Total planos AEE                               : {total_planos:>6}")
    print(f"  Total atendimentos AEE                         : {total_atend:>6}")

    # 2.1 planos sem aluno existente
    pipeline = [
        {"$lookup": {"from": "students", "localField": "student_id",
                     "foreignField": "id", "as": "_s"}},
        {"$match": {"_s": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.planos_aee.aggregate(pipeline).to_list(1)
    plano_orfao = r[0]["n"] if r else 0
    print(f"  → 2.1  Planos AEE sem aluno existente            : {plano_orfao:>6}")

    # 2.2 atendimentos sem plano existente
    pipeline = [
        {"$lookup": {"from": "planos_aee", "localField": "plano_aee_id",
                     "foreignField": "id", "as": "_p"}},
        {"$match": {"_p": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.atendimentos_aee.aggregate(pipeline).to_list(1)
    atend_orfao = r[0]["n"] if r else 0
    print(f"  → 2.2  Atendimentos AEE sem plano existente      : {atend_orfao:>6}")

    # 2.3 atendimento com student_id ≠ plano.student_id
    pipeline = [
        {"$lookup": {"from": "planos_aee", "localField": "plano_aee_id",
                     "foreignField": "id", "as": "_p"}},
        {"$unwind": "$_p"},
        {"$match": {"$expr": {"$ne": ["$student_id", "$_p.student_id"]}}},
        {"$count": "n"},
    ]
    r = await db.atendimentos_aee.aggregate(pipeline).to_list(1)
    atend_incons = r[0]["n"] if r else 0
    print(f"  → 2.3  Atendimentos com student_id ≠ plano       : {atend_incons:>6}")

    # 2.4 alunos com has_disability=true mas SEM plano AEE ativo
    pipeline = [
        {"$match": {"status": "active", "has_disability": True}},
        {"$lookup": {
            "from": "planos_aee",
            "let": {"sid": "$id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$student_id", "$$sid"]},
                    {"$eq": ["$status", "ativo"]},
                ]}}},
                {"$limit": 1},
            ],
            "as": "_planos",
        }},
        {"$match": {"_planos": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.students.aggregate(pipeline).to_list(1)
    has_dis_no_plan = r[0]["n"] if r else 0
    print(f"  → 2.4  has_disability=true SEM plano AEE ativo   : {has_dis_no_plan:>6}")

    # 2.5 alunos com plano AEE ativo mas SEM has_disability nem disabilities
    pipeline = [
        {"$match": {"status": "ativo"}},
        {"$lookup": {"from": "students", "localField": "student_id",
                     "foreignField": "id", "as": "_s"}},
        {"$unwind": "$_s"},
        {"$match": {"$and": [
            {"$or": [
                {"_s.has_disability": False},
                {"_s.has_disability": None},
                {"_s.has_disability": {"$exists": False}},
            ]},
            {"$or": [
                {"_s.disabilities": []},
                {"_s.disabilities": None},
                {"_s.disabilities": {"$exists": False}},
            ]},
        ]}},
        {"$count": "n"},
    ]
    r = await db.planos_aee.aggregate(pipeline).to_list(1)
    plan_no_dis = r[0]["n"] if r else 0
    print(f"  → 2.5  Plano AEE ativo sem deficiência cadastrada: {plan_no_dis:>6}")

    # =========================================================
    # TURMAS
    # =========================================================
    print("\n[3] TURMAS")
    print("-" * 70)

    total_classes = await db.classes.count_documents({})
    print(f"  Total turmas                                   : {total_classes:>6}")

    # 3.1 turma com school_id inexistente
    pipeline = [
        {"$lookup": {"from": "schools", "localField": "school_id",
                     "foreignField": "id", "as": "_s"}},
        {"$match": {"_s": {"$eq": []}}},
        {"$count": "n"},
    ]
    r = await db.classes.aggregate(pipeline).to_list(1)
    cl_no_school = r[0]["n"] if r else 0
    print(f"  → 3.1  Turmas com escola INEXISTENTE             : {cl_no_school:>6}")

    # 3.2 Integral indicado por turno vs atendimento_programa
    integral_via_atend = await db.classes.count_documents({"atendimento_programa": "atendimento_integral"})
    integral_via_turno = await db.classes.count_documents({"turno": "full_time"})
    print(f"  → 3.2  Turmas atendimento_programa=integral       : {integral_via_atend:>6}")
    print(f"  → 3.3  Turmas turno=full_time                     : {integral_via_turno:>6}")
    if integral_via_atend != integral_via_turno:
        print(f"         ⚠ Divergência entre os 2 campos: investigar")

    print()
    print("=" * 70)
    print("  RESUMO EXECUTIVO — PASSIVO TOTAL")
    print("=" * 70)
    total_passivo_matricula = (sem_turma + turma_inexist + turma_outra +
                                sem_escola + esc_inexist + dup_matr + dup_dis)
    total_passivo_aee = plano_orfao + atend_orfao + atend_incons
    print(f"  Passivo matrículas (1.1 a 1.8 excl. série vazia) : {total_passivo_matricula:>6}")
    print(f"  Passivo AEE (2.1 a 2.3)                          : {total_passivo_aee:>6}")
    print(f"  Sem student_series (informacional)               : {sem_serie:>6}")
    print(f"  has_disability sem plano AEE (informacional)     : {has_dis_no_plan:>6}")
    print("=" * 70)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
