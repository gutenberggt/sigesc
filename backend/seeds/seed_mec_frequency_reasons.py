"""Seed dos Motivos Oficiais de Baixa Frequência MEC / Sistema Presença.

Popula as coleções:
  - attendance_frequency_reason_groups
  - attendance_frequency_reasons

Idempotente: usa `mec_code` e `mec_subcode` como chaves naturais (upsert).
Lê o seed institucional versionado em
`/app/backend/seeds/mec/attendance_frequency_reasons.v4.2.json`.

Roda no startup do servidor via `backend.startup.seeds.run_all_seeds`.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).parent / "mec" / "attendance_frequency_reasons.v4.2.json"


def _load_seed():
    with SEED_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


async def seed_attendance_frequency_reasons(db):
    """Faz upsert dos grupos e submotivos MEC. Retorna estatísticas."""
    payload = _load_seed()
    version = payload["version"]
    source = payload["source"]
    now = datetime.now(timezone.utc).isoformat()

    groups_collection = db.attendance_frequency_reason_groups
    reasons_collection = db.attendance_frequency_reasons

    stats = {"groups_upserted": 0, "reasons_upserted": 0, "version": version}

    # 1. Grupos
    code_to_group_id = {}
    for g in payload["groups"]:
        mec_code = g["mec_code"]
        existing = await groups_collection.find_one({"mec_code": mec_code, "mec_version": version}, {"_id": 0, "id": 1})
        group_id = (existing or {}).get("id") or str(uuid.uuid4())
        code_to_group_id[mec_code] = group_id

        await groups_collection.update_one(
            {"mec_code": mec_code, "mec_version": version},
            {
                "$set": {
                    "id": group_id,
                    "mec_code": mec_code,
                    "name": g["name"],
                    "category": g["category"],
                    "mec_version": version,
                    "source": source,
                    "active": g.get("active", True),
                    "sort_order": g.get("sort_order", int(mec_code)),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        stats["groups_upserted"] += 1

    # 2. Submotivos
    for r in payload["reasons"]:
        mec_group_code = r["mec_group_code"]
        mec_subcode = r["mec_subcode"]
        group_id = code_to_group_id.get(mec_group_code)
        if not group_id:
            logger.warning(
                "Submotivo MEC %s referencia grupo %s inexistente",
                mec_subcode,
                mec_group_code,
            )
            continue

        existing = await reasons_collection.find_one(
            {"mec_subcode": mec_subcode, "mec_version": version}, {"_id": 0, "id": 1}
        )
        reason_id = (existing or {}).get("id") or str(uuid.uuid4())

        await reasons_collection.update_one(
            {"mec_subcode": mec_subcode, "mec_version": version},
            {
                "$set": {
                    "id": reason_id,
                    "group_id": group_id,
                    "mec_group_code": mec_group_code,
                    "mec_subcode": mec_subcode,
                    "name": r["name"],
                    "severity_level": r.get("severity_level", 1),
                    "requires_followup": r.get("requires_followup", False),
                    "legacy": r.get("legacy", False),
                    "mec_version": version,
                    "source": source,
                    "active": r.get("active", True),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        stats["reasons_upserted"] += 1

    logger.info(
        "Seed MEC frequency reasons v%s: %d grupos / %d submotivos",
        version,
        stats["groups_upserted"],
        stats["reasons_upserted"],
    )
    return stats
