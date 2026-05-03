"""Multi-Tenant Toolkit — Auditoria + Branding Público + Onboarding (Sprint F).

Endpoints:
  GET  /api/tenant/audit                    — super_admin: lista coleções com
                                              registros sem mantenedora_id
  POST /api/tenant/audit/backfill           — super_admin: tenta auto-derivar
                                              mantenedora_id via parent (school)
  GET  /api/tenant/branding/public          — público: retorna logo+cor+nome
                                              da mantenedora (login screen)
  POST /api/tenant/onboard                  — super_admin: cria nova mantenedora
                                              completa (wizard rápido)
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/tenant", tags=["Multi-Tenant"])


class OnboardPayload(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    secretaria: Optional[str] = None
    admin_email: str
    admin_nome: str
    primary_color: Optional[str] = None
    logotipo_url: Optional[str] = None
    escola_inicial_nome: Optional[str] = None


# Coleções com escopo OBRIGATÓRIO + qual campo "parent" pode derivar mantenedora_id
SCOPED_COLLECTIONS = {
    "schools": None,
    "classes": "school_id",
    "courses": "school_id",
    "students": "school_id",
    "staff": "school_id",
    "enrollments": "school_id",
    "grades": "class_id",
    "learning_objects": "class_id",
    "calendar_events": "school_id",
    "calendario_letivo": "school_id",
    "school_assignments": "school_id",
    "teacher_assignments": "school_id",
    "announcements": "school_id",
    "pre_matriculas": "school_id",
    "intervention_alerts": "school_id",
    "curriculum_components": None,
    "curriculum_adaptations": None,
}


def setup_router(db):

    async def _require_super(request: Request):
        return await AuthMiddleware.require_roles(['super_admin', 'admin'])(request)

    # =================== AUDITORIA ===================

    @router.get("/audit")
    async def audit_tenancy(request: Request, sample_size: int = Query(3, le=50)):
        """Mapeia exatamente onde estão as lacunas de mantenedora_id.

        Para cada coleção crítica retorna `total`, `with_tenant`, `without_tenant`
        e `sample_ids` para inspeção rápida.
        """
        await _require_super(request)
        rows = []
        total_orphans = 0
        for col, parent_field in SCOPED_COLLECTIONS.items():
            total = await db[col].count_documents({})
            with_tenant = await db[col].count_documents({"mantenedora_id": {"$exists": True, "$ne": None}})
            without = total - with_tenant
            sample = []
            if without > 0:
                cursor = db[col].find(
                    {"$or": [
                        {"mantenedora_id": {"$exists": False}},
                        {"mantenedora_id": None},
                    ]},
                    {"_id": 0, "id": 1, "name": 1, parent_field or "id": 1}
                ).limit(sample_size)
                async for d in cursor:
                    sample.append({
                        "id": d.get("id"),
                        "label": d.get("name") or d.get(parent_field or "id"),
                        "parent_field": parent_field,
                        "parent_value": d.get(parent_field) if parent_field else None,
                    })
            rows.append({
                "collection": col,
                "total": total,
                "with_tenant": with_tenant,
                "without_tenant": without,
                "parent_for_backfill": parent_field,
                "sample": sample,
                "coverage_pct": round((with_tenant / total * 100) if total else 100.0, 1),
            })
            total_orphans += without
        return {
            "total_orphans": total_orphans,
            "rows": sorted(rows, key=lambda r: -r["without_tenant"]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @router.post("/audit/backfill")
    async def backfill_tenancy(request: Request, dry_run: bool = True):
        """Tenta derivar `mantenedora_id` a partir do parent (school/class).

        `dry_run=true` (padrão) apenas conta — não escreve. Use `dry_run=false`
        para aplicar de verdade.
        """
        await _require_super(request)
        # Cache schools → mantenedora
        school_to_tenant: dict = {}
        async for s in db.schools.find(
            {"mantenedora_id": {"$ne": None}},
            {"_id": 0, "id": 1, "mantenedora_id": 1}
        ):
            school_to_tenant[s['id']] = s['mantenedora_id']
        class_to_tenant: dict = {}
        async for c in db.classes.find(
            {"mantenedora_id": {"$ne": None}},
            {"_id": 0, "id": 1, "mantenedora_id": 1}
        ):
            class_to_tenant[c['id']] = c['mantenedora_id']

        results = []
        for col, parent_field in SCOPED_COLLECTIONS.items():
            if not parent_field:
                continue
            updated = 0
            no_parent = 0
            cursor = db[col].find(
                {"$or": [{"mantenedora_id": {"$exists": False}}, {"mantenedora_id": None}]},
                {"_id": 0, "id": 1, parent_field: 1}
            )
            async for doc in cursor:
                pv = doc.get(parent_field)
                tenant = None
                if parent_field == "school_id":
                    tenant = school_to_tenant.get(pv)
                elif parent_field == "class_id":
                    tenant = class_to_tenant.get(pv)
                if not tenant:
                    no_parent += 1
                    continue
                if not dry_run:
                    await db[col].update_one(
                        {"id": doc["id"]},
                        {"$set": {"mantenedora_id": tenant}}
                    )
                updated += 1
            results.append({
                "collection": col,
                "would_update": updated if dry_run else None,
                "updated": updated if not dry_run else None,
                "orphan_no_parent_match": no_parent,
            })
        return {"dry_run": dry_run, "results": results}

    # =================== BRANDING PÚBLICO ===================

    @router.get("/branding/public")
    async def public_branding(
        mantenedora_id: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """Retorna branding (logo + cor + nome) sem precisar de autenticação.

        Resolução: por mantenedora_id explícito > host (subdomain) > primeira mantenedora.
        Para login customizado por município.
        """
        target = None
        if mantenedora_id:
            target = await db.mantenedoras.find_one({"id": mantenedora_id}, {"_id": 0})
        if not target and host:
            # Tenta extrair "subdomain" como mantenedora codigo_inep ou slug
            sub = host.split('.')[0] if '.' in host else host
            target = await db.mantenedoras.find_one(
                {"$or": [
                    {"codigo_inep": sub},
                    {"slug": sub},
                ]},
                {"_id": 0},
            )
        if not target:
            target = await db.mantenedoras.find_one({}, {"_id": 0})
        if not target:
            return {
                "name": "SIGESC",
                "logo_url": None,
                "primary_color": "#7c3aed",
                "secondary_color": "#a855f7",
                "secretaria": None,
                "slogan": None,
                "exibir_pre_matricula": False,
                "destaque_mensagem": None,
                "destaque_cor": None,
            }
        return {
            "id": target.get("id"),
            "name": target.get("nome"),
            "logo_url": target.get("logotipo_url"),
            "brasao_url": target.get("brasao_url"),
            "primary_color": target.get("cor_primaria") or "#7c3aed",
            "secondary_color": target.get("cor_secundaria") or "#a855f7",
            "secretaria": target.get("secretaria"),
            "slogan": target.get("slogan"),
            "exibir_pre_matricula": target.get("exibir_pre_matricula", True),
            "destaque_mensagem": target.get("mensagem_destaque"),
            "destaque_cor": target.get("mensagem_destaque_cor"),
        }

    # =================== ONBOARDING (WIZARD) ===================

    @router.post("/onboard", status_code=201)
    async def onboard_mantenedora(payload: OnboardPayload, request: Request):
        """Wizard rápido: cria nova mantenedora + admin local + escola inicial
        (opcional) em uma única transação lógica."""
        user = await _require_super(request)

        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', payload.admin_email or ''):
            raise HTTPException(400, "E-mail inválido")
        existing_email = await db.users.find_one({"email": payload.admin_email}, {"_id": 0, "id": 1})
        if existing_email:
            raise HTTPException(409, "Já existe usuário com este e-mail")

        now = datetime.now(timezone.utc).isoformat()
        mantenedora_id = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]+', '-', payload.nome.lower()).strip('-')[:40]

        mantenedora_doc = {
            "id": mantenedora_id,
            "nome": payload.nome,
            "cnpj": payload.cnpj,
            "municipio": payload.municipio,
            "estado": payload.estado,
            "secretaria": payload.secretaria,
            "logotipo_url": payload.logotipo_url,
            "cor_primaria": payload.primary_color or "#7c3aed",
            "cor_secundaria": "#a855f7",
            "slug": slug,
            "exibir_pre_matricula": True,
            "media_aprovacao": 6.0,
            "frequencia_minima": 75.0,
            "ativa": True,
            "created_at": now,
            "created_by": user.get('email'),
        }
        await db.mantenedoras.insert_one(mantenedora_doc)

        # Cria admin local (gerente)
        from auth_utils import hash_password
        pw_hash = hash_password("Mudar@2026")
        admin_id = str(uuid.uuid4())
        admin_doc = {
            "id": admin_id,
            "email": payload.admin_email,
            "full_name": payload.admin_nome,
            "role": "gerente",
            "mantenedora_id": mantenedora_id,
            "school_links": [],
            "password_hash": pw_hash,
            "status": "active",
            "must_change_password": True,
            "created_at": now,
            "created_by": user.get('email'),
        }
        await db.users.insert_one(admin_doc)

        # Escola inicial (opcional)
        school_id = None
        if payload.escola_inicial_nome:
            school_id = str(uuid.uuid4())
            await db.schools.insert_one({
                "id": school_id,
                "name": payload.escola_inicial_nome,
                "mantenedora_id": mantenedora_id,
                "created_at": now,
                "created_by": user.get('email'),
            })
            # Vincula admin à escola
            await db.users.update_one(
                {"id": admin_id},
                {"$set": {"school_links": [{"school_id": school_id, "role": "gerente"}]}}
            )

        return {
            "ok": True,
            "mantenedora_id": mantenedora_id,
            "admin_user_id": admin_id,
            "admin_temp_password": "Mudar@2026",
            "school_id": school_id,
            "message": "Mantenedora criada. Admin local recebeu senha temporária 'Mudar@2026' (deve ser trocada no primeiro login).",
        }

    return router
