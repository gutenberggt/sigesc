"""PME — Análise dos Anos Finais do Ensino Fundamental.

Painel para o Plano Municipal de Educação: consolida indicadores dos Anos Finais
(6º ao 9º ano) calculados a partir do SIGESC e combina com indicadores externos
informados manualmente (IDEB/SAEB, IBGE, infraestrutura, transporte, etc.).

Escopo: município inteiro (mantenedora), com filtros por escola/zona e ano letivo.
Acesso: super_admin, admin, gerente e perfis SEMED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from tenant_scope import get_mantenedora_scope

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ['super_admin', 'admin', 'admin_teste', 'gerente',
                 'semed', 'semed1', 'semed2', 'semed3']
# Inserir/editar Indicadores Externos é permitido apenas a estes perfis.
EDIT_EXTERNAL_ROLES = ['super_admin', 'admin', 'admin_teste', 'gerente']
AF_LEVEL = 'fundamental_anos_finais'

# Idade esperada (em anos completos no ano letivo) por ano/série dos Anos Finais.
EXPECTED_AGE = {6: 11, 7: 12, 8: 13, 9: 14}


def _serie_num(serie: str) -> Optional[int]:
    """Extrai o número da série (6,7,8,9) de um texto como '6º Ano'."""
    if not serie:
        return None
    import re
    m = re.search(r'(\d+)', str(serie))
    if not m:
        return None
    n = int(m.group(1))
    return n if n in (6, 7, 8, 9) else None


def _age_at_year(birth_date: str, ref_year: int) -> Optional[int]:
    """Idade (anos completos) no dia 31/03 do ano letivo. Aceita dd/mm/aaaa ou ISO."""
    if not birth_date:
        return None
    s = str(birth_date).strip()
    y = mo = d = None
    try:
        if '/' in s:
            d, mo, y = [int(x) for x in s.split('/')[:3]]
        else:
            parts = s[:10].split('-')
            y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        return None
    if not y:
        return None
    age = ref_year - y
    if (mo, d) > (3, 31):  # ainda não fez aniversário até a data de corte
        age -= 1
    return age if 0 <= age <= 30 else None


class ExternalIndicators(BaseModel):
    academic_year: int
    ideb_atual: Optional[float] = None
    ideb_meta: Optional[float] = None
    saeb_lp_9: Optional[float] = None
    saeb_mat_9: Optional[float] = None
    evolucao: list = []          # [{"year":2021,"ideb":4.5,"lp":250,"mat":248}]
    pop_11_14_pct: Optional[float] = None
    pop_16_pct: Optional[float] = None
    bncc_descritores: list = []  # [{"descritor":"D12","nivel_defasagem_pct":40}]
    escolas_total: Optional[int] = None
    escolas_lab_informatica: Optional[int] = None
    escolas_lab_ciencias: Optional[int] = None
    escolas_biblioteca: Optional[int] = None
    escolas_internet: Optional[int] = None
    infraestrutura_obs: Optional[str] = None
    transporte_cobertura_pct: Optional[float] = None
    transporte_impacto_evasao: Optional[str] = None
    formacao_continuada_ativa: Optional[bool] = None
    formacao_continuada_obs: Optional[str] = None
    plano_carreira_atualizado: Optional[bool] = None
    plano_carreira_obs: Optional[str] = None
    observacoes_gerais: Optional[str] = None


def setup_router(db):
    router = APIRouter(prefix="/pme/anos-finais", tags=["PME Anos Finais"])

    async def _auth(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get('role') not in ALLOWED_ROLES:
            raise HTTPException(status_code=403,
                                detail="Acesso restrito a Super Admin, Administrador, Gerente e SEMED.")
        return user

    @router.get("/analytics")
    async def analytics(request: Request, academic_year: Optional[int] = None,
                        school_id: Optional[str] = None, zona: Optional[str] = None):
        user = await _auth(request)
        if not academic_year:
            academic_year = datetime.now().year
        tenant = get_mantenedora_scope(user, request)

        cq = {"education_level": AF_LEVEL, "academic_year": academic_year}
        if tenant:
            cq["mantenedora_id"] = tenant
        if school_id:
            cq["school_id"] = school_id
        classes = await db.classes.find(cq, {"_id": 0}).to_list(5000)

        school_ids = sorted({c.get("school_id") for c in classes if c.get("school_id")})
        schools = await db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "zona_localizacao": 1}
        ).to_list(5000) if school_ids else []
        school_map = {s["id"]: s for s in schools}

        # Filtro por zona (urbana/rural)
        if zona in ("urbana", "rural"):
            classes = [c for c in classes if (school_map.get(c.get("school_id"), {}).get("zona_localizacao") == zona)]
            school_ids = sorted({c.get("school_id") for c in classes if c.get("school_id")})
            school_map = {sid: school_map[sid] for sid in school_ids if sid in school_map}

        af_class_ids = [c["id"] for c in classes]

        # ---- Escolas (urbana/rural) ----
        escolas_lista = []
        zona_counts = {"urbana": 0, "rural": 0, "nao_informado": 0}
        for sid in school_ids:
            sc = school_map.get(sid, {})
            z = sc.get("zona_localizacao") or "nao_informado"
            zona_counts[z if z in zona_counts else "nao_informado"] += 1
            escolas_lista.append({"id": sid, "name": sc.get("name", ""), "zona": z})
        escolas_lista.sort(key=lambda x: (x["zona"], x["name"].lower()))

        # ---- Turmas multisseriadas ----
        multi = [c for c in classes if c.get("is_multi_grade")]
        multi_composicao = []
        for c in multi:
            multi_composicao.append({
                "class_id": c["id"], "name": c.get("name", ""),
                "school": school_map.get(c.get("school_id"), {}).get("name", ""),
                "series": c.get("series") or [],
            })

        # ---- Matrículas (enrollments) do ano ----
        enrollments = []
        if af_class_ids:
            eq = {"class_id": {"$in": af_class_ids}, "academic_year": academic_year}
            enrollments = await db.enrollments.find(
                eq, {"_id": 0, "student_id": 1, "class_id": 1, "status": 1}
            ).to_list(100000)

        student_ids = sorted({e["student_id"] for e in enrollments if e.get("student_id")})
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "color_race": 1, "cor_raca": 1, "disabilities": 1,
             "birth_date": 1, "nis": 1, "student_series": 1}
        ).to_list(100000) if student_ids else []
        student_map = {s["id"]: s for s in students}

        def _race(stu):
            return (stu.get("color_race") or stu.get("cor_raca") or "nao_informada")

        # série por turma (para turmas não-multi usa grade_level; multi usa série da matrícula/aluno)
        class_map = {c["id"]: c for c in classes}

        def _serie_for(enr):
            stu = student_map.get(enr["student_id"], {})
            ser = stu.get("student_series") or class_map.get(enr["class_id"], {}).get("grade_level", "")
            return _serie_num(ser)

        # ---- Matrículas totais por escola/zona ----
        total_matriculas = 0
        por_escola = {}
        por_zona = {"urbana": 0, "rural": 0, "nao_informado": 0}
        active_statuses = {"active", "progressed", "reclassified"}
        for e in enrollments:
            total_matriculas += 1
            cls = class_map.get(e["class_id"], {})
            sid = cls.get("school_id")
            sc = school_map.get(sid, {})
            por_escola.setdefault(sid, {"school": sc.get("name", ""),
                                        "zona": sc.get("zona_localizacao") or "nao_informado",
                                        "total": 0})
            por_escola[sid]["total"] += 1
            z = sc.get("zona_localizacao") or "nao_informado"
            por_zona[z if z in por_zona else "nao_informado"] += 1

        # ---- Demografia (ativos) ----
        cor_raca_dist = {}
        com_deficiencia = 0
        com_nis = 0
        ativos_ids = [e["student_id"] for e in enrollments if e.get("status") in active_statuses]
        ativos_unique = sorted(set(ativos_ids))
        for sid in ativos_unique:
            stu = student_map.get(sid, {})
            cr = _race(stu)
            cor_raca_dist[cr] = cor_raca_dist.get(cr, 0) + 1
            if stu.get("disabilities"):
                com_deficiencia += 1
            if (stu.get("nis") or "").strip():
                com_nis += 1
        n_ativos = len(ativos_unique)

        # ---- Rendimento (por status de matrícula) por série / zona / cor-raça ----
        outcome_map = {
            "active": "cursando", "progressed": "aprovado", "reclassified": "aprovado",
            "dropout": "abandono", "transferred": "transferido",
            "cancelled": "cancelado", "inactive": "inativo", "relocated": "cursando",
        }
        rendimento = {"aprovado": 0, "abandono": 0, "transferido": 0, "cursando": 0,
                      "cancelado": 0, "inativo": 0}
        rend_por_serie = {}
        rend_por_zona = {"urbana": {}, "rural": {}, "nao_informado": {}}
        rend_por_raca = {}
        for e in enrollments:
            out = outcome_map.get(e.get("status"), "cursando")
            if out in rendimento:
                rendimento[out] += 1
            ser = _serie_for(e)
            if ser:
                rend_por_serie.setdefault(ser, {}).setdefault(out, 0)
                rend_por_serie[ser][out] += 1
            cls = class_map.get(e["class_id"], {})
            z = school_map.get(cls.get("school_id"), {}).get("zona_localizacao") or "nao_informado"
            rend_por_zona.setdefault(z, {}).setdefault(out, 0)
            rend_por_zona[z][out] += 1
            cr = _race(student_map.get(e["student_id"], {}))
            rend_por_raca.setdefault(cr, {}).setdefault(out, 0)
            rend_por_raca[cr][out] += 1

        # ---- Distorção idade-série (2+ anos de atraso) ----
        distorcao_por_serie = {}
        for sid in ativos_unique:
            stu = student_map.get(sid, {})
            # série do aluno
            ser = _serie_num(stu.get("student_series") or "")
            if not ser:
                # tenta pela turma da matrícula ativa
                enr = next((e for e in enrollments if e["student_id"] == sid and e.get("status") in active_statuses), None)
                if enr:
                    ser = _serie_num(class_map.get(enr["class_id"], {}).get("grade_level", ""))
            if not ser:
                continue
            age = _age_at_year(stu.get("birth_date"), academic_year)
            d = distorcao_por_serie.setdefault(ser, {"total": 0, "distorcidos": 0})
            d["total"] += 1
            if age is not None and (age - EXPECTED_AGE[ser]) >= 2:
                d["distorcidos"] += 1

        # ---- Evasão/abandono (índice) ----
        abandono_total = rendimento.get("abandono", 0)
        taxa_abandono = round(100.0 * abandono_total / total_matriculas, 1) if total_matriculas else 0.0

        # ---- Perfil docente ----
        teacher_ids = []
        if af_class_ids:
            tas = await db.teacher_assignments.find(
                {"class_id": {"$in": af_class_ids}, "status": "ativo"},
                {"_id": 0, "staff_id": 1}
            ).to_list(100000)
            teacher_ids = sorted({t["staff_id"] for t in tas if t.get("staff_id")})
        docentes = await db.staff.find(
            {"id": {"$in": teacher_ids}},
            {"_id": 0, "nome": 1, "full_name": 1, "formacoes": 1, "especializacoes": 1, "cor_raca": 1}
        ).to_list(100000) if teacher_ids else []
        com_formacao = sum(1 for d in docentes if d.get("formacoes"))
        com_especializacao = sum(1 for d in docentes if d.get("especializacoes"))

        return {
            "academic_year": academic_year,
            "filters": {"school_id": school_id, "zona": zona},
            "escolas": {
                "total": len(school_ids),
                "por_zona": zona_counts,
                "lista": escolas_lista,
            },
            "matriculas": {
                "total": total_matriculas,
                "ativos": n_ativos,
                "por_escola": sorted(por_escola.values(), key=lambda x: -x["total"]),
                "por_zona": por_zona,
            },
            "multisseriadas": {
                "total": len(multi),
                "total_turmas_af": len(classes),
                "composicao": multi_composicao,
            },
            "deficiencia": {
                "com_deficiencia": com_deficiencia,
                "total_ativos": n_ativos,
                "percentual": round(100.0 * com_deficiencia / n_ativos, 1) if n_ativos else 0.0,
            },
            "cor_raca": cor_raca_dist,
            "rendimento": {
                "geral": rendimento,
                "por_serie": rend_por_serie,
                "por_zona": rend_por_zona,
                "por_cor_raca": rend_por_raca,
            },
            "distorcao_idade_serie": distorcao_por_serie,
            "evasao": {"abandono_total": abandono_total, "taxa_abandono_pct": taxa_abandono,
                       "transferidos": rendimento.get("transferido", 0)},
            "socioeconomico": {
                "com_nis": com_nis, "total_ativos": n_ativos,
                "percentual": round(100.0 * com_nis / n_ativos, 1) if n_ativos else 0.0,
            },
            "docentes": {
                "total": len(docentes),
                "com_formacao": com_formacao,
                "com_especializacao": com_especializacao,
                "perc_com_formacao": round(100.0 * com_formacao / len(docentes), 1) if docentes else 0.0,
            },
        }

    @router.get("/external-indicators")
    async def get_external(request: Request, academic_year: Optional[int] = None):
        user = await _auth(request)
        if not academic_year:
            academic_year = datetime.now().year
        tenant = get_mantenedora_scope(user, request)
        q = {"academic_year": academic_year}
        if tenant:
            q["mantenedora_id"] = tenant
        doc = await db.pme_external_indicators.find_one(q, {"_id": 0})
        return doc or {"academic_year": academic_year, "exists": False}

    @router.put("/external-indicators")
    async def upsert_external(payload: ExternalIndicators, request: Request):
        user = await _auth(request)
        if user.get('role') not in EDIT_EXTERNAL_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Apenas Super Administrador, Administrador e Gerente podem inserir os Indicadores Externos.")
        tenant = get_mantenedora_scope(user, request)
        q = {"academic_year": payload.academic_year}
        if tenant:
            q["mantenedora_id"] = tenant
        data = payload.model_dump()
        data["mantenedora_id"] = tenant
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_by"] = {"id": user.get("id"), "email": user.get("email")}
        await db.pme_external_indicators.update_one(q, {"$set": data}, upsert=True)
        return {"success": True, "academic_year": payload.academic_year}

    return router
