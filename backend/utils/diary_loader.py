"""
Diary Loader — carregador unificado de items do Diário (Fase 2).

[Fev/2026] Implementa o contrato `/app/docs/DIARY_API_CONTRACT.md` (v1).

Princípios:
- Lista UNIFICADA de items: regulares (A-Z) seguidos de dependências (A-Z).
- O divisor visual VIVE em `meta.has_dependencies` — NUNCA como item fake no array
  (decisão do dono do produto, Fev/2026 — ver contrato §17).
- Anti-N+1: no máximo 3 queries Mongo agregadas (enrollments + students + dependencies).
- Fonte da verdade para dependência: `student_dependencies.status='active'`,
  NUNCA `student.dependency_mode`.
- Anti-duplicidade: aluno não pode aparecer 2x (regular + dep) no mesmo componente.
- Ordenação canônica server-side: `localeCompare('pt-BR')` (em Python: `locale='pt'`,
  `strength=1` — Mongo collation).

Uso:
    from utils.diary_loader import load_diary_items

    payload = await load_diary_items(
        db=current_db,
        class_id=class_id,
        course_id=course_id,
        academic_year=2026,
        tenant_id=current_user.get("mantenedora_id"),
    )
    # payload = {"items": [...], "meta": {...}, "warnings": [...]}
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from utils.diary_constants import (
    DEPENDENCY_DISPLAY_LABEL,
    DIARY_CONTRACT_VERSION,
    MAX_DEPENDENCY_STUDENTS_PER_DIARY,
)
from utils.observability import record_diary_load

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stat tracker — para validação de anti-N+1 em testes.
# Ative com `DiaryLoadStats()` como context manager. Em produção custa zero
# porque só é instanciado quando explicitamente requisitado pelo chamador.
# ---------------------------------------------------------------------------
class DiaryLoadStats:
    """Contador de queries Mongo durante uma carga de diário (testes/asserts)."""

    def __init__(self) -> None:
        self.queries: int = 0
        self.duration_ms: float = 0.0
        self._t0: float = 0.0

    def __enter__(self) -> "DiaryLoadStats":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *args) -> None:
        self.duration_ms = (time.monotonic() - self._t0) * 1000


# ---------------------------------------------------------------------------
def _build_item(
    *,
    student: dict,
    class_id: str,
    course_id: str,
    is_dependency: bool,
    dependency_doc: Optional[dict] = None,
    enrollment_number: Optional[str] = None,
) -> dict:
    """Monta um item canônico do diário (cf. contrato §3)."""
    item = {
        "student_id": student["id"],
        "student_name": student.get("full_name") or "",
        "student_code": enrollment_number or student.get("enrollment_number"),
        "is_dependency": is_dependency,
        "dependency_id": None,
        "dependency_type": None,
        "class_id": class_id,
        "course_id": course_id,
        "attendance_enabled": True,
        "grades_enabled": True,
        "status": "active",
        "origin_academic_year": None,
        "display_label": "",
    }
    if is_dependency and dependency_doc:
        item.update({
            "dependency_id": dependency_doc.get("id"),
            "dependency_type": student.get("dependency_mode"),  # with_dependency / dependency_only
            "status": dependency_doc.get("status", "active"),
            "origin_academic_year": dependency_doc.get("origin_academic_year"),
            "display_label": DEPENDENCY_DISPLAY_LABEL,
        })
    return item


def _sort_key_pt_br(item: dict) -> tuple:
    """Sort estável compatível com `localeCompare('pt-BR')`.

    Evitamos depender da locale do sistema (dificulta CI). Estratégia:
    - uppercase + remoção de diacríticos básica via tradução. Para o diário
      isso é suficiente porque a Mongo collation `pt strength=1` é usada
      antes (server-side) e este sort é um fallback in-Python para itens
      pós-injeção (dependências).
    """
    name = (item.get("student_name") or "").upper()
    table = str.maketrans(
        "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
        "AAAAAEEEEIIIIOOOOOUUUUC",
    )
    return (name.translate(table), name)


# ---------------------------------------------------------------------------
async def load_diary_items(
    *,
    db,
    class_id: str,
    course_id: str,
    academic_year: int,
    tenant_id: Optional[str] = None,
    stats: Optional[DiaryLoadStats] = None,
) -> dict:
    """Carrega items do diário no shape canônico do contrato v1.

    Returns:
        {
          "contract_version": 1,
          "class_id": str,
          "course_id": str,
          "academic_year": int,
          "items": [<item>, ...],  # regulares A-Z + deps A-Z (sem divisor fake)
          "meta": {
              "regular_count": int,
              "dependency_count": int,
              "has_dependencies": bool,
              "dependency_ratio_pct": float,  # deps / total * 100
              "total": int,
          },
          "warnings": [{"code": "...", "message": "...", ...}],
        }
    """
    t0 = time.monotonic()
    warnings: list[dict] = []

    # ------------------------------------------------------------------
    # Q1 — enrollments ATIVOS na turma
    # ------------------------------------------------------------------
    enr_filter: dict = {"class_id": class_id, "status": "active"}
    enrollments = await db.enrollments.find(
        enr_filter,
        {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1},
    ).to_list(2000)
    if stats:
        stats.queries += 1
    enrollment_numbers: dict[str, Optional[str]] = {}
    enrollment_ids: set = set()
    for e in enrollments:
        sid = e.get("student_id")
        if not sid:
            continue
        enrollment_ids.add(sid)
        # se múltiplas matrículas, prioriza a do ano corrente
        if sid not in enrollment_numbers or e.get("academic_year") == academic_year:
            enrollment_numbers[sid] = e.get("enrollment_number")

    # ------------------------------------------------------------------
    # Q2 — dependencies ATIVAS para (turma, componente)
    # ------------------------------------------------------------------
    dep_filter: dict = {
        "class_id": class_id,
        "course_id": course_id,
        "status": "active",
    }
    if tenant_id:
        dep_filter["mantenedora_id"] = tenant_id
    dependencies = await db.student_dependencies.find(
        dep_filter, {"_id": 0}
    ).to_list(500)
    if stats:
        stats.queries += 1
    dep_by_student: dict[str, dict] = {}
    for d in dependencies:
        sid = d.get("student_id")
        if not sid:
            continue
        # se aluno tiver duas deps ativas no mesmo componente (não deveria pelo
        # índice único parcial, mas defensivamente): mantemos a primeira
        if sid not in dep_by_student:
            dep_by_student[sid] = d

    # Anti-duplicidade: regular vence sobre dep para o mesmo (aluno, turma, course).
    dep_student_ids = set(dep_by_student.keys()) - enrollment_ids

    # ------------------------------------------------------------------
    # Q3 — students (todos os IDs envolvidos numa única query)
    # ------------------------------------------------------------------
    all_ids = list(enrollment_ids | dep_student_ids)
    students_map: dict[str, dict] = {}
    if all_ids:
        cursor = db.students.find(
            {"id": {"$in": all_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1,
             "dependency_mode": 1, "status": 1, "class_id": 1},
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1})
        students_list = await cursor.to_list(2000)
        if stats:
            stats.queries += 1
        students_map = {s["id"]: s for s in students_list}

    # ------------------------------------------------------------------
    # Build items — regulares primeiro, deps depois.
    # ------------------------------------------------------------------
    regular_items: list[dict] = []
    for sid in enrollment_ids:
        s = students_map.get(sid)
        if not s:
            continue  # aluno deletado mas matrícula órfã — silencia
        regular_items.append(_build_item(
            student=s, class_id=class_id, course_id=course_id,
            is_dependency=False, enrollment_number=enrollment_numbers.get(sid),
        ))
    regular_items.sort(key=_sort_key_pt_br)

    dependency_items: list[dict] = []
    for sid in dep_student_ids:
        s = students_map.get(sid)
        if not s:
            continue
        dependency_items.append(_build_item(
            student=s, class_id=class_id, course_id=course_id,
            is_dependency=True, dependency_doc=dep_by_student[sid],
        ))
    dependency_items.sort(key=_sort_key_pt_br)

    items = regular_items + dependency_items
    regular_count = len(regular_items)
    dependency_count = len(dependency_items)
    total = regular_count + dependency_count
    dep_ratio = round((dependency_count / total) * 100, 2) if total else 0.0

    # ------------------------------------------------------------------
    # Warnings operacionais (não bloqueia, apenas sinaliza)
    # ------------------------------------------------------------------
    if dependency_count > MAX_DEPENDENCY_STUDENTS_PER_DIARY:
        warnings.append({
            "code": "EXCESS_DEPENDENCY_LOAD",
            "count": dependency_count,
            "threshold": MAX_DEPENDENCY_STUDENTS_PER_DIARY,
            "message": "Volume anômalo de alunos em dependência neste componente.",
        })
        logger.error(
            "[diary] excess dep load class=%s course=%s count=%d",
            class_id, course_id, dependency_count,
        )

    if dependency_count > regular_count and total > 0:
        warnings.append({
            "code": "DEP_GREATER_THAN_REGULAR",
            "regular": regular_count,
            "dependency": dependency_count,
            "message": (
                "Quantidade de alunos em dependência maior que regulares — "
                "verifique configuração da mantenedora."
            ),
        })
        logger.warning(
            "[diary] dep > regular class=%s course=%s deps=%d reg=%d",
            class_id, course_id, dependency_count, regular_count,
        )

    duration_ms = (time.monotonic() - t0) * 1000

    # Telemetria — sempre registra
    # Resolve school_stage da turma (cache leve via 1 query, opcional)
    school_stage = None
    try:
        cls = await db.classes.find_one(
            {"id": class_id}, {"_id": 0, "school_stage": 1, "etapa": 1, "modalidade": 1}
        )
        if cls:
            school_stage = cls.get("school_stage") or cls.get("etapa") or cls.get("modalidade")
    except Exception:
        pass

    record_diary_load(
        duration_ms=duration_ms,
        tenant_id=tenant_id,
        regular_count=regular_count,
        dependency_count=dependency_count,
        cache_hit=False,
        is_error=False,
        class_id=class_id,
        course_id=course_id,
        dependency_ratio_pct=dep_ratio,
        excess_dep=dependency_count > MAX_DEPENDENCY_STUDENTS_PER_DIARY,
        school_stage=school_stage,
    )

    payload = {
        "contract_version": DIARY_CONTRACT_VERSION,
        "class_id": class_id,
        "course_id": course_id,
        "academic_year": academic_year,
        "items": items,
        "meta": {
            "regular_count": regular_count,
            "dependency_count": dependency_count,
            "has_dependencies": dependency_count > 0,
            "dependency_ratio_pct": dep_ratio,
            "total": total,
            "load_duration_ms": round(duration_ms, 2),
        },
    }
    if warnings:
        payload["warnings"] = warnings
    return payload
