"""
Router PMPI Engine — Motor de Alertas e Metas (Onda 2).

Coleções novas:
- alert_rules: regras configuráveis (KPI + operador + threshold + severidade)
- alerts: alertas gerados (idempotente: open/acknowledged/resolved)
- monthly_goals: metas mensais por escola baseadas em média móvel

Endpoints:
- /alert-rules CRUD
- /alerts GET (list, filtros) + PUT (ack/resolve) + POST /run (executar motor)
- /monthly-goals GET + POST /generate (gera metas do mês atual)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, is_super_admin, get_mantenedora_scope

router = APIRouter(prefix="/pmpi", tags=["PMPI Engine"])


# =========== Constantes ===========
OPERATORS = {"lt", "lte", "gt", "gte"}
SEVERITIES = {"low", "medium", "high", "critical"}
ALERT_STATUS = {"open", "acknowledged", "resolved"}
KPI_METRICS = {"frequencia", "aulas_lancadas", "notas_lancadas",
               "atrasos_dias", "carga_horaria"}


# =========== Modelos ===========

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = ""
    kpi: str
    operator: str = "lt"                 # lt/lte/gt/gte
    threshold: float
    severity: str = "medium"             # low/medium/high/critical
    active: bool = True
    notify_roles: List[str] = Field(default_factory=lambda: ["diretor", "semed"])


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    kpi: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    active: Optional[bool] = None
    notify_roles: Optional[List[str]] = None


class AlertUpdate(BaseModel):
    status: str                          # acknowledged/resolved
    note: Optional[str] = None


# =========== Avaliação de regra ===========

def _compare(value: Optional[float], operator: str, threshold: float) -> bool:
    if value is None:
        return False
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    return False


# =========== Router setup ===========

def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    # Import atrasado para evitar ciclo
    from routers.pmpi import setup_router as _pmpi_setup  # noqa: F401

    def _get_db(user: dict):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db else db
        return db

    def _can_manage(user: dict) -> bool:
        return user.get("role") in (
            "super_admin", "admin", "admin_teste", "gerente",
            "semed", "semed1", "semed2", "semed3",
        )

    # ============= ALERT RULES CRUD =============

    @router.get("/alert-rules")
    async def list_rules(request: Request):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        query = apply_tenant_filter({}, user, request)
        cursor = current_db.alert_rules.find(query, {"_id": 0}).sort("created_at", -1)
        return {"items": [x async for x in cursor]}

    @router.post("/alert-rules")
    async def create_rule(payload: AlertRuleCreate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão para criar regras")
        if payload.kpi not in KPI_METRICS:
            raise HTTPException(status_code=400, detail=f"KPI inválido. Use {sorted(KPI_METRICS)}")
        if payload.operator not in OPERATORS:
            raise HTTPException(status_code=400, detail="Operador inválido")
        if payload.severity not in SEVERITIES:
            raise HTTPException(status_code=400, detail="Severidade inválida")
        current_db = _get_db(user)
        tenant_id = get_mantenedora_scope(user, request) or user.get("mantenedora_id")
        now = datetime.now(timezone.utc).isoformat()
        rule = {
            "id": str(uuid4()),
            "mantenedora_id": tenant_id,
            **payload.model_dump(),
            "created_by": user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await current_db.alert_rules.insert_one(dict(rule))
        return rule

    @router.put("/alert-rules/{rule_id}")
    async def update_rule(rule_id: str, payload: AlertRuleUpdate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": rule_id}, user, request)
        existing = await current_db.alert_rules.find_one(query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
        data = payload.model_dump(exclude_unset=True)
        if "kpi" in data and data["kpi"] not in KPI_METRICS:
            raise HTTPException(status_code=400, detail="KPI inválido")
        if "operator" in data and data["operator"] not in OPERATORS:
            raise HTTPException(status_code=400, detail="Operador inválido")
        if "severity" in data and data["severity"] not in SEVERITIES:
            raise HTTPException(status_code=400, detail="Severidade inválida")
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await current_db.alert_rules.update_one({"id": rule_id}, {"$set": data})
        return await current_db.alert_rules.find_one({"id": rule_id}, {"_id": 0})

    @router.delete("/alert-rules/{rule_id}")
    async def delete_rule(rule_id: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": rule_id}, user, request)
        existing = await current_db.alert_rules.find_one(query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
        await current_db.alert_rules.delete_one({"id": rule_id})
        return {"deleted": True}

    @router.post("/alert-rules/seed-defaults")
    async def seed_defaults(request: Request):
        """Semeia 5 regras padrão (1 por KPI) se ainda não existirem."""
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        tenant_id = get_mantenedora_scope(user, request) or user.get("mantenedora_id")
        defaults = [
            {"name": "Frequência crítica", "kpi": "frequencia", "operator": "lt",
             "threshold": 70, "severity": "critical", "description": "Frequência média < 70%"},
            {"name": "Aulas não lançadas", "kpi": "aulas_lancadas", "operator": "lt",
             "threshold": 70, "severity": "high",
             "description": "Menos de 70% das aulas previstas foram lançadas"},
            {"name": "Notas atrasadas", "kpi": "notas_lancadas", "operator": "lt",
             "threshold": 70, "severity": "high",
             "description": "Menos de 70% das notas do bimestre foram lançadas"},
            {"name": "Atraso excessivo em lançamentos", "kpi": "atrasos_dias",
             "operator": "gt", "threshold": 5, "severity": "medium",
             "description": "Atraso médio > 5 dias para registrar aulas"},
            {"name": "Carga horária abaixo do previsto", "kpi": "carga_horaria",
             "operator": "lt", "threshold": 65, "severity": "high",
             "description": "Execução da carga horária < 65% do previsto para o período"},
        ]
        created = []
        now = datetime.now(timezone.utc).isoformat()
        for d in defaults:
            exists = await current_db.alert_rules.find_one(
                {"mantenedora_id": tenant_id, "name": d["name"]}, {"_id": 0, "id": 1}
            )
            if exists:
                continue
            rule = {
                "id": str(uuid4()),
                "mantenedora_id": tenant_id,
                "active": True,
                "notify_roles": ["diretor", "semed"],
                "created_by": user.get("id"),
                "created_at": now,
                "updated_at": now,
                **d,
            }
            await current_db.alert_rules.insert_one(dict(rule))
            created.append(rule["name"])
        return {"seeded": created, "total_created": len(created)}

    # ============= ALERTS =============

    @router.get("/alerts")
    async def list_alerts(request: Request,
                          status: Optional[str] = None,
                          school_id: Optional[str] = None,
                          severity: Optional[str] = None,
                          limit: int = 200):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        query = apply_tenant_filter({}, user, request)
        if status:
            if status not in ALERT_STATUS:
                raise HTTPException(status_code=400, detail="Status inválido")
            query["status"] = status
        if school_id:
            query["school_id"] = school_id
        if severity:
            if severity not in SEVERITIES:
                raise HTTPException(status_code=400, detail="Severidade inválida")
            query["severity"] = severity
        cursor = current_db.alerts.find(query, {"_id": 0}).sort("detected_at", -1).limit(limit)
        items = [x async for x in cursor]
        # Contadores por severidade (abertos)
        open_q = {**query, "status": "open"}
        counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        async for row in current_db.alerts.aggregate([
            {"$match": open_q},
            {"$group": {"_id": "$severity", "n": {"$sum": 1}}},
        ]):
            sev = row.get("_id")
            if sev in counts:
                counts[sev] = row["n"]
        return {"items": items, "open_by_severity": counts}

    @router.put("/alerts/{alert_id}")
    async def update_alert(alert_id: str, payload: AlertUpdate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if payload.status not in ALERT_STATUS:
            raise HTTPException(status_code=400, detail="Status inválido")
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": alert_id}, user, request)
        existing = await current_db.alerts.find_one(query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Alerta não encontrado")
        now = datetime.now(timezone.utc).isoformat()
        update = {"status": payload.status, "updated_at": now}
        if payload.note is not None:
            update["note"] = payload.note
        if payload.status == "acknowledged":
            update["acknowledged_at"] = now
            update["acknowledged_by"] = user.get("id")
            update["acknowledged_by_name"] = user.get("full_name") or user.get("email")
        if payload.status == "resolved":
            update["resolved_at"] = now
            update["resolved_by"] = user.get("id")
            update["resolved_by_name"] = user.get("full_name") or user.get("email")
        await current_db.alerts.update_one({"id": alert_id}, {"$set": update})
        return await current_db.alerts.find_one({"id": alert_id}, {"_id": 0})

    @router.post("/alerts/run")
    async def run_engine(request: Request):
        """Executa o motor de alertas: percorre todas as escolas do tenant,
        calcula KPIs (reaproveitando a função do router PMPI) e avalia as regras.
        
        Para cada match (rule, school):
        - Se já existe alerta com status='open', atualiza o kpi_value
        - Senão, cria novo alerta
        Para alertas 'open' que deixaram de estar violados, marca como 'resolved'.
        """
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão para executar motor")
        current_db = _get_db(user)

        # Busca escolas e regras
        tenant_query = apply_tenant_filter({}, user, request)
        schools_list = [s async for s in current_db.schools.find(
            tenant_query, {"_id": 0, "id": 1, "name": 1}
        )]
        rules = [r async for r in current_db.alert_rules.find(
            {**tenant_query, "active": True}, {"_id": 0}
        )]
        if not rules:
            return {"processed_schools": len(schools_list), "rules": 0,
                    "alerts_created": 0, "alerts_resolved": 0,
                    "message": "Nenhuma regra ativa. Execute /alert-rules/seed-defaults."}

        # Import dinâmico do cálculo de KPIs (service compartilhado)
        from services.pmpi_compute import compute_kpis_for_school

        created = 0
        resolved = 0
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Para cada escola, calcula KPIs e avalia regras
        matched_keys = set()
        for school in schools_list:
            sid = school["id"]
            kpis_full = await compute_kpis_for_school(current_db, sid, days_window=30)
            # Extrai só o valor por KPI para avaliação das regras
            kpi_values = {k: v.get("value") for k, v in kpis_full.items()}

            for rule in rules:
                val = kpi_values.get(rule["kpi"])
                if _compare(val, rule["operator"], rule["threshold"]):
                    matched_keys.add((rule["id"], sid))
                    existing = await current_db.alerts.find_one(
                        {"rule_id": rule["id"], "school_id": sid, "status": "open"},
                        {"_id": 0, "id": 1},
                    )
                    if existing:
                        await current_db.alerts.update_one(
                            {"id": existing["id"]},
                            {"$set": {
                                "kpi_value": val,
                                "updated_at": now_iso,
                                "last_seen_at": now_iso,
                            }},
                        )
                    else:
                        alert = {
                            "id": str(uuid4()),
                            "mantenedora_id": rule["mantenedora_id"],
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
                            "detected_at": now_iso,
                            "updated_at": now_iso,
                            "last_seen_at": now_iso,
                        }
                        await current_db.alerts.insert_one(dict(alert))
                        created += 1

        # Auto-resolve alertas abertos que não estão mais violados
        open_cursor = current_db.alerts.find(
            {**tenant_query, "status": "open"}, {"_id": 0, "id": 1, "rule_id": 1, "school_id": 1}
        )
        async for a in open_cursor:
            key = (a["rule_id"], a["school_id"])
            if key not in matched_keys:
                await current_db.alerts.update_one(
                    {"id": a["id"]},
                    {"$set": {
                        "status": "resolved",
                        "resolved_at": now_iso,
                        "resolved_by_name": "motor-auto",
                        "updated_at": now_iso,
                    }},
                )
                resolved += 1

        return {
            "processed_schools": len(schools_list),
            "rules_evaluated": len(rules),
            "alerts_created": created,
            "alerts_auto_resolved": resolved,
            "ran_at": now_iso,
        }

    # ============= MONTHLY GOALS =============

    @router.get("/monthly-goals")
    async def list_goals(request: Request, month: Optional[str] = None):
        """Lista metas. Se `month` (YYYY-MM) não informado, retorna do mês atual."""
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        if not month:
            now = datetime.now(timezone.utc)
            month = f"{now.year}-{now.month:02d}"
        query = apply_tenant_filter({"month": month}, user, request)
        cursor = current_db.monthly_goals.find(query, {"_id": 0}).sort("school_name", 1)
        return {"items": [x async for x in cursor], "month": month}

    @router.post("/monthly-goals/generate")
    async def generate_goals(request: Request):
        """Gera metas do mês atual por escola.
        
        Lógica simples: usa o valor atual de cada KPI como baseline e define
        a meta como baseline + delta de melhoria (clamped a [50..100] para %).
        - Se value < 70 → meta = value + 10
        - Se 70 ≤ value < 85 → meta = value + 5
        - Se value ≥ 85 → meta = value
        - atrasos_dias: meta = max(2, floor(value * 0.8))
        """
        user = await AuthMiddleware.get_current_user(request)
        if not _can_manage(user):
            raise HTTPException(status_code=403, detail="Sem permissão")
        current_db = _get_db(user)
        now = datetime.now(timezone.utc)
        month = f"{now.year}-{now.month:02d}"
        tenant_query = apply_tenant_filter({}, user, request)
        tenant_id = get_mantenedora_scope(user, request) or user.get("mantenedora_id")

        schools_list = [s async for s in current_db.schools.find(
            tenant_query, {"_id": 0, "id": 1, "name": 1}
        )]

        # Reaproveita a função compute do service compartilhado
        from services.pmpi_compute import compute_kpis_for_school
        generated = 0
        updated = 0
        for school in schools_list:
            sid = school["id"]
            kpis_full = await compute_kpis_for_school(current_db, sid, days_window=30)
            baseline = {k: v.get("value") for k, v in kpis_full.items()}

            # Define metas
            goals = {}
            for metric in ("frequencia", "aulas_lancadas", "notas_lancadas", "carga_horaria"):
                v = baseline.get(metric)
                if v is None:
                    goals[metric] = 85.0
                elif v < 70:
                    goals[metric] = round(min(v + 10, 100.0), 1)
                elif v < 85:
                    goals[metric] = round(min(v + 5, 100.0), 1)
                else:
                    goals[metric] = round(v, 1)
            v = baseline.get("atrasos_dias")
            goals["atrasos_dias"] = max(2.0, round(v * 0.8, 1)) if v is not None else 2.0

            existing = await current_db.monthly_goals.find_one(
                {"mantenedora_id": tenant_id, "school_id": sid, "month": month},
                {"_id": 0, "id": 1},
            )
            payload = {
                "month": month,
                "school_id": sid,
                "school_name": school.get("name"),
                "mantenedora_id": tenant_id,
                "baseline": baseline,
                "goals": goals,
                "updated_at": now.isoformat(),
            }
            if existing:
                await current_db.monthly_goals.update_one(
                    {"id": existing["id"]}, {"$set": payload}
                )
                updated += 1
            else:
                payload["id"] = str(uuid4())
                payload["created_at"] = now.isoformat()
                await current_db.monthly_goals.insert_one(dict(payload))
                generated += 1

        return {
            "month": month,
            "schools": len(schools_list),
            "goals_created": generated,
            "goals_updated": updated,
        }

    return router
