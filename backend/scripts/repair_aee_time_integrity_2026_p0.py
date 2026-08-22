"""P0 AEE — correção controlada dos 14 registros temporais históricos de 2026.

Dry-run por padrão. O modo --apply só prossegue se TODOS os 14 documentos ainda
estiverem exatamente no estado auditado e se os dois Planos alvo não possuírem
head AEE V2. A seleção é exclusivamente por IDs e valores esperados.

Antes de alterar os documentos, grava backup lógico em
``aee_time_integrity_repairs``. Em falha intermediária, tenta restaurar os
registros já modificados usando os snapshots de precheck.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from aee_v2.time_integrity import classify_time_interval, validate_time_interval


OPERATION_ID = "P0_AEE_TIME_2026_20260822_V1"
BACKUP_COLLECTION = "aee_time_integrity_repairs"

PLAN_TARGETS = [
    {
        "id": "26a44929-759a-4112-9904-e785e39c4179",
        "expected": {
            "academic_year": 2026,
            "horario_inicio": "03:30",
            "horario_fim": "05:00",
        },
        "update": {
            "horario_inicio": "15:30",
            "horario_fim": "17:00",
        },
        "reason": "Registro vespertino digitado sem o prefixo 1 nas horas.",
    },
    {
        "id": "7ab2f140-832f-480c-a8be-b1ca4d631633",
        "expected": {
            "academic_year": 2026,
            "horario_inicio": "13:30",
            "horario_fim": "03:00",
        },
        "update": {
            "horario_inicio": "13:30",
            "horario_fim": "15:00",
        },
        "reason": "Horário final vespertino registrado como 03:00 em vez de 15:00.",
    },
]

NICOLLAS_PLAN_ID = "7ab2f140-832f-480c-a8be-b1ca4d631633"
ATTENDANCE_IDS = [
    "d64bb7aa-c942-4701-90f8-dd3f9d71b264",
    "7202420c-a404-4c11-ad2e-7074d10dca0d",
    "7355b71e-7faa-4d9f-b9a7-ac6f9ac927a4",
    "4e2d0f02-d694-4034-889b-d7eddd18ba07",
    "a59e6d02-f3f0-4fab-bcdb-b602c040c677",
    "8c338174-763e-4b01-97e6-f62accdadf01",
    "1ef6dc9d-0a6f-4c3f-ab8d-3f0675d100e5",
    "ff724844-c81c-4e7b-bdf5-160059e9bc1d",
    "67e50bc7-ace6-4fec-bc57-8e6d5e6f88af",
    "3c7c8d0c-5316-49f0-b908-2a70a292c6b4",
    "7cf54938-818d-47b1-9c6a-e6f4aa4beeaa",
    "7ae3e039-12ed-4f81-9653-43f1d3f9ebc9",
]

ATTENDANCE_TARGETS = [
    {
        "id": attendance_id,
        "expected": {
            "plano_aee_id": NICOLLAS_PLAN_ID,
            "horario_inicio": "13:30",
            "horario_fim": "03:00",
            "duracao_minutos": 810,
        },
        "update": {
            "horario_inicio": "13:30",
            "horario_fim": "15:00",
            "duracao_minutos": 90,
        },
        "reason": "Fim corrigido para 15:00 e duração recalculada para 90 minutos.",
    }
    for attendance_id in ATTENDANCE_IDS
]


def _matches_expected(doc: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(doc.get(key) == value for key, value in expected.items())


def _projection() -> dict[str, int]:
    return {"_id": 0}


def _exact_filter(target: dict[str, Any]) -> dict[str, Any]:
    return {"id": target["id"], **deepcopy(target["expected"])}


def _validate_targets() -> None:
    for target in PLAN_TARGETS:
        validate_time_interval(
            target["update"]["horario_inicio"],
            target["update"]["horario_fim"],
            require_pair=True,
        )
    for target in ATTENDANCE_TARGETS:
        duration = validate_time_interval(
            target["update"]["horario_inicio"],
            target["update"]["horario_fim"],
            require_pair=True,
        )
        if duration != target["update"]["duracao_minutos"]:
            raise RuntimeError(
                f"Target {target['id']} possui duração de update incompatível: "
                f"{target['update']['duracao_minutos']} != {duration}."
            )


async def _precheck(db) -> dict[str, Any]:
    _validate_targets()
    errors: list[dict[str, Any]] = []
    plan_docs: list[dict[str, Any]] = []
    attendance_docs: list[dict[str, Any]] = []

    for target in PLAN_TARGETS:
        doc = await db.planos_aee.find_one({"id": target["id"]}, _projection())
        if not doc:
            errors.append({"code": "PLAN_MISSING", "id": target["id"]})
            continue
        plan_docs.append(deepcopy(doc))
        if not _matches_expected(doc, target["expected"]):
            errors.append(
                {
                    "code": "PLAN_STATE_CHANGED",
                    "id": target["id"],
                    "expected": target["expected"],
                    "actual": {k: doc.get(k) for k in target["expected"]},
                }
            )

    for target in ATTENDANCE_TARGETS:
        doc = await db.atendimentos_aee.find_one({"id": target["id"]}, _projection())
        if not doc:
            errors.append({"code": "ATTENDANCE_MISSING", "id": target["id"]})
            continue
        attendance_docs.append(deepcopy(doc))
        if not _matches_expected(doc, target["expected"]):
            errors.append(
                {
                    "code": "ATTENDANCE_STATE_CHANGED",
                    "id": target["id"],
                    "expected": target["expected"],
                    "actual": {k: doc.get(k) for k in target["expected"]},
                }
            )

    plan_ids = [target["id"] for target in PLAN_TARGETS]
    heads = await db.aee_dossier_v2_heads.find(
        {"legacy_plano_id": {"$in": plan_ids}},
        {
            "_id": 0,
            "id": 1,
            "legacy_plano_id": 1,
            "active_snapshot_id": 1,
            "working_snapshot_id": 1,
        },
    ).to_list(None)
    if heads:
        errors.append(
            {
                "code": "AEE_V2_HEAD_PRESENT",
                "message": "Correção legado bloqueada porque um Plano alvo possui head AEE V2.",
                "heads": heads,
            }
        )

    return {
        "ok": not errors,
        "errors": errors,
        "plan_docs": plan_docs,
        "attendance_docs": attendance_docs,
        "heads": heads,
    }


async def _write_backup(db, precheck: dict[str, Any]) -> None:
    existing = await db[BACKUP_COLLECTION].find_one(
        {"operation_id": OPERATION_ID},
        {"_id": 0, "operation_id": 1},
    )
    if existing:
        raise RuntimeError(
            f"Backup lógico {OPERATION_ID} já existe; apply repetido foi bloqueado."
        )

    backup = {
        "operation_id": OPERATION_ID,
        "kind": "aee_time_integrity_historical_repair",
        "academic_year": 2026,
        "created_at": datetime.now(timezone.utc),
        "targets_count": 14,
        "plans_before": deepcopy(precheck["plan_docs"]),
        "attendances_before": deepcopy(precheck["attendance_docs"]),
        "planned_plan_updates": deepcopy(PLAN_TARGETS),
        "planned_attendance_updates": deepcopy(ATTENDANCE_TARGETS),
    }
    result = await db[BACKUP_COLLECTION].insert_one(backup)
    if not result.acknowledged:
        raise RuntimeError("Mongo não confirmou a gravação do backup lógico.")


async def _rollback(db, changed: list[tuple[str, dict[str, Any]]]) -> list[str]:
    failures: list[str] = []
    for collection_name, original in reversed(changed):
        document_id = original.get("id")
        if not document_id:
            failures.append(f"{collection_name}: documento original sem id")
            continue
        replacement = deepcopy(original)
        replacement.pop("_id", None)
        result = await db[collection_name].replace_one({"id": document_id}, replacement)
        if result.matched_count != 1:
            failures.append(f"{collection_name}:{document_id}")
    return failures


async def _apply(db, precheck: dict[str, Any]) -> dict[str, Any]:
    if not precheck["ok"]:
        raise RuntimeError("Precheck falhou; apply bloqueado.")

    await _write_backup(db, precheck)
    originals = {
        "planos_aee": {doc["id"]: doc for doc in precheck["plan_docs"]},
        "atendimentos_aee": {doc["id"]: doc for doc in precheck["attendance_docs"]},
    }
    changed: list[tuple[str, dict[str, Any]]] = []

    try:
        for target in PLAN_TARGETS:
            result = await db.planos_aee.update_one(
                _exact_filter(target),
                {"$set": deepcopy(target["update"])},
            )
            if result.matched_count != 1 or result.modified_count != 1:
                raise RuntimeError(
                    f"Plano {target['id']} não foi atualizado exatamente uma vez "
                    f"(matched={result.matched_count}, modified={result.modified_count})."
                )
            changed.append(("planos_aee", originals["planos_aee"][target["id"]]))

        for target in ATTENDANCE_TARGETS:
            result = await db.atendimentos_aee.update_one(
                _exact_filter(target),
                {"$set": deepcopy(target["update"])},
            )
            if result.matched_count != 1 or result.modified_count != 1:
                raise RuntimeError(
                    f"Atendimento {target['id']} não foi atualizado exatamente uma vez "
                    f"(matched={result.matched_count}, modified={result.modified_count})."
                )
            changed.append(
                ("atendimentos_aee", originals["atendimentos_aee"][target["id"]])
            )
    except Exception:
        rollback_failures = await _rollback(db, changed)
        if rollback_failures:
            raise RuntimeError(
                "Falha durante o apply e rollback incompleto: " + ", ".join(rollback_failures)
            )
        raise

    return {"changed": len(changed), "rollback_failures": []}


async def _postcheck(db) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    for target in PLAN_TARGETS:
        doc = await db.planos_aee.find_one({"id": target["id"]}, _projection()) or {}
        actual = {key: doc.get(key) for key in target["update"]}
        if actual != target["update"]:
            errors.append(
                {"code": "PLAN_POSTCHECK_FAILED", "id": target["id"], "actual": actual}
            )
        result = classify_time_interval(doc.get("horario_inicio"), doc.get("horario_fim"))
        if result["issues"]:
            errors.append(
                {
                    "code": "PLAN_STILL_INVALID",
                    "id": target["id"],
                    "issues": result["issues"],
                }
            )

    for target in ATTENDANCE_TARGETS:
        doc = await db.atendimentos_aee.find_one({"id": target["id"]}, _projection()) or {}
        actual = {key: doc.get(key) for key in target["update"]}
        if actual != target["update"]:
            errors.append(
                {
                    "code": "ATTENDANCE_POSTCHECK_FAILED",
                    "id": target["id"],
                    "actual": actual,
                }
            )
        result = classify_time_interval(
            doc.get("horario_inicio"),
            doc.get("horario_fim"),
            stored_duration=doc.get("duracao_minutos"),
        )
        if result["issues"]:
            errors.append(
                {
                    "code": "ATTENDANCE_STILL_INVALID",
                    "id": target["id"],
                    "issues": result["issues"],
                }
            )

    return {"ok": not errors, "errors": errors}


def _print_precheck(precheck: dict[str, Any]) -> None:
    print("=" * 78)
    print(" P0 AEE — CORREÇÃO TEMPORAL HISTÓRICA 2026 — PRECHECK")
    print("=" * 78)
    print(f"Planos esperados        : {len(PLAN_TARGETS)}")
    print(f"Planos encontrados      : {len(precheck['plan_docs'])}")
    print(f"Atendimentos esperados  : {len(ATTENDANCE_TARGETS)}")
    print(f"Atendimentos encontrados: {len(precheck['attendance_docs'])}")
    print(f"Heads V2 encontrados    : {len(precheck['heads'])}")
    print(f"Erros                   : {len(precheck['errors'])}")

    print("\nPLANOS — CORREÇÕES PLANEJADAS")
    for target in PLAN_TARGETS:
        print(
            f"  {target['id']} | "
            f"{target['expected']['horario_inicio']} -> {target['expected']['horario_fim']} "
            f"=> {target['update']['horario_inicio']} -> {target['update']['horario_fim']}"
        )

    print("\nATENDIMENTOS — CORREÇÕES PLANEJADAS")
    for target in ATTENDANCE_TARGETS:
        print(
            f"  {target['id']} | 13:30 -> 03:00 / 810 min "
            f"=> 13:30 -> 15:00 / 90 min"
        )

    if precheck["errors"]:
        print("\nERROS/BLOCKERS")
        for error in precheck["errors"]:
            print("  -", json.dumps(error, ensure_ascii=False, default=str, sort_keys=True))

    print()
    if precheck["ok"]:
        print("✅ PRECHECK PASS — os 14 documentos permanecem exatamente no estado auditado.")
    else:
        print("❌ PRECHECK FAIL — --apply está bloqueado.")


async def main(apply: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "sigesc_db")]
    try:
        precheck = await _precheck(db)
        _print_precheck(precheck)

        if not apply:
            print("\nDRY-RUN — NENHUM INSERT / UPDATE / DELETE EXECUTADO")
            return 0 if precheck["ok"] else 2

        if not precheck["ok"]:
            print("\nAPPLY NÃO EXECUTADO.")
            return 2

        print("\nAPPLY AUTORIZADO — gravando backup lógico antes das correções...")
        result = await _apply(db, precheck)
        print(f"Documentos corrigidos: {result['changed']}/14")
        print(f"Backup lógico         : {BACKUP_COLLECTION}/{OPERATION_ID}")

        postcheck = await _postcheck(db)
        print(f"Pós-check erros       : {len(postcheck['errors'])}")
        if postcheck["errors"]:
            for error in postcheck["errors"]:
                print("  -", json.dumps(error, ensure_ascii=False, default=str, sort_keys=True))
            print("❌ APPLY CONCLUÍDO, MAS PÓS-CHECK FALHOU — não considerar homologado.")
            return 3

        print("✅ APPLY PASS — 14/14 documentos corrigidos e validados.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa as 14 correções depois de precheck estrito e backup lógico.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))
