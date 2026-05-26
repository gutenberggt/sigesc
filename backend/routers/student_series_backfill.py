"""
[Sprint 1.2] Backfill de `students.student_series` (campo derivado).

PROBLEMA HISTÓRICO:
  ~1.497 alunos ativos no banco têm `student_series` vazio/null. Esse campo
  é a fonte primária para contagem por série em escolas multisseriadas e
  fallback para escolas regulares. A ausência distorce censo e painéis.

REGRA DE BACKFILL (validada com owner — Fev/2026):
  HARD INVARIANT: NUNCA sobrescreve `student_series` já preenchido.

  Para cada aluno elegível (status=active, student_series vazio/null):
    1. Localiza matrícula ATIVA (canonical — apenas 1 esperada pós Sprint 1.0).
    2. Localiza turma (`classes.id == enrollment.class_id`).
    3. Aplica regra de categoria:

  ┌──────┬─────────────────────────────────────────┬───────────────────────────┐
  │ Cat. │ Condição                                │ Ação                      │
  ├──────┼─────────────────────────────────────────┼───────────────────────────┤
  │  A   │ Turma regular (is_multi_grade=False)    │ FILL = classes.grade_level│
  │      │ AND classes.grade_level definido        │                           │
  ├──────┼─────────────────────────────────────────┼───────────────────────────┤
  │  B   │ Multisseriada (is_multi_grade=True)     │ FILL = classes.series[0]  │
  │      │ AND len(series)==1                      │                           │
  │      │ AND consistência verificada             │                           │
  │      │ (outros alunos da turma com             │                           │
  │      │  student_series preenchido bate ou      │                           │
  │      │  estão todos vazios)                    │                           │
  ├──────┼─────────────────────────────────────────┼───────────────────────────┤
  │  C   │ Multisseriada ambígua (series>=2 ou    │ SKIP (revisão pedagógica) │
  │      │  consistência falhou ou series==[])     │                           │
  ├──────┼─────────────────────────────────────────┼───────────────────────────┤
  │  D   │ Sem matrícula ativa                     │ SKIP                      │
  ├──────┼─────────────────────────────────────────┼───────────────────────────┤
  │  E   │ Matrícula sem class_id ou turma sem     │ SKIP (sem regex agora)    │
  │      │ grade_level                             │                           │
  └──────┴─────────────────────────────────────────┴───────────────────────────┘

TELEMETRIA NO ALUNO (apenas referencial, fonte primária = runs collection):
  - series_backfill_run_id:  uuid do run que aplicou
  - series_backfill_source:  "classes.grade_level" | "classes.series[0]"

ENDPOINTS:
  GET  /api/admin/students/series-backfill/preview              → read-only diagnóstico
  POST /api/admin/students/series-backfill/apply                → envelopado por critical_mutation
  GET  /api/admin/students/series-backfill/runs                 → histórico
  GET  /api/admin/students/series-backfill/runs/{run_id}        → detalhe
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from lib.critical_mutation import with_critical_mutation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
TARGET = "student_series_backfill"
RUNS_COLLECTION = "student_series_backfill_runs"
LOCKS_COLLECTION = "student_series_backfill_locks"
IDEMPOTENCY_COLLECTION = "student_series_backfill_idempotency"


class BackfillRequest(BaseModel):
    dry_run: bool = True


# ---------------------------------------------------------------------------
# Núcleo: detecção e categorização
# ---------------------------------------------------------------------------
def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


async def _build_class_series_consistency_map(db) -> Dict[str, set]:
    """Para cada `class_id`, retorna o conjunto distinto de
    `student_series` JÁ PREENCHIDO entre alunos com matrícula ativa.

    Usado pela regra B: turma multisseriada com `series=[X]` só é
    automatizável se todos os alunos atualmente preenchidos na turma
    concordam com X (ou nenhum preenchido).
    """
    pipeline = [
        {"$match": {"status": "active"}},
        # join na collection students para pegar student_series
        {"$lookup": {
            "from": "students",
            "localField": "student_id",
            "foreignField": "id",
            "as": "_stu",
        }},
        {"$unwind": "$_stu"},
        {"$match": {
            "_stu.student_series": {"$nin": [None, ""]},
            "class_id": {"$ne": None},
        }},
        {"$group": {
            "_id": "$class_id",
            "series_set": {"$addToSet": "$_stu.student_series"},
        }},
    ]
    out: Dict[str, set] = {}
    async for d in db.enrollments.aggregate(pipeline):
        out[d["_id"]] = set(d["series_set"])
    return out


async def _find_eligible_students(db) -> List[Dict[str, Any]]:
    """Alunos ATIVOS com `student_series` vazio."""
    cursor = db.students.find(
        {
            "status": {"$ne": "inactive"},
            "$or": [
                {"student_series": {"$exists": False}},
                {"student_series": None},
                {"student_series": ""},
            ],
        },
        {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "student_series": 1},
    )
    return await cursor.to_list(None)


async def _build_diagnostic(db) -> Dict[str, Any]:
    """Retorna o diagnóstico completo (preview read-only)."""
    eligible = await _find_eligible_students(db)
    student_ids = [s["id"] for s in eligible]

    # Carrega matrículas ativas dos elegíveis
    enrolls = {
        e["student_id"]: e
        async for e in db.enrollments.find(
            {"student_id": {"$in": student_ids}, "status": "active"},
            {"_id": 0, "student_id": 1, "class_id": 1, "id": 1},
        )
    }

    # Carrega turmas únicas envolvidas
    class_ids = list({e["class_id"] for e in enrolls.values() if e.get("class_id")})
    classes = {
        c["id"]: c
        async for c in db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "grade_level": 1, "is_multi_grade": 1,
             "series": 1, "school_id": 1},
        )
    }

    # Mapa de consistência por turma (regra B)
    class_consistency = await _build_class_series_consistency_map(db)

    # Nomes de escolas (cache)
    school_ids = list({c.get("school_id") for c in classes.values() if c.get("school_id")})
    school_ids += [s.get("school_id") for s in eligible if s.get("school_id")]
    school_ids = list({s for s in school_ids if s})
    schools = {
        s["id"]: s
        async for s in db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}
        )
    }

    # Categoriza cada aluno
    cat_A: List[Dict[str, Any]] = []
    cat_B: List[Dict[str, Any]] = []
    cat_C: List[Dict[str, Any]] = []  # multi ambíguo
    cat_D: List[Dict[str, Any]] = []  # sem matrícula
    cat_E: List[Dict[str, Any]] = []  # dados incompletos

    for stu in eligible:
        sid = stu["id"]
        enr = enrolls.get(sid)
        if not enr:
            cat_D.append({"student_id": sid, "student_name": stu.get("full_name"),
                          "reason": "no_active_enrollment"})
            continue
        cid = enr.get("class_id")
        if not cid:
            cat_E.append({"student_id": sid, "student_name": stu.get("full_name"),
                          "reason": "enrollment_without_class_id",
                          "enrollment_id": enr.get("id")})
            continue
        cls = classes.get(cid)
        if not cls:
            cat_E.append({"student_id": sid, "student_name": stu.get("full_name"),
                          "reason": "class_not_found", "class_id": cid})
            continue
        grade = cls.get("grade_level")
        is_multi = bool(cls.get("is_multi_grade"))
        series = cls.get("series") or []

        if not is_multi:
            if _is_empty(grade):
                cat_E.append({"student_id": sid, "student_name": stu.get("full_name"),
                              "reason": "class_without_grade_level",
                              "class_id": cid, "class_name": cls.get("name")})
                continue
            cat_A.append({
                "student_id": sid,
                "student_name": stu.get("full_name"),
                "class_id": cid,
                "class_name": cls.get("name"),
                "fill_with": grade,
                "source": "classes.grade_level",
            })
        else:
            # Multisseriada
            if len(series) == 1:
                consistent_set = class_consistency.get(cid, set())
                if not consistent_set or consistent_set == {series[0]}:
                    cat_B.append({
                        "student_id": sid,
                        "student_name": stu.get("full_name"),
                        "class_id": cid,
                        "class_name": cls.get("name"),
                        "fill_with": series[0],
                        "source": "classes.series[0]",
                        "consistency": "ok",
                    })
                else:
                    cat_C.append({
                        "student_id": sid,
                        "student_name": stu.get("full_name"),
                        "class_id": cid,
                        "class_name": cls.get("name"),
                        "reason": "multi_grade_inconsistent_filled_students",
                        "class_series": series,
                        "other_students_have_series": sorted(consistent_set),
                    })
            else:
                cat_C.append({
                    "student_id": sid,
                    "student_name": stu.get("full_name"),
                    "class_id": cid,
                    "class_name": cls.get("name"),
                    "reason": "multi_grade_multiple_or_empty_series",
                    "class_series": series,
                })

    # Agregações
    would_fill = len(cat_A) + len(cat_B)
    skipped = len(cat_C) + len(cat_D) + len(cat_E)

    # Distribuição por série derivada
    series_dist: Dict[str, int] = {}
    for c in cat_A + cat_B:
        series_dist[c["fill_with"]] = series_dist.get(c["fill_with"], 0) + 1

    # Quebra por escola
    by_school: Dict[str, Dict[str, int]] = {}
    for c in cat_A + cat_B:
        cls = classes.get(c["class_id"], {})
        school_id = cls.get("school_id") or "(sem_escola)"
        b = by_school.setdefault(school_id, {"would_fill": 0, "skipped": 0})
        b["would_fill"] += 1
    for c in cat_C + cat_E:
        cls = classes.get(c.get("class_id"), {})
        school_id = cls.get("school_id") or "(sem_escola)"
        b = by_school.setdefault(school_id, {"would_fill": 0, "skipped": 0})
        b["skipped"] += 1
    for c in cat_D:
        # alunos sem matrícula ativa — usa school_id do students.school_id
        stu_obj = next((s for s in eligible if s["id"] == c["student_id"]), {})
        school_id = stu_obj.get("school_id") or "(sem_escola)"
        b = by_school.setdefault(school_id, {"would_fill": 0, "skipped": 0})
        b["skipped"] += 1

    by_school_list = sorted(
        [
            {
                "school_id": sid,
                "school_name": (schools.get(sid) or {}).get("name") or sid,
                **counts,
            }
            for sid, counts in by_school.items()
        ],
        key=lambda x: -(x["would_fill"] + x["skipped"]),
    )

    return {
        "total_eligible": len(eligible),
        "would_fill": {
            "scenario_A_regular": len(cat_A),
            "scenario_B_single_multi_consistent": len(cat_B),
            "total": would_fill,
        },
        "skipped": {
            "scenario_C_multi_ambiguous": len(cat_C),
            "scenario_D_no_active_enrollment": len(cat_D),
            "scenario_E_incomplete_data": len(cat_E),
            "total": skipped,
        },
        "by_target_series": sorted(
            [{"grade_level": k, "count": v} for k, v in series_dist.items()],
            key=lambda x: -x["count"],
        ),
        "by_school": by_school_list[:50],  # top 50 escolas
        "sample_skipped": {
            "C": cat_C[:10],
            "D": cat_D[:10],
            "E": cat_E[:10],
        },
        # Listas internas para o executor reutilizar (não exposto na API)
        "_candidates_A": cat_A,
        "_candidates_B": cat_B,
    }


async def _execute_backfill_work(db, payload: BackfillRequest, run_id_hint: Optional[str]) -> Dict[str, Any]:
    """Executor compatível com `with_critical_mutation`.

    NÃO grava auditoria; quem grava é o wrapper. Apenas calcula candidatos,
    aplica updates (se !dry_run) e retorna `{mode, summary, diff, payload}`.
    """
    diag = await _build_diagnostic(db)
    candidates = diag["_candidates_A"] + diag["_candidates_B"]
    now_iso = datetime.now(timezone.utc).isoformat()
    filled = 0
    diff_applied: List[Dict[str, Any]] = []

    if not payload.dry_run and candidates:
        # Update em batch (chunks de 500 para evitar payload gigante)
        BATCH = 500
        # IMPORTANTE: cada update inclui filtro `student_series in [null, "", $exists:false]`
        # como GUARD para nunca sobrescrever (HARD INVARIANT).
        for i in range(0, len(candidates), BATCH):
            chunk = candidates[i:i + BATCH]
            for c in chunk:
                result = await db.students.update_one(
                    {
                        "id": c["student_id"],
                        "$or": [
                            {"student_series": {"$exists": False}},
                            {"student_series": None},
                            {"student_series": ""},
                        ],
                    },
                    {"$set": {
                        "student_series": c["fill_with"],
                        "series_backfill_run_id": run_id_hint or "pending",
                        "series_backfill_source": c["source"],
                        "series_backfill_at": now_iso,
                    }}
                )
                if result.modified_count == 1:
                    filled += 1
                    diff_applied.append({
                        "student_id": c["student_id"],
                        "from": None,
                        "to": c["fill_with"],
                        "source": c["source"],
                    })

    return {
        "mode": "dry_run" if payload.dry_run else "apply",
        "summary": {
            "total_eligible": diag["total_eligible"],
            "would_fill": diag["would_fill"]["total"],
            "filled": filled,
            "skipped_C": diag["skipped"]["scenario_C_multi_ambiguous"],
            "skipped_D": diag["skipped"]["scenario_D_no_active_enrollment"],
            "skipped_E": diag["skipped"]["scenario_E_incomplete_data"],
        },
        "diff": {
            "candidates_A": [
                {"student_id": c["student_id"], "to": c["fill_with"], "source": c["source"]}
                for c in diag["_candidates_A"]
            ],
            "candidates_B": [
                {"student_id": c["student_id"], "to": c["fill_with"], "source": c["source"]}
                for c in diag["_candidates_B"]
            ],
            # `applied` é a fonte da verdade para o rollback: cada entry traz
            # `from` (valor antes — sempre null/"" por HARD INVARIANT) e `to`
            # (valor preenchido). Permite reversão determinística sem
            # reconstruir a regra de migração.
            "applied": diff_applied,
            # [Sprint 1.2 — Rollback contract explícito]
            # Declara como esse run pode ser revertido. Field_restore =
            # restaura o valor exato do snapshot por campo.
            "rollback": {
                "type": "field_restore",
                "fields": ["student_series"],
                "telemetry_fields_to_unset": [
                    "series_backfill_run_id",
                    "series_backfill_source",
                    "series_backfill_at",
                ],
                "strategy": "restore_previous_value_from_snapshot",
                "reversed_by_run_id": None,  # populado quando rollback ocorre
            },
        },
        "payload": {
            "dry_run": payload.dry_run,
            "total_eligible": diag["total_eligible"],
            "would_fill": diag["would_fill"],
            "skipped": diag["skipped"],
            "by_target_series": diag["by_target_series"],
            "by_school": diag["by_school"],
            "sample_skipped": diag["sample_skipped"],
            "filled": filled,
        },
    }


# ---------------------------------------------------------------------------
# Router


async def _execute_rollback(
    db, original_run: Dict[str, Any], rollback_run_id: str
) -> Dict[str, Any]:
    """Reverte um apply do backfill conforme o `rollback contract` gravado
    no run original. Determinístico — não reprocessa regra de migração.

    Para cada entry em `original_run.diff.applied`:
      - restaura `students.student_series` para `entry.from` (geralmente null)
      - remove campos de telemetria (`series_backfill_*`)
      - guard CAS: só reverte se aluno ainda tem o valor `entry.to`
        (proteção contra rollback destrutivo se outro processo mudou
        o campo depois do apply original).
    """
    applied = (original_run.get("diff") or {}).get("applied") or []
    rollback_contract = (original_run.get("diff") or {}).get("rollback") or {}
    telemetry_fields = rollback_contract.get("telemetry_fields_to_unset") or [
        "series_backfill_run_id",
        "series_backfill_source",
        "series_backfill_at",
    ]

    reverted = 0
    skipped_no_match = 0
    diff_reverted: List[Dict[str, Any]] = []

    for entry in applied:
        student_id = entry.get("student_id")
        previous_value = entry.get("from")
        expected_current = entry.get("to")
        if not student_id:
            continue

        set_ops: Dict[str, Any] = {}
        unset_ops: Dict[str, Any] = {f: "" for f in telemetry_fields}
        if previous_value is None or previous_value == "":
            unset_ops["student_series"] = ""
        else:
            set_ops["student_series"] = previous_value

        update_doc: Dict[str, Any] = {}
        if set_ops:
            update_doc["$set"] = set_ops
        if unset_ops:
            update_doc["$unset"] = unset_ops

        result = await db.students.update_one(
            {"id": student_id, "student_series": expected_current},
            update_doc,
        )
        if result.modified_count == 1:
            reverted += 1
            diff_reverted.append({
                "student_id": student_id,
                "from": expected_current,
                "to": previous_value,
            })
        else:
            skipped_no_match += 1

    # Marca o run original como revertido (telemetria — fonte oficial é
    # o NOVO run com mode=rollback gravado pelo wrapper)
    try:
        await db[RUNS_COLLECTION].update_one(
            {"run_id": original_run["run_id"]},
            {"$set": {"diff.rollback.reversed_by_run_id": rollback_run_id}},
        )
    except Exception as e:
        logger.warning(f"[rollback] falha ao marcar run original: {e}")

    return {
        "mode": "rollback",
        "summary": {
            "reversed_run_id": original_run["run_id"],
            "reverted": reverted,
            "skipped_no_match": skipped_no_match,
            "total_in_original": len(applied),
        },
        "diff": {
            "reversed_run_id": original_run["run_id"],
            "applied": diff_reverted,
        },
        "payload": {
            "reversed_run_id": original_run["run_id"],
            "reverted": reverted,
            "skipped_no_match": skipped_no_match,
            "total_in_original": len(applied),
        },
    }


# ---------------------------------------------------------------------------
def setup_student_series_backfill_router(db):
    router = APIRouter(prefix="/admin/students", tags=["StudentSeriesBackfill"])

    @router.get("/series-backfill/preview")
    async def preview(request: Request):
        """Diagnóstico READ-ONLY. Retorna distribuição por categoria, escola
        e série derivada, com amostras de C/D/E para revisão pedagógica.
        Não altera nada no banco.
        """
        await AuthMiddleware.require_roles(['super_admin'])(request)
        diag = await _build_diagnostic(db)
        # Remove campos internos do retorno público
        diag.pop("_candidates_A", None)
        diag.pop("_candidates_B", None)
        diag["generated_at"] = datetime.now(timezone.utc).isoformat()
        return diag

    @router.post("/series-backfill/apply")
    async def apply(
        request: Request, payload: BackfillRequest, response: Response
    ):
        """Aplica o backfill. dry_run=True (default) só simula.

        [Sprint 1.1.E] Envelopado por `with_critical_mutation`:
          - Idempotency-Key (TTL 24h)
          - Lock por target (TTL 10min, 409 em concorrência)
          - Trilha em `student_series_backfill_runs`
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

        async def executor(run_id: str):
            # run_id pré-gerado pelo wrapper é gravado em cada aluno
            # (telemetria referencial; fonte primária = runs collection)
            return await _execute_backfill_work(db, payload, run_id_hint=run_id)

        return await with_critical_mutation(
            db,
            target=TARGET,
            actor=current_user,
            request=request,
            response=response,
            executor=executor,
            runs_collection=RUNS_COLLECTION,
            locks_collection=LOCKS_COLLECTION,
            idempotency_collection=IDEMPOTENCY_COLLECTION,
        )

    @router.get("/series-backfill/runs")
    async def list_runs(
        request: Request,
        mode: Optional[str] = Query(None, pattern="^(dry_run|apply)$"),
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
    ):
        await AuthMiddleware.require_roles(['super_admin'])(request)
        q: Dict[str, Any] = {}
        if mode:
            q["mode"] = mode
        cursor = (
            db[RUNS_COLLECTION]
            .find(q, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await db[RUNS_COLLECTION].count_documents(q)
        return {"total": total, "skip": skip, "limit": limit, "items": items}

    @router.get("/series-backfill/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        await AuthMiddleware.require_roles(['super_admin'])(request)
        doc = await db[RUNS_COLLECTION].find_one({"run_id": run_id}, {"_id": 0})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run não encontrado: {run_id}"
            )
        return doc

    @router.post("/series-backfill/runs/{run_id}/rollback")
    async def rollback_run(
        run_id: str, request: Request, response: Response
    ):
        """Reverte um apply específico via `rollback contract` do diff.

        Pré-condições (HTTP 409 / 400 se violadas):
          - run deve existir
          - run.mode deve ser `apply` (não reverte dry_run)
          - run não pode já ter sido revertido (diff.rollback.reversed_by_run_id)

        A reversão é determinística: lê `diff.applied[]` e restaura cada
        aluno ao estado anterior (geralmente `student_series = null`), com
        CAS lógico que NÃO sobrescreve mudanças posteriores ao apply.

        Cria um NOVO run com `mode='rollback'` apontando ao original via
        `summary.reversed_run_id` e `diff.reversed_run_id`.

        Envelopado por `with_critical_mutation` (lock + idempotency).
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

        original = await db[RUNS_COLLECTION].find_one(
            {"run_id": run_id}, {"_id": 0}
        )
        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run não encontrado: {run_id}"
            )
        if original.get("mode") != "apply":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Só é possível reverter runs com mode='apply' (esse é '{original.get('mode')}')"
            )
        already_reversed = (
            (original.get("diff") or {}).get("rollback", {}).get("reversed_by_run_id")
        )
        if already_reversed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Run já foi revertido anteriormente",
                    "reversed_by_run_id": already_reversed,
                }
            )

        async def executor(rollback_run_id: str):
            return await _execute_rollback(db, original, rollback_run_id)

        return await with_critical_mutation(
            db,
            target=TARGET,
            actor=current_user,
            request=request,
            response=response,
            executor=executor,
            runs_collection=RUNS_COLLECTION,
            locks_collection=LOCKS_COLLECTION,
            idempotency_collection=IDEMPOTENCY_COLLECTION,
        )

    return router
