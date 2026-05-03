"""
Router PMPI Intelligence — Onda 3.

Funcionalidades:
1. IA Preditiva (Claude Sonnet via Emergent LLM Key) — análise de risco por escola.
2. Perfil do Gestor — classifica diretor como proativo/reativo/crítico.
3. Ranking Institucional — score composto ordenando escolas.
4. Intervenção Progressiva — recomenda nível 1/2/3 por escola.
5. Relatório Mensal PDF — consolida KPIs + alertas + planos do mês.
6. Cron Diário — agendador rodando motor + metas automaticamente.
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope, is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pmpi", tags=["PMPI Intelligence"])

# Scheduler global (único por processo)
_scheduler: Optional[AsyncIOScheduler] = None


# --------------- Cálculo de score composto ---------------

def _score_from_kpis(kpis: dict) -> Optional[float]:
    """Score 0..100 como média ponderada dos 5 KPIs.
    - frequencia, aulas_lancadas, notas_lancadas, carga_horaria: % diretamente
    - atrasos_dias: penaliza (10 - min(atraso, 10)) * 10
    """
    weights = {
        "frequencia": 0.30,
        "aulas_lancadas": 0.20,
        "notas_lancadas": 0.20,
        "carga_horaria": 0.20,
        "atrasos_dias": 0.10,
    }
    total_w = 0.0
    total_v = 0.0
    for k, w in weights.items():
        v = kpis.get(k, {}).get("value")
        if v is None:
            continue
        if k == "atrasos_dias":
            v = max(0.0, 100.0 - min(float(v), 10.0) * 10.0)
        else:
            v = max(0.0, min(float(v), 100.0))
        total_v += v * w
        total_w += w
    if total_w == 0:
        return None
    return round(total_v / total_w, 2)


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    global _scheduler

    def _get_db(user: dict):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db else db
        return db

    def _can_read(user: dict) -> bool:
        return user.get("role") in (
            "super_admin", "admin", "admin_teste", "gerente",
            "semed", "semed1", "semed2", "semed3",
            "diretor", "coordenador", "secretario",
        )

    def _can_manage(user: dict) -> bool:
        return user.get("role") in (
            "super_admin", "admin", "admin_teste", "gerente",
            "semed", "semed1", "semed2", "semed3",
        )

    # ==================== IA PREDITIVA ====================

    @router.post("/ai/analyze/{school_id}")
    async def ai_analyze_school(school_id: str, request: Request):
        """Analisa KPIs de uma escola via Claude Sonnet e retorna:
        - nivel_risco (baixo/medio/alto)
        - analise (texto descritivo)
        - recomendacoes (lista de ações sugeridas)
        - previsao_proximo_mes (texto)
        """
        user = await AuthMiddleware.get_current_user(request)
        if not _can_read(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)

        # Busca KPIs da escola (reaproveita lógica do router pmpi)
        base_filter = apply_tenant_filter({}, user, request)
        school = await current_db.schools.find_one(
            {**base_filter, "id": school_id},
            {"_id": 0, "id": 1, "name": 1},
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        # Calcula KPIs usando o service compartilhado
        from services.pmpi_compute import compute_kpis_for_school
        kpis_full = await compute_kpis_for_school(current_db, school_id, days_window=30)
        kpis = {k: v.get("value") for k, v in kpis_full.items()}

        # Alertas ativos e planos em andamento
        alerts_open = await current_db.alerts.count_documents({
            **base_filter, "school_id": school_id, "status": "open",
        })
        plans_active = await current_db.action_plans.count_documents({
            **base_filter, "school_id": school_id,
            "status": {"$in": ["active", "in_progress"]},
        })

        # Tendência: frequência do mês anterior (comparativo)
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc)
        window_prev_start = (now - _td(days=60)).isoformat()[:10]
        window_prev_end = (now - _td(days=30)).isoformat()[:10]
        class_ids = []
        async for c in current_db.classes.find({"school_id": school_id}, {"_id": 0, "id": 1}):
            if c.get("id"):
                class_ids.append(c["id"])
        total_p, pres_p = 0, 0
        base_q = {"school_id": school_id, "date": {"$gte": window_prev_start, "$lt": window_prev_end}}
        first_att = await current_db.attendance.find_one(base_q, {"_id": 0, "id": 1})
        if first_att is None and class_ids:
            base_q = {"class_id": {"$in": class_ids},
                      "date": {"$gte": window_prev_start, "$lt": window_prev_end}}
        async for att in current_db.attendance.find(base_q, {"_id": 0, "records": 1}).limit(2000):
            for rec in (att.get("records") or []):
                total_p += 1
                if (rec.get("status") or "").lower() in ("presente", "present", "p"):
                    pres_p += 1
        freq_prev = round(100.0 * pres_p / total_p, 2) if total_p else None

        # Chama LLM
        from services.llm_client import chat_with_claude, llm_provider
        if llm_provider() == "none":
            raise HTTPException(status_code=500, detail="Nenhuma LLM key configurada (ANTHROPIC_API_KEY ou EMERGENT_LLM_KEY)")

        try:
            payload = {
                "escola": school.get("name"),
                "periodo_analise": "ultimos 30 dias",
                "kpis_atuais": kpis,
                "kpi_frequencia_mes_anterior": freq_prev,
                "alertas_abertos": alerts_open,
                "planos_ativos": plans_active,
                "mes_referencia": now.strftime("%Y-%m"),
            }
            system_prompt = (
                "Você é um analista sênior de gestão escolar brasileira. "
                "Receberá indicadores (KPIs) de uma escola e deverá retornar "
                "SOMENTE um JSON válido com as chaves: "
                "nivel_risco (string: 'baixo'|'medio'|'alto'), "
                "analise (string de 2-3 frases em português), "
                "recomendacoes (array de 3-5 strings, cada uma uma ação concreta), "
                "previsao_proximo_mes (string de 1-2 frases com projeção realista). "
                "Não inclua markdown, ```json ou qualquer texto fora do JSON. "
                "Considere que atrasos_dias é quanto menor melhor; demais KPIs são percentuais (0-100%). "
                "Níveis de risco: alto se algum KPI < 65%, médio se entre 65-80%, baixo se >= 80%."
            )
            raw = await chat_with_claude(
                system_prompt=system_prompt,
                user_text=f"Analise esta escola e retorne o JSON conforme o formato. DADOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}",
                session_id=f"pmpi-ai-{school_id}-{now.isoformat()}",
                model="claude-sonnet-4-5-20250929",
                timeout_s=45,
            )
            if not raw:
                raise HTTPException(status_code=502, detail="LLM indisponível ou timeout")
            # Tenta extrair JSON do response
            text = str(raw).strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1] if "```" in text else text
                if text.startswith("json"):
                    text = text[4:].strip()
            try:
                parsed = json.loads(text)
            except Exception:
                # Fallback: tenta achar { ... }
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(text[start:end + 1])
                else:
                    parsed = {"nivel_risco": "medio", "analise": text[:500],
                              "recomendacoes": [], "previsao_proximo_mes": ""}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("LLM error")
            raise HTTPException(status_code=502, detail=f"Erro LLM: {e}")

        # Persiste resultado
        record = {
            "id": str(uuid4()),
            "mantenedora_id": school.get("mantenedora_id"),
            "school_id": school_id,
            "school_name": school.get("name"),
            "kpis_input": kpis,
            "kpi_frequencia_mes_anterior": freq_prev,
            "alertas_abertos": alerts_open,
            "planos_ativos": plans_active,
            "nivel_risco": parsed.get("nivel_risco"),
            "analise": parsed.get("analise"),
            "recomendacoes": parsed.get("recomendacoes") or [],
            "previsao_proximo_mes": parsed.get("previsao_proximo_mes"),
            "generated_at": now.isoformat(),
            "generated_by": user.get("id"),
            "model": "claude-sonnet-4-5-20250929",
        }
        try:
            await current_db.ai_risk_analyses.insert_one(dict(record))
        except Exception:
            pass
        return record

    @router.get("/ai/analyses")
    async def list_analyses(request: Request,
                            school_id: Optional[str] = None,
                            limit: int = 50):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        query = apply_tenant_filter({}, user, request)
        if school_id:
            query["school_id"] = school_id
        cursor = current_db.ai_risk_analyses.find(query, {"_id": 0}).sort("generated_at", -1).limit(limit)
        return {"items": [x async for x in cursor]}

    # ==================== PERFIL DO GESTOR ====================

    @router.get("/manager-profile")
    async def list_manager_profiles(request: Request):
        """Calcula perfil (proativo/reativo/crítico) para diretores/gestores.
        
        Critérios baseados em dados de 60 dias:
        - tempo_medio_ack: tempo médio em horas para reconhecer alertas na sua escola
        - planos_no_prazo: % planos concluídos no prazo
        - alertas_reincidentes: nº de alertas reabertos na mesma regra/escola
        
        Classificação:
        - proativo: ack <=24h, planos >=70%, reincidentes <=1
        - reativo: ack <=72h E (planos >=40% OU reincidentes <=3)
        - critico: demais casos
        """
        user = await AuthMiddleware.get_current_user(request)
        if not _can_read(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        base = apply_tenant_filter({}, user, request)
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=60)).isoformat()

        # Fonte da verdade: school_assignments (Gestão de Servidores).
        # Gestores reais são lotados como diretor/coordenador no ano corrente.
        # Em users.role muitos aparecem como "professor" pois é o cadastro base.
        assignments = [a async for a in current_db.school_assignments.find(
            {
                **base,
                "status": "ativo",
                "academic_year": now.year,
                "funcao": {"$in": ["diretor", "coordenador"]},
            },
            {"_id": 0, "staff_id": 1, "school_id": 1, "funcao": 1},
        )]

        # Agrupa lotações por staff_id (um diretor pode atender múltiplas escolas)
        from collections import defaultdict
        schools_by_staff: dict = defaultdict(list)
        funcao_by_staff: dict = {}
        for a in assignments:
            sid = a.get("staff_id")
            if not sid:
                continue
            schools_by_staff[sid].append(a.get("school_id"))
            # Mantém prioridade: diretor > coordenador
            current_f = funcao_by_staff.get(sid)
            if current_f != "diretor":
                funcao_by_staff[sid] = a.get("funcao")

        if not schools_by_staff:
            return {"items": []}

        # Resolve nome/email + user_id direto via campo `staff.user_id`
        staff_ids = list(schools_by_staff.keys())
        staff_docs = await current_db.staff.find(
            {"id": {"$in": staff_ids}},
            {"_id": 0, "id": 1, "email": 1, "nome": 1, "user_id": 1},
        ).to_list(length=len(staff_ids))

        managers = []
        for sdoc in staff_docs:
            sid = sdoc["id"]
            school_ids = [s for s in schools_by_staff.get(sid, []) if s]
            if not school_ids:
                continue
            managers.append({
                "id": sdoc.get("user_id") or sid,  # user_id se já logou; senão staff_id
                "email": sdoc.get("email"),
                "full_name": sdoc.get("nome") or sdoc.get("email") or "Gestor",
                "role": funcao_by_staff.get(sid, "diretor"),
                "school_ids": school_ids,
            })

        results = []
        for m in managers:
            school_ids = m["school_ids"]
            if not school_ids:
                continue

            alerts_q = {**base, "school_id": {"$in": school_ids}, "detected_at": {"$gte": cutoff}}

            total_ack = 0
            sum_hours = 0.0
            reincidentes = 0
            seen_rules = set()
            async for a in current_db.alerts.find(alerts_q,
                {"_id": 0, "rule_id": 1, "detected_at": 1,
                 "acknowledged_at": 1, "acknowledged_by": 1}):
                if a.get("acknowledged_at") and a.get("acknowledged_by") == m["id"]:
                    try:
                        d1 = datetime.fromisoformat(str(a["detected_at"]).replace("Z", "+00:00"))
                        d2 = datetime.fromisoformat(str(a["acknowledged_at"]).replace("Z", "+00:00"))
                        delta_h = (d2 - d1).total_seconds() / 3600.0
                        if delta_h >= 0:
                            sum_hours += delta_h
                            total_ack += 1
                    except Exception:
                        pass
                rkey = (a.get("rule_id"), "__")
                if rkey in seen_rules:
                    reincidentes += 1
                else:
                    seen_rules.add(rkey)

            ack_avg_hours = round(sum_hours / total_ack, 1) if total_ack else None

            # Planos: % concluídos no prazo
            plans_q = {**base, "school_id": {"$in": school_ids},
                       "created_at": {"$gte": cutoff}}
            total_plans = await current_db.action_plans.count_documents(plans_q)
            on_time = 0
            async for p in current_db.action_plans.find(
                {**plans_q, "status": "completed"},
                {"_id": 0, "due_date": 1, "completed_at": 1}):
                try:
                    if p.get("due_date") and p.get("completed_at"):
                        d_due = datetime.fromisoformat(str(p["due_date"])[:10])
                        d_done = datetime.fromisoformat(str(p["completed_at"]).replace("Z", "+00:00"))
                        if d_done.tzinfo:
                            d_done = d_done.replace(tzinfo=None)
                        if d_done.date() <= d_due.date():
                            on_time += 1
                except Exception:
                    pass
            plans_ontime_pct = round(100.0 * on_time / total_plans, 1) if total_plans else None

            # Classificação
            if ack_avg_hours is not None and ack_avg_hours <= 24 and \
               (plans_ontime_pct is None or plans_ontime_pct >= 70) and reincidentes <= 1:
                profile = "proativo"
            elif ack_avg_hours is not None and ack_avg_hours <= 72 and \
                 ((plans_ontime_pct is not None and plans_ontime_pct >= 40) or reincidentes <= 3):
                profile = "reativo"
            else:
                profile = "critico"

            results.append({
                "user_id": m["id"],
                "user_name": m.get("full_name") or m.get("email"),
                "role": m.get("role"),
                "school_ids": school_ids,
                "tempo_medio_ack_horas": ack_avg_hours,
                "planos_no_prazo_pct": plans_ontime_pct,
                "alertas_reincidentes": reincidentes,
                "total_planos": total_plans,
                "perfil": profile,
            })

        return {"items": results, "computed_at": now.isoformat()}

    # ==================== RANKING INSTITUCIONAL ====================

    @router.get("/ranking")
    async def ranking(request: Request):
        """Ordena escolas do tenant pelo score composto dos 5 KPIs."""
        user = await AuthMiddleware.get_current_user(request)
        if not _can_read(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        base = apply_tenant_filter({}, user, request)
        schools_list = [s async for s in current_db.schools.find(
            base, {"_id": 0, "id": 1, "name": 1}
        )]

        # Usa service compartilhado para cálculo
        from services.pmpi_compute import compute_kpis_for_school
        now = datetime.now(timezone.utc)

        items = []
        for school in schools_list:
            k = await compute_kpis_for_school(current_db, school["id"], days_window=30)
            score = _score_from_kpis(k)
            items.append({
                "school_id": school["id"],
                "school_name": school.get("name"),
                "score": score,
                "kpis": k,
            })
        # Ordena desc por score (None vai pro final)
        items.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0)))
        # Atribui posição
        for i, it in enumerate(items, 1):
            it["position"] = i
        return {"items": items, "computed_at": now.isoformat()}

    # ==================== INTERVENÇÃO PROGRESSIVA ====================

    @router.get("/intervention-level/{school_id}")
    async def intervention_level(school_id: str, request: Request):
        """Calcula nível de intervenção recomendado (1/2/3) para uma escola.
        
        - Nível 1 (acompanhamento): 1-2 alertas abertos ou score 70-85
        - Nível 2 (intervenção): 3+ alertas OU 1+ alerta crítico OU score 50-70
        - Nível 3 (ação direta SEMED): 5+ alertas OU 2+ críticos OU score < 50
        """
        user = await AuthMiddleware.get_current_user(request)
        if not _can_read(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        base = apply_tenant_filter({}, user, request)
        school = await current_db.schools.find_one(
            {**base, "id": school_id}, {"_id": 0, "id": 1, "name": 1},
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")
        alerts_open = await current_db.alerts.count_documents({
            **base, "school_id": school_id, "status": "open",
        })
        alerts_critical = await current_db.alerts.count_documents({
            **base, "school_id": school_id, "status": "open", "severity": "critical",
        })
        # Chama ranking internamente para score
        ranking_res = await ranking(request)
        entry = next((x for x in ranking_res["items"] if x["school_id"] == school_id), None)
        score = entry["score"] if entry else None

        level = 1
        recommendation = "Acompanhamento regular"
        notify = ["diretor"]
        if alerts_open >= 5 or alerts_critical >= 2 or (score is not None and score < 50):
            level = 3
            recommendation = ("Ação direta da SEMED: visita técnica, auditoria pedagógica "
                              "e plano de recuperação institucional obrigatório em 7 dias.")
            notify = ["diretor", "coordenador", "semed", "secretario"]
        elif alerts_open >= 3 or alerts_critical >= 1 or (score is not None and score < 70):
            level = 2
            recommendation = ("Intervenção estruturada: plano de ação supervisionado pela "
                              "coordenação pedagógica em até 15 dias.")
            notify = ["diretor", "coordenador", "semed"]
        elif alerts_open >= 1 or (score is not None and score < 85):
            level = 1
            recommendation = "Acompanhamento regular com revisão semanal de indicadores."
            notify = ["diretor"]
        else:
            level = 0
            recommendation = "Escola em situação satisfatória. Manter boas práticas."
            notify = []

        return {
            "school_id": school_id,
            "school_name": school.get("name"),
            "intervention_level": level,
            "recommendation": recommendation,
            "notify_roles": notify,
            "alerts_open": alerts_open,
            "alerts_critical": alerts_critical,
            "score": score,
        }

    # ==================== CRON DIÁRIO ====================

    @router.get("/cron/status")
    async def cron_status(request: Request):
        """Retorna status do scheduler e jobs agendados."""
        await AuthMiddleware.get_current_user(request)
        if _scheduler is None:
            return {"running": False, "jobs": []}
        jobs = [{
            "id": j.id,
            "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        } for j in _scheduler.get_jobs()]
        return {"running": _scheduler.running, "jobs": jobs}

    @router.post("/cron/trigger-now")
    async def cron_trigger_now(request: Request):
        """Dispara manualmente a execução de todos os tenants (usado para teste)."""
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        await _daily_job_for_db(db)
        if sandbox_db is not None:
            try:
                await _daily_job_for_db(sandbox_db)
            except Exception:
                pass
        return {"ok": True, "triggered_at": datetime.now(timezone.utc).isoformat()}

    # -------- Inicializa scheduler (roda 1× ao subir o backend) --------
    if _scheduler is None:
        try:
            sch = AsyncIOScheduler(timezone="America/Belem")

            async def _job():
                try:
                    await _daily_job_for_db(db)
                    if sandbox_db is not None:
                        try:
                            await _daily_job_for_db(sandbox_db)
                        except Exception:
                            pass
                    logger.info("PMPI cron diário concluído.")
                except Exception as exc:
                    logger.exception(f"PMPI cron falhou: {exc}")

            # Todo dia às 06:00 (Belém)
            sch.add_job(_job, CronTrigger(hour=6, minute=0),
                        id="pmpi-daily", replace_existing=True)
            sch.start()
            _scheduler = sch
            logger.info("PMPI AsyncIOScheduler iniciado (job diário às 06:00 America/Belem).")
        except Exception as exc:
            logger.warning(f"Falha ao iniciar scheduler PMPI: {exc}")

    return router


# Job diário (fora do setup para ser importável)
async def _daily_job_for_db(target_db):
    """Executa motor de alertas + gera metas para TODOS os tenants do banco."""
    from services.pmpi_compute import compute_kpis_for_school
    now = datetime.now(timezone.utc)
    tenants = [t async for t in target_db.mantenedoras.find({}, {"_id": 0, "id": 1})]
    for t in tenants:
        tid = t.get("id")
        if not tid:
            continue
        schools_list = [s async for s in target_db.schools.find(
            {"mantenedora_id": tid}, {"_id": 0, "id": 1, "name": 1}
        )]
        rules = [r async for r in target_db.alert_rules.find(
            {"mantenedora_id": tid, "active": True}, {"_id": 0}
        )]
        matched_keys = set()

        for school in schools_list:
            sid = school["id"]
            kpis_full = await compute_kpis_for_school(target_db, sid, days_window=30)
            kpi_values = {k: v.get("value") for k, v in kpis_full.items()}

            def _cmp(v, op, thr):
                if v is None:
                    return False
                return ({"lt": v < thr, "lte": v <= thr, "gt": v > thr, "gte": v >= thr}.get(op, False))

            for rule in rules:
                val = kpi_values.get(rule["kpi"])
                if _cmp(val, rule["operator"], rule["threshold"]):
                    matched_keys.add((rule["id"], sid))
                    existing = await target_db.alerts.find_one(
                        {"rule_id": rule["id"], "school_id": sid, "status": "open"},
                        {"_id": 0, "id": 1},
                    )
                    if existing:
                        await target_db.alerts.update_one(
                            {"id": existing["id"]},
                            {"$set": {"kpi_value": val,
                                      "updated_at": now.isoformat(),
                                      "last_seen_at": now.isoformat()}},
                        )
                    else:
                        await target_db.alerts.insert_one({
                            "id": str(uuid4()),
                            "mantenedora_id": tid,
                            "school_id": sid,
                            "school_name": school.get("name"),
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                            "kpi": rule["kpi"],
                            "kpi_value": val,
                            "threshold": rule["threshold"],
                            "operator": rule["operator"],
                            "severity": rule["severity"],
                            "status": "open",
                            "detected_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                            "last_seen_at": now.isoformat(),
                            "source": "cron",
                        })
        # Auto-resolve
        async for a in target_db.alerts.find(
            {"mantenedora_id": tid, "status": "open"},
            {"_id": 0, "id": 1, "rule_id": 1, "school_id": 1}):
            if (a["rule_id"], a["school_id"]) not in matched_keys:
                await target_db.alerts.update_one(
                    {"id": a["id"]},
                    {"$set": {"status": "resolved",
                              "resolved_at": now.isoformat(),
                              "resolved_by_name": "cron-auto",
                              "updated_at": now.isoformat()}},
                )
        # Tag log
        try:
            await target_db.pmpi_cron_log.insert_one({
                "id": str(uuid4()),
                "mantenedora_id": tid,
                "ran_at": now.isoformat(),
                "schools_processed": len(schools_list),
                "rules_evaluated": len(rules),
            })
        except Exception:
            pass
