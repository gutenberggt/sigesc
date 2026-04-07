"""
Router para Histórico Escolar.
CRUD de registros anuais do histórico do aluno + geração de PDF.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Histórico Escolar"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    from auth_middleware import AuthMiddleware

    ALLOWED_ROLES = ['admin', 'secretario', 'diretor', 'auxiliar_secretaria']

    async def get_db(request):
        current_user = await AuthMiddleware.get_current_user(request)
        role = current_user.get('role', '')
        if role not in ALLOWED_ROLES:
            raise HTTPException(status_code=403, detail="Acesso negado. Apenas Administrador, Secretário, Diretor e Auxiliar de Secretaria podem gerenciar históricos.")
        if sandbox_db is not None and current_user.get('sandbox'):
            return sandbox_db, current_user
        return db, current_user

    @router.get("/student-history/{student_id}")
    async def get_student_history(student_id: str, request: Request):
        """Retorna o histórico escolar completo do aluno."""
        current_db, current_user = await get_db(request)

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        history = await current_db.student_history.find_one(
            {"student_id": student_id}, {"_id": 0}
        )

        if not history:
            history = {
                "student_id": student_id,
                "records": [],
                "observations": "",
                "media_aprovacao": 6.0
            }

        return history

    @router.post("/student-history/{student_id}")
    async def save_student_history(student_id: str, request: Request):
        """Cria ou atualiza o histórico escolar do aluno."""
        current_db, current_user = await get_db(request)

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        body = await request.json()
        records = body.get('records', [])
        observations = body.get('observations', '')
        media_aprovacao = body.get('media_aprovacao', 6.0)

        # Validar cada registro
        for rec in records:
            if not rec.get('serie'):
                raise HTTPException(status_code=400, detail="Cada registro precisa ter uma série/ano")

        now = datetime.now(timezone.utc).isoformat()

        existing = await current_db.student_history.find_one({"student_id": student_id})

        history_data = {
            "student_id": student_id,
            "records": records,
            "observations": observations,
            "media_aprovacao": media_aprovacao,
            "updated_at": now,
            "updated_by": current_user.get('id', '')
        }

        if existing:
            await current_db.student_history.update_one(
                {"student_id": student_id},
                {"$set": history_data}
            )
        else:
            history_data["id"] = str(uuid.uuid4())
            history_data["created_at"] = now
            history_data["created_by"] = current_user.get('id', '')
            await current_db.student_history.insert_one(history_data)

        result = await current_db.student_history.find_one(
            {"student_id": student_id}, {"_id": 0}
        )
        return result

    @router.delete("/student-history/{student_id}/{serie}")
    async def delete_history_record(student_id: str, serie: str, request: Request):
        """Remove um registro de uma série específica do histórico."""
        current_db, current_user = await get_db(request)

        result = await current_db.student_history.update_one(
            {"student_id": student_id},
            {"$pull": {"records": {"serie": serie}}}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        return {"message": f"Registro da série {serie} removido"}

    return router
