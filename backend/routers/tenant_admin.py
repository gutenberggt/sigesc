"""Multi-Tenant Toolkit — Auditoria + Branding por Domínio + Onboarding (Sprint F+G).

Endpoints:
  GET  /api/tenant/audit                    — super_admin: lacunas mantenedora_id
  POST /api/tenant/audit/backfill           — super_admin: auto-derivar via parent
  GET  /api/tenant/branding/public          — público: resolve via Host header
                                              (sem query param de tenant!)
  GET  /api/tenant/domains                  — super_admin: lista vínculos
  POST /api/tenant/domains                  — super_admin: vincular domínio
  DELETE /api/tenant/domains/{id}           — super_admin: desvincular
  POST /api/tenant/onboard                  — super_admin: cria nova mantenedora
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query, Response
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
    domain: Optional[str] = None  # vincula domínio inicial


class DomainPayload(BaseModel):
    mantenedora_id: str
    domain: str
    is_primary: bool = False


class BrandingUpdatePayload(BaseModel):
    name: Optional[str] = None
    slogan: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _is_hex_color(value: Optional[str]) -> bool:
    return bool(value and _HEX_RE.match(value.strip()))


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

    # =================== BRANDING PÚBLICO (POR DOMÍNIO) ===================

    @router.get("/branding/public")
    async def public_branding(request: Request, response: Response):
        """Resolve mantenedora pelo `Host` header — sem confiar em query params.

        Headers de cache:
          - `Cache-Control: private, max-age=300` (5 min)
          - `Vary: Host` (CDN deve segregar por host)

        Resolução:
          1. Host bate com `tenant_domains.domain` → tenant resolvido
          2. Senão, primeiro segmento do host bate com `mantenedora.slug` ou `codigo_inep`
          3. Senão, retorna `default=true` (frontend exibe branding genérico, sem
             erro silencioso)
        """
        host = (request.headers.get('host') or '').split(':')[0].lower().strip()
        response.headers['Cache-Control'] = 'private, max-age=300'
        response.headers['Vary'] = 'Host'

        target = None
        resolved_via = None

        if host:
            link = await db.tenant_domains.find_one(
                {"domain": host, "ativo": True}, {"_id": 0}
            )
            if link:
                target = await db.mantenedoras.find_one(
                    {"id": link['mantenedora_id'], "ativa": {"$ne": False}},
                    {"_id": 0}
                )
                resolved_via = "domain_exact"

            if not target:
                sub = host.split('.')[0]
                if sub and sub not in ('www', 'app', 'api'):
                    target = await db.mantenedoras.find_one(
                        {"$or": [{"slug": sub}, {"codigo_inep": sub}]},
                        {"_id": 0},
                    )
                    if target:
                        resolved_via = "subdomain_match"

        if not target:
            # Fallback explícito — não inventa branding silencioso
            return {
                "default": True,
                "resolved_via": "fallback_default",
                "host": host,
                "name": "SIGESC",
                "logo_url": None,
                "brasao_url": None,
                "primary_color": "#7c3aed",
                "secondary_color": "#a855f7",
                "secretaria": None,
                "slogan": "Sistema Integrado de Gestão Escolar",
                "exibir_pre_matricula": False,
                "destaque_mensagem": None,
                "destaque_cor": None,
            }
        return {
            "default": False,
            "resolved_via": resolved_via,
            "host": host,
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

    # =================== BRANDING — UPDATE (G4 Live Preview, Mai/2026) ===================

    @router.put("/branding")
    async def update_branding(payload: BrandingUpdatePayload, request: Request):
        """Atualiza branding da mantenedora ativa do usuário.

        super_admin pode passar X-Mantenedora-Id para editar branding de outro tenant.
        Admin/gerente/secretario só podem editar a própria mantenedora.
        """
        user = await AuthMiddleware.get_current_user(request)
        role = user.get("role")
        if role not in ("super_admin", "admin", "admin_teste", "gerente", "secretario"):
            raise HTTPException(403, "Sem permissão para alterar branding")

        target_id = user.get("mantenedora_id")
        if role == "super_admin":
            override = request.headers.get("X-Mantenedora-Id")
            if override:
                target_id = override
        if not target_id:
            raise HTTPException(400, "Mantenedora alvo não identificada")

        update_doc: dict = {}
        if payload.name is not None:
            update_doc["nome"] = payload.name.strip()[:200]
        if payload.slogan is not None:
            update_doc["slogan"] = payload.slogan.strip()[:300]
        if payload.logo_url is not None:
            update_doc["logotipo_url"] = payload.logo_url.strip()[:500] or None
        if payload.primary_color is not None:
            if not _is_hex_color(payload.primary_color):
                raise HTTPException(400, "primary_color inválido (use formato #RRGGBB)")
            update_doc["cor_primaria"] = payload.primary_color
        if payload.secondary_color is not None:
            if not _is_hex_color(payload.secondary_color):
                raise HTTPException(400, "secondary_color inválido (use formato #RRGGBB)")
            update_doc["cor_secundaria"] = payload.secondary_color

        if not update_doc:
            raise HTTPException(400, "Nenhuma alteração informada")

        update_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.mantenedoras.update_one(
            {"id": target_id}, {"$set": update_doc}
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Mantenedora não encontrada")

        updated = await db.mantenedoras.find_one(
            {"id": target_id},
            {"_id": 0, "id": 1, "nome": 1, "slogan": 1, "logotipo_url": 1,
             "cor_primaria": 1, "cor_secundaria": 1, "brasao_url": 1},
        )
        return {
            "id": updated.get("id"),
            "name": updated.get("nome"),
            "slogan": updated.get("slogan"),
            "logo_url": updated.get("logotipo_url"),
            "primary_color": updated.get("cor_primaria") or "#7c3aed",
            "secondary_color": updated.get("cor_secundaria") or "#a855f7",
            "brasao_url": updated.get("brasao_url"),
        }

    # =================== TENANT DOMAINS (CRUD) ===================

    @router.get("/domains")
    async def list_domains(request: Request, mantenedora_id: Optional[str] = None):
        await _require_super(request)
        filt: dict = {}
        if mantenedora_id:
            filt["mantenedora_id"] = mantenedora_id
        items = await db.tenant_domains.find(filt, {"_id": 0}).to_list(length=500)
        # Enriquece com nome da mantenedora
        ids = list({d['mantenedora_id'] for d in items})
        names: dict = {}
        async for m in db.mantenedoras.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "nome": 1}):
            names[m['id']] = m['nome']
        for d in items:
            d['mantenedora_nome'] = names.get(d['mantenedora_id'])
        return {"items": items}

    @router.post("/domains", status_code=201)
    async def create_domain(payload: DomainPayload, request: Request):
        user = await _require_super(request)
        domain = (payload.domain or '').lower().strip()
        if not re.match(r'^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$', domain):
            raise HTTPException(400, "Domínio inválido (use formato: tenant.sigesc.com.br)")
        # mantenedora deve existir
        m = await db.mantenedoras.find_one({"id": payload.mantenedora_id}, {"_id": 0, "id": 1})
        if not m:
            raise HTTPException(404, "Mantenedora não encontrada")
        existing = await db.tenant_domains.find_one({"domain": domain}, {"_id": 0, "id": 1})
        if existing:
            raise HTTPException(409, "Domínio já vinculado")
        doc = {
            "id": str(uuid.uuid4()),
            "mantenedora_id": payload.mantenedora_id,
            "domain": domain,
            "is_primary": payload.is_primary,
            "ativo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get('email'),
        }
        await db.tenant_domains.insert_one(doc)
        # Garante índice único (idempotente)
        await db.tenant_domains.create_index("domain", unique=True)
        return {k: v for k, v in doc.items() if k != "_id"}

    @router.delete("/domains/{domain_id}")
    async def delete_domain(domain_id: str, request: Request):
        await _require_super(request)
        r = await db.tenant_domains.delete_one({"id": domain_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Domínio não encontrado")
        return {"ok": True}

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

        # Domínio inicial (opcional)
        domain_linked = None
        if payload.domain:
            dom = payload.domain.lower().strip()
            if re.match(r'^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$', dom):
                exists_d = await db.tenant_domains.find_one({"domain": dom}, {"_id": 0, "id": 1})
                if not exists_d:
                    await db.tenant_domains.insert_one({
                        "id": str(uuid.uuid4()),
                        "mantenedora_id": mantenedora_id,
                        "domain": dom,
                        "is_primary": True,
                        "ativo": True,
                        "created_at": now,
                        "created_by": user.get('email'),
                    })
                    await db.tenant_domains.create_index("domain", unique=True)
                    domain_linked = dom

        return {
            "ok": True,
            "mantenedora_id": mantenedora_id,
            "admin_user_id": admin_id,
            "admin_temp_password": "Mudar@2026",
            "school_id": school_id,
            "domain_linked": domain_linked,
            "message": "Mantenedora criada. Admin local recebeu senha temporária 'Mudar@2026' (deve ser trocada no primeiro login).",
        }

    return router
