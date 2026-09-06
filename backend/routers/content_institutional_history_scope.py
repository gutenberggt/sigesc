"""Leitura institucional de histórico de Conteúdos por escopo do Diário.

Issue #480: depois que o vínculo ATUAL já foi autorizado por
``list_assignment_content_history``, a autoria histórica deixa de ser chave de
visibilidade. Registros canônicos de outro assignment, na mesma turma e no mesmo
componente, entram na linha do tempo apenas para consulta.

Esta camada NÃO altera ownership, não autoriza escrita e não modifica documentos.
Ela envolve somente a função de leitura usada por ``content_dvd_history``.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _tenant_compatible(item: Mapping[str, Any], tenant_id: Optional[str]) -> bool:
    """Campo ausente é tolerado apenas porque class_id já é âncora exata.

    Tenant explicitamente divergente nunca atravessa a ponte.
    """
    item_tenant = _sid(item.get("mantenedora_id"))
    expected = _sid(tenant_id)
    if item_tenant and expected and item_tenant != expected:
        return False
    return True


def _public_scoped_item(
    item: Mapping[str, Any],
    *,
    current_assignment_id: str,
    valid_from: Optional[str],
) -> dict:
    out = dict(item)
    out.pop("_id", None)
    out["course_id"] = out.get("course_id") or out.get("component_id")
    out["component_id"] = out.get("component_id") or out.get("course_id")
    out.setdefault("source", "content_entries")
    out.setdefault("legacy", False)
    is_current = _sid(out.get("assignment_id")) == _sid(current_assignment_id)
    if not is_current:
        out["read_only"] = True
        out["historical_scope_read"] = True
    else:
        out.setdefault("read_only", False)
    out["historical_backfill"] = bool(
        valid_from
        and out.get("date")
        and str(out.get("date")) < str(valid_from)
    )
    return out


def merge_scope_history_items(
    base_items: list[dict],
    scoped_candidates: list[dict],
    *,
    current_assignment_id: str,
    tenant_id: Optional[str],
    valid_from: Optional[str],
) -> list[dict]:
    """Mescla histórico canônico de mesmo escopo sem usar autoria como filtro."""
    merged: list[dict] = [dict(item) for item in base_items]
    seen = {
        (str(item.get("source") or ""), str(item.get("id") or ""))
        for item in merged
    }

    for raw in scoped_candidates:
        if raw.get("deleted") is True:
            continue
        if not _tenant_compatible(raw, tenant_id):
            continue
        item = _public_scoped_item(
            raw,
            current_assignment_id=current_assignment_id,
            valid_from=valid_from,
        )
        key = (str(item.get("source") or ""), str(item.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    # Mesmo contrato predominante do bridge original: data desc e aula asc.
    merged.sort(
        key=lambda item: (
            item.get("aula_numero") is None,
            item.get("aula_numero") if item.get("aula_numero") is not None else 0,
        )
    )
    merged.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return merged


async def list_institutional_scope_history(
    original,
    db,
    current_user: Mapping[str, Any],
    *,
    assignment_id: str,
    class_id: Optional[str] = None,
    date: Optional[str] = None,
    teacher_id: Optional[str] = None,
    component_id: Optional[str] = None,
    include_deleted: bool = False,
    active_mantenedora_id: Optional[str] = None,
) -> dict:
    """Amplia SOMENTE a projeção de leitura após autorização do vínculo atual.

    O ``original`` continua responsável por RBAC, tenant, escola, turma,
    componente e vigência do vínculo atual. Depois dessa autorização, buscamos
    registros canônicos adicionais pela identidade institucional
    turma+componente(+data), ignorando autoria/assignment histórico.
    """
    # teacher_id é deliberadamente removido do filtro de leitura institucional.
    base = await original(
        db,
        current_user,
        assignment_id=assignment_id,
        class_id=class_id,
        date=date,
        teacher_id=None,
        component_id=component_id,
        include_deleted=include_deleted,
        active_mantenedora_id=active_mantenedora_id,
    )

    assignment = await db.teacher_class_assignments.find_one(
        {"id": assignment_id, "deleted": False},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "component_id": 1,
            "mantenedora_id": 1,
            "valid_from": 1,
        },
    )
    # O original já falharia se o vínculo não existisse; defesa adicional.
    if not assignment:
        return base

    resolved_class_id = class_id or assignment.get("class_id")
    resolved_component_id = component_id or assignment.get("component_id")
    if not resolved_class_id:
        return base

    class_info = await db.classes.find_one(
        {"id": resolved_class_id},
        {"_id": 0, "mantenedora_id": 1},
    ) or {}
    tenant_id = class_info.get("mantenedora_id") or assignment.get("mantenedora_id")

    query: dict[str, Any] = {"class_id": resolved_class_id}
    if not include_deleted:
        query["deleted"] = False
    if resolved_component_id:
        query["component_id"] = resolved_component_id
    if date:
        query["date"] = date

    scoped = await db.content_entries.find(query, {"_id": 0}).to_list(5000)
    items = merge_scope_history_items(
        list(base.get("items") or []),
        scoped,
        current_assignment_id=assignment_id,
        tenant_id=tenant_id,
        valid_from=assignment.get("valid_from"),
    )
    result = dict(base)
    result["items"] = items
    result["total"] = len(items)
    history_bridge = dict(result.get("history_bridge") or {})
    history_bridge["institutional_scope_read"] = True
    history_bridge["authorship_is_visibility_key"] = False
    result["history_bridge"] = history_bridge
    return result


def install_content_institutional_history_scope(content_dvd_history_mod, content_history_bridge_mod):
    """Instala a política apenas no router/PDF de leitura de conteúdo."""
    if getattr(content_dvd_history_mod, "_issue_480_institutional_history_installed", False):
        return

    original = content_history_bridge_mod.list_assignment_content_history

    async def scoped_history(db, current_user, **kwargs):
        return await list_institutional_scope_history(
            original,
            db,
            current_user,
            **kwargs,
        )

    # O módulo de router importou a função por valor; trocar este global afeta
    # somente as superfícies de leitura/PDF nele definidas. Cópia e escrita não
    # são redirecionadas.
    content_dvd_history_mod.list_assignment_content_history = scoped_history
    content_dvd_history_mod._issue_480_institutional_history_installed = True
