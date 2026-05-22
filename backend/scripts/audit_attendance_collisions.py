"""
Fase 0 — Diagnóstico do estado atual do Diário/Frequência.

Read-only. Não altera dados. Não cria collections.

Objetivo: ANTES de implementar audit log + optimistic locking + split
de conteúdo, mapear:

  1. Volume e shape real de `db.attendance` (campos, autoria, timestamps).
  2. Existência de duplicidades (mesma turma+data → >1 doc).
  3. Onde mora "conteúdo" hoje (campos: observations, content, descricao, etc.).
  4. Existência de coleção de horário/grade da turma.
  5. Existência de coleções de auditoria pré-existentes.
  6. Indexes atuais na coleção `attendance`.
  7. Saúde do calendário letivo.

Saída: relatório JSON em /app/test_reports/fase_0_diagnostico_diario.json
"""
import asyncio
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

REPORT_PATH = "/app/test_reports/fase_0_diagnostico_diario.json"


async def _connect():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


async def inspect_attendance(db) -> dict:
    coll = db.attendance
    total = await coll.count_documents({})

    # Field coverage (1 sample doc + agregação por presença de campo)
    sample = await coll.find_one({}, {"_id": 0})
    fields_present = list(sample.keys()) if sample else []

    # Autoria/timestamps existentes (% de cobertura em todos os docs)
    coverage_fields = [
        "created_by", "created_at", "updated_by", "updated_at",
        "version", "validated_by", "validated_at",
        "last_modified_by", "last_modified_at",
    ]
    coverage = {}
    for f in coverage_fields:
        coverage[f] = await coll.count_documents({f: {"$exists": True, "$ne": None}})

    # Duplicidades por (class_id, date) — onde teoricamente deveria ser único
    pipeline = [
        {"$group": {
            "_id": {"class_id": "$class_id", "date": "$date"},
            "n": {"$sum": 1},
            "ids": {"$push": "$id"},
            "created_by_set": {"$addToSet": "$created_by"},
        }},
        {"$match": {"n": {"$gt": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 20},
    ]
    duplicates = await coll.aggregate(pipeline).to_list(20)
    # Conta total de pares com duplicidade
    pipeline_count = [
        {"$group": {"_id": {"c": "$class_id", "d": "$date"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "duplicated_pairs"},
    ]
    dup_count = await coll.aggregate(pipeline_count).to_list(1)
    total_duplicated_pairs = dup_count[0]["duplicated_pairs"] if dup_count else 0

    # Multi-autor por documento (created_by diverge entre docs do mesmo class_id+date)
    multi_author_examples = [
        d for d in duplicates if len(d.get("created_by_set", []) or []) > 1
    ][:5]

    # Tamanho médio de records[]
    size_pipe = [
        {"$project": {"sz": {"$size": {"$ifNull": ["$records", []]}}}},
        {"$group": {"_id": None, "avg_size": {"$avg": "$sz"}, "max_size": {"$max": "$sz"}}},
    ]
    sz = await coll.aggregate(size_pipe).to_list(1)
    avg_max = sz[0] if sz else {"avg_size": 0, "max_size": 0}

    # Distribuição de campos que poderiam ser "conteúdo"
    content_like_fields = ["observations", "content", "conteudo", "descricao", "anotacoes", "diario_texto"]
    content_coverage = {}
    for f in content_like_fields:
        content_coverage[f] = await coll.count_documents(
            {f: {"$exists": True, "$nin": [None, ""]}}
        )

    # Sample de doc com observation não-vazia
    sample_with_obs = await coll.find_one(
        {"observations": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "id": 1, "class_id": 1, "date": 1, "observations": 1, "created_by": 1},
    )

    return {
        "total_docs": total,
        "fields_in_sample": fields_present,
        "field_coverage": coverage,
        "duplicated_pairs_total": total_duplicated_pairs,
        "top_duplicated_pairs_sample": [
            {"class_id": d["_id"]["class_id"], "date": d["_id"]["date"], "count": d["n"],
             "doc_ids": d["ids"][:5], "distinct_authors": len(d.get("created_by_set", []) or [])}
            for d in duplicates[:10]
        ],
        "multi_author_same_day": len(multi_author_examples),
        "multi_author_examples": [
            {"class_id": d["_id"]["class_id"], "date": d["_id"]["date"],
             "authors": d.get("created_by_set", [])}
            for d in multi_author_examples
        ],
        "avg_records_per_doc": avg_max.get("avg_size", 0),
        "max_records_per_doc": avg_max.get("max_size", 0),
        "content_like_field_coverage": content_coverage,
        "sample_with_observation": sample_with_obs,
    }


async def inspect_schedule(db) -> dict:
    """Procurar collections de horário/grade."""
    candidate_names = [
        "horarios", "horario", "schedules", "schedule",
        "class_schedules", "grade_horaria", "grade_horario",
        "class_timetable", "timetable", "aulas_programadas",
        "horario_aulas", "horarios_aulas",
    ]
    found = {}
    all_collections = await db.list_collection_names()
    for name in candidate_names:
        if name in all_collections:
            count = await db[name].count_documents({})
            sample = await db[name].find_one({}, {"_id": 0})
            found[name] = {
                "count": count,
                "sample_fields": list(sample.keys()) if sample else [],
                "sample": sample,
            }
    # Procura por qualquer collection que contenha "horario" ou "schedule" no nome
    pattern_matches = [
        c for c in all_collections
        if ("horario" in c.lower() or "schedule" in c.lower() or "grade" in c.lower())
        and c not in candidate_names
    ]
    for c in pattern_matches:
        count = await db[c].count_documents({})
        sample = await db[c].find_one({}, {"_id": 0})
        found[c] = {
            "count": count,
            "sample_fields": list(sample.keys()) if sample else [],
            "sample": sample,
        }
    return {"candidate_collections_found": found, "matched_by_pattern": pattern_matches}


async def inspect_audit_logs(db) -> dict:
    candidates = [
        "audit_log", "audit_logs", "attendance_audit", "attendance_audit_log",
        "content_audit_log", "system_audit", "change_log", "history",
        "attendance_history", "content_history", "diario_audit",
    ]
    all_collections = await db.list_collection_names()
    found = {}
    for name in candidates:
        if name in all_collections:
            count = await db[name].count_documents({})
            sample = await db[name].find_one({}, {"_id": 0})
            found[name] = {
                "count": count,
                "sample_fields": list(sample.keys()) if sample else [],
            }
    return found


async def inspect_indexes(db) -> dict:
    res = {}
    for coll_name in ["attendance", "calendario_letivo", "calendar_events", "classes", "students"]:
        try:
            idx = await db[coll_name].index_information()
            res[coll_name] = {k: v.get("key") for k, v in idx.items()}
        except Exception as e:
            res[coll_name] = f"error: {e}"
    return res


async def inspect_calendar(db) -> dict:
    cals = await db.calendario_letivo.find({}, {"_id": 0}).to_list(50)
    events_count = await db.calendar_events.count_documents({})
    years_covered = sorted({c.get("ano_letivo") for c in cals if c.get("ano_letivo")})
    return {
        "calendarios_letivos_total": len(cals),
        "anos_cobertos": years_covered,
        "calendar_events_total": events_count,
        "sample_calendario": cals[0] if cals else None,
    }


async def main():
    db = await _connect()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_name": os.environ["DB_NAME"],
        "phase": "0 - Diagnóstico Diário/Frequência",
        "attendance": await inspect_attendance(db),
        "schedule": await inspect_schedule(db),
        "existing_audit_collections": await inspect_audit_logs(db),
        "indexes": await inspect_indexes(db),
        "calendar": await inspect_calendar(db),
    }
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    # Print resumo executivo
    a = report["attendance"]
    print("=" * 60)
    print("DIAGNÓSTICO DIÁRIO/FREQUÊNCIA — FASE 0")
    print("=" * 60)
    print(f"attendance docs total: {a['total_docs']}")
    print(f"campos no doc-amostra: {a['fields_in_sample']}")
    print(f"cobertura created_by:  {a['field_coverage'].get('created_by', 0)}")
    print(f"cobertura updated_by:  {a['field_coverage'].get('updated_by', 0)}  ← provavelmente 0")
    print(f"cobertura version:     {a['field_coverage'].get('version', 0)}  ← provavelmente 0")
    print(f"DUPLICIDADES (mesma turma+data → >1 doc): {a['duplicated_pairs_total']}")
    print(f"multi-autor no mesmo dia: {a['multi_author_same_day']}")
    print(f"observations não-vazia em: {a['content_like_field_coverage'].get('observations', 0)} docs")
    print()
    print(f"horários: {list(report['schedule']['candidate_collections_found'].keys()) or 'NENHUMA collection encontrada!'}")
    print(f"audit logs pré-existentes: {list(report['existing_audit_collections'].keys()) or 'nenhum'}")
    print(f"calendário: anos cobertos = {report['calendar']['anos_cobertos']}")
    print()
    print(f"Relatório completo em: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
