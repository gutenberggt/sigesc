"""
Curriculum Resolver — Evidence-First + Curricular Compatibility (Ago/2026).

Resolução determinística de componentes curriculares de um aluno em uma turma.
Princípio: compatibilidade curricular explícita limita a escolha entre componentes
homônimos; dentro do mesmo nível de compatibilidade, preserva-se a precedência
histórica de evidência acadêmica concreta > vínculo cadastral explícito > inferência.

ORDEM DE RESOLUÇÃO:
  STEP 1 — Evidence: course_ids com `grades` + `attendance` reais do aluno.
  STEP 2 — class.course_ids: matriz curricular explícita da turma.
  STEP 3 — teacher_assignments: cursos vinculados a professores ativos da turma.
  STEP 4 — Fallback por nivel_ensino: SOMENTE se (no_evidence AND no_matrix).
  STEP 5 — Dedupe final por nome normalizado:
    1) maior curricular_rank
    2) maior evidence_score
    3) active=true
    4) created_at mais recente
    5) course_id (estável)

WARNINGS:
  - CLASS_WITHOUT_CURRICULUM_MATRIX: turma sem `course_ids`.
  - DUPLICATE_COURSE_NAME: dois ou mais cursos com mesmo nome chegaram à resolução.
  - CURRICULAR_COMPATIBILITY_REVIEW_REQUIRED: colisão homônima contém escopo
    curricular incompatível ou inconclusivo e exige revisão cadastral.

REGRAS CRÍTICAS:
  - Puro (apenas leitura).
  - Determinístico (mesmo input → mesma saída).
  - Não esconde inconsistência: warnings sempre emitidos.
  - PDF + Boletim Online + render_jobs DEVEM consumir esta mesma resolução.
  - Quando a turma possui `mantenedora_id`, TODA leitura interna fica presa ao tenant.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from typing import Any, Optional

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


def _norm_scalar(value: Any) -> str:
    if value is None:
        return ""
    return _norm_name(str(value))


def _tenant_query(query: dict, tenant_id: Optional[str]) -> dict:
    """Aplica isolamento de mantenedora sem acoplar o resolver ao FastAPI.

    O resolver é compartilhado por vários consumidores. O tenant é derivado da
    própria turma já carregada/validada; quando ausente (dados/consumidores
    legados), o comportamento histórico é preservado.
    """
    scoped = dict(query)
    if tenant_id:
        scoped["mantenedora_id"] = tenant_id
    return scoped


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


def _series_tokens(value: Any) -> set[str]:
    """Normaliza séries/etapas em tokens comparáveis sem presumir currículo.

    Exemplos:
      "8º ANO" -> {"ano:8"}
      ["8º", "9º"] -> {"ano:8", "ano:9"}
      "EJA 3ª ETAPA" -> {"eja:3"}
    """
    if value is None:
        return set()
    if isinstance(value, dict):
        out: set[str] = set()
        for key in value.keys():
            out.update(_series_tokens(key))
        return out
    if isinstance(value, (list, tuple, set)):
        out: set[str] = set()
        for item in value:
            out.update(_series_tokens(item))
        return out

    text = _norm_scalar(value)
    if not text:
        return set()
    digits = [d for d in re.findall(r"(?<!\d)([1-9])(?!\d)", text)]
    if not digits:
        return set()

    prefix = "eja" if ("eja" in text or "etapa" in text) else "ano"
    return {f"{prefix}:{d}" for d in digits}


def _resolve_class_curricular_context(
    class_info: dict,
    student_info: dict,
) -> tuple[Optional[str], set[str]]:
    level = class_info.get("nivel_ensino") or class_info.get("education_level")
    if not level:
        level = _infer_nivel_ensino(
            student_info.get("student_series")
            or class_info.get("grade_level")
            or ""
        )

    class_series = _series_tokens(class_info.get("series"))
    if not class_series:
        class_series = _series_tokens(student_info.get("student_series"))
    if not class_series:
        class_series = _series_tokens(class_info.get("grade_level"))
    return level, class_series


def _curricular_fit(
    course: dict,
    *,
    class_level: Optional[str],
    class_series: set[str],
) -> dict:
    """Classifica compatibilidade para ordenar somente colisões homônimas.

    Rank 3 = forte; rank 2 = inconclusivo/review; rank 1 = incompatível.
    O rank nunca cria vínculo nem busca candidato fora do conjunto já resolvido.
    """
    course_level = course.get("nivel_ensino")
    if class_level and course_level and _norm_scalar(course_level) != _norm_scalar(class_level):
        return {
            "rank": 1,
            "classification": "LEVEL_MISMATCH",
            "class_level": class_level,
            "course_level": course_level,
            "class_series": sorted(class_series),
        }

    if not class_level:
        return {
            "rank": 2,
            "classification": "UNKNOWN_CLASS_LEVEL",
            "class_level": None,
            "course_level": course_level,
            "class_series": sorted(class_series),
        }

    if not course_level:
        return {
            "rank": 2,
            "classification": "COURSE_LEVEL_UNKNOWN_REQUIRES_REVIEW",
            "class_level": class_level,
            "course_level": None,
            "class_series": sorted(class_series),
        }

    if not class_series:
        return {
            "rank": 2,
            "classification": "LEVEL_MATCH_SERIES_UNKNOWN",
            "class_level": class_level,
            "course_level": course_level,
            "class_series": [],
        }

    explicit = _series_tokens(course.get("grade_levels"))
    matrix = _series_tokens(course.get("carga_horaria_por_serie"))

    explicit_full = bool(explicit) and class_series.issubset(explicit)
    matrix_full = bool(matrix) and class_series.issubset(matrix)
    explicit_overlap = bool(explicit & class_series)
    matrix_overlap = bool(matrix & class_series)

    if explicit and matrix:
        if explicit_full and matrix_full:
            classification = "EXPLICIT_AND_MATRIX_FULL_MATCH"
            rank = 3
        elif not explicit_overlap and not matrix_overlap:
            classification = "NO_SERIES_MATCH"
            rank = 1
        else:
            classification = "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW"
            rank = 2
    elif explicit:
        if explicit_full:
            classification = "EXPLICIT_SERIES_FULL_MATCH"
            rank = 3
        elif explicit_overlap:
            classification = "PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW"
            rank = 2
        else:
            classification = "NO_SERIES_MATCH"
            rank = 1
    elif matrix:
        if matrix_full:
            classification = "PER_SERIES_MATRIX_FULL_MATCH"
            rank = 3
        elif matrix_overlap:
            classification = "PARTIAL_MATRIX_SERIES_MATCH_REQUIRES_REVIEW"
            rank = 2
        else:
            classification = "NO_SERIES_MATCH"
            rank = 1
    else:
        classification = "LEVEL_MATCH_NO_SERIES_SCOPE"
        rank = 2

    return {
        "rank": rank,
        "classification": classification,
        "class_level": class_level,
        "course_level": course_level,
        "class_series": sorted(class_series),
        "explicit_series": sorted(explicit),
        "matrix_series": sorted(matrix),
    }


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
        return [
            c for c in components
            if (c.get("atendimento_programa") or "") in ("", "regular", "atendimento_integral")
        ]
    if ap == "aee":
        return [
            c for c in components
            if (c.get("atendimento_programa") or "").lower() == "aee"
        ]
    return [
        c for c in components
        if (c.get("atendimento_programa") or "") in ("", "regular")
    ]


async def _collect_evidence(
    db,
    *,
    student_id: str,
    class_id: str,
    academic_year: int,
    tenant_id: Optional[str] = None,
) -> dict[str, dict]:
    """Coleta evidência acadêmica REAL do aluno: grades + attendance."""
    evidence: dict[str, dict] = defaultdict(
        lambda: {"grades_count": 0, "attendance_count": 0}
    )
    async for g in db.grades.find(
        _tenant_query(
            {
                "student_id": student_id,
                "class_id": class_id,
                "academic_year": academic_year,
            },
            tenant_id,
        ),
        {"_id": 0, "course_id": 1},
    ):
        cid = g.get("course_id")
        if cid:
            evidence[cid]["grades_count"] += 1

    async for att in db.attendance.find(
        _tenant_query({"class_id": class_id}, tenant_id),
        {"_id": 0, "course_id": 1, "records": 1},
    ):
        cid = att.get("course_id")
        if not cid:
            continue
        for rec in att.get("records") or []:
            if rec.get("student_id") == student_id:
                evidence[cid]["attendance_count"] += 1
    return dict(evidence)


async def _collect_teacher_assignment_course_ids(
    db, class_id: str, *, tenant_id: Optional[str] = None
) -> list[str]:
    out: list[str] = []
    seen = set()
    async for a in db.teacher_assignments.find(
        _tenant_query(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo", "ativo"]}},
            tenant_id,
        ),
        {"_id": 0, "course_id": 1},
    ):
        cid = a.get("course_id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def _collect_fallback_course_ids(
    db, *, nivel_ensino: str, tenant_id: Optional[str] = None
) -> list[str]:
    out: list[str] = []
    seen = set()
    async for c in db.courses.find(
        _tenant_query({"nivel_ensino": nivel_ensino}, tenant_id),
        {"_id": 0, "id": 1},
    ):
        cid = c.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def _load_courses(
    db, ids: list[str], *, tenant_id: Optional[str] = None
) -> dict[str, dict]:
    if not ids:
        return {}
    out: dict[str, dict] = {}
    async for c in db.courses.find(
        _tenant_query({"id": {"$in": ids}}, tenant_id),
        {
            "_id": 0, "id": 1, "name": 1, "active": 1,
            "atendimento_programa": 1, "optativo": 1,
            "nivel_ensino": 1, "grade_levels": 1,
            "carga_horaria_por_serie": 1,
            "created_at": 1, "deleted_at": 1,
        },
    ):
        out[c["id"]] = c
    return out


def _pick_winner(group: list[dict]) -> tuple[dict, str]:
    """Dedupe: curricular_rank > evidence > active > created_at > course_id."""
    max_curricular = max(int(c.get("curricular_rank") or 0) for c in group)
    top = [c for c in group if int(c.get("curricular_rank") or 0) == max_curricular]
    reason = (
        "stronger_curricular_compatibility"
        if len(top) < len(group)
        else None
    )

    max_ev = max(c["evidence_score"] for c in top)
    evidence_top = [c for c in top if c["evidence_score"] == max_ev]
    if len(evidence_top) < len(top):
        top = evidence_top
        reason = reason or "higher_evidence"
    else:
        top = evidence_top

    if len(top) > 1:
        actives = [c for c in top if c["active"]]
        if actives and len(actives) < len(top):
            top = actives
            reason = reason or "active_tiebreak"

    if len(top) > 1:
        top.sort(key=lambda c: (c.get("created_at") or ""), reverse=True)
        if (top[0].get("created_at") or "") != (top[-1].get("created_at") or ""):
            reason = reason or "recency_tiebreak"

    if len(top) > 1:
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

    Quando `class_info` contém `mantenedora_id`, o escopo é propagado para
    grades, attendance, teacher_assignments e courses. O contrato público
    continua intacto para consumidores legados.
    """
    warnings: list[dict] = []
    resolution_path: list[dict] = []

    if class_info is None:
        class_info = await db.classes.find_one(
            {"id": class_id},
            {
                "_id": 0, "id": 1, "name": 1, "course_ids": 1,
                "nivel_ensino": 1, "education_level": 1, "grade_level": 1,
                "series": 1,
                "atendimento_programa": 1, "school_id": 1, "academic_year": 1,
                "mantenedora_id": 1,
            },
        ) or {}

    tenant_id = class_info.get("mantenedora_id")

    if student_info is None:
        student_info = await db.students.find_one(
            _tenant_query({"id": student_id}, tenant_id),
            {"_id": 0, "id": 1, "student_series": 1, "class_id": 1},
        ) or {}

    class_level, class_series = _resolve_class_curricular_context(
        class_info, student_info
    )

    evidence_map = await _collect_evidence(
        db,
        student_id=student_id,
        class_id=class_id,
        academic_year=academic_year,
        tenant_id=tenant_id,
    )
    evidence_course_ids = list(evidence_map.keys())
    resolution_path.append({
        "step": "evidence",
        "found": len(evidence_course_ids),
        "course_ids": evidence_course_ids,
    })

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

    ta_course_ids = await _collect_teacher_assignment_course_ids(
        db, class_id, tenant_id=tenant_id
    )
    resolution_path.append({
        "step": "teacher_assignments",
        "found": len(ta_course_ids),
        "course_ids": ta_course_ids,
    })

    no_evidence = len(evidence_course_ids) == 0
    no_matrix = len(class_course_ids) == 0 and len(ta_course_ids) == 0
    fallback_course_ids: list[str] = []
    if no_evidence and no_matrix:
        if class_level:
            fallback_course_ids = await _collect_fallback_course_ids(
                db, nivel_ensino=class_level, tenant_id=tenant_id
            )
        resolution_path.append({
            "step": "nivel_ensino_fallback",
            "activated": True,
            "nivel_ensino": class_level,
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

    courses_map = await _load_courses(
        db, list(candidates.keys()), tenant_id=tenant_id
    )

    components: list[dict] = []
    for cid, cand in candidates.items():
        doc = courses_map.get(cid) or {}
        ev = evidence_map.get(cid, {"grades_count": 0, "attendance_count": 0})
        fit = _curricular_fit(
            doc,
            class_level=class_level,
            class_series=class_series,
        )
        components.append({
            "course_id": cid,
            "course_name": doc.get("name"),
            "active": bool(doc.get("active", True)),
            "atendimento_programa": doc.get("atendimento_programa") or "regular",
            "optativo": bool(doc.get("optativo", False)),
            "nivel_ensino": doc.get("nivel_ensino"),
            "grade_levels": doc.get("grade_levels") or [],
            "carga_horaria_por_serie": doc.get("carga_horaria_por_serie") or {},
            "created_at": doc.get("created_at"),
            "source": cand["source"],
            "grades_count": ev["grades_count"],
            "attendance_count": ev["attendance_count"],
            "evidence_score": ev["grades_count"] + ev["attendance_count"],
            "curricular_rank": fit["rank"],
            "curricular_classification": fit["classification"],
            "curricular_fit": fit,
            "dedupe_kept_reason": None,
        })

    components = _apply_atendimento_filter(components, atendimento_programa_filter)

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
            "curricular_classifications": [
                c["curricular_classification"] for c in group
            ],
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
                    "curricular_rank": c["curricular_rank"],
                    "curricular_classification": c["curricular_classification"],
                    "winner_course_id": winner["course_id"],
                    "winner_reason": reason,
                })

        review_required = any(
            c["curricular_rank"] < 3 for c in group
        )
        if review_required:
            warnings.append({
                "code": "CURRICULAR_COMPATIBILITY_REVIEW_REQUIRED",
                "course_name": group[0].get("course_name"),
                "class_id": class_id,
                "class_level": class_level,
                "class_series": sorted(class_series),
                "course_ids": [c["course_id"] for c in group],
                "classifications": {
                    c["course_id"]: c["curricular_classification"]
                    for c in group
                },
                "winner_course_id": winner["course_id"],
                "winner_reason": reason,
                "message": (
                    "Colisão de componentes homônimos contém compatibilidade "
                    "curricular inconclusiva ou incompatível; revisar cadastro."
                ),
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

    final_components.sort(
        key=lambda c: _norm_name(c.get("course_name") or "")
    )

    return {
        "components": final_components,
        "warnings": warnings,
        "debug": {
            "tenant_id": tenant_id,
            "class_level": class_level,
            "class_series": sorted(class_series),
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
                    "curricular_rank": c["curricular_rank"],
                    "curricular_classification": c["curricular_classification"],
                    "dedupe_kept_reason": c["dedupe_kept_reason"],
                }
                for c in final_components
            ],
        },
    }
