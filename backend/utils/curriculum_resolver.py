"""
Curriculum Resolver — Evidence-First (Fev/2026).

Resolução determinística de componentes curriculares de um aluno em uma turma.
Princípio: evidência acadêmica concreta > vínculo cadastral explícito > inferência.

ORDEM DE RESOLUÇÃO:
  STEP 1 — Evidence: course_ids com `grades` + `attendance` reais do aluno.
  STEP 2 — class.course_ids: matriz curricular explícita da turma (exclui colisões de nome com evidência).
  STEP 3 — teacher_assignments: cursos vinculados a professores ativos da turma (exclui colisões).
  STEP 4 — Fallback por nivel_ensino: SOMENTE se (no_evidence AND no_matrix).
  STEP 5 — Dedupe final por nome normalizado:
    1) maior evidence_score
    2) active=true
    3) created_at mais recente
    4) course_id (estável)

WARNINGS:
  - CLASS_WITHOUT_CURRICULUM_MATRIX: turma sem `course_ids`.
  - DUPLICATE_COURSE_NAME: dois ou mais cursos com mesmo nome chegaram à resolução.

REGRAS CRÍTICAS:
  - Puro (apenas leitura).
  - Determinístico (mesmo input → mesma saída).
  - Não esconde inconsistência: warnings sempre emitidos.
  - PDF + Boletim Online + render_jobs DEVEM consumir esta mesma resolução.
"""
from __future__ import annotations

import logging
import unicodedata
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


def _norm_name(name: str) -> str:
    """Normaliza nome de curso para detecção de duplicidade.

    casefold + strip accents + colapsa espaços.
    """
    if not name:
        return ""
    s = "".join(
        c for c in unicodedata.normalize("NFKD", str(name))
        if not unicodedata.combining(c)
    )
    return " ".join(s.casefold().strip().split())


def _infer_nivel_ensino(grade_level: str) -> Optional[str]:
    """Infere `nivel_ensino` a partir de `grade_level` / `student_series`.

    Replicado do bulletin PDF para manter compatibilidade exata.
    """
    gl = (grade_level or "").lower()
    if not gl:
        return None
    if any(x in gl for x in [
        'berçário', 'bercario', 'maternal', 'pré', 'pre',
    ]):
        return 'educacao_infantil'
    if any(x in gl for x in [
        '1º ano', '2º ano', '3º ano', '4º ano', '5º ano',
        '1 ano', '2 ano', '3 ano', '4 ano', '5 ano',
    ]):
        return 'fundamental_anos_iniciais'
    if any(x in gl for x in [
        '6º ano', '7º ano', '8º ano', '9º ano',
        '6 ano', '7 ano', '8 ano', '9 ano',
    ]):
        return 'fundamental_anos_finais'
    if 'eja' in gl or 'etapa' in gl:
        if any(x in gl for x in ['3', '4', 'final']):
            return 'eja_final'
        return 'eja'
    return None


def _apply_atendimento_filter(
    components: list[dict], atendimento_filter: Optional[str]
) -> list[dict]:
    """Filtra componentes por atendimento_programa da turma.

    Replica regra do PDF antigo (linhas 291-301 de routers/documents.py).
    """
    if not atendimento_filter:
        return components
    ap = atendimento_filter.lower().strip()
    if ap in ("atendimento_integral", "integral"):
        # Turma integral: manter regulares + integrais, excluir AEE
        return [
            c for c in components
            if (c.get("atendimento_programa") or "") in ("", "regular", "atendimento_integral")
        ]
    if ap == "aee":
        return [
            c for c in components
            if (c.get("atendimento_programa") or "").lower() == "aee"
        ]
    # Turma regular: excluir integral e AEE
    return [
        c for c in components
        if (c.get("atendimento_programa") or "") in ("", "regular")
    ]


async def _collect_evidence(
    db, *, student_id: str, class_id: str, academic_year: int
) -> dict[str, dict]:
    """Coleta evidência acadêmica REAL do aluno: grades + attendance."""
    evidence: dict[str, dict] = defaultdict(
        lambda: {"grades_count": 0, "attendance_count": 0}
    )
    async for g in db.grades.find(
        {
            "student_id": student_id,
            "class_id": class_id,
            "academic_year": academic_year,
        },
        {"_id": 0, "course_id": 1},
    ):
        cid = g.get("course_id")
        if cid:
            evidence[cid]["grades_count"] += 1

    async for att in db.attendance.find(
        {"class_id": class_id},
        {"_id": 0, "course_id": 1, "records": 1},
    ):
        cid = att.get("course_id")
        if not cid:
            continue
        for rec in att.get("records") or []:
            if rec.get("student_id") == student_id:
                evidence[cid]["attendance_count"] += 1
    return dict(evidence)


async def _collect_teacher_assignment_course_ids(db, class_id: str) -> list[str]:
    out: list[str] = []
    seen = set()
    async for a in db.teacher_assignments.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo", "ativo"]}},
        {"_id": 0, "course_id": 1},
    ):
        cid = a.get("course_id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def _collect_fallback_course_ids(
    db, *, nivel_ensino: str
) -> list[str]:
    out: list[str] = []
    seen = set()
    async for c in db.courses.find(
        {"nivel_ensino": nivel_ensino},
        {"_id": 0, "id": 1},
    ):
        cid = c.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def _load_courses(db, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    out: dict[str, dict] = {}
    async for c in db.courses.find(
        {"id": {"$in": ids}},
        {
            "_id": 0, "id": 1, "name": 1, "active": 1,
            "atendimento_programa": 1, "optativo": 1,
            "nivel_ensino": 1, "created_at": 1, "deleted_at": 1,
        },
    ):
        out[c["id"]] = c
    return out


def _pick_winner(group: list[dict]) -> tuple[dict, str]:
    """Aplica dedupe determinístico: evidence_score > active > created_at > course_id."""
    max_ev = max(c["evidence_score"] for c in group)
    top = [c for c in group if c["evidence_score"] == max_ev]
    reason = "higher_evidence" if any(
        c["evidence_score"] == 0 for c in group
    ) and max_ev > 0 else None

    if len(top) > 1:
        actives = [c for c in top if c["active"]]
        if actives and len(actives) < len(top):
            top = actives
            reason = reason or "active_tiebreak"

    if len(top) > 1:
        # created_at desc — vazio fica por último
        top.sort(key=lambda c: (c.get("created_at") or ""), reverse=True)
        if (top[0].get("created_at") or "") != (top[-1].get("created_at") or ""):
            reason = reason or "recency_tiebreak"

    if len(top) > 1:
        # Estável por course_id
        top.sort(key=lambda c: c["course_id"])
        reason = reason or "course_id_tiebreak"

    if reason is None:
        reason = "only_candidate"
    return top[0], reason


async def resolve_curriculum(
    db,
    *,
    student_id: str,
    class_id: str,
    academic_year: int,
    class_info: Optional[dict] = None,
    student_info: Optional[dict] = None,
    atendimento_programa_filter: Optional[str] = None,
) -> dict:
    """Resolve componentes curriculares de um aluno em uma turma.

    Retorna:
        {
          "components": [
            {course_id, course_name, active, atendimento_programa, optativo,
             nivel_ensino, source ('evidence'|'class'|'teacher_assignment'|'fallback'),
             evidence_score, grades_count, attendance_count, dedupe_kept_reason}
          ],
          "warnings": [{code, ...}],
          "debug": {
            evidence_course_ids, class_course_ids, teacher_assignment_course_ids,
            fallback_course_ids, dropped_by_dedupe, duplicate_names_detected,
            resolution_path, final_resolution
          }
        }
    """
    warnings: list[dict] = []
    resolution_path: list[dict] = []

    # Carrega class_info / student_info se não fornecidos
    if class_info is None:
        class_info = await db.classes.find_one(
            {"id": class_id},
            {
                "_id": 0, "id": 1, "name": 1, "course_ids": 1,
                "nivel_ensino": 1, "education_level": 1, "grade_level": 1,
                "atendimento_programa": 1, "school_id": 1, "academic_year": 1,
            },
        ) or {}
    if student_info is None:
        student_info = await db.students.find_one(
            {"id": student_id},
            {"_id": 0, "id": 1, "student_series": 1, "class_id": 1},
        ) or {}

    # STEP 1 — Evidence
    evidence_map = await _collect_evidence(
        db, student_id=student_id, class_id=class_id, academic_year=academic_year
    )
    evidence_course_ids = list(evidence_map.keys())
    resolution_path.append({
        "step": "evidence",
        "found": len(evidence_course_ids),
        "course_ids": evidence_course_ids,
    })

    # STEP 2 — class.course_ids
    class_course_ids = list(class_info.get("course_ids") or [])
    resolution_path.append({
        "step": "class_course_ids",
        "found": len(class_course_ids),
        "course_ids": class_course_ids,
    })
    if not class_course_ids:
        warnings.append({
            "code": "CLASS_WITHOUT_CURRICULUM_MATRIX",
            "class_id": class_id,
            "message": (
                "Turma sem matriz curricular explícita. Resolver utilizou "
                "fallback controlado."
            ),
        })

    # STEP 3 — teacher_assignments
    ta_course_ids = await _collect_teacher_assignment_course_ids(db, class_id)
    resolution_path.append({
        "step": "teacher_assignments",
        "found": len(ta_course_ids),
        "course_ids": ta_course_ids,
    })

    # STEP 4 — Fallback por nivel_ensino (somente se sem evidência E sem matriz)
    no_evidence = len(evidence_course_ids) == 0
    no_matrix = len(class_course_ids) == 0 and len(ta_course_ids) == 0
    fallback_course_ids: list[str] = []
    if no_evidence and no_matrix:
        nivel = class_info.get("nivel_ensino") or class_info.get("education_level")
        if not nivel:
            grade_level = (
                student_info.get("student_series")
                or class_info.get("grade_level")
                or ""
            )
            nivel = _infer_nivel_ensino(grade_level)
        if nivel:
            fallback_course_ids = await _collect_fallback_course_ids(
                db, nivel_ensino=nivel
            )
        resolution_path.append({
            "step": "nivel_ensino_fallback",
            "activated": True,
            "nivel_ensino": nivel,
            "found": len(fallback_course_ids),
        })
    else:
        resolution_path.append({
            "step": "nivel_ensino_fallback",
            "activated": False,
            "skip_reason": (
                "has_academic_evidence" if not no_evidence else "has_curriculum_matrix"
            ),
        })

    # Une candidatos com prioridade de source
    candidates: dict[str, dict] = {}
    for cid in evidence_course_ids:
        candidates[cid] = {"course_id": cid, "source": "evidence"}
    for cid in class_course_ids:
        if cid not in candidates:
            candidates[cid] = {"course_id": cid, "source": "class"}
    for cid in ta_course_ids:
        if cid not in candidates:
            candidates[cid] = {"course_id": cid, "source": "teacher_assignment"}
    for cid in fallback_course_ids:
        if cid not in candidates:
            candidates[cid] = {"course_id": cid, "source": "fallback"}

    # Hidrata com courses
    courses_map = await _load_courses(db, list(candidates.keys()))

    components: list[dict] = []
    for cid, cand in candidates.items():
        doc = courses_map.get(cid) or {}
        ev = evidence_map.get(cid, {"grades_count": 0, "attendance_count": 0})
        components.append({
            "course_id": cid,
            "course_name": doc.get("name"),
            "active": bool(doc.get("active", True)),
            "atendimento_programa": doc.get("atendimento_programa") or "regular",
            "optativo": bool(doc.get("optativo", False)),
            "nivel_ensino": doc.get("nivel_ensino"),
            "created_at": doc.get("created_at"),
            "source": cand["source"],
            "grades_count": ev["grades_count"],
            "attendance_count": ev["attendance_count"],
            "evidence_score": ev["grades_count"] + ev["attendance_count"],
            "dedupe_kept_reason": None,
        })

    # Filtro por atendimento_programa (replica regra do PDF)
    components = _apply_atendimento_filter(components, atendimento_programa_filter)

    # STEP 5 — Dedupe final por nome normalizado
    by_norm: dict[str, list[dict]] = defaultdict(list)
    for c in components:
        n = _norm_name(c.get("course_name") or "")
        if not n:
            n = f"__unnamed__{c['course_id']}"
        by_norm[n].append(c)

    final_components: list[dict] = []
    duplicate_names_detected: list[dict] = []
    dropped_by_dedupe: list[dict] = []

    for norm_name, group in by_norm.items():
        if len(group) == 1:
            group[0]["dedupe_kept_reason"] = "only_candidate"
            final_components.append(group[0])
            continue

        duplicate_names_detected.append({
            "course_name": group[0].get("course_name") or "(sem nome)",
            "course_ids": [c["course_id"] for c in group],
            "sources": [c["source"] for c in group],
        })
        winner, reason = _pick_winner(group)
        winner["dedupe_kept_reason"] = reason
        final_components.append(winner)
        for c in group:
            if c["course_id"] != winner["course_id"]:
                dropped_by_dedupe.append({
                    "course_id": c["course_id"],
                    "course_name": c.get("course_name"),
                    "source": c["source"],
                    "evidence_score": c["evidence_score"],
                    "active": c["active"],
                    "winner_course_id": winner["course_id"],
                    "winner_reason": reason,
                })

        warnings.append({
            "code": "DUPLICATE_COURSE_NAME",
            "course_name": group[0].get("course_name"),
            "class_id": class_id,
            "course_ids": [c["course_id"] for c in group],
            "resolved_by_evidence": winner["evidence_score"] > 0,
            "winner_course_id": winner["course_id"],
            "winner_reason": reason,
            "message": (
                f"Mais de um componente curricular com nome "
                f"'{group[0].get('course_name')}' candidato à resolução. "
                f"Sistema escolheu por {reason}."
            ),
        })
        logger.warning(
            "curriculum_resolver.duplicate_name class_id=%s name=%s "
            "candidates=%s winner=%s reason=%s",
            class_id, group[0].get("course_name"),
            [c["course_id"] for c in group],
            winner["course_id"], reason,
        )

    # Ordenação final estável (por nome normalizado)
    final_components.sort(
        key=lambda c: _norm_name(c.get("course_name") or "")
    )

    return {
        "components": final_components,
        "warnings": warnings,
        "debug": {
            "evidence_course_ids": evidence_course_ids,
            "class_course_ids": class_course_ids,
            "teacher_assignment_course_ids": ta_course_ids,
            "fallback_course_ids": fallback_course_ids,
            "dropped_by_dedupe": dropped_by_dedupe,
            "duplicate_names_detected": duplicate_names_detected,
            "resolution_path": resolution_path,
            "final_resolution": [
                {
                    "course_id": c["course_id"],
                    "course_name": c["course_name"],
                    "source": c["source"],
                    "evidence_score": c["evidence_score"],
                    "dedupe_kept_reason": c["dedupe_kept_reason"],
                }
                for c in final_components
            ],
        },
    }
