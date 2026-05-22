"""
Auditoria pedagógica de conteúdo (Rodada 2 — Fase 2).

Análogo a `attendance_audit_diary.py`. Alimenta `audit_logs` (coleção
canônica) com contexto pedagógico rico para CRUD de `content_entries`.

Regra absoluta: nunca destruir texto. Toda escrita preserva
`previous_content` no log. Soft delete mantém o doc + registra
`change_kind='content_deleted'` com o texto à época da exclusão.
"""
from typing import Optional


def _truncate(text: Optional[str], n: int = 2000) -> Optional[str]:
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= n else s[:n] + "...[truncado]"


def diff_summary(prev: Optional[str], new: Optional[str]) -> dict:
    """Resumo leve de diff. Não é diff por linha — apenas tamanho e mudança.
    Suficiente para auditoria operacional; investigação detalhada usa
    `previous_content` vs `new_content` direto.
    """
    p, n = prev or "", new or ""
    return {
        "previous_length": len(p),
        "new_length": len(n),
        "delta_chars": len(n) - len(p),
        "is_complete_rewrite": bool(p and n and p[:50] != n[:50]),
    }


def build_content_audit_extra(
    *,
    entry: dict,
    change_kind: str,
    expected_version: Optional[int],
    final_version: int,
    previous_content: Optional[str] = None,
    new_content: Optional[str] = None,
    change_note: Optional[str] = None,
    class_info: Optional[dict] = None,
) -> dict:
    """Monta `extra_data` para o audit_log de uma operação de conteúdo."""
    extra = {
        "entity_type": "content_entry",
        "entity_scope": "pedagogical_content",
        "class_id": entry.get("class_id"),
        "class_name": (class_info or {}).get("name"),
        "date": entry.get("date"),
        "course_id": entry.get("course_id"),
        "component_id": entry.get("component_id"),
        "teacher_id": entry.get("teacher_id"),
        "teacher_name": entry.get("teacher_name"),
        "aula_numero": entry.get("aula_numero"),
        "content_entry_id": entry.get("id"),
        "change_kind": change_kind,
        "expected_version": expected_version,
        "final_version": final_version,
        "status_at_change": entry.get("status"),
    }
    # Texto: ESSENCIAL preservar quando há sobrescrita ou delete
    if previous_content is not None or new_content is not None:
        extra["previous_content"] = _truncate(previous_content)
        extra["new_content"] = _truncate(new_content)
        extra["diff_summary"] = diff_summary(previous_content, new_content)
    if change_note:
        extra["change_note"] = change_note[:500]
    return extra
