"""
Bulletin Builder — read-model pedagógico (Boletim Online MVP).

[Fev/2026] Passo 5 — escopo MÍNIMO autorizado pelo owner:
- Consome `compute_composite_closure(...)` (NUNCA o diário vivo).
- Lê `db.grades` e `db.attendance` filtrando por (student_id, academic_year, class_id)
  onde `class_id` é o dono do período (`§6.1` ACADEMIC_EVENT_CONTRACT — class_id
  é IMUTÁVEL no registro).
- Separa `regular_only` de `dependency` via `regular_only_filter`.
- Retorna shape canônico com `is_composite` e `composite_segments`.

PROIBIDO nesta V1:
- ❌ Calcular média final consolidada cross-period (responsabilidade do Histórico Fase 4).
- ❌ Persistir snapshot de boletim (PDF + assinatura é Fase posterior).
- ❌ Renderizar HTML/PDF.
- ❌ Mutar qualquer estado.

Princípio: boletim é PROJEÇÃO. Read-model derivado. Nunca fonte de verdade.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from utils.grade_dependency_filters import with_regular_only
from utils.temporal_closure import compute_composite_closure

logger = logging.getLogger(__name__)

BULLETIN_VERSION = "1"


def _to_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError, AttributeError):
        return None


def _is_in_window(record_date: str, start: str, end: str) -> bool:
    """Retorna True se `record_date` (YYYY-MM-DD) está em [start, end] inclusive."""
    d = _to_date(record_date)
    s = _to_date(start)
    e = _to_date(end)
    if not d or not s or not e:
        return False
    return s <= d <= e


async def _resolve_class_info(db, class_id: str) -> dict:
    if not class_id:
        return {}
    cls = await db.classes.find_one({"id": class_id}, {"_id": 0}) or {}
    return {
        "id": cls.get("id"),
        "name": cls.get("name"),
        "grade_level": cls.get("grade_level"),
        "education_level": cls.get("education_level") or cls.get("nivel_ensino"),
        "school_id": cls.get("school_id"),
    }


async def _resolve_school_info(db, school_id: Optional[str]) -> dict:
    if not school_id:
        return {}
    sch = await db.schools.find_one({"id": school_id}, {"_id": 0, "id": 1, "name": 1}) or {}
    return {"id": sch.get("id"), "name": sch.get("name")}


async def _resolve_courses_for_class(db, class_id: str) -> list[dict]:
    cls = await db.classes.find_one({"id": class_id}, {"_id": 0, "course_ids": 1}) or {}
    cids = cls.get("course_ids") or []
    if not cids:
        return []
    courses = []
    async for c in db.courses.find(
        {"id": {"$in": cids}},
        {"_id": 0, "id": 1, "name": 1, "atendimento_programa": 1, "optativo": 1},
    ):
        courses.append(c)
    return courses


def _bimesters_owned_by_period(period_index: int, bimesters: list[dict]) -> list[int]:
    """Lista de bimestres (1..4) que pertencem a um período."""
    return [
        b["bimester"]
        for b in bimesters
        if b.get("period_index") == period_index and b.get("bimester")
    ]


def _normalize_course_name(name: str) -> str:
    """Normaliza nome de curso para detecção de duplicidade.

    Casefold + colapsa espaços. NÃO remove acentos (já vêm normalizados na
    base; qualquer divergência ortográfica é problema curricular real, não
    falso positivo).
    """
    if not name:
        return ""
    return " ".join(str(name).strip().casefold().split())


def _flag_duplicate_course_names(
    components: list[dict], *, segment_class_id: str, period_index: int
) -> list[dict]:
    """Detecta componentes com mesmo nome no mesmo segmento.

    Não remove, não unifica. Apenas marca cada componente afetado com
    `_warning_duplicate_name=True` e retorna lista de warnings (objetos)
    a serem agregados no payload do boletim.

    Princípio: boletim espelha o cadastro fielmente. Cabe ao admin sanear.
    """
    warnings: list[dict] = []
    if not components:
        return warnings

    by_norm: dict[str, list[dict]] = {}
    for c in components:
        norm = _normalize_course_name(c.get("course_name") or "")
        if not norm:
            continue
        by_norm.setdefault(norm, []).append(c)

    for norm, group in by_norm.items():
        if len(group) <= 1:
            continue
        for c in group:
            c["_warning_duplicate_name"] = True
        warnings.append({
            "code": "DUPLICATE_COURSE_NAME",
            "type": "duplicate_course_name",
            "course_name": group[0].get("course_name"),
            "class_id": segment_class_id,
            "period_index": period_index,
            "course_ids": [c.get("course_id") for c in group],
            "message": (
                f"Existe mais de um componente curricular com o mesmo nome "
                f"('{group[0].get('course_name')}') vinculado à turma neste "
                f"período. Verifique o cadastro de cursos."
            ),
        })
    return warnings


async def _grades_for_segment(
    db,
    *,
    student_id: str,
    academic_year: int,
    class_id: str,
    course_ids: list[str],
) -> list[dict]:
    """Notas regulares (exclui dependency) onde class_id é dona."""
    flt: dict = {
        "student_id": student_id,
        "academic_year": academic_year,
        "class_id": class_id,
    }
    if course_ids:
        flt["course_id"] = {"$in": course_ids}
    flt = with_regular_only(flt)
    out = []
    async for g in db.grades.find(flt, {"_id": 0}):
        out.append(g)
    return out


async def _dependency_grades_for_student(
    db, *, student_id: str, academic_year: int
) -> list[dict]:
    """Lista TODAS as notas de dependência do aluno no ano (independente de class_id).

    Dependência é entidade própria — não amarrada à temporalidade do diário regular.
    """
    flt = {
        "student_id": student_id,
        "academic_year": academic_year,
        "dependency_id": {"$exists": True, "$ne": None},
    }
    out = []
    async for g in db.grades.find(flt, {"_id": 0}):
        out.append(g)
    return out


async def _attendance_summary_for_segment(
    db,
    *,
    student_id: str,
    class_id: str,
    period_start: str,
    period_end: str,
) -> dict:
    """Frequência regular do aluno no segmento (exclui dependency_id)."""
    total = 0
    presentes = 0
    faltas_por_curso: dict[str, int] = {}
    cursor = db.attendance.find(
        {
            "class_id": class_id,
            "date": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0, "records": 1, "course_id": 1, "date": 1},
    )
    async for att in cursor:
        cid = att.get("course_id")
        for rec in att.get("records") or []:
            if rec.get("student_id") != student_id:
                continue
            # Pula registros de dependência
            if rec.get("dependency_id"):
                continue
            total += 1
            status = (rec.get("status") or "").lower()
            if status in ("presente", "present", "p"):
                presentes += 1
            elif status in ("falta", "faltou", "absent", "f", "ausente"):
                if cid:
                    faltas_por_curso[cid] = faltas_por_curso.get(cid, 0) + 1

    freq_pct = round(100.0 * presentes / total, 2) if total > 0 else None
    return {
        "total_records": total,
        "present": presentes,
        "absent": total - presentes,
        "frequencia_pct": freq_pct,
        "absences_by_course": faltas_por_curso,
    }


async def build_student_bulletin(
    db,
    *,
    student_id: str,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Monta o boletim canônico do aluno no ano.

    Shape:
        {
          bulletin_version, student, academic_year, primary_school, primary_class,
          is_composite, composite_segments: [
            {period_index, class, school, period_start, period_end, source,
             governing_event_id, governing_event_type,
             components: [{course_id, course_name, atendimento_programa, optativo,
                           is_dependency: false, bimesters_owned: [...],
                           grades: {b1, b2, b3, b4, rec_s1, rec_s2, recovery, final_average, status}}],
             attendance_summary: {...}}
          ],
          dependency_components: [...],   // lista paralela (sem afetar regular)
          warnings: [...]
        }

    Read-only puro. NÃO persiste nada.
    """
    student = await db.students.find_one(
        {"id": student_id},
        {"_id": 0, "id": 1, "full_name": 1, "registration_number": 1,
         "class_id": 1, "school_id": 1, "mantenedora_id": 1, "dependency_mode": 1},
    )
    if not student:
        return {
            "bulletin_version": BULLETIN_VERSION,
            "student": None,
            "academic_year": academic_year,
            "is_composite": False,
            "composite_segments": [],
            "dependency_components": [],
            "warnings": [{"code": "STUDENT_NOT_FOUND"}],
        }

    closure = await compute_composite_closure(
        db,
        student_id=student_id,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
    )
    periods: list[dict] = closure.get("periods", [])
    bimesters: list[dict] = closure.get("bimesters", [])

    warnings: list[dict] = []
    if not periods:
        warnings.append({"code": "NO_PERIODS",
                         "message": "Aluno sem matrícula ativa nem evento acadêmico no ano."})

    # Resolve metadados de turma/escola "primária" — aqui usamos o ÚLTIMO período
    # (turma vigente ao final do ano) como referência de cabeçalho.
    primary_class: dict = {}
    primary_school: dict = {}
    if periods:
        last_p = periods[-1]
        primary_class = await _resolve_class_info(db, last_p.get("class_id"))
        primary_school = await _resolve_school_info(
            db, primary_class.get("school_id") or last_p.get("school_id")
        )

    # Build composite segments
    composite_segments: list[dict] = []
    for p in periods:
        cls = await _resolve_class_info(db, p["class_id"])
        sch = await _resolve_school_info(db, cls.get("school_id") or p.get("school_id"))
        courses = await _resolve_courses_for_class(db, p["class_id"])
        course_ids = [c.get("id") for c in courses if c.get("id")]

        # Notas regulares dessa turma para o aluno
        grades = await _grades_for_segment(
            db,
            student_id=student_id,
            academic_year=academic_year,
            class_id=p["class_id"],
            course_ids=course_ids,
        )
        grades_by_course: dict[str, dict] = {g.get("course_id"): g for g in grades if g.get("course_id")}

        # Bimestres "donos" deste período (atribuídos pela closure)
        owned = _bimesters_owned_by_period(p["period_index"], bimesters)

        # Frequência do segmento
        attendance_summary = await _attendance_summary_for_segment(
            db,
            student_id=student_id,
            class_id=p["class_id"],
            period_start=p["period_start"],
            period_end=p["period_end"],
        )

        components: list[dict] = []
        # Inclui TODOS os cursos da turma (mesmo sem nota — frontend exibe "—")
        seen = set()
        for c in courses:
            cid = c.get("id")
            if not cid:
                continue
            seen.add(cid)
            g = grades_by_course.get(cid) or {}
            components.append({
                "course_id": cid,
                "course_name": c.get("name") or "(sem nome)",
                "atendimento_programa": c.get("atendimento_programa") or "regular",
                "optativo": bool(c.get("optativo", False)),
                "is_dependency": False,
                "bimesters_owned_by_this_period": owned,
                "grades": {
                    "b1": g.get("b1"),
                    "b2": g.get("b2"),
                    "b3": g.get("b3"),
                    "b4": g.get("b4"),
                    "rec_s1": g.get("rec_s1"),
                    "rec_s2": g.get("rec_s2"),
                    "recovery": g.get("recovery"),
                    "final_average": g.get("final_average"),
                    "status": g.get("status"),
                } if g else {
                    "b1": None, "b2": None, "b3": None, "b4": None,
                    "rec_s1": None, "rec_s2": None, "recovery": None,
                    "final_average": None, "status": None,
                },
                "absences_in_period": attendance_summary["absences_by_course"].get(cid, 0),
            })

        # Notas em cursos NÃO listados na turma (ex.: aluno tem nota em curso desativado)
        for cid, g in grades_by_course.items():
            if cid in seen:
                continue
            components.append({
                "course_id": cid,
                "course_name": g.get("course_name") or "(curso desconhecido)",
                "atendimento_programa": "regular",
                "optativo": False,
                "is_dependency": False,
                "bimesters_owned_by_this_period": owned,
                "grades": {
                    "b1": g.get("b1"), "b2": g.get("b2"),
                    "b3": g.get("b3"), "b4": g.get("b4"),
                    "rec_s1": g.get("rec_s1"), "rec_s2": g.get("rec_s2"),
                    "recovery": g.get("recovery"),
                    "final_average": g.get("final_average"),
                    "status": g.get("status"),
                },
                "absences_in_period": attendance_summary["absences_by_course"].get(cid, 0),
            })

        composite_segments.append({
            "period_index": p["period_index"],
            "class": cls,
            "school": sch,
            "period_start": p["period_start"],
            "period_end": p["period_end"],
            "source": p["source"],
            "governing_event_id": p.get("governing_event_id"),
            "governing_event_type": p.get("governing_event_type"),
            "governing_effective_date": p.get("governing_effective_date"),
            "bimesters_owned": owned,
            "components": components,
            "attendance_summary": attendance_summary,
        })

        # Detecta duplicidade de nome de curso no segmento (não remove,
        # apenas marca + agrega warning). Boletim é espelho fiel do cadastro;
        # saneamento é responsabilidade do admin via endpoint diagnóstico.
        warnings.extend(
            _flag_duplicate_course_names(
                components,
                segment_class_id=p["class_id"],
                period_index=p["period_index"],
            )
        )

    # Componentes de dependência — paralelo, sem afetar regular
    dep_grades = await _dependency_grades_for_student(
        db, student_id=student_id, academic_year=academic_year
    )
    dependency_components: list[dict] = []
    for g in dep_grades:
        dependency_components.append({
            "course_id": g.get("course_id"),
            "course_name": g.get("course_name") or "(componente em dependência)",
            "is_dependency": True,
            "dependency_id": g.get("dependency_id"),
            "class_id_origin": g.get("class_id"),
            "grades": {
                "b1": g.get("b1"), "b2": g.get("b2"),
                "b3": g.get("b3"), "b4": g.get("b4"),
                "final_average": g.get("final_average"),
                "status": g.get("status"),
            },
        })

    return {
        "bulletin_version": BULLETIN_VERSION,
        "student": {
            "id": student["id"],
            "full_name": student.get("full_name"),
            "registration_number": student.get("registration_number"),
            "dependency_mode": student.get("dependency_mode") or "none",
        },
        "academic_year": academic_year,
        "primary_school": primary_school,
        "primary_class": primary_class,
        "is_composite": closure.get("is_composite", False),
        "composite_segments": composite_segments,
        "dependency_components": dependency_components,
        "warnings": warnings,
    }
