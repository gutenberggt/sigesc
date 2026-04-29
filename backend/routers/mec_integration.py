"""
Router para Integração MEC Gestão Presente.
Gerencia configuração, consulta de elegibilidades e envio de dados.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from datetime import datetime, timezone
import logging
import httpx

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MEC Integration"])

MEC_ENVIRONMENTS = {
    "homologacao": "https://api-cmde.hmg.gestaopresente.mec.gov.br/v1",
    "producao": "https://api-cmde.gestaopresente.mec.gov.br/v1"
}


def setup_router(db, **kwargs):

    async def get_mec_config():
        """Busca a configuração MEC salva."""
        config = await db.mec_integration.find_one({}, {"_id": 0})
        return config

    @router.get("/mec/config")
    async def get_config(request: Request):
        """Retorna configuração atual da integração MEC."""
        await AuthMiddleware.require_roles(['super_admin'])(request)
        config = await get_mec_config()
        if not config:
            return {
                "environment": "homologacao",
                "pgp_public_key": "",
                "pgp_private_key_configured": False,
                "api_key": "",
                "server_ip": "",
                "responsible_name": "",
                "responsible_email": "",
                "responsible_cpf": "",
                "responsible_phone": "",
                "responsible_role": "",
                "status": "not_configured",
                "last_sync": None
            }
        # Nunca retornar chave privada
        config.pop("pgp_private_key", None)
        config["pgp_private_key_configured"] = bool(config.get("_has_private_key"))
        config.pop("_has_private_key", None)
        return config

    @router.put("/mec/config")
    async def update_config(request: Request):
        """Atualiza configuração da integração MEC."""
        await AuthMiddleware.require_roles(['super_admin'])(request)
        body = await request.json()

        update_data = {}
        allowed_fields = [
            "environment", "pgp_public_key", "api_key", "server_ip",
            "responsible_name", "responsible_email", "responsible_cpf",
            "responsible_phone", "responsible_role"
        ]
        for field in allowed_fields:
            if field in body:
                update_data[field] = body[field]

        if "pgp_private_key" in body and body["pgp_private_key"]:
            update_data["pgp_private_key"] = body["pgp_private_key"]
            update_data["_has_private_key"] = True

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Determinar status
        has_key = bool(update_data.get("api_key") or (await get_mec_config() or {}).get("api_key"))
        update_data["status"] = "configured" if has_key else "pending"

        await db.mec_integration.update_one(
            {}, {"$set": update_data}, upsert=True
        )

        return {"message": "Configuração atualizada com sucesso", "status": update_data["status"]}

    @router.get("/mec/elegibilidades")
    async def consultar_elegibilidades(
        request: Request,
        search: Optional[str] = None,
        inep: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ):
        """Consulta elegibilidades de estudantes no MEC."""
        await AuthMiddleware.require_roles(['super_admin'])(request)

        config = await get_mec_config()
        if not config or not config.get("api_key"):
            raise HTTPException(status_code=400, detail="Integração MEC não configurada. Configure a chave de API primeiro.")

        env = config.get("environment", "homologacao")
        base_url = MEC_ENVIRONMENTS.get(env)
        api_key = config.get("api_key")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if search:
                    # Busca por CPF ou NIS
                    clean = search.replace(".", "").replace("-", "").strip()
                    url = f"{base_url}/elegibilidades/{clean}"
                    resp = await client.get(url, headers=headers)
                elif inep:
                    url = f"{base_url}/elegibilidades/inep/{inep}"
                    resp = await client.get(url, headers=headers)
                else:
                    url = f"{base_url}/elegibilidades"
                    resp = await client.get(url, headers=headers, params={"page": page, "size": page_size})

                if resp.status_code == 200:
                    data = resp.json()
                    # Registrar última consulta
                    await db.mec_integration.update_one(
                        {}, {"$set": {"last_sync": datetime.now(timezone.utc).isoformat(), "last_sync_type": "elegibilidades"}}
                    )
                    return data
                elif resp.status_code == 401:
                    raise HTTPException(status_code=401, detail="Chave de API inválida ou expirada.")
                elif resp.status_code == 403:
                    raise HTTPException(status_code=403, detail="Acesso negado. Verifique se o IP do servidor está autorizado.")
                else:
                    raise HTTPException(status_code=resp.status_code, detail=f"Erro na API do MEC: {resp.text}")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Não foi possível conectar à API do MEC. Verifique a conexão.")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Tempo limite excedido ao consultar a API do MEC.")

    @router.get("/mec/students/mapping")
    async def get_students_mapping(
        request: Request,
        school_id: Optional[str] = None
    ):
        """Retorna mapeamento de alunos SIGESC → MEC (campos necessários)."""
        await AuthMiddleware.require_roles(['super_admin'])(request)

        query = {"status": {"$in": ["active", "Ativo"]}}
        if school_id:
            query["school_id"] = school_id

        students = await db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "cpf": 1, "nis": 1, "inep_code": 1,
             "school_id": 1, "class_id": 1, "birth_date": 1}
        ).sort("full_name", 1).to_list(10000)

        # Buscar INEP das escolas
        school_ids = list(set(s.get("school_id") for s in students if s.get("school_id")))
        schools = await db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "inep_code": 1}
        ).to_list(1000)
        school_map = {s["id"]: s for s in schools}

        result = []
        for s in students:
            school = school_map.get(s.get("school_id"), {})
            has_cpf = bool(s.get("cpf"))
            has_nis = bool(s.get("nis"))
            has_inep = bool(school.get("inep_code"))

            result.append({
                "id": s["id"],
                "full_name": s["full_name"],
                "cpf": s.get("cpf", ""),
                "nis": s.get("nis", ""),
                "inep_code": s.get("inep_code", ""),
                "school_name": school.get("name", ""),
                "school_inep": school.get("inep_code", ""),
                "ready": has_cpf and has_inep,
                "missing_fields": [
                    f for f, v in [("CPF", has_cpf), ("NIS", has_nis), ("INEP Escola", has_inep)]
                    if not v
                ]
            })

        total = len(result)
        ready = sum(1 for r in result if r["ready"])

        return {
            "students": result,
            "total": total,
            "ready_count": ready,
            "not_ready_count": total - ready
        }

    @router.get("/mec/sync/status")
    async def get_sync_status(request: Request):
        """Status geral da integração."""
        await AuthMiddleware.require_roles(['super_admin'])(request)

        config = await get_mec_config()

        # Contar alunos com CPF preenchido
        total_active = await db.students.count_documents({"status": {"$in": ["active", "Ativo"]}})
        with_cpf = await db.students.count_documents({"status": {"$in": ["active", "Ativo"]}, "cpf": {"$ne": None, "$ne": ""}})
        with_nis = await db.students.count_documents({"status": {"$in": ["active", "Ativo"]}, "nis": {"$ne": None, "$ne": ""}})

        # Contar escolas com INEP
        total_schools = await db.schools.count_documents({})
        with_inep = await db.schools.count_documents({"inep_code": {"$ne": None, "$ne": ""}})

        return {
            "status": (config or {}).get("status", "not_configured"),
            "environment": (config or {}).get("environment", "homologacao"),
            "last_sync": (config or {}).get("last_sync"),
            "details": {
                "students_total": total_active,
                "students_with_cpf": with_cpf,
                "students_with_nis": with_nis,
                "schools_total": total_schools,
                "schools_with_inep": with_inep
            }
        }

    return router
