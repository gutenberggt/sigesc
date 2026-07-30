"""
FrequencyBatchBuilder — transforma o SSoT de frequência (coleção `attendance`) em lotes CMDE.

REGRAS (Sprint 002.b):
- SOMENTE LEITURA sobre `attendance` (e coleções de apoio students/schools/medical_certificates).
- NÃO cria regra nova de frequência: as faltas válidas vêm de
  `services.attendance_utils.compute_monthly_valid_absences` (consolidação por dia ≥50%, SSoT).
  `dias_letivos` é apenas a contagem de dias com aula registrada para o aluno na competência
  (representação derivada do mesmo SSoT); `frequencia_percentual` é derivado — NÃO altera dado.
- NÃO envia ao MEC. NÃO faz reserva/lease (Queue Manager é a 002.c).
- `dry_run=True` (padrão) → apenas PREVIEW (nada persistido). `dry_run=False` → persiste
  FrequencyBatch (ready) + QueueItem (pending), idempotente por `idempotency_key`. Exige
  competência ENCERRADA.
"""
import math
from datetime import datetime, timezone

from mig.core.ids import generate_correlation_id, compute_idempotency_key
from mig.core.audit import MigAuditService
from mig.core.exceptions import MigConfigError
from mig.cmde.config_repo import CmdeConfigRepository
from mig.cmde.frequency_models import FrequencyBatch, QueueItem, BatchTotals
from mig.cmde.frequency_repository import FrequencyRepository
from mig.cmde import frequency_validators as fval
from services.attendance_utils import (
    compute_monthly_valid_absences, fetch_medical_days_for_students,
)

PROVIDER = "cmde"
OPERATION = "frequency"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _current_competencia() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


class FrequencyBatchBuilder:
    def __init__(self, db, batch_size: int = 200):
        self.db = db
        self.batch_size = batch_size
        self.config_repo = CmdeConfigRepository(db)
        self.repo = FrequencyRepository(db)
        self.audit = MigAuditService(db)

    async def build(self, request, context: dict = None) -> dict:
        ctx = context or {}
        tenant = ctx.get("tenant")
        competencia = request.competencia
        try:
            year = int(competencia[:4]); month = int(competencia[5:7])
            assert 1 <= month <= 12
        except Exception:
            raise MigConfigError("Competência inválida. Use o formato AAAA-MM.")

        environment = (await self.config_repo.get_raw() or {}).get("environment", "homologacao")
        correlation_id = generate_correlation_id("CMDE")
        competencia_fechada = competencia < _current_competencia()

        # ---- 1. Leitura do SSoT (attendance) — somente leitura ----
        att_query = {"date": {"$regex": f"^{competencia}"}}
        if tenant:
            att_query["mantenedora_id"] = tenant
        if request.class_id:
            att_query["class_id"] = request.class_id
        elif request.school_id:
            klasses = await self.db.classes.find(
                {"school_id": request.school_id}, {"_id": 0, "id": 1}).to_list(100000)
            att_query["class_id"] = {"$in": [k["id"] for k in klasses]}

        docs = await self.db.attendance.find(
            att_query, {"_id": 0, "date": 1, "records": 1, "class_id": 1}).to_list(None)

        # ---- 2. Alunos + escolas (apoio, somente leitura) ----
        sids = sorted({r.get("student_id") for d in docs for r in (d.get("records") or [])
                       if r.get("student_id")})
        students = await self.db.students.find(
            {"id": {"$in": sids}},
            {"_id": 0, "id": 1, "full_name": 1, "cpf": 1, "nis": 1, "inep_code": 1, "school_id": 1}
        ).to_list(None) if sids else []
        stu_map = {s["id"]: s for s in students}
        school_ids = sorted({s.get("school_id") for s in students if s.get("school_id")})
        schools = await self.db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "inep_code": 1}
        ).to_list(None) if school_ids else []
        school_map = {s["id"]: s for s in schools}

        # ---- 3. Consolidação SSoT (NENHUMA regra nova) ----
        medical = await fetch_medical_days_for_students(self.db, sids, year)
        faltas_map = compute_monthly_valid_absences(docs, medical, set(sids))

        dias_by_sid: dict = {}
        for d in docs:
            date_str = (d.get("date") or "")[:10]
            for r in (d.get("records") or []):
                sid = r.get("student_id")
                if sid:
                    dias_by_sid.setdefault(sid, set()).add(date_str)

        # ---- 4. Monta itens + prontidão ----
        ready_items = []
        pendencias = []
        items_preview = []
        for sid in sids:
            stu = stu_map.get(sid, {})
            school = school_map.get(stu.get("school_id"), {})
            dias_letivos = len(dias_by_sid.get(sid, set()))
            faltas = int((faltas_map.get(sid) or {}).get(month, 0))
            freq = round((dias_letivos - faltas) / dias_letivos * 100, 1) if dias_letivos else 0.0
            record = {
                "student_id": sid,
                "full_name": stu.get("full_name", ""),
                "cpf": stu.get("cpf", ""),
                "nis": stu.get("nis", ""),
                "inep_aluno": stu.get("inep_code", ""),
                "school_inep": school.get("inep_code", ""),
                "competencia": competencia,
                "dias_letivos": dias_letivos,
                "faltas_validas": faltas,
                "frequencia_percentual": freq,
                "situacao": "",
            }
            missing = fval.missing_fields(record)
            item_ready = (not missing) and competencia_fechada
            idem = compute_idempotency_key(
                tenant=tenant, provider=PROVIDER, operation=OPERATION, competencia=competencia,
                student_id=sid, school_inep=record["school_inep"], payload_version=1)

            if item_ready:
                ready_items.append((record, idem))
            else:
                reasons = list(missing)
                if not competencia_fechada:
                    reasons.append("Competência não encerrada")
                if len(pendencias) < 500:
                    pendencias.append({"student_id": sid, "full_name": record["full_name"],
                                       "missing": reasons})
            if len(items_preview) < 10:
                items_preview.append({**record, "ready": item_ready, "idempotency_key": idem})

        analyzed = len(sids)
        ready_count = len(ready_items)
        pending_count = analyzed - ready_count
        lotes_previstos = math.ceil(ready_count / self.batch_size) if ready_count else 0

        # ---- 5. Persistência (apenas quando NÃO dry-run e competência fechada) ----
        persisted = False
        batch_ids = []
        if not request.dry_run:
            if not competencia_fechada:
                raise MigConfigError("Competência não encerrada — construção real bloqueada. "
                                     "Use dry-run ou aguarde o fechamento do mês.")
            for i in range(0, ready_count, self.batch_size):
                chunk = ready_items[i:i + self.batch_size]
                batch = FrequencyBatch(
                    correlation_id=correlation_id, tenant=tenant, environment=environment,
                    competencia=competencia, scope={"school_id": request.school_id,
                                                    "class_id": request.class_id},
                    status="ready", created_by=ctx.get("actor"),
                    totals=BatchTotals(items=len(chunk)))
                await self.repo.save_batch(batch)
                batch_ids.append(batch.id)
                for record, idem in chunk:
                    item = QueueItem(
                        batch_id=batch.id, correlation_id=correlation_id, tenant=tenant,
                        idempotency_key=idem, student_id=record["student_id"],
                        school_inep=record["school_inep"], competencia=competencia,
                        payload_snapshot=record, status="PENDING")
                    await self.repo.upsert_item(item)
            persisted = True

        # ---- 6. Auditoria (correlation_id ponta a ponta) ----
        await self.audit.record({
            "provider": PROVIDER,
            "operation": "FREQUENCY_BATCH_BUILT" if persisted else "FREQUENCY_BATCH_PREVIEW",
            "tenant": tenant, "actor": ctx.get("actor"), "status": "success",
            "started_at": _now_iso(), "finished_at": _now_iso(), "duration_ms": 0,
            "environment": environment, "correlation_id": correlation_id,
            "records_processed": analyzed, "records_accepted": ready_count,
            "records_rejected": pending_count,
        })

        return {
            "correlation_id": correlation_id, "competencia": competencia, "tenant": tenant,
            "environment": environment, "dry_run": bool(request.dry_run),
            "competencia_fechada": competencia_fechada, "batch_size": self.batch_size,
            "analyzed": analyzed, "ready_count": ready_count, "pending_count": pending_count,
            "lotes_previstos": lotes_previstos, "pendencias": pendencias,
            "items_preview": items_preview, "persisted": persisted, "batch_ids": batch_ids,
        }
