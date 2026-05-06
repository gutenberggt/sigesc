"""Bootstrap multi-tenant + self-healing idempotente.

Extraído de `server.py` (Fev/2026). Roda no startup. Idempotente — só atualiza
documentos sem `mantenedora_id` ou usuários sem `super_admin`.
"""
import datetime as _dt
import logging
import uuid as _uuid

logger = logging.getLogger(__name__)

_TENANT_COLLECTIONS = (
    "schools", "staff", "students", "classes", "courses",
    "enrollments", "grades", "learning_objects", "calendar_events",
    "calendario_letivo", "school_assignments", "teacher_assignments",
    "payroll_items", "announcements", "users", "pre_matriculas",
    "mantenedora_documentos",
)

_BOOTSTRAP_COLLECTIONS = (
    "schools", "staff", "students", "classes", "courses",
    "enrollments", "grades", "learning_objects", "calendar_events",
    "calendario_letivo", "school_assignments", "teacher_assignments",
    "payroll_items", "announcements", "users",
)


async def bootstrap_initial_mantenedora(db):
    """Cria mantenedora principal se ainda não houver nenhuma. Promove o
    primeiro admin a `super_admin`. Idempotente."""
    try:
        existing = await db.mantenedoras.count_documents({})
        if existing != 0:
            return

        mid = str(_uuid.uuid4())
        await db.mantenedoras.insert_one({
            "id": mid,
            "name": "Mantenedora Principal",
            "ativo": True,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
        })

        for coll in _BOOTSTRAP_COLLECTIONS:
            try:
                await db[coll].update_many(
                    {"mantenedora_id": {"$exists": False}},
                    {"$set": {"mantenedora_id": mid}},
                )
            except Exception:
                pass
        logger.info(f"Multi-tenant: mantenedora principal criada (id={mid}).")

        first_admin = await db.users.find_one(
            {"role": "admin"}, {"_id": 0, "id": 1, "email": 1}
        )
        if first_admin:
            await db.users.update_one(
                {"id": first_admin["id"]},
                {"$set": {"role": "super_admin"}},
            )
            logger.info(
                f"Multi-tenant: {first_admin.get('email')} promovido a super_admin."
            )
    except Exception as exc:
        logger.warning(f"Multi-tenant: bootstrap ignorado: {exc}")


async def self_heal_tenant_data(db):
    """Self-healing: garante que existe pelo menos 1 super_admin e backfilla
    `mantenedora_id` em documentos legados. Roda sempre — idempotente."""
    try:
        any_super = await db.users.find_one(
            {"$or": [{"role": "super_admin"}, {"roles": "super_admin"}]},
            {"_id": 0, "id": 1},
        )
        first_mant = await db.mantenedoras.find_one(
            {}, {"_id": 0, "id": 1, "nome": 1, "name": 1}
        )
        first_mant_id = first_mant.get("id") if first_mant else None

        if not any_super:
            legacy_admin = await db.users.find_one(
                {"role": "admin", "is_primary": True},
                {"_id": 0, "id": 1, "email": 1},
            ) or await db.users.find_one(
                {"role": "admin"},
                {"_id": 0, "id": 1, "email": 1},
            )
            if legacy_admin:
                await db.users.update_one(
                    {"id": legacy_admin["id"]},
                    {"$set": {"role": "super_admin", "is_primary": True}},
                )
                logger.info(
                    f"Self-heal: {legacy_admin.get('email')} promovido a super_admin (is_primary=True)."
                )

        if first_mant_id:
            total_healed = 0
            for coll in _TENANT_COLLECTIONS:
                try:
                    res = await db[coll].update_many(
                        {"$or": [
                            {"mantenedora_id": {"$exists": False}},
                            {"mantenedora_id": None},
                            {"mantenedora_id": ""},
                        ]},
                        {"$set": {"mantenedora_id": first_mant_id}},
                    )
                    if res.modified_count:
                        total_healed += res.modified_count
                        logger.info(
                            f"Self-heal: backfill mantenedora_id em {coll}: {res.modified_count} docs."
                        )
                except Exception:
                    pass
            if total_healed:
                logger.info(f"Self-heal: total de {total_healed} documentos migrados.")
    except Exception as exc:
        logger.warning(f"Self-heal multi-tenant ignorado: {exc}")
