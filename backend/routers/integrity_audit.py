"""
[Fase 1 — Diagnóstico Global] Endpoint admin de auditoria de integridade.

GET /api/admin/integrity-audit            → JSON consolidado
GET /api/admin/integrity-audit?format=csv → CSV exportável

Acesso: super_admin only.
Apenas leitura — não altera dados.

Categorias e severidades:
  CRÍTICOS    — aluno ativo sem turma, turma inexistente, escola inexistente,
                atendimento AEE órfão, duplicidade de matrícula ativa
  MODERADOS   — turma de outra escola, disabilities[] duplicadas
  INFORMATIVOS — student_series vazio, has_disability sem plano AEE,
                turma com escola inexistente
"""
import csv
import logging
from io import StringIO
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query, status
from fastapi.responses import StreamingResponse

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)


# Severidade por tipo de inconsistência
SEVERITY_BY_TYPE = {
    # críticos
    "aluno_sem_turma": "critico",
    "turma_inexistente": "critico",
    "escola_inexistente": "critico",
    "atendimento_aee_orfao": "critico",
    "matricula_duplicada": "critico",
    # moderados
    "turma_outra_escola": "moderado",
    "disabilities_duplicadas": "moderado",
    "atendimento_aee_aluno_inconsistente": "moderado",
    # informativos
    "student_series_vazio": "informativo",
    "has_disability_sem_plano": "informativo",
    "turma_com_escola_inexistente": "informativo",
    "plano_aee_orfao": "informativo",
}

TYPE_LABELS = {
    "aluno_sem_turma": "Aluno ativo sem turma",
    "turma_inexistente": "Turma inexistente",
    "escola_inexistente": "Escola inexistente",
    "atendimento_aee_orfao": "Atendimento AEE sem plano",
    "matricula_duplicada": "2+ matrículas ativas",
    "turma_outra_escola": "Turma de outra escola",
    "disabilities_duplicadas": "disabilities[] duplicadas",
    "atendimento_aee_aluno_inconsistente": "Atendimento AEE com aluno divergente do plano",
    "student_series_vazio": "Aluno ativo com série vazia",
    "has_disability_sem_plano": "has_disability sem plano AEE ativo",
    "turma_com_escola_inexistente": "Turma com escola inexistente",
    "plano_aee_orfao": "Plano AEE sem aluno",
}


def setup_integrity_audit_router(db):
    router = APIRouter(prefix="/admin", tags=["IntegrityAudit"])

    async def _collect_inconsistencies():
        """Roda todas as queries e devolve a lista bruta de itens detalhados.

        Cada item:
            {
              "tipo": str,
              "severidade": str,
              "school_id": str|None,
              "school_name": str|None,
              "student_id": str|None,
              "student_name": str|None,
              "class_id": str|None,
              "class_name": str|None,
              "observacao": str,
            }
        """
        items = []

        # ---- 1.1 Aluno ativo sem turma ----
        async for s in db.students.find({
            "status": "active",
            "$or": [{"class_id": None}, {"class_id": ""}, {"class_id": {"$exists": False}}],
        }, {"_id": 0, "id": 1, "full_name": 1, "school_id": 1}):
            school = await db.schools.find_one({"id": s.get("school_id")}, {"_id": 0, "name": 1}) if s.get("school_id") else None
            items.append({
                "tipo": "aluno_sem_turma",
                "severidade": SEVERITY_BY_TYPE["aluno_sem_turma"],
                "school_id": s.get("school_id"),
                "school_name": school.get("name") if school else None,
                "student_id": s.get("id"),
                "student_name": s.get("full_name"),
                "class_id": None,
                "class_name": None,
                "observacao": "Aluno marcado como ATIVO mas sem class_id.",
            })

        # ---- 1.2 + 1.3 Turma inexistente OU de outra escola ----
        async for s in db.students.aggregate([
            {"$match": {"status": "active", "class_id": {"$nin": [None, ""]}}},
            {"$lookup": {"from": "classes", "localField": "class_id",
                         "foreignField": "id", "as": "_c"}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$project": {
                "_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1,
                "_c": {"$arrayElemAt": ["$_c", 0]},
                "_s": {"$arrayElemAt": ["$_s", 0]},
            }},
        ]):
            cls = s.get("_c")
            sch = s.get("_s")
            if cls is None:
                items.append({
                    "tipo": "turma_inexistente",
                    "severidade": SEVERITY_BY_TYPE["turma_inexistente"],
                    "school_id": s.get("school_id"),
                    "school_name": sch.get("name") if sch else None,
                    "student_id": s.get("id"),
                    "student_name": s.get("full_name"),
                    "class_id": s.get("class_id"),
                    "class_name": None,
                    "observacao": f"class_id {s.get('class_id')} não existe na coleção classes.",
                })
            elif cls.get("school_id") != s.get("school_id"):
                items.append({
                    "tipo": "turma_outra_escola",
                    "severidade": SEVERITY_BY_TYPE["turma_outra_escola"],
                    "school_id": s.get("school_id"),
                    "school_name": sch.get("name") if sch else None,
                    "student_id": s.get("id"),
                    "student_name": s.get("full_name"),
                    "class_id": s.get("class_id"),
                    "class_name": cls.get("name"),
                    "observacao": f"Turma pertence à escola {cls.get('school_id')} e não à do aluno.",
                })

        # ---- 1.5 Escola inexistente ----
        async for s in db.students.aggregate([
            {"$match": {"status": "active", "school_id": {"$nin": [None, ""]}}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$match": {"_s": {"$eq": []}}},
            {"$project": {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1}},
        ]):
            items.append({
                "tipo": "escola_inexistente",
                "severidade": SEVERITY_BY_TYPE["escola_inexistente"],
                "school_id": s.get("school_id"),
                "school_name": None,
                "student_id": s.get("id"),
                "student_name": s.get("full_name"),
                "class_id": s.get("class_id"),
                "class_name": None,
                "observacao": f"school_id {s.get('school_id')} não existe na coleção schools.",
            })

        # ---- 1.6 student_series vazio (informativo) ----
        async for s in db.students.aggregate([
            {"$match": {
                "status": "active",
                "$or": [{"student_series": None}, {"student_series": ""}, {"student_series": {"$exists": False}}],
            }},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$lookup": {"from": "classes", "localField": "class_id",
                         "foreignField": "id", "as": "_c"}},
            {"$project": {
                "_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1,
                "_s": {"$arrayElemAt": ["$_s", 0]},
                "_c": {"$arrayElemAt": ["$_c", 0]},
            }},
        ]):
            items.append({
                "tipo": "student_series_vazio",
                "severidade": SEVERITY_BY_TYPE["student_series_vazio"],
                "school_id": s.get("school_id"),
                "school_name": (s.get("_s") or {}).get("name"),
                "student_id": s.get("id"),
                "student_name": s.get("full_name"),
                "class_id": s.get("class_id"),
                "class_name": (s.get("_c") or {}).get("name"),
                "observacao": "student_series ausente; relatórios devem usar classes.grade_level.",
            })

        # ---- 1.7 Duplicidade de matrícula ativa ----
        async for g in db.enrollments.aggregate([
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$student_id", "n": {"$sum": 1},
                        "school_ids": {"$addToSet": "$school_id"}}},
            {"$match": {"n": {"$gt": 1}}},
        ]):
            student = await db.students.find_one({"id": g["_id"]}, {"_id": 0, "full_name": 1, "school_id": 1})
            sch = await db.schools.find_one({"id": (student or {}).get("school_id")}, {"_id": 0, "name": 1}) if student else None
            items.append({
                "tipo": "matricula_duplicada",
                "severidade": SEVERITY_BY_TYPE["matricula_duplicada"],
                "school_id": (student or {}).get("school_id"),
                "school_name": sch.get("name") if sch else None,
                "student_id": g["_id"],
                "student_name": (student or {}).get("full_name"),
                "class_id": None,
                "class_name": None,
                "observacao": f"{g['n']} matrículas ativas (status=active) para o mesmo aluno.",
            })

        # ---- 1.8 disabilities[] duplicadas (moderado) ----
        async for s in db.students.aggregate([
            {"$match": {"disabilities": {"$exists": True, "$ne": []}}},
            {"$addFields": {
                "_uniq": {"$size": {"$setUnion": ["$disabilities", []]}},
                "_tot": {"$size": "$disabilities"},
            }},
            {"$match": {"$expr": {"$lt": ["$_uniq", "$_tot"]}}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$project": {
                "_id": 0, "id": 1, "full_name": 1, "school_id": 1,
                "disabilities": 1,
                "_s": {"$arrayElemAt": ["$_s", 0]},
            }},
        ]):
            items.append({
                "tipo": "disabilities_duplicadas",
                "severidade": SEVERITY_BY_TYPE["disabilities_duplicadas"],
                "school_id": s.get("school_id"),
                "school_name": (s.get("_s") or {}).get("name"),
                "student_id": s.get("id"),
                "student_name": s.get("full_name"),
                "class_id": None,
                "class_name": None,
                "observacao": f"disabilities = {s.get('disabilities')}",
            })

        # ---- 2.1 Plano AEE órfão (informativo) ----
        async for p in db.planos_aee.aggregate([
            {"$lookup": {"from": "students", "localField": "student_id",
                         "foreignField": "id", "as": "_s"}},
            {"$match": {"_s": {"$eq": []}}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_sc"}},
            {"$project": {"_id": 0, "id": 1, "student_id": 1, "school_id": 1,
                          "_sc": {"$arrayElemAt": ["$_sc", 0]}}},
        ]):
            items.append({
                "tipo": "plano_aee_orfao",
                "severidade": SEVERITY_BY_TYPE["plano_aee_orfao"],
                "school_id": p.get("school_id"),
                "school_name": (p.get("_sc") or {}).get("name"),
                "student_id": p.get("student_id"),
                "student_name": None,
                "class_id": None,
                "class_name": None,
                "observacao": f"Plano AEE {p.get('id')} aponta para aluno inexistente.",
            })

        # ---- 2.2 Atendimento AEE órfão (crítico) ----
        async for a in db.atendimentos_aee.aggregate([
            {"$lookup": {"from": "planos_aee", "localField": "plano_aee_id",
                         "foreignField": "id", "as": "_p"}},
            {"$match": {"_p": {"$eq": []}}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_sc"}},
            {"$lookup": {"from": "students", "localField": "student_id",
                         "foreignField": "id", "as": "_st"}},
            {"$project": {
                "_id": 0, "id": 1, "plano_aee_id": 1, "student_id": 1, "school_id": 1,
                "_sc": {"$arrayElemAt": ["$_sc", 0]},
                "_st": {"$arrayElemAt": ["$_st", 0]},
            }},
        ]):
            items.append({
                "tipo": "atendimento_aee_orfao",
                "severidade": SEVERITY_BY_TYPE["atendimento_aee_orfao"],
                "school_id": a.get("school_id"),
                "school_name": (a.get("_sc") or {}).get("name"),
                "student_id": a.get("student_id"),
                "student_name": (a.get("_st") or {}).get("full_name"),
                "class_id": None,
                "class_name": None,
                "observacao": f"Atendimento {a.get('id')} referencia plano_aee_id {a.get('plano_aee_id')} inexistente.",
            })

        # ---- 2.3 Atendimento AEE com aluno inconsistente com plano (moderado) ----
        async for a in db.atendimentos_aee.aggregate([
            {"$lookup": {"from": "planos_aee", "localField": "plano_aee_id",
                         "foreignField": "id", "as": "_p"}},
            {"$unwind": "$_p"},
            {"$match": {"$expr": {"$ne": ["$student_id", "$_p.student_id"]}}},
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_sc"}},
            {"$lookup": {"from": "students", "localField": "student_id",
                         "foreignField": "id", "as": "_st"}},
            {"$project": {
                "_id": 0, "id": 1, "student_id": 1, "school_id": 1,
                "plano_student_id": "$_p.student_id",
                "_sc": {"$arrayElemAt": ["$_sc", 0]},
                "_st": {"$arrayElemAt": ["$_st", 0]},
            }},
        ]):
            items.append({
                "tipo": "atendimento_aee_aluno_inconsistente",
                "severidade": SEVERITY_BY_TYPE["atendimento_aee_aluno_inconsistente"],
                "school_id": a.get("school_id"),
                "school_name": (a.get("_sc") or {}).get("name"),
                "student_id": a.get("student_id"),
                "student_name": (a.get("_st") or {}).get("full_name"),
                "class_id": None,
                "class_name": None,
                "observacao": f"Atendimento {a.get('id')} student_id={a.get('student_id')} ≠ plano.student_id={a.get('plano_student_id')}",
            })

        # ---- 2.4 has_disability=true sem plano AEE ativo (informativo) ----
        async for s in db.students.aggregate([
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
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$project": {
                "_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1,
                "_s": {"$arrayElemAt": ["$_s", 0]},
            }},
        ]):
            items.append({
                "tipo": "has_disability_sem_plano",
                "severidade": SEVERITY_BY_TYPE["has_disability_sem_plano"],
                "school_id": s.get("school_id"),
                "school_name": (s.get("_s") or {}).get("name"),
                "student_id": s.get("id"),
                "student_name": s.get("full_name"),
                "class_id": s.get("class_id"),
                "class_name": None,
                "observacao": "Aluno marcado com deficiência mas sem Plano AEE ativo (verificar elegibilidade).",
            })

        # ---- 3.1 Turma com escola inexistente (informativo) ----
        async for c in db.classes.aggregate([
            {"$lookup": {"from": "schools", "localField": "school_id",
                         "foreignField": "id", "as": "_s"}},
            {"$match": {"_s": {"$eq": []}}},
            {"$project": {"_id": 0, "id": 1, "name": 1, "school_id": 1}},
        ]):
            items.append({
                "tipo": "turma_com_escola_inexistente",
                "severidade": SEVERITY_BY_TYPE["turma_com_escola_inexistente"],
                "school_id": c.get("school_id"),
                "school_name": None,
                "student_id": None,
                "student_name": None,
                "class_id": c.get("id"),
                "class_name": c.get("name"),
                "observacao": f"Turma {c.get('name')} referencia school_id inexistente.",
            })

        return items

    def _build_summary(items):
        """Constrói resumo consolidado com agrupamentos por tipo, severidade e escola."""
        by_type = {}
        by_severity = {"critico": 0, "moderado": 0, "informativo": 0}
        by_school = {}
        for it in items:
            t = it["tipo"]
            by_type[t] = by_type.get(t, 0) + 1
            by_severity[it["severidade"]] = by_severity.get(it["severidade"], 0) + 1
            sk = it.get("school_name") or it.get("school_id") or "(sem escola)"
            by_school[sk] = by_school.get(sk, 0) + 1
        return {
            "total": len(items),
            "by_severity": by_severity,
            "by_type": [
                {"tipo": t, "label": TYPE_LABELS.get(t, t),
                 "severidade": SEVERITY_BY_TYPE.get(t), "count": c}
                for t, c in sorted(by_type.items(), key=lambda x: -x[1])
            ],
            "by_school": [
                {"escola": s, "count": c}
                for s, c in sorted(by_school.items(), key=lambda x: -x[1])
            ],
        }

    @router.get("/integrity-audit")
    async def integrity_audit(
        request: Request,
        format: str = Query("json", pattern="^(json|csv)$"),
    ):
        """Auditoria global de integridade. Apenas super_admin.

        Query params:
          - format=json (default) → JSON consolidado
          - format=csv            → CSV exportável
        """
        await AuthMiddleware.require_roles(['super_admin'])(request)

        started_at = datetime.now(timezone.utc)
        logger.info(f"[integrity-audit] start at {started_at.isoformat()}")
        items = await _collect_inconsistencies()
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        logger.info(
            f"[integrity-audit] done in {duration_ms}ms — {len(items)} inconsistências"
        )

        if format == "csv":
            buf = StringIO()
            writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["escola", "tipo", "aluno", "turma", "severidade", "observacao"])
            for it in items:
                writer.writerow([
                    it.get("school_name") or it.get("school_id") or "",
                    TYPE_LABELS.get(it["tipo"], it["tipo"]),
                    it.get("student_name") or it.get("student_id") or "",
                    it.get("class_name") or it.get("class_id") or "",
                    it.get("severidade"),
                    it.get("observacao") or "",
                ])
            buf.seek(0)
            stamp = finished_at.strftime("%Y%m%d_%H%M%S")
            return StreamingResponse(
                iter([buf.getvalue()]),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="integrity-audit_{stamp}.csv"',
                },
            )

        summary = _build_summary(items)
        return {
            "generated_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "summary": summary,
            "items": items,
        }

    return router
