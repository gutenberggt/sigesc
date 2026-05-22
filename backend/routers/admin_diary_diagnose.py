"""
Diagnóstico admin: cobertura da grade horária vs. lançamentos (Fev/2026).

Objetivo: revelar, de forma read-only, POR QUE uma turma está aparecendo
com dias INCONSISTENTE no Calendário Operacional do Diário.

Hipótese mais frequente: a grade horária (`teacher_class_assignments`) foi
cadastrada com `valid_from` posterior ao início do ano letivo, e por isso
todos os lançamentos anteriores aparecem como "evidência fora de slot".

Endpoint:
  GET /api/admin/diary/grade-diagnose/{class_id}
    ?from=YYYY-MM-DD     (opcional; default = início do ano letivo da turma)
    ?to=YYYY-MM-DD       (opcional; default = hoje)

Roles autorizados: super_admin, admin, admin_teste, gerente, secretario,
diretor, semed3.

LGPD-safe: NÃO expõe nomes de alunos, conteúdo pedagógico ou observações.
Expõe apenas contagens e datas operacionais.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date as date_cls, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

DIAGNOSE_ROLES = [
    'super_admin', 'admin', 'admin_teste', 'gerente',
    'secretario', 'diretor', 'semed3',
]


def _parse_date(s: str) -> date_cls:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _iso_today() -> str:
    return date_cls.today().isoformat()


def setup_admin_diary_diagnose_router(db):
    router = APIRouter(prefix="/admin/diary", tags=["Admin · Diagnose Diário"])

    @router.get("/grade-diagnose/{class_id}")
    async def grade_diagnose(
        class_id: str,
        request: Request,
        from_: Optional[str] = Query(default=None, alias="from",
                                     pattern=r"^\d{4}-\d{2}-\d{2}$"),
        to: Optional[str] = Query(default=None,
                                  pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ):
        await AuthMiddleware.require_roles(DIAGNOSE_ROLES)(request)

        klass = await db.classes.find_one(
            {"id": class_id},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1,
             "academic_year": 1, "shift": 1},
        )
        if not klass:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        academic_year = klass.get("academic_year")
        period_from = from_ or (f"{academic_year}-02-01" if academic_year else _iso_today())
        period_to = to or _iso_today()
        if _parse_date(period_from) > _parse_date(period_to):
            raise HTTPException(status_code=400,
                                detail="from > to")

        school = await db.schools.find_one(
            {"id": klass.get("school_id")}, {"_id": 0, "name": 1},
        ) or {}

        # ------------------------------------------------------------------
        # 1) Inventário de assignments (incluindo deleted)
        # ------------------------------------------------------------------
        all_assigns = await db.teacher_class_assignments.find(
            {"class_id": class_id},
            {"_id": 0, "id": 1, "valid_from": 1, "valid_until": 1,
             "deleted": 1, "component_id": 1, "weekly_slots": 1},
        ).to_list(5000)

        total_assigns = len(all_assigns)
        deleted_count = sum(1 for a in all_assigns if a.get("deleted"))
        active_assigns = [a for a in all_assigns if not a.get("deleted")]

        valid_from_counter = Counter(a.get("valid_from") for a in active_assigns)
        valid_until_counter = Counter(a.get("valid_until") for a in active_assigns)

        sorted_vfs = sorted([v for v in valid_from_counter.keys() if v])
        earliest_vf = sorted_vfs[0] if sorted_vfs else None
        latest_vf = sorted_vfs[-1] if sorted_vfs else None

        # ------------------------------------------------------------------
        # 2) Cobertura mensal: quantos assignments ativos cobrem cada mês
        # ------------------------------------------------------------------
        # Para cada mês entre period_from..period_to, calcula:
        #   - n_assignments_active: nº de assignments cuja vigência intersecta o mês
        #   - n_attendance: nº de registros de attendance daquele mês
        #   - n_content: nº de content_entries daquele mês
        def _month_iter(d_from: date_cls, d_to: date_cls):
            cur = d_from.replace(day=1)
            while cur <= d_to:
                # último dia do mês
                if cur.month == 12:
                    nxt = cur.replace(year=cur.year + 1, month=1, day=1)
                else:
                    nxt = cur.replace(month=cur.month + 1, day=1)
                last = nxt - timedelta(days=1)
                yield cur, last
                cur = nxt

        d_from = _parse_date(period_from)
        d_to = _parse_date(period_to)
        months_report = []

        for m_from, m_to in _month_iter(d_from, d_to):
            m_from_iso = m_from.isoformat()
            m_to_iso = m_to.isoformat()

            # Assignments cujo intervalo intersecta o mês
            n_active = 0
            for a in active_assigns:
                vf = a.get("valid_from")
                vu = a.get("valid_until")
                if not vf:
                    continue
                if vf > m_to_iso:
                    continue
                if vu is not None and vu < m_from_iso:
                    continue
                n_active += 1

            n_att = await db.attendance.count_documents({
                "class_id": class_id,
                "date": {"$gte": m_from_iso, "$lte": m_to_iso},
            })
            n_ce = await db.content_entries.count_documents({
                "class_id": class_id,
                "date": {"$gte": m_from_iso, "$lte": m_to_iso},
                "deleted": False,
            })
            months_report.append({
                "month": m_from.strftime("%Y-%m"),
                "from": m_from_iso,
                "to": m_to_iso,
                "n_assignments_active": n_active,
                "n_attendance": n_att,
                "n_content_entries": n_ce,
                "is_suspicious": n_active == 0 and (n_att > 0 or n_ce > 0),
            })

        # ------------------------------------------------------------------
        # 3) Datas exatas com registro mas SEM nenhum assignment ativo
        # ------------------------------------------------------------------
        # Para o range completo, busca todas as datas distintas de attendance
        # e content_entries, depois checa quais NÃO têm assignment ativo no dia.
        att_dates_pipeline = [
            {"$match": {"class_id": class_id,
                        "date": {"$gte": period_from, "$lte": period_to}}},
            {"$group": {"_id": "$date"}},
            {"$sort": {"_id": 1}},
            {"$limit": 500},
        ]
        ce_dates_pipeline = [
            {"$match": {"class_id": class_id, "deleted": False,
                        "date": {"$gte": period_from, "$lte": period_to}}},
            {"$group": {"_id": "$date"}},
            {"$sort": {"_id": 1}},
            {"$limit": 500},
        ]
        att_dates = [d["_id"] async for d in db.attendance.aggregate(att_dates_pipeline)]
        ce_dates = [d["_id"] async for d in db.content_entries.aggregate(ce_dates_pipeline)]

        def _assignment_active_on(day_iso: str) -> bool:
            d = _parse_date(day_iso)
            for a in active_assigns:
                vf = a.get("valid_from")
                vu = a.get("valid_until")
                if not vf:
                    continue
                if d < _parse_date(vf):
                    continue
                if vu is not None and d > _parse_date(vu):
                    continue
                # Há slot para esse dia da semana?
                wd = d.isoweekday()
                for slot in (a.get("weekly_slots") or []):
                    if slot.get("weekday") == wd:
                        return True
            return False

        orphan_attendance = [d for d in att_dates if not _assignment_active_on(d)]
        orphan_content = [d for d in ce_dates if not _assignment_active_on(d)]

        # ------------------------------------------------------------------
        # 4) Diagnóstico textual (recomendação)
        # ------------------------------------------------------------------
        recommendation = "OK"
        explanation = ""
        if total_assigns == 0:
            recommendation = "CADASTRAR_GRADE"
            explanation = (
                "Esta turma NÃO possui nenhum assignment de professor "
                "cadastrado. Toda frequência lançada aparecerá como órfã."
            )
        elif len(active_assigns) == 0:
            recommendation = "GRADE_DELETADA"
            explanation = (
                f"Todos os {total_assigns} assignments desta turma estão "
                "marcados como deleted=true. Re-cadastrar ou desfazer a "
                "exclusão lógica."
            )
        elif earliest_vf and academic_year:
            expected_school_year_start = f"{academic_year}-02-01"
            if earliest_vf > expected_school_year_start:
                recommendation = "AJUSTAR_VALID_FROM"
                explanation = (
                    f"A grade horária só passou a vigorar em {earliest_vf}, "
                    f"mas o ano letivo de {academic_year} começou em "
                    f"{expected_school_year_start}. Lançamentos antes de "
                    f"{earliest_vf} aparecerão como evidência fora de slot. "
                    "Ajustar `valid_from` dos assignments para o início do "
                    "ano letivo (ou data real de início das aulas)."
                )

        if not orphan_attendance and not orphan_content and recommendation == "OK":
            explanation = (
                "Nenhuma evidência órfã detectada no período analisado. "
                "Se ainda há dias 'INCONSISTENTE' no calendário, eles podem "
                "estar em outro intervalo — amplie o range."
            )

        return {
            "class": {
                "id": klass["id"],
                "name": klass.get("name"),
                "school_name": school.get("name"),
                "academic_year": academic_year,
                "shift": klass.get("shift"),
            },
            "period_analyzed": {"from": period_from, "to": period_to},
            "assignments_inventory": {
                "total": total_assigns,
                "deleted": deleted_count,
                "active": len(active_assigns),
                "earliest_valid_from": earliest_vf,
                "latest_valid_from": latest_vf,
                "valid_from_distribution": dict(valid_from_counter),
                "valid_until_distribution": {
                    (k if k is not None else "null"): v
                    for k, v in valid_until_counter.items()
                },
            },
            "monthly_coverage": months_report,
            "orphans": {
                "attendance_dates_count": len(orphan_attendance),
                "attendance_dates_sample": orphan_attendance[:30],
                "content_dates_count": len(orphan_content),
                "content_dates_sample": orphan_content[:30],
            },
            "diagnosis": {
                "recommendation": recommendation,
                "explanation": explanation,
            },
        }

    return router
