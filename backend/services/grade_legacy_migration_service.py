"""
[Fase 2 — Fev/2026] Migração definitiva da Grade Horária:
`class_schedules` (legacy) → `teacher_class_assignments` (modelo novo).

CONTEXTO ARQUITETURAL:
  O erro original foi clássico — WRITE em uma coleção (`class_schedules`,
  onde a UI "Horário de Aulas" grava) e READ em outra
  (`teacher_class_assignments`, onde o painel de Integridade/Diário lê).
  O hotfix (Fase 1) corrigiu a LEITURA (dual-read). A Fase 2 corrige a
  MODELAGEM: persiste a grade no modelo novo como fonte única da verdade.

ESTRATÉGIA (aprovada pelo owner):
  - curto prazo  → compatibilidade e estabilidade (dual-read + bridge mantidos)
  - médio prazo  → fonte única de verdade (esta migração)
  - longo prazo  → remoção controlada do legado (sprint futuro)

TRANSFORM:
  Reutiliza `services.legacy_schedule_bridge.build_assignments_from_legacy`
  (já validado nas Fases 9/10 do Diário). ZERO regra nova de mapeamento.

HARD INVARIANTS:
  1. NUNCA toca turma que já possui assignment REAL no modelo novo
     (source != "legacy_migration"). Idempotência: só migra onde o novo
     está vazio de dados reais.
  2. Id determinístico `legacy::{class}::{course}::{teacher}` → re-rodar
     não duplica; rollback apaga exatamente esses docs.
  3. Apply FALHA se detectar duplicidade determinística inesperada (id já
     existe vinculado a um doc NÃO-migração).
  4. Rollback só apaga docs criados pela migração (CAS rigoroso:
     `updated_at == created_at`), nunca um doc editado manualmente depois.

NÃO remове (mantidos para compatibilidade): dual-read do painel, bridge
legacy, compat com Diário e Attendance.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.legacy_schedule_bridge import build_assignments_from_legacy

logger = logging.getLogger(__name__)

COLLECTION = "teacher_class_assignments"
MIGRATION_SOURCE = "legacy_migration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# Diagnóstico de buckets (reaproveitável — espelha o endpoint
# /maintenance/schedules-write-read-diagnostic, mas como função pura de I/O).
# ===========================================================================
async def compute_schedules_diagnostic(db, academic_year: int) -> Dict[str, Any]:
    """Buckets legacy vs novo para o ano. READ-ONLY."""
    classes_active = await db.classes.find(
        {"academic_year": academic_year},
        {"_id": 0, "id": 1, "status": 1},
    ).to_list(5000)
    active_ids = {
        c["id"] for c in classes_active
        if (c.get("status") or "active") == "active"
    }

    try:
        legacy_raw = await db.class_schedules.distinct("class_id", {})
    except Exception:
        legacy_raw = []
    legacy_ids = {cid for cid in legacy_raw if cid in active_ids}

    try:
        new_raw = await db[COLLECTION].distinct("class_id", {"deleted": {"$ne": True}})
    except Exception:
        new_raw = []
    new_ids = {cid for cid in new_raw if cid in active_ids}

    both = legacy_ids & new_ids
    legacy_only = legacy_ids - new_ids
    new_only = new_ids - legacy_ids
    without_any = active_ids - legacy_ids - new_ids
    return {
        "academic_year": academic_year,
        "total_active_classes": len(active_ids),
        "with_class_schedules": len(legacy_ids),
        "with_teacher_assignments": len(new_ids),
        "both": len(both),
        "legacy_only": len(legacy_only),
        "new_only": len(new_only),
        "without_any_schedule": len(without_any),
    }


# ===========================================================================
# Helpers de candidatura
# ===========================================================================
def _build_class_filter(scope: Dict[str, Any], default_year: int) -> Dict[str, Any]:
    flt: dict = {"academic_year": scope.get("academic_year") or default_year}
    if scope.get("school_id"):
        flt["school_id"] = scope["school_id"]
    if scope.get("class_id"):
        flt["id"] = scope["class_id"]
    return flt


async def _classes_with_real_new_model(db, class_ids: List[str]) -> set:
    """Conjunto de class_ids que JÁ possuem assignment REAL no modelo novo
    (source != legacy_migration, não deletado). Estes são INTOCÁVEIS
    (HARD INVARIANT 1)."""
    if not class_ids:
        return set()
    cursor = db[COLLECTION].find(
        {
            "class_id": {"$in": class_ids},
            "deleted": {"$ne": True},
            "source": {"$ne": MIGRATION_SOURCE},
        },
        {"_id": 0, "class_id": 1},
    )
    return {d["class_id"] async for d in cursor}


def _enrich_assignment(
    synthetic: Dict[str, Any],
    class_doc: Dict[str, Any],
    schedule: Dict[str, Any],
    academic_year: int,
    run_id: Optional[str],
    now_iso: str,
) -> Dict[str, Any]:
    """Enriquece a saída do bridge para o shape pleno do modelo novo +
    marcadores de migração."""
    doc = dict(synthetic)
    doc["class_name"] = class_doc.get("name")
    doc["shift"] = schedule.get("shift") or class_doc.get("shift")
    doc["academic_year"] = academic_year
    doc["deleted"] = False
    doc["is_substitute"] = bool(doc.get("is_substitute", False))
    # Marcadores institucionais (auditoria + rollback determinístico)
    doc["source"] = MIGRATION_SOURCE
    doc["migrated_from_legacy"] = True
    doc["migration_run_id"] = run_id
    doc["synthetic_validity"] = True
    # CAS anchor: created_at == updated_at no nascimento; edição manual bumpa.
    doc["created_at"] = now_iso
    doc["updated_at"] = now_iso
    doc["created_by"] = MIGRATION_SOURCE
    return doc


# ===========================================================================
# Diagnóstico / Preview
# ===========================================================================
async def build_migration_diagnostic(
    db, scope: Dict[str, Any], run_id: Optional[str] = None
) -> Dict[str, Any]:
    """Monta o plano de migração (read-only). Retorna candidatos enriquecidos
    + agregações exigidas pelo owner.
    """
    default_year = datetime.now(timezone.utc).year
    year = scope.get("academic_year") or default_year
    now_iso = _now_iso()

    class_filter = _build_class_filter(scope, default_year)
    classes = await db.classes.find(
        class_filter,
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1,
         "academic_year": 1, "status": 1, "shift": 1},
    ).to_list(5000)
    classes = [c for c in classes if (c.get("status") or "active") == "active"]
    class_by_id = {c["id"]: c for c in classes}
    all_class_ids = list(class_by_id.keys())

    # Turmas com modelo novo REAL → intocáveis
    real_new = await _classes_with_real_new_model(db, all_class_ids)

    candidates: List[Dict[str, Any]] = []          # docs a criar (enriquecidos)
    affected_class_ids: set = set()
    ignored_has_new: List[Dict[str, Any]] = []     # turmas puladas (invariante 1)
    no_legacy_slots: List[str] = []                # tem class_schedules mas sem slots úteis

    for cid in all_class_ids:
        cls = class_by_id[cid]
        if cid in real_new:
            ignored_has_new.append({
                "class_id": cid, "class_name": cls.get("name"),
                "school_id": cls.get("school_id"),
                "reason": "already_has_real_new_model",
            })
            continue
        # Schedule legacy desta turma
        schedule = await db.class_schedules.find_one({"class_id": cid}, {"_id": 0})
        if not schedule:
            continue
        bridged = await build_assignments_from_legacy(db, class_doc=cls)
        if not bridged:
            no_legacy_slots.append(cid)
            continue
        for b in bridged:
            candidates.append(
                _enrich_assignment(b, cls, schedule, year, run_id, now_iso)
            )
            affected_class_ids.add(cid)

    # Estado atual no banco dos ids candidatos → desconta o que já foi migrado
    # (progresso real) e mapeia source para a checagem de invariante no apply.
    cand_ids = [c["id"] for c in candidates]
    existing_map: Dict[str, Optional[str]] = {}
    if cand_ids:
        async for d in db[COLLECTION].find(
            {"id": {"$in": cand_ids}}, {"_id": 0, "id": 1, "source": 1}
        ):
            existing_map[d["id"]] = d.get("source")

    pending = [c for c in candidates if c["id"] not in existing_map]
    already_migrated = sum(
        1 for c in candidates if existing_map.get(c["id"]) == MIGRATION_SOURCE
    )
    unexpected_ids = [
        cid for cid, src in existing_map.items() if src != MIGRATION_SOURCE
    ]
    pending_class_ids = {c["class_id"] for c in pending}

    # Agregações por escola — baseadas no que FALTA migrar (pending)
    by_school: Dict[str, Dict[str, Any]] = {}
    for doc in pending:
        sid = doc.get("school_id") or "(sem_escola)"
        b = by_school.setdefault(sid, {"classes": set(), "assignments": 0})
        b["classes"].add(doc["class_id"])
        b["assignments"] += 1
    school_ids = [s for s in by_school.keys() if s != "(sem_escola)"]
    school_names: Dict[str, str] = {}
    if school_ids:
        async for s in db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}
        ):
            school_names[s["id"]] = s.get("name")
    by_school_list = sorted(
        [
            {
                "school_id": sid,
                "school_name": school_names.get(sid, sid),
                "classes": len(v["classes"]),
                "assignments": v["assignments"],
            }
            for sid, v in by_school.items()
        ],
        key=lambda x: -x["assignments"],
    )

    sample = (pending or candidates)[:5]

    return {
        "scope": {
            "academic_year": year,
            "school_id": scope.get("school_id"),
            "class_id": scope.get("class_id"),
        },
        "total_classes_affected": len(pending_class_ids),
        "total_assignments_to_create": len(pending),
        "already_migrated_assignments": already_migrated,
        "ignored_classes_with_new_model": len(ignored_has_new),
        "classes_with_legacy_but_no_usable_slots": len(no_legacy_slots),
        "unexpected_duplicate_ids": unexpected_ids[:20],
        "by_school": by_school_list,
        "ignored_sample": ignored_has_new[:5],
        "sample_synthesized": sample,
        # internos (não expor no preview público)
        "_candidates": candidates,
        "_pending": pending,
        "_existing_map": existing_map,
        "_unexpected_ids": unexpected_ids,
        "_affected_class_ids": sorted(pending_class_ids),
    }


# ===========================================================================
# Apply
# ===========================================================================
class UnexpectedDeterministicDuplicate(Exception):
    """Id determinístico colidiu com um doc NÃO-migração — aborta o apply."""


async def execute_migration(
    db, scope: Dict[str, Any], dry_run: bool, run_id: str
) -> Dict[str, Any]:
    """Executor compatível com `with_critical_mutation`.

    NÃO grava auditoria de run (quem grava é o wrapper). Calcula candidatos,
    valida duplicidade determinística, insere (se !dry_run) e devolve
    `{mode, summary, diff, payload}`.
    """
    default_year = datetime.now(timezone.utc).year
    year = scope.get("academic_year") or default_year

    t0 = time.monotonic()
    diag_before = await compute_schedules_diagnostic(db, year)
    diag = await build_migration_diagnostic(db, scope, run_id=run_id)
    candidates: List[Dict[str, Any]] = diag["_candidates"]
    pending: List[Dict[str, Any]] = diag["_pending"]
    unexpected_ids: List[str] = diag["_unexpected_ids"]

    created = 0
    already_present = diag["already_migrated_assignments"]
    diff_applied: List[Dict[str, Any]] = []

    if not dry_run and candidates:
        # INVARIANTE 3: colisão com doc NÃO-migração → aborta tudo.
        if unexpected_ids:
            raise UnexpectedDeterministicDuplicate(
                f"{len(unexpected_ids)} id(s) determinístico(s) já existem vinculados "
                f"a documentos NÃO-migração. Abortado para preservar integridade. "
                f"Exemplos: {unexpected_ids[:5]}"
            )

        if pending:
            # Insere CÓPIAS: o driver injeta `_id` (ObjectId) nos dicts passados;
            # usando cópias preservamos `candidates`/`sample_synthesized` livres
            # de ObjectId (que quebraria a serialização JSON da resposta).
            await db[COLLECTION].insert_many([dict(c) for c in pending], ordered=False)
            created = len(pending)
            for c in pending:
                diff_applied.append({
                    "id": c["id"],
                    "class_id": c["class_id"],
                    "school_id": c.get("school_id"),
                    "component_id": c.get("component_id"),
                    "teacher_id": c.get("teacher_id"),
                    "created_at": c["created_at"],
                })

    elapsed_s = max(time.monotonic() - t0, 1e-6)
    throughput = round(created / elapsed_s, 2) if created else 0.0

    # Diagnóstico pós (só relevante em apply real)
    diag_after = await compute_schedules_diagnostic(db, year) if not dry_run else diag_before
    legacy_only_dropped = diag_before["legacy_only"] - diag_after["legacy_only"]
    without_any_delta = diag_after["without_any_schedule"] - diag_before["without_any_schedule"]
    diagnostic_ok = (legacy_only_dropped >= 0) and (without_any_delta <= 0)

    return {
        "mode": "dry_run" if dry_run else "apply",
        "summary": {
            "scope": diag["scope"],
            "total_classes_affected": diag["total_classes_affected"],
            "total_assignments_to_create": diag["total_assignments_to_create"],
            "created": created,
            "already_present_idempotent": already_present,
            "already_migrated_assignments": diag["already_migrated_assignments"],
            "ignored_classes_with_new_model": diag["ignored_classes_with_new_model"],
            "elapsed_seconds": round(elapsed_s, 3),
            "throughput_docs_per_sec": throughput,
            "diagnostic_before": diag_before,
            "diagnostic_after": diag_after,
            "legacy_only_dropped": legacy_only_dropped,
            "without_any_delta": without_any_delta,
            "diagnostic_ok": diagnostic_ok,
        },
        "diff": {
            "applied": diff_applied,
            # [Rollback contract explícito]
            "rollback": {
                "type": "delete_created",
                "collection": COLLECTION,
                "match": {"migration_run_id": run_id, "source": MIGRATION_SOURCE},
                "cas": "delete somente se updated_at == created_at (não editado após migração)",
                "reversed_by_run_id": None,
            },
        },
        "payload": {
            "dry_run": dry_run,
            "scope": diag["scope"],
            "total_classes_affected": diag["total_classes_affected"],
            "total_assignments_to_create": diag["total_assignments_to_create"],
            "created": created,
            "already_present_idempotent": already_present,
            "already_migrated_assignments": diag["already_migrated_assignments"],
            "ignored_classes_with_new_model": diag["ignored_classes_with_new_model"],
            "by_school": diag["by_school"],
            "sample_synthesized": diag["sample_synthesized"],
            "elapsed_seconds": round(elapsed_s, 3),
            "throughput_docs_per_sec": throughput,
            "diagnostic_before": diag_before,
            "diagnostic_after": diag_after,
            "diagnostic_ok": diagnostic_ok,
        },
    }


# ===========================================================================
# Rollback
# ===========================================================================
async def execute_rollback(
    db, original_run: Dict[str, Any], rollback_run_id: str, runs_collection: str
) -> Dict[str, Any]:
    """Reverte um apply apagando APENAS os docs criados por ele, com CAS
    rigoroso (`updated_at == created_at`). Nunca apaga doc editado depois.
    """
    original_run_id = original_run["run_id"]
    applied = (original_run.get("diff") or {}).get("applied") or []

    reverted = 0
    skipped_manual_edit = 0
    skipped_missing = 0
    report: List[Dict[str, Any]] = []

    for entry in applied:
        aid = entry.get("id")
        if not aid:
            continue
        # CAS: só apaga se ainda é doc de migração deste run E não foi editado
        # (updated_at == created_at).
        res = await db[COLLECTION].delete_one({
            "id": aid,
            "migration_run_id": original_run_id,
            "source": MIGRATION_SOURCE,
            "$expr": {"$eq": ["$updated_at", "$created_at"]},
        })
        if getattr(res, "deleted_count", 0) == 1:
            reverted += 1
            report.append({"id": aid, "status": "deleted"})
        else:
            # Distingue: existe mas foi editado (manual) vs não existe mais
            still = await db[COLLECTION].find_one(
                {"id": aid}, {"_id": 0, "id": 1, "updated_at": 1, "created_at": 1, "source": 1}
            )
            if still:
                skipped_manual_edit += 1
                report.append({"id": aid, "status": "skipped_manual_edit_or_changed"})
            else:
                skipped_missing += 1
                report.append({"id": aid, "status": "already_absent"})

    # Marca o run original como revertido (telemetria; fonte oficial = novo run)
    try:
        await db[runs_collection].update_one(
            {"run_id": original_run_id},
            {"$set": {"diff.rollback.reversed_by_run_id": rollback_run_id}},
        )
    except Exception as e:
        logger.warning(f"[grade_migration rollback] falha ao marcar run original: {e}")

    return {
        "mode": "rollback",
        "summary": {
            "reversed_run_id": original_run_id,
            "reverted": reverted,
            "skipped_manual_edit": skipped_manual_edit,
            "skipped_missing": skipped_missing,
            "total_in_original": len(applied),
        },
        "diff": {
            "reversed_run_id": original_run_id,
            "report": report,
        },
        "payload": {
            "reversed_run_id": original_run_id,
            "reverted": reverted,
            "skipped_manual_edit": skipped_manual_edit,
            "skipped_missing": skipped_missing,
            "total_in_original": len(applied),
            "report": report[:200],
        },
    }
