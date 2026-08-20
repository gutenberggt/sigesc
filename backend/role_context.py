"""Canonical helpers for multi-role session context.

`users.role` is the principal cadastral role. The active session role lives in
JWT claims and may differ temporarily from the principal role when the user
switches role in the UI.
"""

from datetime import datetime
from typing import Any, Dict, List


SCHOOL_SCOPED_ROLES = {
    "professor",
    "secretario",
    "coordenador",
    "auxiliar_secretaria",
    "diretor",
}


def get_authorized_roles(user_doc: Dict[str, Any]) -> List[str]:
    """Return principal + additional roles, preserving order and uniqueness."""
    roles: List[str] = []
    principal = user_doc.get("role")
    if principal:
        roles.append(principal)
    for role in user_doc.get("roles") or []:
        if role and role not in roles:
            roles.append(role)
    return roles


def _normalize_user_school_links(user_doc: Dict[str, Any], active_role: str) -> List[Dict[str, Any]]:
    """Normalize legacy/current user.school_links into SchoolLink-compatible dicts."""
    normalized: List[Dict[str, Any]] = []
    seen = set()

    for raw in user_doc.get("school_links") or []:
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            continue

        school_id = raw.get("school_id")
        if not school_id or school_id in seen:
            continue

        raw_roles = raw.get("roles") or []
        # Legacy records may have singular `role` instead of `roles`.
        if not raw_roles and raw.get("role"):
            raw_roles = [raw.get("role")]

        # If the link explicitly declares roles, keep only links valid for the
        # active role. Legacy links without role metadata remain compatible.
        if raw_roles and active_role not in raw_roles:
            continue

        normalized.append({
            "school_id": school_id,
            "roles": [active_role] if active_role else list(raw_roles),
            "class_ids": raw.get("class_ids") or [],
        })
        seen.add(school_id)

    return normalized


async def resolve_role_context(
    db,
    user_doc: Dict[str, Any],
    active_role: str,
    *,
    academic_year: int | None = None,
) -> Dict[str, Any]:
    """Resolve school scope for one active role.

    Active school assignments are the authoritative source when a canonical
    staff record and assignments exist for the current academic year. If there
    are no assignments at all, user.school_links remains the legacy fallback.

    Returns:
      school_links: SchoolLink-compatible dictionaries
      school_ids: deduplicated ids
      source: "lotacoes" or "user_school_links"
      has_active_assignments: whether the staff member has any active lotação
      has_role_assignment: whether at least one active lotação matches role
    """
    if academic_year is None:
        academic_year = datetime.now().year

    fallback_links = _normalize_user_school_links(user_doc, active_role)

    if active_role not in SCHOOL_SCOPED_ROLES:
        return {
            "school_links": fallback_links,
            "school_ids": [link["school_id"] for link in fallback_links],
            "source": "user_school_links",
            "has_active_assignments": False,
            "has_role_assignment": bool(fallback_links),
        }

    user_id = user_doc.get("id")
    email = user_doc.get("email")

    staff = None
    if user_id:
        staff = await db.staff.find_one(
            {"user_id": user_id},
            {"_id": 0, "id": 1},
        )

    if not staff and email:
        legacy_staff = await db.staff.find_one(
            {"email": email},
            {"_id": 0, "id": 1, "user_id": 1},
        )
        if legacy_staff and not legacy_staff.get("user_id"):
            staff = legacy_staff

    if not staff:
        return {
            "school_links": fallback_links,
            "school_ids": [link["school_id"] for link in fallback_links],
            "source": "user_school_links",
            "has_active_assignments": False,
            "has_role_assignment": bool(fallback_links),
        }

    lotacoes = await db.school_assignments.find(
        {
            "staff_id": staff["id"],
            "status": "ativo",
            "academic_year": academic_year,
        },
        {"_id": 0, "school_id": 1, "funcao": 1},
    ).to_list(200)

    if not lotacoes:
        return {
            "school_links": fallback_links,
            "school_ids": [link["school_id"] for link in fallback_links],
            "source": "user_school_links",
            "has_active_assignments": False,
            "has_role_assignment": bool(fallback_links),
        }

    links: List[Dict[str, Any]] = []
    seen = set()
    for lotacao in lotacoes:
        funcao = str(lotacao.get("funcao") or "").strip().lower()
        school_id = lotacao.get("school_id")
        if funcao != active_role or not school_id or school_id in seen:
            continue
        links.append({
            "school_id": school_id,
            "roles": [active_role],
            "class_ids": [],
        })
        seen.add(school_id)

    return {
        "school_links": links,
        "school_ids": [link["school_id"] for link in links],
        "source": "lotacoes",
        "has_active_assignments": True,
        "has_role_assignment": bool(links),
    }
