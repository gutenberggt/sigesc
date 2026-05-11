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

from utils.curriculum_resolver import resolve_curriculum
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
         "class_id": 1, "school_id": 1, "mantenedora_id": 1, "dependency_mode": 1,
         "student_series": 1},
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

        # >>> Curriculum Resolver (evidence-first) — fonte ÚNICA de componentes.
        # Não monta currículo manualmente. Não duplica. Não inventa fallback amplo.
        cls_full = await db.classes.find_one(
            {"id": p["class_id"]},
            {"_id": 0, "id": 1, "course_ids": 1, "atendimento_programa": 1,
             "nivel_ensino": 1, "education_level": 1, "grade_level": 1,
             "school_id": 1, "academic_year": 1},
        ) or {}
        resolution = await resolve_curriculum(
            db,
            student_id=student_id,
            class_id=p["class_id"],
            academic_year=academic_year,
            class_info=cls_full,
            student_info={
                "id": student_id,
                "student_series": student.get("student_series"),
                "class_id": student.get("class_id"),
            },
            atendimento_programa_filter=cls_full.get("atendimento_programa"),
        )
        resolved_components = resolution["components"]
        warnings.extend(resolution["warnings"])
        course_ids = [c["course_id"] for c in resolved_components if c.get("course_id")]

        # Notas regulares dessa turma para o aluno (restringe aos course_ids resolvidos)
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

        # Componentes do segmento = resolução canônica (mesma para PDF/UI/render_jobs)
        components: list[dict] = []
        for rc in resolved_components:
            cid = rc["course_id"]
            g = grades_by_course.get(cid) or {}
            components.append({
                "course_id": cid,
                "course_name": rc.get("course_name") or "(sem nome)",
                "atendimento_programa": rc.get("atendimento_programa") or "regular",
                "optativo": bool(rc.get("optativo", False)),
                "is_dependency": False,
                "bimesters_owned_by_this_period": owned,
                # Metadados do resolver (observabilidade)
                "resolution_source": rc.get("source"),
                "resolution_evidence_score": rc.get("evidence_score", 0),
                "resolution_dedupe_reason": rc.get("dedupe_kept_reason"),
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
            # Debug do resolver (observabilidade por segmento)
            "resolution_debug": resolution["debug"],
        })


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
        "bulletin_type": "regular",
    }


async def build_student_dependency_bulletin(
    db,
    *,
    student_id: str,
    target_class_id: str,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Monta o boletim de DEPENDÊNCIA para a turma `target_class_id`.

    Diferenças do boletim regular:
      - Inclui APENAS os `course_id`s vinculados a dependências ATIVAS do aluno
        nessa turma específica (collection `student_dependencies`).
      - Cálculo de aprovação considera SOMENTE esses componentes (regras
        pedagógicas da mantenedora — média/frequência — aplicadas no escopo).
      - Frequência computada apenas para os componentes da dependência.
      - Não consolida periods/segments do diário regular do aluno;
        a turma de dependência é independente da temporalidade do diário
        de matrícula regular.

    Shape semelhante ao boletim regular para reuso de UI/PDF, mas com:
      - `bulletin_type: "dependency"`
      - `is_composite: false`
      - `composite_segments` com 1 segmento (a própria turma de dep).
      - `dependency_components` herda os mesmos componentes (compatibilidade
        com renderização de "Componentes em dependência" do PDF antigo).
    """
    student = await db.students.find_one(
        {"id": student_id},
        {"_id": 0, "id": 1, "full_name": 1, "registration_number": 1,
         "class_id": 1, "school_id": 1, "mantenedora_id": 1, "dependency_mode": 1,
         "student_series": 1},
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
            "bulletin_type": "dependency",
            "target_class_id": target_class_id,
        }

    target_class = await _resolve_class_info(db, target_class_id)
    if not target_class.get("id"):
        return {
            "bulletin_version": BULLETIN_VERSION,
            "student": {
                "id": student["id"],
                "full_name": student.get("full_name"),
                "registration_number": student.get("registration_number"),
                "dependency_mode": student.get("dependency_mode") or "none",
            },
            "academic_year": academic_year,
            "is_composite": False,
            "composite_segments": [],
            "dependency_components": [],
            "warnings": [{"code": "DEPENDENCY_CLASS_NOT_FOUND",
                          "class_id": target_class_id}],
            "bulletin_type": "dependency",
            "target_class_id": target_class_id,
        }
    target_school = await _resolve_school_info(db, target_class.get("school_id"))

    # Dependências ATIVAS do aluno NESSA turma específica
    active_deps: list[dict] = []
    async for d in db.student_dependencies.find(
        {
            "student_id": student_id,
            "class_id": target_class_id,
            "academic_year": academic_year,
            "status": "active",
        },
        {"_id": 0},
    ):
        active_deps.append(d)

    warnings: list[dict] = []
    if not active_deps:
        warnings.append({
            "code": "NO_ACTIVE_DEPENDENCIES",
            "class_id": target_class_id,
            "message": (
                "Aluno não possui dependências ativas nesta turma para o ano. "
                "Cadastre antes de gerar boletim de dependência."
            ),
        })

    dep_course_ids = sorted({d["course_id"] for d in active_deps if d.get("course_id")})

    # Hidrata cursos
    courses_map: dict[str, dict] = {}
    if dep_course_ids:
        async for c in db.courses.find(
            {"id": {"$in": dep_course_ids}},
            {"_id": 0, "id": 1, "name": 1, "atendimento_programa": 1, "optativo": 1},
        ):
            courses_map[c["id"]] = c

    # Período do boletim de dep = ano letivo completo na turma alvo.
    # Não há composite (dep é entidade própria, fora da temporalidade do regular).
    period_start = f"{academic_year}-01-01"
    period_end = f"{academic_year}-12-31"

    # Notas de dependência (filtradas) — `grades` com `dependency_id`
    dep_ids = {d.get("id") for d in active_deps}
    grades_by_course: dict[str, dict] = {}
    async for g in db.grades.find(
        {
            "student_id": student_id,
            "academic_year": academic_year,
            "course_id": {"$in": dep_course_ids} if dep_course_ids else "__none__",
            "dependency_id": {"$in": list(dep_ids)} if dep_ids else "__none__",
        },
        {"_id": 0},
    ):
        if g.get("course_id"):
            grades_by_course[g["course_id"]] = g

    # Frequência: SÓ chamadas dos course_ids da dep nessa turma
    absences_by_course: dict[str, int] = {}
    total_records = 0
    presentes = 0
    if dep_course_ids:
        async for att in db.attendance.find(
            {
                "class_id": target_class_id,
                "course_id": {"$in": dep_course_ids},
                "date": {"$gte": period_start, "$lte": period_end},
            },
            {"_id": 0, "records": 1, "course_id": 1},
        ):
            cid = att.get("course_id")
            for rec in att.get("records") or []:
                if rec.get("student_id") != student_id:
                    continue
                total_records += 1
                st = (rec.get("status") or "").lower()
                if st in ("presente", "present", "p"):
                    presentes += 1
                elif st in ("falta", "faltou", "absent", "f", "ausente"):
                    if cid:
                        absences_by_course[cid] = absences_by_course.get(cid, 0) + 1
    freq_pct = round(100.0 * presentes / total_records, 2) if total_records > 0 else None
    attendance_summary = {
        "total_records": total_records,
        "present": presentes,
        "absent": total_records - presentes,
        "frequency_pct": freq_pct,
        "absences_by_course": absences_by_course,
    }

    # Monta componentes — só os de dependência, com metadados de origem
    components: list[dict] = []
    for cid in dep_course_ids:
        doc = courses_map.get(cid) or {}
        dep = next((d for d in active_deps if d.get("course_id") == cid), {})
        g = grades_by_course.get(cid) or {}
        components.append({
            "course_id": cid,
            "course_name": doc.get("name") or "(componente em dependência)",
            "atendimento_programa": doc.get("atendimento_programa") or "regular",
            "optativo": bool(doc.get("optativo", False)),
            "is_dependency": True,
            "dependency_id": dep.get("id"),
            "origin_academic_year": dep.get("origin_academic_year"),
            "origin_class_id": dep.get("origin_class_id"),
            "bimesters_owned_by_this_period": [1, 2, 3, 4],
            "grades": {
                "b1": g.get("b1"), "b2": g.get("b2"),
                "b3": g.get("b3"), "b4": g.get("b4"),
                "rec_s1": g.get("rec_s1"), "rec_s2": g.get("rec_s2"),
                "recovery": g.get("recovery"),
                "final_average": g.get("final_average"),
                "status": g.get("status"),
            } if g else {
                "b1": None, "b2": None, "b3": None, "b4": None,
                "rec_s1": None, "rec_s2": None, "recovery": None,
                "final_average": None, "status": None,
            },
            "absences_in_period": absences_by_course.get(cid, 0),
        })

    segment = {
        "period_index": 1,
        "class": target_class,
        "school": target_school,
        "period_start": period_start,
        "period_end": period_end,
        "source": "dependency",
        "bimesters_owned": [1, 2, 3, 4],
        "components": components,
        "attendance_summary": attendance_summary,
    }

    return {
        "bulletin_version": BULLETIN_VERSION,
        "student": {
            "id": student["id"],
            "full_name": student.get("full_name"),
            "registration_number": student.get("registration_number"),
            "dependency_mode": student.get("dependency_mode") or "none",
        },
        "academic_year": academic_year,
        "primary_school": target_school,
        "primary_class": target_class,
        "is_composite": False,
        "composite_segments": [segment] if components else [],
        "dependency_components": components,  # compat com PDF antigo
        "warnings": warnings,
        "bulletin_type": "dependency",
        "target_class_id": target_class_id,
    }


async def list_student_bulletins(
    db,
    *,
    student_id: str,
    academic_year: int,
) -> list[dict]:
    """Catálogo de boletins disponíveis para o aluno no ano.

    Retorno:
      [
        {type: 'regular', class_id, class_name, school_id, school_name, label},
        {type: 'dependency', class_id, class_name, school_id, school_name,
         label, course_ids: [...]},
        ...
      ]

    Regras:
      - `dependency_only`: catálogo NÃO inclui boletim regular.
      - `with_dependency`: catálogo inclui boletim regular + 1 por turma de dep.
      - `none`: catálogo inclui APENAS boletim regular.
    """
    student = await db.students.find_one(
        {"id": student_id},
        {"_id": 0, "id": 1, "full_name": 1, "dependency_mode": 1, "class_id": 1},
    )
    if not student:
        return []

    mode = student.get("dependency_mode") or "none"
    catalog: list[dict] = []

    # Boletim regular (todos exceto dependency_only)
    if mode != "dependency_only" and student.get("class_id"):
        cls = await _resolve_class_info(db, student["class_id"])
        sch = await _resolve_school_info(db, cls.get("school_id"))
        catalog.append({
            "type": "regular",
            "class_id": cls.get("id"),
            "class_name": cls.get("name"),
            "school_id": sch.get("id"),
            "school_name": sch.get("name"),
            "label": f"Boletim Regular · {cls.get('name') or '(sem turma)'}",
        })

    # Boletim(ns) de dependência — agrupado por class_id
    dep_classes: dict[str, list[str]] = {}
    async for d in db.student_dependencies.find(
        {
            "student_id": student_id,
            "academic_year": academic_year,
            "status": "active",
        },
        {"_id": 0, "class_id": 1, "course_id": 1},
    ):
        cid = d.get("class_id")
        coid = d.get("course_id")
        if not cid or not coid:
            continue
        dep_classes.setdefault(cid, []).append(coid)

    for class_id, course_ids in dep_classes.items():
        cls = await _resolve_class_info(db, class_id)
        sch = await _resolve_school_info(db, cls.get("school_id"))
        catalog.append({
            "type": "dependency",
            "class_id": class_id,
            "class_name": cls.get("name"),
            "school_id": sch.get("id"),
            "school_name": sch.get("name"),
            "label": f"Boletim Dependência · {cls.get('name') or class_id}",
            "course_ids": sorted(set(course_ids)),
        })

    return catalog
