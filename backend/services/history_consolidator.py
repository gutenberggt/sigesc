"""Consolidador do Histórico Escolar — coleta TODA a vida acadêmica do aluno
no SIGESC e monta um dict no formato esperado por
`pdf.historico_escolar.generate_historico_escolar_pdf`.

Princípio: a infraestrutura do sistema é fonte da verdade. O PDF é a
representação. Cada record consolidado é deduzido de:

  - `enrollments[]` por (student, academic_year, class)
  - `grades[]` agregadas por (student, year, course)
  - `attendance[]` agregada por (student, year, class)
  - `student_dependencies[]` (dependências cursadas)
  - `student_history.records[]` (escolas anteriores fora do SIGESC,
    marcadas com `manual: True`)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from utils.school_resolution import resolve_school_at

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Util — mapeia grade_level genérico para o slot do template ("1º", ..., "9º")
# ---------------------------------------------------------------------------
_SERIE_RE = re.compile(r"(\d)\s*[ºª°o]?\s*(ano|serie|série)?", re.IGNORECASE)


def _grade_level_to_slot(grade_level: Optional[str]) -> Optional[str]:
    if not grade_level:
        return None
    gl = grade_level.strip().lower()
    if "eja" in gl or "infantil" in gl or "pré" in gl or "pre-" in gl or "berç" in gl:
        return None  # template é só Fundamental I+II
    m = _SERIE_RE.search(gl)
    if not m:
        return None
    n = m.group(1)
    if n not in "123456789":
        return None
    return f"{n}º"


def _classify_resultado(*, enrollment_status: str, grade_avg: Optional[float],
                        freq_pct: Optional[float], media_aprovacao: float,
                        freq_min: float = 75.0) -> str:
    """Determina APROVADO/REPROVADO/EM CURSO/TRANSFERIDO/CANCELADO."""
    s = (enrollment_status or "").lower()
    if s in ("active", "ativo"):
        return "EM CURSO"
    if s in ("transferred", "transferido"):
        return "TRANSFERIDO"
    if s in ("cancelled", "canceled", "cancelado", "inactive", "dropout"):
        return "CANCELADO"
    # finalizado / completed / archived → calcula
    if grade_avg is None and freq_pct is None:
        return ""  # sem dados — deixa em branco
    if grade_avg is not None and grade_avg < media_aprovacao:
        return "REPROVADO"
    if freq_pct is not None and freq_pct < freq_min:
        return "REPROVADO"
    return "APROVADO"


# ---------------------------------------------------------------------------
async def _aggregate_grades(db, *, student_id: str, academic_year: int,
                            course_ids: list[str]) -> dict[str, float]:
    """Retorna {course_name: media_anual} para o aluno/ano.

    Considera os campos flat `b1..b4` do GradeCreate. Calcula média simples
    dos bimestres COM nota lançada (ignora None).
    """
    if not course_ids:
        return {}
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(200)
    cname = {c["id"]: c.get("name", "") for c in courses}

    grades = await db.grades.find(
        {"student_id": student_id, "academic_year": academic_year,
         "course_id": {"$in": course_ids}},
        {"_id": 0}
    ).to_list(500)

    result: dict[str, float] = {}
    for g in grades:
        vals = [g.get(k) for k in ("b1", "b2", "b3", "b4")]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if not vals:
            continue
        media = round(sum(vals) / len(vals), 1)
        n = cname.get(g.get("course_id"))
        if n:
            result[n] = media
    return result


async def _aggregate_attendance(db, *, student_id: str, class_id: str,
                                academic_year: int) -> Optional[float]:
    """Retorna percentual de frequência consolidado (1 falta = 1 dia, mesmo padrão da declaração)."""
    atts = await db.attendance.find(
        {"class_id": class_id, "academic_year": academic_year,
         "records.student_id": student_id},
        {"_id": 0}
    ).to_list(None)
    if not atts:
        return None
    falta_dates = set()
    present_dates = set()
    for a in atts:
        d = (a.get("date") or "")[:10]
        if not d:
            continue
        for sr in a.get("records") or []:
            if sr.get("student_id") != student_id:
                continue
            status = (sr.get("status") or "").upper()
            if status in ("F", "A", "ABSENT"):
                falta_dates.add(d)
            else:
                present_dates.add(d)
            break
    total = len(falta_dates) + len(present_dates)
    if total == 0:
        return None
    return round(100.0 * len(present_dates) / total, 1)


# ---------------------------------------------------------------------------
async def build_consolidated_history(db, *, student_id: str,
                                     media_aprovacao: float = 6.0) -> dict:
    """Retorna o `history` dict pronto para o PDF.

    Estrutura:
    {
        "student_id": str,
        "media_aprovacao": float,
        "observations": str,
        "records": [ ... ],  # 1 por (year, serie) consolidado + manuais
        "consolidated_meta": {
            "from_enrollments": int,
            "from_manual_history": int,
            "years_covered": [int]
        },
    }
    """
    # 1) Enrollments do aluno em TODOS os anos
    enrollments = await db.enrollments.find(
        {"student_id": student_id}, {"_id": 0}
    ).to_list(200)

    # Agrupa por (academic_year, class_id) — mantém o enrollment com
    # status preferencialmente em ['active','transferred','archived','completed']
    by_key: dict[tuple[int, str], dict] = {}
    for e in enrollments:
        year = int(e.get("academic_year") or 0)
        cid = e.get("class_id") or ""
        if not year or not cid:
            continue
        prev = by_key.get((year, cid))
        if prev is None:
            by_key[(year, cid)] = e
        else:
            # Preserva o mais recente por created_at
            if (e.get("created_at") or "") > (prev.get("created_at") or ""):
                by_key[(year, cid)] = e

    # 2) Para cada (year, class), monta um record consolidado
    records: list[dict] = []
    years_covered: set[int] = set()
    class_ids_cache: dict[str, dict] = {}
    school_cache: dict[str, dict] = {}

    for (year, class_id), enr in sorted(by_key.items()):
        if class_id not in class_ids_cache:
            ci = await db.classes.find_one({"id": class_id}, {"_id": 0})
            class_ids_cache[class_id] = ci or {}
        class_info = class_ids_cache[class_id]
        if not class_info:
            continue
        # [Fase 1.5] Atribuição TEMPORAL de escola por ano letivo. Se a turma
        # sofreu re-homing institucional, `class_info.school_id` aponta para o
        # DESTINO atual — atribuir anos passados a ela falsearia o Histórico
        # Escolar (documento legal). Resolve via `school_history[]` tomando como
        # referência o INÍCIO do ano letivo (escola onde o ano foi conduzido).
        # Sem histórico → `school_id` atual (turma nunca transferida).
        school_id = resolve_school_at(
            class_info.get("school_history"),
            f"{year}-01-01",
            fallback_school_id=class_info.get("school_id"),
        )
        if school_id and school_id not in school_cache:
            school_cache[school_id] = await db.schools.find_one(
                {"id": school_id}, {"_id": 0}
            ) or {}
        school = school_cache.get(school_id, {})

        serie_slot = _grade_level_to_slot(class_info.get("grade_level"))

        # Grades consolidadas por componente
        course_ids = class_info.get("course_ids") or []
        grades_map = await _aggregate_grades(
            db, student_id=student_id,
            academic_year=year, course_ids=course_ids
        )

        # Frequência %
        freq_pct = await _aggregate_attendance(
            db, student_id=student_id,
            class_id=class_id, academic_year=year
        )

        # Média geral (sanity)
        if grades_map:
            avg = round(sum(grades_map.values()) / len(grades_map), 1)
        else:
            avg = None

        resultado = _classify_resultado(
            enrollment_status=enr.get("status") or "",
            grade_avg=avg, freq_pct=freq_pct,
            media_aprovacao=media_aprovacao,
        )

        records.append({
            "serie": serie_slot or "",
            "grades": grades_map,
            "carga_horaria": class_info.get("carga_horaria_anual") or "",
            "resultado": resultado,
            "ano_letivo": str(year),
            "escola": (school.get("name") or "").strip(),
            "frequencia": freq_pct if freq_pct is not None else "",
            "raw_grade_level": class_info.get("grade_level") or "",
            "_consolidated": True,
            "_class_id": class_id,
            "_school_id": school_id,
            "_active": (enr.get("status") or "") in ("active", "Ativo"),
        })
        years_covered.add(year)

    # 2.1) DEDUP por (ano_letivo, série): troca de turma no mesmo ano gera UM único
    # registro (documento legal não pode repetir a série). Une as notas de todas as
    # turmas do ano e usa a MAIOR frequência (cópias idênticas entre turmas) — evita
    # dupla contagem. Mantém rastreabilidade em `_merged_class_ids`.
    from collections import OrderedDict
    _grouped = OrderedDict()
    for r in records:
        _grouped.setdefault((r["ano_letivo"], r["serie"]), []).append(r)

    def _merge_year_serie(recs):
        if len(recs) == 1:
            recs[0]["_merged_class_ids"] = [recs[0]["_class_id"]]
            return recs[0]
        # base: matrícula ativa, senão a com mais notas
        best = max(recs, key=lambda r: (1 if r.get("_active") else 0, len(r.get("grades") or {})))
        merged = dict(best)
        g = {}
        for r in recs:
            g.update(r.get("grades") or {})
        merged["grades"] = g
        freqs = [r["frequencia"] for r in recs if isinstance(r["frequencia"], (int, float))]
        if freqs:
            merged["frequencia"] = max(freqs)
        if g:
            merged_avg = round(sum(g.values()) / len(g), 1)
            merged["resultado"] = _classify_resultado(
                enrollment_status="active" if any(r.get("_active") for r in recs) else "",
                grade_avg=merged_avg, freq_pct=(merged["frequencia"] if isinstance(merged["frequencia"], (int, float)) else None),
                media_aprovacao=media_aprovacao,
            )
        merged["_merged_class_ids"] = [r["_class_id"] for r in recs]
        return merged

    records = [_merge_year_serie(v) for v in _grouped.values()]

    # 3) Junta com registros manuais (escolas anteriores fora do SIGESC).
    manual = await db.student_history.find_one(
        {"student_id": student_id}, {"_id": 0}
    )
    manual_records = []
    if manual and manual.get("records"):
        for m in manual["records"]:
            # Evita duplicar series já cobertas pela consolidação
            slot = m.get("serie")
            if slot and any(r["serie"] == slot for r in records):
                continue
            mr = dict(m)
            mr["_consolidated"] = False
            manual_records.append(mr)

    records.extend(manual_records)

    return {
        "student_id": student_id,
        "media_aprovacao": media_aprovacao,
        "observations": (manual or {}).get("observations") or "",
        "custom_diversificada": (manual or {}).get("custom_diversificada") or [],
        "records": records,
        "consolidated_meta": {
            "from_enrollments": len(by_key),
            "from_manual_history": len(manual_records),
            "years_covered": sorted(years_covered),
        },
    }
