"""R2.0g.3 — ponte fail-closed de identidade para Cópia Manual de Conteúdo.

Corrige a resolução histórica sem alterar dados:

- ``teacher_assignments.staff_id`` referencia ``staff.id``;
- ``staff.user_id`` referencia ``users.id``;
- atores já canônicos em ``users.id`` continuam aceitos;
- e-mail é somente fallback inequívoco;
- vínculo legado ambíguo continua bloqueando;
- vínculo legado apenas não resolvido pode ceder à evidência inequívoca da
  frequência da própria data de destino.

O ``super_admin`` operador nunca é usado como autoria pedagógica.
"""
from __future__ import annotations

import re
from typing import Optional


_USER_PROJECTION = {
    "_id": 0,
    "id": 1,
    "full_name": 1,
    "name": 1,
    "email": 1,
    "staff_id": 1,
}


async def _canonical_user_for_actor(db, actor_id: str) -> Optional[dict]:
    """Resolve user canônico a partir de user.id ou da identidade staff legada."""
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return None

    # DVD/canônico: teacher_id já referencia users.id.
    direct = await db.users.find_one({"id": actor_id}, _USER_PROJECTION)
    if direct and direct.get("id"):
        return direct

    # Legado oficial: teacher_assignments.staff_id -> staff.id -> staff.user_id.
    staff = await db.staff.find_one(
        {"id": actor_id},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1},
    )
    if staff:
        user_id = str(staff.get("user_id") or "").strip()
        if user_id:
            linked = await db.users.find_one({"id": user_id}, _USER_PROJECTION)
            if linked and linked.get("id"):
                return linked

        # Compatibilidade histórica: e-mail somente se houver exatamente um user.
        email = str(staff.get("email") or "").strip()
        if email:
            escaped = re.escape(email)
            matches = await db.users.find(
                {"email": {"$regex": f"^{escaped}$", "$options": "i"}},
                _USER_PROJECTION,
            ).to_list(2)
            if len(matches) == 1 and matches[0].get("id"):
                return matches[0]
            if len(matches) > 1:
                return None

    # Compatibilidade de schemas transitórios que materializaram users.staff_id.
    compat = await db.users.find_one({"staff_id": actor_id}, _USER_PROJECTION)
    if compat and compat.get("id"):
        return compat
    return None


async def _legacy_binding(
    db,
    *,
    class_doc: dict,
    component_id: str,
) -> Optional[dict]:
    """Resolve vínculo legado usando staff_id como identidade histórica primária."""
    academic_year = class_doc.get("academic_year")
    query = {
        "class_id": class_doc.get("id"),
        "course_id": component_id,
        "status": "ativo",
    }
    if academic_year is not None:
        query["academic_year"] = {"$in": [academic_year, str(academic_year)]}

    rows = await db.teacher_assignments.find(
        query,
        {"_id": 0, "staff_id": 1, "teacher_id": 1},
    ).to_list(100)

    actor_ids = sorted(
        {
            str(row.get("staff_id") or row.get("teacher_id"))
            for row in rows
            if row.get("staff_id") or row.get("teacher_id")
        }
    )
    if len(actor_ids) > 1:
        return {"status": "AMBIGUOUS", "reason": "MULTIPLE_LEGACY_TEACHERS"}
    if not actor_ids:
        return None

    user = await _canonical_user_for_actor(db, actor_ids[0])
    if not user or not user.get("id"):
        return {
            "status": "UNRESOLVED",
            "reason": "LEGACY_TEACHER_USER_ID_UNRESOLVED",
        }
    return {
        "status": "RESOLVED",
        "mode": "LEGACY_CANONICAL",
        "assignment_id": None,
        "teacher_id": user.get("id"),
        "teacher_name": user.get("full_name") or user.get("name"),
        "historical_backfill": False,
    }


async def _resolve_target_binding(
    db,
    *,
    class_doc: dict,
    component_id: str,
    target_date: str,
) -> dict:
    """Resolve autoria do destino sem transformar ausência de ponte em autoria falsa."""
    # DVD tem precedência e qualquer ambiguidade nele permanece bloqueante.
    dvd = await _BOUND_MODULE._dvd_binding(
        db,
        class_id=class_doc["id"],
        component_id=component_id,
        target_date=target_date,
    )
    if dvd:
        return dvd

    legacy = await _legacy_binding(
        db,
        class_doc=class_doc,
        component_id=component_id,
    )
    if legacy and legacy.get("status") in {"RESOLVED", "AMBIGUOUS"}:
        return legacy

    # Se o legado existe mas apenas perdeu a ponte staff->user, a frequência da
    # própria data pode fornecer snapshot inequívoco. Ambiguidade nunca cai aqui.
    attendance = await _BOUND_MODULE._attendance_teacher_binding(
        db,
        class_id=class_doc["id"],
        component_id=component_id,
        target_date=target_date,
    )
    if attendance:
        return attendance

    if legacy:
        return legacy
    return {
        "status": "UNRESOLVED",
        "reason": "TARGET_TEACHER_NOT_RESOLVED",
    }


_BOUND_MODULE = None


def install_manual_content_copy_identity_bridge(manual_copy_module):
    """Instala a correção antes de o setup do router registrar os endpoints."""
    global _BOUND_MODULE
    _BOUND_MODULE = manual_copy_module
    manual_copy_module._canonical_user_for_actor = _canonical_user_for_actor
    manual_copy_module._legacy_binding = _legacy_binding
    manual_copy_module._resolve_target_binding = _resolve_target_binding
    return manual_copy_module
