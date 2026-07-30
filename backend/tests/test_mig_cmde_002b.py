"""
Sprint 002.b — Testes do FrequencyBatchBuilder.

Cobre: consolidação a partir do SSoT (read-only), prontidão, idempotência, isolamento
multi-tenant, dados incompletos, dry-run vs persistência, e NÃO-mutação do SSoT (attendance).
"""
import sys, os, asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()

from motor.motor_asyncio import AsyncIOMotorClient
from mig.cmde.batch_builder import FrequencyBatchBuilder
from mig.cmde.frequency_repository import BATCHES, QUEUE
from mig.cmde.dtos import FrequencyBatchRequestDTO
from mig.core.ids import compute_idempotency_key

COMP = "2020-05"                      # competência antiga → sempre ENCERRADA
MONTH = 5
TA, TB = "bb_tenant_A", "bb_tenant_B"
CLASS_A, CLASS_B = "bb_class_A", "bb_class_B"
SCHOOL_A, SCHOOL_B = "bb_school_A", "bb_school_B"


async def _seed(db):
    await _clean(db)
    # Escolas
    await db.schools.insert_many([
        {"id": SCHOOL_A, "name": "Escola A", "inep_code": "11111111", "mantenedora_id": TA},
        {"id": SCHOOL_B, "name": "Escola B", "inep_code": "22222222", "mantenedora_id": TB},
    ])
    # Turmas
    await db.classes.insert_many([
        {"id": CLASS_A, "school_id": SCHOOL_A, "mantenedora_id": TA},
        {"id": CLASS_B, "school_id": SCHOOL_B, "mantenedora_id": TB},
    ])
    # Alunos: A1 pronto (cpf+inep), A2 sem cpf/nis → pendência; B1 pronto (tenant B)
    await db.students.insert_many([
        {"id": "bb_A1", "full_name": "Aluno A1", "cpf": "111", "nis": "", "inep_code": "",
         "school_id": SCHOOL_A, "status": "active"},
        {"id": "bb_A2", "full_name": "Aluno A2", "cpf": "", "nis": "", "inep_code": "",
         "school_id": SCHOOL_A, "status": "active"},
        {"id": "bb_B1", "full_name": "Aluno B1", "cpf": "999", "nis": "", "inep_code": "",
         "school_id": SCHOOL_B, "status": "active"},
    ])
    # Attendance (SSoT): tenant A, competência 2020-05
    # A1: 3 dias, 1 falta (F) ; A2: 2 dias, 0 falta
    await db.attendance.insert_many([
        {"id": "bb_att_1", "class_id": CLASS_A, "mantenedora_id": TA, "date": f"{COMP}-04",
         "records": [{"student_id": "bb_A1", "status": "P"}, {"student_id": "bb_A2", "status": "P"}]},
        {"id": "bb_att_2", "class_id": CLASS_A, "mantenedora_id": TA, "date": f"{COMP}-05",
         "records": [{"student_id": "bb_A1", "status": "F"}, {"student_id": "bb_A2", "status": "P"}]},
        {"id": "bb_att_3", "class_id": CLASS_A, "mantenedora_id": TA, "date": f"{COMP}-06",
         "records": [{"student_id": "bb_A1", "status": "P"}]},
        # tenant B, mesma competência
        {"id": "bb_att_4", "class_id": CLASS_B, "mantenedora_id": TB, "date": f"{COMP}-04",
         "records": [{"student_id": "bb_B1", "status": "P"}]},
    ])


async def _clean(db):
    for sid in ([SCHOOL_A, SCHOOL_B]):
        pass
    await db.schools.delete_many({"id": {"$in": [SCHOOL_A, SCHOOL_B]}})
    await db.classes.delete_many({"id": {"$in": [CLASS_A, CLASS_B]}})
    await db.students.delete_many({"id": {"$in": ["bb_A1", "bb_A2", "bb_B1"]}})
    await db.attendance.delete_many({"mantenedora_id": {"$in": [TA, TB]}})
    await db[BATCHES].delete_many({"tenant": {"$in": [TA, TB]}})
    await db[QUEUE].delete_many({"tenant": {"$in": [TA, TB]}})


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await _seed(db)
    builder = FrequencyBatchBuilder(db, batch_size=200)

    # --- 1. Preview tenant A (dry-run padrão) ---
    res = await builder.build(FrequencyBatchRequestDTO(competencia=COMP, dry_run=True),
                              context={"tenant": TA, "actor": "tester"})
    assert res["analyzed"] == 2, res              # A1 e A2 (não vê B1)
    assert res["ready_count"] == 1 and res["pending_count"] == 1, res
    assert res["competencia_fechada"] is True and res["dry_run"] is True
    assert res["lotes_previstos"] == 1 and res["persisted"] is False
    # A1 consolidação: 3 dias letivos, 1 falta válida (F isolado no dia → <50%)
    prev_a1 = next(i for i in res["items_preview"] if i["student_id"] == "bb_A1")
    assert prev_a1["dias_letivos"] == 3 and prev_a1["faltas_validas"] == 1, prev_a1
    assert prev_a1["frequencia_percentual"] == 66.7 and prev_a1["ready"] is True, prev_a1
    # A2 pendência: falta identificador (sem CPF/NIS)
    pend_a2 = next(p for p in res["pendencias"] if p["student_id"] == "bb_A2")
    assert "Identificador (CPF/NIS)" in pend_a2["missing"], pend_a2
    # idempotency_key determinística/estável
    assert prev_a1["idempotency_key"] == compute_idempotency_key(
        tenant=TA, provider="cmde", operation="frequency", competencia=COMP,
        student_id="bb_A1", school_inep="11111111", payload_version=1)
    print("OK 002b: preview tenant A (consolidação SSoT + prontidão + idempotência)")

    # --- 2. Isolamento multi-tenant: nada persistido em dry-run ---
    assert await db[QUEUE].count_documents({"tenant": TA}) == 0
    print("OK 002b: dry-run não persiste (SSoT/coleções operacionais intactas)")

    # --- 3. Escopo por escola (tenant A, school A) ---
    res_school = await builder.build(
        FrequencyBatchRequestDTO(competencia=COMP, school_id=SCHOOL_A, dry_run=True),
        context={"tenant": TA})
    assert res_school["analyzed"] == 2, res_school
    print("OK 002b: escopo por escola resolve turmas corretamente")

    # --- 4. Persistência (dry_run=False) + idempotência de re-build ---
    r1 = await builder.build(FrequencyBatchRequestDTO(competencia=COMP, dry_run=False),
                             context={"tenant": TA, "actor": "tester"})
    assert r1["persisted"] is True and len(r1["batch_ids"]) == 1
    q_after_1 = await db[QUEUE].count_documents({"tenant": TA})
    assert q_after_1 == 1, ("apenas A1 pronto vira item", q_after_1)
    r2 = await builder.build(FrequencyBatchRequestDTO(competencia=COMP, dry_run=False),
                             context={"tenant": TA, "actor": "tester"})
    q_after_2 = await db[QUEUE].count_documents({"tenant": TA})
    assert q_after_2 == 1, ("re-build NÃO duplica item (idempotency_key)", q_after_2)
    item = await db[QUEUE].find_one({"tenant": TA}, {"_id": 0})
    assert item["status"] == "PENDING" and item["student_id"] == "bb_A1"
    assert item["payload_snapshot"]["faltas_validas"] == 1
    print("OK 002b: persistência ready + idempotência (re-build não duplica)")

    # --- 5. Isolamento tenant B ---
    res_b = await builder.build(FrequencyBatchRequestDTO(competencia=COMP, dry_run=True),
                                context={"tenant": TB})
    assert res_b["analyzed"] == 1, res_b          # só B1
    assert all(p["student_id"] != "bb_A1" for p in res_b["pendencias"])
    print("OK 002b: isolamento multi-tenant (A não vaza para B)")

    # --- 6. SSoT (attendance) NÃO foi mutado ---
    att_count = await db.attendance.count_documents({"mantenedora_id": TA})
    assert att_count == 3, att_count
    sample = await db.attendance.find_one({"mantenedora_id": TA, "date": f"{COMP}-05"}, {"_id": 0})
    assert sample["records"] == [{"student_id": "bb_A1", "status": "F"},
                                 {"student_id": "bb_A2", "status": "P"}], sample
    print("OK 002b: SSoT (attendance) permanece inalterado após build")

    # --- 7. Competência em curso → não persiste (bloqueio) ---
    from datetime import datetime, timezone
    open_comp = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    res_open = await builder.build(FrequencyBatchRequestDTO(competencia=open_comp, dry_run=True),
                                   context={"tenant": TA})
    assert res_open["competencia_fechada"] is False
    from mig.core.exceptions import MigConfigError
    try:
        await builder.build(FrequencyBatchRequestDTO(competencia=open_comp, dry_run=False),
                            context={"tenant": TA})
        assert False, "deveria bloquear build real de competência aberta"
    except MigConfigError:
        pass
    print("OK 002b: competência em curso bloqueia persistência (só preview)")

    await _clean(db)
    print("\nSPRINT 002.b — TODOS OS TESTES PASSARAM ✅")


if __name__ == "__main__":
    asyncio.run(run())
