"""
Router para Controle de Vacinas.
Gerencia o status vacinal dos alunos.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional, List
from datetime import datetime, timezone
import logging

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Vacinas"])


def setup_router(db, **kwargs):
    """Configura o router com dependências."""

    @router.get("/vaccines/students")
    async def list_students_vaccine_status(
        request: Request,
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        academic_year: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ):
        """Lista alunos com status vacinal. Acesso: admin e agente_vacinas."""
        current_user = await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'agente_vacinas']
        )(request)

        if not academic_year:
            academic_year = datetime.now().year

        query = {"status": {"$in": ["active", "Ativo"]}}
        if school_id:
            query["school_id"] = school_id
        if class_id:
            query["class_id"] = class_id
        if search and len(search) >= 3:
            query["full_name"] = {"$regex": search, "$options": "i"}

        total = await db.students.count_documents(query)
        skip = (page - 1) * page_size

        students = await db.students.find(
            query, {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1, "birth_date": 1, "cpf": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).skip(skip).limit(page_size).to_list(page_size)

        student_ids = [s["id"] for s in students]

        # Buscar status vacinal em lote
        vaccine_docs = await db.vaccine_status.find(
            {"student_id": {"$in": student_ids}, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(len(student_ids))

        vaccine_map = {v["student_id"]: v for v in vaccine_docs}

        result = []
        for s in students:
            v = vaccine_map.get(s["id"])
            vaccine_info = {
                "status": v["status"] if v else "not_verified",
                "verified_at": v.get("verified_at") if v else None,
                "verified_by": v.get("verified_by") if v else None
            }
            # Aplicar filtro de status
            if status_filter:
                if status_filter == "not_verified" and vaccine_info["status"] != "not_verified":
                    continue
                if status_filter == "up_to_date" and vaccine_info["status"] != "up_to_date":
                    continue
                if status_filter == "not_up_to_date" and vaccine_info["status"] != "not_up_to_date":
                    continue

            result.append({
                **s,
                "vaccine": vaccine_info
            })

        return {
            "items": result,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    @router.put("/vaccines/status/{student_id}")
    async def update_vaccine_status(
        student_id: str,
        request: Request
    ):
        """Atualiza o status vacinal de um aluno."""
        current_user = await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'agente_vacinas']
        )(request)

        body = await request.json()
        new_status = body.get("status")
        academic_year = body.get("academic_year", datetime.now().year)

        if new_status not in ("not_verified", "up_to_date", "not_up_to_date"):
            raise HTTPException(status_code=400, detail="Status inválido. Use: not_verified, up_to_date, not_up_to_date")

        student = await db.students.find_one({"id": student_id}, {"_id": 0, "id": 1})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        now = datetime.now(timezone.utc).isoformat()

        await db.vaccine_status.update_one(
            {"student_id": student_id, "academic_year": academic_year},
            {"$set": {
                "student_id": student_id,
                "academic_year": academic_year,
                "status": new_status,
                "verified_by": current_user["id"],
                "verified_at": now,
                "updated_at": now
            }},
            upsert=True
        )

        return {
            "student_id": student_id,
            "status": new_status,
            "verified_at": now,
            "verified_by": current_user["id"]
        }

    @router.get("/vaccines/status/batch")
    async def get_vaccine_status_batch(
        request: Request,
        student_ids: str = Query(..., description="Comma-separated student IDs"),
        academic_year: Optional[int] = None
    ):
        """Retorna status vacinal em lote (para uso na tela de Frequência)."""
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        ids_list = [sid.strip() for sid in student_ids.split(",") if sid.strip()]
        if not ids_list:
            return {}

        docs = await db.vaccine_status.find(
            {"student_id": {"$in": ids_list}, "academic_year": academic_year},
            {"_id": 0, "student_id": 1, "status": 1}
        ).to_list(len(ids_list))

        return {d["student_id"]: d["status"] for d in docs}

    @router.get("/vaccines/summary")
    async def get_vaccine_summary(
        request: Request,
        school_id: Optional[str] = None,
        academic_year: Optional[int] = None
    ):
        """Resumo estatístico do status vacinal."""
        await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'agente_vacinas']
        )(request)

        if not academic_year:
            academic_year = datetime.now().year

        student_query = {"status": {"$in": ["active", "Ativo"]}}
        if school_id:
            student_query["school_id"] = school_id

        total_students = await db.students.count_documents(student_query)

        pipeline = [
            {"$match": {"academic_year": academic_year}},
        ]
        if school_id:
            student_ids_in_school = await db.students.distinct("id", student_query)
            pipeline.append({"$match": {"student_id": {"$in": student_ids_in_school}}})

        pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
        counts = await db.vaccine_status.aggregate(pipeline).to_list(10)

        count_map = {c["_id"]: c["count"] for c in counts}

        verified_up = count_map.get("up_to_date", 0)
        verified_not = count_map.get("not_up_to_date", 0)
        total_verified = verified_up + verified_not
        not_verified = total_students - total_verified

        return {
            "total_students": total_students,
            "up_to_date": verified_up,
            "not_up_to_date": verified_not,
            "not_verified": not_verified
        }

    @router.get("/vaccines/class/{class_id}/students")
    async def get_class_students_vaccine(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None
    ):
        """Lista alunos de uma turma com status vacinal (exclui inativos)."""
        await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'agente_vacinas']
        )(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Status a excluir
        excluded = ["deceased", "transferred", "dropout", "relocated", "reclassified", "progressed",
                     "Falecido", "Transferido", "Desistente", "Remanejado", "Reclassificado", "Progredido"]

        # Buscar alunos via enrollments ativos na turma
        enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": "active", "academic_year": academic_year},
            {"_id": 0, "student_id": 1}
        ).to_list(1000)
        enrolled_ids = [e["student_id"] for e in enrollments]

        # Buscar também alunos com class_id direto
        direct = await db.students.find(
            {"class_id": class_id, "status": {"$nin": excluded + ["inactive"]}},
            {"_id": 0, "id": 1}
        ).to_list(1000)
        direct_ids = [s["id"] for s in direct]

        all_ids = list(set(enrolled_ids + direct_ids))
        if not all_ids:
            return {"students": [], "class_name": "", "total": 0}

        students = await db.students.find(
            {"id": {"$in": all_ids}, "status": {"$nin": excluded}},
            {"_id": 0, "id": 1, "full_name": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

        # Buscar status vacinal em lote
        sids = [s["id"] for s in students]
        vdocs = await db.vaccine_status.find(
            {"student_id": {"$in": sids}, "academic_year": academic_year},
            {"_id": 0, "student_id": 1, "status": 1}
        ).to_list(len(sids))
        vmap = {v["student_id"]: v["status"] for v in vdocs}

        # Nome da turma
        turma = await db.classes.find_one({"id": class_id}, {"_id": 0, "name": 1, "grade_level": 1})
        class_name = turma.get("name", "") if turma else ""

        result = []
        for s in students:
            result.append({
                "id": s["id"],
                "full_name": s["full_name"],
                "vaccine_status": vmap.get(s["id"], "not_verified")
            })

        return {"students": result, "class_name": class_name, "total": len(result)}

    return router
