"""Intervenções Curriculares — Feed + Gerenciamento (Sprint C Feb 2026).

Endpoints:
  GET  /api/intervencoes                    — feed ativo para o gestor
  GET  /api/intervencoes/notifications      — inbox in-app do usuário logado
  POST /api/intervencoes/notifications/{id}/read — marcar lida
  POST /api/intervencoes/{id}/resolve       — marcar resolvida manualmente
  POST /api/intervencoes/run-detection      — trigger manual (debug/admin)

Scheduler: roda toda segunda-feira às 07:00 UTC.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from auth_middleware import AuthMiddleware
from services.intervention_detector import run_intervention_detection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intervencoes", tags=["Intervenções"])

_scheduler: Optional[AsyncIOScheduler] = None


def setup_router(db, **_kwargs):

    global _scheduler

    async def _auth_manager(request: Request):
        return await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'coordenador', 'apoio_pedagogico', 'diretor', 'secretario']
        )(request)

    async def _auth_any(request: Request):
        return await AuthMiddleware.get_current_user(request)

    # =================== FEED (gestão) ===================

    @router.get("")
    async def list_interventions(
        request: Request,
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = Query(200, le=500),
    ):
        user = await _auth_manager(request)
        filt: dict = {} if include_resolved else {"resolved_at": None}
        if school_id:
            filt["school_id"] = school_id
        if class_id:
            filt["class_id"] = class_id
        # Escopo por usuário não-admin: suas escolas apenas
        if user.get('role') not in ('super_admin', 'admin', 'admin_teste', 'gerente'):
            user_schools = [s.get('school_id') for s in user.get('school_links') or []]
            if user_schools:
                filt["school_id"] = {"$in": user_schools} if not school_id else school_id
        cursor = (
            db.intervention_alerts.find(filt, {"_id": 0})
            # piores primeiro: nao_cumpre > fechado_critico > em_risco; dentro deles mais antigos
            .sort([("escalation_level", -1), ("first_detected_at", 1)])
            .limit(limit)
        )
        items = await cursor.to_list(length=limit)
        summary = {
            "total_active": await db.intervention_alerts.count_documents({"resolved_at": None}),
            "critical": await db.intervention_alerts.count_documents(
                {"resolved_at": None, "status": {"$in": ["nao_cumpre", "fechado_critico"]}}
            ),
            "level_3": await db.intervention_alerts.count_documents(
                {"resolved_at": None, "escalation_level": 3}
            ),
        }
        return {"items": items, "summary": summary}

    @router.post("/{alert_id}/resolve")
    async def resolve_intervention(alert_id: str, request: Request):
        user = await _auth_manager(request)
        r = await db.intervention_alerts.update_one(
            {"id": alert_id, "resolved_at": None},
            {"$set": {
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get('email'),
            }},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Alerta não encontrado ou já resolvido")
        return {"ok": True}

    @router.post("/run-detection")
    async def trigger_detection(request: Request, academic_year: Optional[int] = None):
        """Trigger manual (uso admin/debug). Em produção, prefira o cron."""
        await AuthMiddleware.require_roles(['super_admin', 'admin'])(request)
        stats = await run_intervention_detection(db, academic_year=academic_year)
        return {"ok": True, **stats}

    # =================== RANKING (Sprint D) ===================

    LEVEL_WEIGHT = {1: 1, 2: 2, 3: 3}

    def _score(avg_days: Optional[float], rate: float, active: int) -> float:
        """Score simples 0–100: premia velocidade, taxa e backlog baixo."""
        adj_time = 100 - ((avg_days or 0) * 5)
        s = max(min(adj_time, 100), 0) * 0.5 + rate * 100 * 0.4 - active * 2
        return round(max(min(s, 100), 0), 1)

    @router.get("/ranking")
    async def ranking(
        request: Request,
        period: str = Query("30d", pattern="^(7d|30d|60d|90d|all)$"),
        only_mine: bool = False,
    ):
        """Ranking por escola com peso por nível de escalonamento.

        Mitigação política:
          - Por padrão, só super_admin/admin/secretario enxergam ranking completo.
          - Diretor/coordenador recebem apenas a sua escola (?only_mine=true
            forçado automaticamente).
        """
        user = await _auth_manager(request)
        role = user.get('role')
        full_access = role in ('super_admin', 'admin', 'admin_teste', 'secretario')
        if not full_access:
            only_mine = True

        from datetime import timedelta
        window_days = {"7d": 7, "30d": 30, "60d": 60, "90d": 90, "all": None}[period]
        since_iso = None
        if window_days is not None:
            since_iso = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()

        # 1. Carrega alerts dentro da janela (criado ≥ since)
        filt: dict = {}
        if since_iso:
            filt["first_detected_at"] = {"$gte": since_iso}
        if only_mine:
            user_schools = [s.get('school_id') for s in user.get('school_links') or []]
            if not user_schools:
                return {"period": period, "rows": [], "self": None}
            filt["school_id"] = {"$in": user_schools}

        alerts = await db.intervention_alerts.find(filt, {"_id": 0}).to_list(length=5000)

        # 2. School + class counts (contexto)
        school_map: dict = {}
        async for s in db.schools.find({}, {"_id": 0, "id": 1, "name": 1}):
            school_map[s['id']] = s
        class_counts: dict = {}
        async for c in db.classes.find({}, {"_id": 0, "school_id": 1}):
            sid = c.get('school_id')
            if sid:
                class_counts[sid] = class_counts.get(sid, 0) + 1

        # 3. Coord/diretor responsável por escola (primeiro coordenador ativo)
        coord_map: dict = {}
        async for u in db.users.find(
            {"status": "active", "role": {"$in": ["coordenador", "diretor"]}},
            {"_id": 0, "id": 1, "full_name": 1, "role": 1, "school_links": 1}
        ):
            for link in (u.get('school_links') or []):
                sid = link.get('school_id')
                if sid and sid not in coord_map:
                    coord_map[sid] = u

        # 4. Agrega por escola
        from collections import defaultdict
        bucket = defaultdict(lambda: {
            "received": 0, "resolved": 0, "active": 0,
            "resolution_days_sum": 0.0, "resolution_days_n": 0,
            "weighted_received": 0.0, "weighted_resolved": 0.0,
            "level_3": 0, "level_2": 0, "level_1": 0,
        })
        for a in alerts:
            sid = a.get('school_id') or '_sem_escola_'
            b = bucket[sid]
            level = a.get('escalation_level') or 1
            weight = LEVEL_WEIGHT.get(level, 1)
            b["received"] += 1
            b["weighted_received"] += weight
            b[f"level_{level}"] = b.get(f"level_{level}", 0) + 1
            if a.get('resolved_at'):
                b["resolved"] += 1
                b["weighted_resolved"] += weight
                try:
                    d1 = datetime.fromisoformat(a['first_detected_at'])
                    d2 = datetime.fromisoformat(a['resolved_at'])
                    if d1.tzinfo is None:
                        d1 = d1.replace(tzinfo=timezone.utc)
                    if d2.tzinfo is None:
                        d2 = d2.replace(tzinfo=timezone.utc)
                    days = (d2 - d1).total_seconds() / 86400.0
                    b["resolution_days_sum"] += days
                    b["resolution_days_n"] += 1
                except Exception:
                    pass
            else:
                b["active"] += 1

        rows = []
        for sid, b in bucket.items():
            avg_days = (b["resolution_days_sum"] / b["resolution_days_n"]) if b["resolution_days_n"] else None
            rate = (b["weighted_resolved"] / b["weighted_received"]) if b["weighted_received"] else 0.0
            school = school_map.get(sid) or {"name": "—", "id": sid}
            coord = coord_map.get(sid) or {}
            rows.append({
                "school_id": sid,
                "school_name": school.get("name"),
                "num_classes": class_counts.get(sid, 0),
                "gestor_nome": coord.get("full_name") or "—",
                "gestor_role": coord.get("role") or "—",
                "received": b["received"],
                "resolved": b["resolved"],
                "active": b["active"],
                "resolution_rate": round(rate * 100, 1),
                "avg_resolution_days": round(avg_days, 1) if avg_days is not None else None,
                "weighted_score": _score(avg_days, rate, b["active"]),
                "critical_level_3": b.get("level_3", 0),
            })
        rows.sort(key=lambda r: (-r["weighted_score"], r["school_name"] or ""))
        for i, r in enumerate(rows, start=1):
            r["rank"] = i

        # Self (gestor vê apenas o próprio)
        self_row = None
        if not full_access and rows:
            self_row = rows[0]

        return {
            "period": period,
            "rows": rows if full_access else [],
            "self": self_row,
            "full_access": full_access,
            "total_schools": len(rows),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # =================== PLANO DE AÇÃO AUTOMÁTICO (Sprint E) ===================

    async def _coverage_pending_summary(school_id: Optional[str]) -> dict:
        """Retorna pendências agregadas por componente×bimestre p/ uma escola."""
        filt_classes: dict = {}
        if school_id:
            filt_classes["school_id"] = school_id
        class_ids = [c['id'] async for c in db.classes.find(filt_classes, {"_id": 0, "id": 1})]
        if not class_ids:
            return {"pct": 100.0, "total": 0, "covered": 0, "missing": [], "critico_components": []}
        # adaptations
        adapts = await db.curriculum_adaptations.find(
            {"ativo": True}, {"_id": 0, "id": 1, "component_id": 1, "ano": 1, "bimestre": 1, "codigo_local": 1}
        ).to_list(length=5000)
        used_ids: set = set()
        async for lo in db.learning_objects.find(
            {"class_id": {"$in": class_ids}},
            {"_id": 0, "adaptation_ids": 1}
        ):
            for aid in (lo.get("adaptation_ids") or []):
                used_ids.add(aid)
        total = len(adapts)
        covered = sum(1 for a in adapts if a['id'] in used_ids)
        pct = round((covered / total * 100) if total else 100.0, 1)
        # Missing por (componente, bimestre)
        comp_map: dict = {}
        async for c in db.curriculum_components.find({}, {"_id": 0, "id": 1, "codigo": 1}):
            comp_map[c['id']] = c.get('codigo')
        from collections import defaultdict
        buckets = defaultdict(list)
        for a in adapts:
            if a['id'] not in used_ids:
                key = (comp_map.get(a['component_id'], '?'), a.get('bimestre'))
                buckets[key].append(a)
        critical = []
        for (comp, bim), lst in buckets.items():
            if not comp:
                continue
            critical.append({
                "componente_codigo": comp,
                "bimestre": bim,
                "missing_count": len(lst),
                "samples": [it.get('codigo_local') for it in lst[:5] if it.get('codigo_local')],
            })
        critical.sort(key=lambda x: -x["missing_count"])
        return {"pct": pct, "total": total, "covered": covered, "critico_components": critical[:5]}

    async def _lancamento_rate(school_id: Optional[str]) -> float:
        """Estimativa simples: registros dos últimos 30 dias / dias úteis * turmas.

        Retorna pct [0–1]. Quando não há dados suficientes retorna 1.0 (não pune).
        """
        filt: dict = {}
        if school_id:
            filt["school_id"] = school_id
        class_ids = [c['id'] async for c in db.classes.find(filt, {"_id": 0, "id": 1})]
        if not class_ids:
            return 1.0
        from datetime import timedelta
        d0 = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        lanzados = await db.learning_objects.count_documents(
            {"class_id": {"$in": class_ids}, "date": {"$gte": d0}}
        )
        # Meta heurística: 3 aulas/turma/semana × 4 semanas = 12 por turma em 30d
        expected = max(len(class_ids) * 12, 1)
        return min(lanzados / expected, 1.0)

    @router.get("/plano-acao")
    async def plan_of_action(
        request: Request,
        school_id: Optional[str] = None,
        period: str = Query("30d", pattern="^(7d|30d|60d|90d|all)$"),
    ):
        """Gera plano de ação priorizado (máx 5 ações) baseado em regras fixas.

        Motor determinístico — não depende de IA. Transparente e auditável.
        """
        user = await _auth_manager(request)
        # Se não super, força escola do usuário
        if user.get('role') not in ('super_admin', 'admin', 'admin_teste', 'secretario'):
            user_schools = [s.get('school_id') for s in user.get('school_links') or []]
            if not user_schools:
                raise HTTPException(403, "Usuário sem escola vinculada")
            if school_id and school_id not in user_schools:
                raise HTTPException(403, "Fora do seu escopo")
            school_id = school_id or user_schools[0]

        if not school_id:
            raise HTTPException(400, "school_id obrigatório para gerar plano")

        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        if not school:
            raise HTTPException(404, "Escola não encontrada")

        # 1. Métricas do ranking (reaproveita lógica)
        from datetime import timedelta
        window = {"7d": 7, "30d": 30, "60d": 60, "90d": 90, "all": None}[period]
        filt: dict = {"school_id": school_id}
        if window:
            filt["first_detected_at"] = {
                "$gte": (datetime.now(timezone.utc) - timedelta(days=window)).isoformat()
            }
        alerts = await db.intervention_alerts.find(filt, {"_id": 0}).to_list(length=5000)
        received = len(alerts)
        resolved_list = [a for a in alerts if a.get('resolved_at')]
        active_list = [a for a in alerts if not a.get('resolved_at')]
        level_3_active = [a for a in active_list if a.get('escalation_level') == 3]
        # tempo médio
        avg_days = None
        if resolved_list:
            soma = 0.0
            n = 0
            for a in resolved_list:
                try:
                    d1 = datetime.fromisoformat(a['first_detected_at'])
                    d2 = datetime.fromisoformat(a['resolved_at'])
                    if d1.tzinfo is None:
                        d1 = d1.replace(tzinfo=timezone.utc)
                    if d2.tzinfo is None:
                        d2 = d2.replace(tzinfo=timezone.utc)
                    soma += (d2 - d1).total_seconds() / 86400
                    n += 1
                except Exception:
                    pass
            if n:
                avg_days = round(soma / n, 1)
        resolution_rate = round(len(resolved_list) / received, 3) if received else 1.0

        # 2. Cobertura
        cov = await _coverage_pending_summary(school_id)

        # 3. Lançamentos
        lancamento_rate = round(await _lancamento_rate(school_id), 3)

        # 4. Classificação
        # score inline
        adj_time = 100 - ((avg_days or 0) * 5)
        score = max(min(max(0, min(adj_time, 100)) * 0.5 + resolution_rate * 100 * 0.4
                        - len(active_list) * 2, 100), 0)
        score = round(score, 1)
        if score >= 80:
            classif = "Adequado"
        elif score >= 60:
            classif = "Atenção"
        else:
            classif = "Crítico"

        # 5. Geração de ações (regras fixas)
        acoes = []

        # Regra 1 — Cobertura baixa
        if cov["pct"] < 70 and cov["critico_components"]:
            top = cov["critico_components"][0]
            samples = ', '.join(top.get('samples') or []) or '—'
            acoes.append({
                "categoria": "cobertura",
                "prioridade": 1,
                "titulo": f"Regularizar habilidades pendentes — {top['componente_codigo']} / {top.get('bimestre') or '—'}º bim.",
                "descricao": (
                    f"{top['missing_count']} habilidades ainda não foram trabalhadas. "
                    f"Exemplos: {samples}."
                ),
                "impacto": "alto",
                "prazo_dias": 7,
                "responsavel": "coordenador",
                "metrica_sucesso": f"Elevar cobertura de {top['componente_codigo']} a ≥90% no bimestre",
                "link": f"/admin/curriculo/cobertura?component={top['componente_codigo']}",
            })

        # Regra 2 — Muitos alertas N3
        if len(level_3_active) >= 3:
            turmas = list({a.get('class_name') for a in level_3_active if a.get('class_name')})[:5]
            acoes.append({
                "categoria": "nivel_3",
                "prioridade": 1,
                "titulo": "Intervenção imediata em turmas críticas (Nível 3)",
                "descricao": (
                    f"{len(level_3_active)} alertas estão há ≥4 semanas sem resolução. "
                    f"Turmas envolvidas: {', '.join(turmas) or '—'}."
                ),
                "impacto": "alto",
                "prazo_dias": 3,
                "responsavel": "diretor",
                "metrica_sucesso": "Zerar alertas Nível 3 em 7 dias",
                "link": "/admin/intervencoes",
            })

        # Regra 3 — Baixa execução do professor (lançamentos)
        if lancamento_rate < 0.7:
            acoes.append({
                "categoria": "lancamentos",
                "prioridade": 2,
                "titulo": "Cobrar regularização de lançamentos no diário",
                "descricao": (
                    f"Taxa de lançamentos em 30 dias: {round(lancamento_rate * 100)}% da meta. "
                    f"Professores podem estar atrasando registros."
                ),
                "impacto": "alto",
                "prazo_dias": 5,
                "responsavel": "coordenador",
                "metrica_sucesso": "Atingir ≥90% da meta de lançamentos em 2 semanas",
                "link": "/admin/learning-objects",
            })

        # Regra 4 — Baixa taxa de resolução
        if received >= 3 and resolution_rate < 0.6:
            acoes.append({
                "categoria": "fluxo_resposta",
                "prioridade": 3,
                "titulo": "Revisar fluxo de resposta a alertas",
                "descricao": (
                    f"Taxa de resolução: {round(resolution_rate * 100)}% "
                    f"({len(resolved_list)}/{received}). Reveja o procedimento de triagem."
                ),
                "impacto": "medio",
                "prazo_dias": 14,
                "responsavel": "coordenador",
                "metrica_sucesso": "Atingir ≥80% de taxa de resolução em 30 dias",
                "link": "/admin/intervencoes",
            })

        # Regra 5 — Tempo médio alto
        if avg_days is not None and avg_days > 5:
            acoes.append({
                "categoria": "tempo_resposta",
                "prioridade": 3,
                "titulo": "Implantar rotina semanal de acompanhamento",
                "descricao": (
                    f"Tempo médio de resolução: {avg_days} dias. "
                    f"Sugestão: reunião semanal de 30 minutos para triagem de alertas."
                ),
                "impacto": "medio",
                "prazo_dias": 14,
                "responsavel": "diretor",
                "metrica_sucesso": "Reduzir tempo médio para ≤3 dias em 30 dias",
                "link": "/admin/ranking-gestores",
            })

        # Ordenar e limitar
        acoes.sort(key=lambda a: (a["prioridade"],
                                  {"alto": 0, "medio": 1, "baixo": 2}.get(a.get("impacto"), 3)))
        acoes = acoes[:5]
        # reposicionar numeração final
        for i, a in enumerate(acoes, start=1):
            a["ordem"] = i

        return {
            "school_id": school_id,
            "school_name": school.get("name"),
            "period": period,
            "score": score,
            "classificacao": classif,
            "contexto": {
                "received": received,
                "resolved": len(resolved_list),
                "active": len(active_list),
                "level_3_active": len(level_3_active),
                "avg_resolution_days": avg_days,
                "resolution_rate": resolution_rate,
                "coverage_pct": cov["pct"],
                "coverage_missing_total": cov["total"] - cov["covered"],
                "lancamento_rate": lancamento_rate,
            },
            "acoes": acoes,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # =================== INBOX IN-APP ===================

    @router.get("/notifications")
    async def my_notifications(request: Request, limit: int = Query(30, le=200)):
        user = await _auth_any(request)
        cursor = (
            db.intervention_notifications.find({"user_id": user['id']}, {"_id": 0})
            .sort([("read", 1), ("created_at", -1)])
            .limit(limit)
        )
        items = await cursor.to_list(length=limit)
        unread = await db.intervention_notifications.count_documents(
            {"user_id": user['id'], "read": False}
        )
        return {"items": items, "unread": unread}

    @router.post("/notifications/{notif_id}/read")
    async def mark_read(notif_id: str, request: Request):
        user = await _auth_any(request)
        await db.intervention_notifications.update_one(
            {"id": notif_id, "user_id": user['id']},
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True}

    @router.post("/notifications/read-all")
    async def mark_all_read(request: Request):
        user = await _auth_any(request)
        r = await db.intervention_notifications.update_many(
            {"user_id": user['id'], "read": False},
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "updated": r.modified_count}

    # =================== SCHEDULER ===================

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

        async def scheduled_job():
            logger.info("[interventions] Cron semanal disparado")
            try:
                stats = await run_intervention_detection(db)
                logger.info("[interventions] detecção OK: %s", stats)
            except Exception as e:
                logger.error("[interventions] falha na detecção semanal: %s", e)

        # Toda segunda-feira às 07:00 UTC
        _scheduler.add_job(
            scheduled_job,
            CronTrigger(day_of_week='mon', hour=7, minute=0, timezone='UTC'),
            id='interventions_weekly',
            replace_existing=True,
        )
        try:
            _scheduler.start()
            logger.info("[interventions] Scheduler iniciado (seg 07:00 UTC)")
        except Exception as e:
            logger.warning("[interventions] Scheduler não pôde iniciar: %s", e)

    return router
