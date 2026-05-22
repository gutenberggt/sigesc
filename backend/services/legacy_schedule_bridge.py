"""
Legacy Schedule Bridge — camada de compatibilidade (Fev/2026).

Quando uma turma NÃO possui assignments no modelo novo
(`teacher_class_assignments`), este serviço lê do modelo legacy
(`class_schedules` + `teacher_assignments`) e devolve assignments
sintéticos no MESMO shape esperado pelo Diário (com `weekly_slots`,
`valid_from`, `valid_until`).

PRINCÍPIOS (aprovados pelo owner — Fev/2026):
  1. Apenas leitura. Nenhuma escrita.
  2. Fallback transparente — modelo novo TEM PRIORIDADE absoluta.
  3. Sem merge, sem sincronização, sem repair.
  4. Toda saída marca `source="legacy_bridge"` e `synthetic_validity=True`.
  5. Auditoria preservada — snapshots congelam a saída do bridge tal qual.

ALCANCE: usado em
  - `routers/calendar_diary_state.py` (UI operacional)
  - `services/diary_snapshot_service.py` (snapshot imutável)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mapa: nome do dia em PT-BR (lower, sem acento) → ISO weekday (1=Seg..7=Dom)
WEEKDAY_MAP = {
    "segunda": 1, "segunda-feira": 1, "seg": 1,
    "terca": 2, "terça": 2, "terca-feira": 2, "terça-feira": 2, "ter": 2,
    "quarta": 3, "quarta-feira": 3, "qua": 3,
    "quinta": 4, "quinta-feira": 4, "qui": 4,
    "sexta": 5, "sexta-feira": 5, "sex": 5,
    "sabado": 6, "sábado": 6, "sab": 6,
    "domingo": 7, "dom": 7,
}


def _normalize_day(raw: str) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return WEEKDAY_MAP.get(s)


async def build_assignments_from_legacy(
    db, *, class_doc: dict,
) -> list[dict]:
    """Constrói lista de assignments sintéticos a partir do modelo legacy.

    Args:
      db: motor database handle.
      class_doc: documento da turma (com `id`, `academic_year` no mínimo).

    Returns:
      Lista de assignments no shape esperado pelo Diário. Vazia se a turma
      também não possui dados no modelo legacy.
    """
    class_id = class_doc.get("id")
    academic_year = class_doc.get("academic_year")
    if not class_id or not academic_year:
        return []

    # Fonte 1 — Slots da semana × disciplina
    schedule = await db.class_schedules.find_one(
        {"class_id": class_id}, {"_id": 0},
    )
    if not schedule or not (schedule.get("schedule_slots") or []):
        return []

    # Fonte 2 — Professor por disciplina (ativo)
    ta_cursor = db.teacher_assignments.find(
        {
            "class_id": class_id,
            "status": "ativo",
            "academic_year": academic_year,
        },
        {"_id": 0, "id": 1, "staff_id": 1, "course_id": 1, "created_at": 1},
    )
    teacher_assigns = await ta_cursor.to_list(500)

    # Agrupa professores por course_id (suporta múltiplos professores na
    # mesma disciplina — escolhe deterministicamente o de menor created_at).
    by_course: dict[str, list[dict]] = {}
    for ta in teacher_assigns:
        cid = ta.get("course_id")
        if not cid:
            continue
        by_course.setdefault(cid, []).append(ta)
    for cid, lst in by_course.items():
        lst.sort(key=lambda t: (t.get("created_at") or "", t.get("id") or ""))
        if len(lst) > 1:
            logger.warning(
                "[legacy_bridge] multiple teacher_assignments for course "
                "class_id=%s course_id=%s count=%d — picking earliest",
                class_id, cid, len(lst),
            )

    # Resolve nomes de professores em batch.
    # `teacher_assignments.staff_id` aponta para a collection `staff` na maioria
    # das instalações; algumas escolas têm o mesmo id também em `users`.
    # Estratégia: tenta `staff` primeiro (fonte canônica de servidores),
    # depois fallback em `users` para o que sobrar.
    staff_ids = {lst[0]["staff_id"] for lst in by_course.values() if lst}
    staff_names: dict[str, str] = {}
    if staff_ids:
        staff_cur = db.staff.find(
            {"id": {"$in": list(staff_ids)}},
            {"_id": 0, "id": 1, "full_name": 1, "name": 1, "nome": 1},
        )
        async for s in staff_cur:
            nm = s.get("full_name") or s.get("name") or s.get("nome")
            if nm:
                staff_names[s["id"]] = nm
        missing = staff_ids - set(staff_names.keys())
        if missing:
            users_cur = db.users.find(
                {"id": {"$in": list(missing)}},
                {"_id": 0, "id": 1, "full_name": 1},
            )
            async for u in users_cur:
                if u.get("full_name"):
                    staff_names[u["id"]] = u["full_name"]

    slot_times = schedule.get("slot_times") or {}

    def _slot_time(aula_num: int) -> tuple[Optional[str], Optional[str]]:
        st = slot_times.get(str(aula_num)) or slot_times.get(aula_num) or {}
        return st.get("start"), st.get("end")

    # Vigência sintética: ano letivo completo (aprovado pelo owner).
    valid_from = f"{academic_year}-02-01"
    valid_until = f"{academic_year}-12-31"

    # Agrupa slots por (course_id, teacher_id) → lista de (weekday, aula_numero)
    # Isso casa com o shape do modelo novo: 1 assignment com weekly_slots[].
    grouped: dict[tuple, list[dict]] = {}
    course_names: dict[str, str] = {}
    for slot in schedule["schedule_slots"]:
        course_id = slot.get("course_id")
        aula_numero = slot.get("slot_number") or slot.get("aula_numero")
        weekday = _normalize_day(slot.get("day") or slot.get("weekday"))
        if not course_id or not aula_numero or not weekday:
            continue
        # Preserva course_name do slot para resolver component_name depois
        if slot.get("course_name") and course_id not in course_names:
            course_names[course_id] = slot["course_name"]
        teachers = by_course.get(course_id) or []
        teacher_id = teachers[0]["staff_id"] if teachers else None
        if not teacher_id:
            logger.warning(
                "[legacy_bridge] schedule slot without teacher "
                "class_id=%s course_id=%s aula=%d weekday=%d",
                class_id, course_id, aula_numero, weekday,
            )
        start_t, end_t = _slot_time(aula_numero)
        key = (course_id, teacher_id)
        grouped.setdefault(key, []).append({
            "weekday": weekday,
            "aula_numero": aula_numero,
            "start_time": start_t,
            "end_time": end_t,
        })

    # Fallback de course_name: se algum course não veio nomeado nos slots,
    # busca em `courses` collection.
    missing_course_ids = set(grouped.keys()) and {
        cid for (cid, _) in grouped.keys() if cid not in course_names
    }
    if missing_course_ids:
        courses_cur = db.courses.find(
            {"id": {"$in": list(missing_course_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        )
        async for c in courses_cur:
            if c.get("name"):
                course_names[c["id"]] = c["name"]

    # Monta os assignments sintéticos
    bridged: list[dict] = []
    for (course_id, teacher_id), slots in grouped.items():
        # Ordena slots por (weekday, aula_numero) para previsibilidade
        slots.sort(key=lambda s: (s["weekday"], s["aula_numero"]))
        bridged.append({
            "id": f"legacy::{class_id}::{course_id}::{teacher_id or 'none'}",
            "class_id": class_id,
            "school_id": class_doc.get("school_id"),
            "mantenedora_id": class_doc.get("mantenedora_id"),
            "component_id": course_id,    # legacy course_id → component_id
            "component_name": course_names.get(course_id),
            "course_id": course_id,        # preserva também o nome legacy
            "course_name": course_names.get(course_id),
            "teacher_id": teacher_id,
            "teacher_name": staff_names.get(teacher_id or "") or None,
            "weekly_slots": slots,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "deleted": False,
            "is_substitute": False,
            # Marcadores institucionais (auditoria + observabilidade)
            "source": "legacy_bridge",
            "synthetic_validity": True,
        })

    # Observabilidade — quantas turmas dependem do bridge (medir migração futura)
    if bridged:
        logger.info(
            "[legacy_bridge] legacy_bridge_used=True class_id=%s "
            "school_id=%s academic_year=%s assignments_built=%d slots_total=%d",
            class_id, class_doc.get("school_id"), academic_year,
            len(bridged), sum(len(b["weekly_slots"]) for b in bridged),
        )

    return bridged
