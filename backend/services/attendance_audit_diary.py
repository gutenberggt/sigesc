"""
Serviço de auditoria pedagógica da frequência (Diário).

Fase 1 da Rodada 1 — Maio/2026.

Responsabilidade: produzir um payload rico de auditoria pedagógica a
cada save de attendance, alimentando a coleção `audit_logs` (canônica
do sistema) via `audit_service.log()`.

NÃO cria nova coleção. NÃO duplica trilha. Apenas enriquece o
`extra_data` com o contexto pedagógico que o log genérico não tem:

  - entity_scope: 'daily_frequency' (vs futuro 'content_entry')
  - class_id, class_name
  - date, course_id, aula_numero
  - student_ids_changed: lista dos alunos cujo status mudou
  - per_student_changes: [{student_id, previous_status, new_status}, ...]
  - change_kind: 'create' | 'update' | 'overwrite_after_conflict'
  - expected_version / final_version
  - change_note (quando overwrite mediante justificativa)

A intenção é manter `audit_logs` como única fonte da timeline e fornecer
filtros futuros do tipo "todas as edições do aluno X" ou "todas as
sobrescritas pós-conflito da turma Y".
"""
from typing import Optional


def diff_records(old_records: list, new_records: list) -> list:
    """Compara dois snapshots de `records[]` e retorna lista de mudanças
    a nível de aluno. Ignora mudanças em `dependency_id` (campo de
    contexto, não de status pedagógico)."""
    def _by_sid(rs):
        return {(r.get("student_id") or ""): r for r in (rs or []) if r.get("student_id")}

    old_by = _by_sid(old_records)
    new_by = _by_sid(new_records)
    out = []
    all_sids = set(old_by) | set(new_by)
    for sid in all_sids:
        prev = (old_by.get(sid) or {}).get("status")
        new = (new_by.get(sid) or {}).get("status")
        if prev == new:
            continue
        out.append({
            "student_id": sid,
            "previous_status": prev,
            "new_status": new,
        })
    return out


async def build_diary_audit_extra(
    *,
    db,
    attendance_doc: dict,
    class_info: Optional[dict],
    per_student_changes: list,
    change_kind: str,
    expected_version: Optional[int],
    final_version: int,
    change_note: Optional[str] = None,
) -> dict:
    """Monta o dict `extra_data` para um log de attendance.

    Documento principal já fica no `old_value`/`new_value` do log
    genérico (handled pelo audit_service). Aqui só agregamos contexto
    pedagógico de leitura rápida.
    """
    extra = {
        "entity_type": "attendance",
        "entity_scope": "daily_frequency",
        "class_id": attendance_doc.get("class_id"),
        "class_name": (class_info or {}).get("name"),
        "date": attendance_doc.get("date"),
        "course_id": attendance_doc.get("course_id"),
        "aula_numero": attendance_doc.get("aula_numero"),
        "attendance_id": attendance_doc.get("id"),
        "change_kind": change_kind,
        "expected_version": expected_version,
        "final_version": final_version,
        "student_ids_changed": [c["student_id"] for c in per_student_changes],
        "per_student_changes": per_student_changes,
        "total_student_changes": len(per_student_changes),
    }
    if change_note:
        extra["change_note"] = change_note[:500]  # cap defensivo
    return extra
