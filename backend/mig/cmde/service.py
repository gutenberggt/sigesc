"""
CmdeService — orquestrador dos casos de uso da Integração MEC Gestão Presente (CMDE).

É o GovProvider do CMDE. Não faz HTTP direto (usa CmdeClient) e não conhece detalhes de
transporte. O router apenas delega a este serviço.
"""
from typing import Optional

from mig.providers.base import GovProvider
from mig.core.exceptions import MigConfigError
from mig.cmde.config_repo import CmdeConfigRepository
from mig.cmde.client import CmdeClient
from mig.cmde.mapper import CmdeMapper
from mig.cmde.dtos import MecConfigUpdateDTO

_ACTIVE_STATUSES = ["active", "Ativo"]


class CmdeService(GovProvider):
    name = "cmde"

    def __init__(self, db):
        self.db = db
        self.config_repo = CmdeConfigRepository(db)

    # ---- Configuração ----
    async def get_config(self) -> dict:
        return await self.config_repo.get_public_config()

    async def update_config(self, body: dict) -> dict:
        # Apenas campos do contrato (PGP intencionalmente fora — decisão Sprint 000)
        allowed = set(MecConfigUpdateDTO.model_fields.keys())
        update_data = {k: v for k, v in (body or {}).items() if k in allowed}
        status = await self.config_repo.update_config(update_data)
        return {"message": "Configuração atualizada com sucesso", "status": status}

    # ---- Status ----
    async def sync_status(self) -> dict:
        config = await self.config_repo.get_raw()
        total_active = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}})
        with_cpf = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}, "cpf": {"$ne": ""}})
        with_nis = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}, "nis": {"$ne": ""}})
        total_schools = await self.db.schools.count_documents({})
        with_inep = await self.db.schools.count_documents({"inep_code": {"$ne": ""}})
        return {
            "status": (config or {}).get("status", "not_configured"),
            "environment": (config or {}).get("environment", "homologacao"),
            "last_sync": (config or {}).get("last_sync"),
            "details": {
                "students_total": total_active,
                "students_with_cpf": with_cpf,
                "students_with_nis": with_nis,
                "schools_total": total_schools,
                "schools_with_inep": with_inep,
            },
        }

    # ---- Mapeamento de alunos ----
    async def students_mapping(self, school_id: Optional[str] = None) -> dict:
        query = {"status": {"$in": _ACTIVE_STATUSES}}
        if school_id:
            query["school_id"] = school_id
        students = await self.db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "cpf": 1, "nis": 1, "inep_code": 1,
             "school_id": 1, "class_id": 1, "birth_date": 1}
        ).sort("full_name", 1).to_list(10000)

        school_ids = list(set(s.get("school_id") for s in students if s.get("school_id")))
        schools = await self.db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "inep_code": 1}
        ).to_list(1000)
        school_map = {s["id"]: s for s in schools}

        result = [CmdeMapper.build_mapping_row(s, school_map.get(s.get("school_id"), {})) for s in students]
        total = len(result)
        ready = sum(1 for r in result if r["ready"])
        return {"students": result, "total": total, "ready_count": ready, "not_ready_count": total - ready}

    # ---- Consulta de elegibilidades (única saída HTTP) ----
    async def query(self, search: Optional[str] = None, inep: Optional[str] = None,
                    page: int = 1, page_size: int = 50) -> dict:
        config = await self.config_repo.get_raw()
        if not config or not config.get("api_key"):
            raise MigConfigError("Integração MEC não configurada. Configure a chave de API primeiro.")

        client = CmdeClient(environment=config.get("environment", "homologacao"),
                            api_key=config.get("api_key"))
        if search:
            data = await client.elegibilidade_por_documento(search)
        elif inep:
            data = await client.elegibilidade_por_inep(inep)
        else:
            data = await client.elegibilidades_paginadas(page, page_size)

        await self.config_repo.touch_last_sync("elegibilidades")
        return data
