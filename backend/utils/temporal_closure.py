"""
Fechamento Temporal Composto — Passo 3 da governança temporal pedagógica.

[Fev/2026] Implementa o §11 de `/app/docs/ACADEMIC_EVENT_CONTRACT.md`:

    "Fechamento anual | Cada turma fecha **seus** períodos;
     aluno movimentado tem fechamento composto"

PRINCÍPIO ARQUITETURAL CRÍTICO:
========================================================================
O fechamento de um aluno NUNCA é monolítico. Quando há eventos
acadêmicos (transferência, remanejamento, reclassificação,
progressão parcial), o aluno cumpre janelas distintas em turmas
distintas. Cada turma fecha apenas o intervalo em que foi dona
do registro pedagógico.

Esta camada é a INVERSA da `academic_event_lens.resolve_student_ownership`:
    - Lens: "(student, class, date) → editable?"
    - Closure: "(student, year) → list[(class, [start, end])]"

Tudo passa por `compute_temporal_periods(...)`. Nenhum router deve
montar janelas de fechamento manualmente.
========================================================================

API canônica:

    periods = await compute_temporal_periods(
        db,
        student_id=sid,
        academic_year=2026,
        mantenedora_id=tid,
    )
    # periods = [
    #   {
    #     "period_index": 0,
    #     "class_id": "...", "course_id": None,
    #     "school_id": "...",
    #     "period_start": "2026-02-01",
    #     "period_end":   "2026-08-14",
    #     "source": "origin" | "destination" | "sole",
    #     "governing_event_id": "..." | None,
    #     "governing_event_type": "transfer" | None,
    #   }, ...
    # ]

Regra de propriedade do bimestre:
    Um bimestre B com [start, end] pertence ao período P se P contém
    a data de FECHAMENTO do bimestre (ou seja, B.end). Bimestres
    cujo final cai antes de qualquer período do aluno são órfãos
    (caso patológico — aluno saiu antes do começo do bimestre).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from utils.academic_event_lens import (
    _get_institutional_tz,  # type: ignore[attr-defined]
    _to_date,                # type: ignore[attr-defined]
    pick_governing_event,
)

logger = logging.getLogger(__name__)

CLOSURE_VERSION = "1"


# ===========================================================================
# Helpers
# ===========================================================================
async def _resolve_year_window(
    db, *, mantenedora_id: Optional[str], academic_year: int
) -> tuple[date, date]:
    """Resolve [year_start, year_end] do calendário letivo, com fallback Jan 1 → Dez 31."""
    cal = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year}, {"_id": 0}
    )
    if cal:
        # Tenta usar bimestre_1_inicio e bimestre_4_fim como envelope.
        b1_start = cal.get("bimestre_1_inicio")
        b4_end = cal.get("bimestre_4_fim")
        if b1_start and b4_end:
            try:
                return date.fromisoformat(b1_start[:10]), date.fromisoformat(b4_end[:10])
            except (ValueError, TypeError):
                pass

    # Fallback: ano civil completo.
    return date(academic_year, 1, 1), date(academic_year, 12, 31)


async def _load_bimester_calendar(
    db, *, academic_year: int
) -> list[dict]:
    """Retorna lista ordenada de bimestres com {bimester, start, end}.

    Se calendário não configurado, retorna lista vazia (caller decide fallback).
    """
    cal = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year}, {"_id": 0}
    )
    if not cal:
        return []
    out: list[dict] = []
    for i in (1, 2, 3, 4):
        s = cal.get(f"bimestre_{i}_inicio")
        e = cal.get(f"bimestre_{i}_fim")
        if not s or not e:
            continue
        try:
            out.append({
                "bimester": i,
                "start": date.fromisoformat(s[:10]),
                "end": date.fromisoformat(e[:10]),
            })
        except (ValueError, TypeError):
            continue
    return out


async def _resolve_student_class_default(
    db, *, student_id: str, academic_year: int
) -> Optional[str]:
    """Resolve a turma "padrão" do aluno no ano (matrícula ativa).

    Usado quando o aluno NÃO tem nenhum evento acadêmico no ano —
    o período único é a turma onde ele está matriculado.
    """
    # 1. Tenta enrollment ativo no ano
    enr = await db.enrollments.find_one(
        {
            "student_id": student_id,
            "academic_year": academic_year,
            "status": {"$in": ["active", "approved", "matricula_ativa"]},
        },
        {"_id": 0, "class_id": 1, "school_id": 1},
        sort=[("created_at", -1)],
    )
    if enr and enr.get("class_id"):
        return enr["class_id"]

    # 2. Fallback: students.class_id (snapshot do aluno)
    stu = await db.students.find_one(
        {"id": student_id}, {"_id": 0, "class_id": 1}
    )
    if stu and stu.get("class_id"):
        return stu["class_id"]
    return None


# ===========================================================================
# API canônica
# ===========================================================================
async def compute_temporal_periods(
    db,
    *,
    student_id: str,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
) -> list[dict]:
    """Calcula a lista ordenada de períodos de propriedade do aluno no ano.

    A lista é cronológica e cobre [year_start, year_end] sem gaps.

    Quando o aluno não tem nenhum evento acadêmico aprovado e válido no ano,
    a lista contém UM único período = (turma_atual_do_aluno, [year_start, year_end]).

    Quando há eventos, cada `effective_date` divide a linha do tempo. Em cada
    fatia escolhemos o governante via `pick_governing_event` (precedência fixa V1).

    Sem matrícula ativa e sem eventos → retorna lista vazia.
    """
    tz = await _get_institutional_tz(db, mantenedora_id)
    year_start, year_end = await _resolve_year_window(
        db, mantenedora_id=mantenedora_id, academic_year=academic_year
    )

    # Eventos aprovados do aluno NO ANO (qualquer turma envolvida).
    flt: dict = {
        "student_id": student_id,
        "approval_status": "approved",
        "superseded_by_event_id": None,
        "academic_year": academic_year,
    }
    events = await db.academic_events.find(flt, {"_id": 0}).to_list(200)

    # Fast-path: sem eventos, retorna 1 período sole na turma matrícula.
    if not events:
        default_class = await _resolve_student_class_default(
            db, student_id=student_id, academic_year=academic_year
        )
        if not default_class:
            return []
        return [{
            "period_index": 0,
            "class_id": default_class,
            "course_id": None,
            "school_id": None,
            "period_start": str(year_start),
            "period_end": str(year_end),
            "source": "sole",
            "governing_event_id": None,
            "governing_event_type": None,
            "governing_effective_date": None,
        }]

    # Coleta breakpoints únicos = todas as effective_dates dentro do ano
    breakpoints: set[date] = {year_start, year_end + timedelta(days=1)}
    for ev in events:
        try:
            eff = _to_date(ev.get("effective_date"), tz)
        except (ValueError, TypeError):
            continue
        # Clamp ao ano
        if eff < year_start:
            eff = year_start
        elif eff > year_end + timedelta(days=1):
            eff = year_end + timedelta(days=1)
        breakpoints.add(eff)

    sorted_bp = sorted(breakpoints)
    raw_segments: list[tuple[date, date]] = []
    for i in range(len(sorted_bp) - 1):
        seg_start = sorted_bp[i]
        seg_end = sorted_bp[i + 1] - timedelta(days=1)
        if seg_end < seg_start:
            continue
        raw_segments.append((seg_start, seg_end))

    # Para cada segmento, escolhe a turma proprietária.
    periods: list[dict] = []
    default_class = await _resolve_student_class_default(
        db, student_id=student_id, academic_year=academic_year
    )

    for idx, (seg_start, seg_end) in enumerate(raw_segments):
        # Eventos cuja effective_date <= seg_start estão "ativos" no segmento.
        active_events: list[dict] = []
        for ev in events:
            try:
                eff = _to_date(ev.get("effective_date"), tz)
            except (ValueError, TypeError):
                continue
            if eff <= seg_start:
                active_events.append(ev)

        governing = pick_governing_event(active_events) if active_events else None

        if governing:
            class_id = governing.get("destination_class_id")
            school_id = governing.get("destination_school_id")
            source = "destination"
        else:
            # Pré-evento — destino da origem (ou turma default)
            # Se há eventos futuros, a "origem" do primeiro evento é a turma de partida.
            # Se algum evento tem effective_date > seg_start, usa origin_class_id dele.
            future_events = [
                ev for ev in events
                if _to_date(ev.get("effective_date"), tz) > seg_start
            ]
            if future_events:
                # Pegue o evento de menor effective_date (mais próximo) como referência
                future_events.sort(key=lambda e: e.get("effective_date") or "")
                ref = future_events[0]
                class_id = ref.get("origin_class_id")
                school_id = ref.get("origin_school_id")
                source = "origin"
            else:
                class_id = default_class
                school_id = None
                source = "sole"

        if not class_id:
            # Segmento sem dono identificável — pula
            continue

        period = {
            "period_index": idx,
            "class_id": class_id,
            "course_id": None,
            "school_id": school_id,
            "period_start": str(seg_start),
            "period_end": str(seg_end),
            "source": source,
            "governing_event_id": governing["id"] if governing else None,
            "governing_event_type": governing.get("event_type") if governing else None,
            "governing_effective_date": (
                str(_to_date(governing["effective_date"], tz)) if governing else None
            ),
        }
        periods.append(period)

    # Merge segmentos consecutivos com mesmo class_id+source+governing.
    return _merge_consecutive_periods(periods)


def _merge_consecutive_periods(periods: list[dict]) -> list[dict]:
    """Funde períodos consecutivos com mesma turma e mesmo evento governante.

    Reduz ruído quando múltiplos eventos consecutivos do mesmo aluno apontam
    para a mesma turma de destino.
    """
    if len(periods) <= 1:
        # Reindexa para garantir period_index sequencial
        for i, p in enumerate(periods):
            p["period_index"] = i
        return periods
    merged: list[dict] = [dict(periods[0])]
    for p in periods[1:]:
        last = merged[-1]
        same_owner = (
            last["class_id"] == p["class_id"]
            and last.get("governing_event_id") == p.get("governing_event_id")
            and last["source"] == p["source"]
        )
        if same_owner:
            last["period_end"] = p["period_end"]
        else:
            merged.append(dict(p))
    for i, p in enumerate(merged):
        p["period_index"] = i
    return merged


def assign_bimesters_to_periods(
    bimester_calendar: list[dict],
    periods: list[dict],
) -> list[dict]:
    """Anota cada bimestre com o período (turma) que o "fecha".

    Regra: bimestre pertence ao período cujo intervalo contém a DATA FINAL
    do bimestre. Bimestres cuja data final está fora de qualquer período
    do aluno (ex.: aluno saiu antes do encerramento) ficam com `period_index=None`.

    Retorna lista do bimester_calendar enriquecida com:
        - period_index: int | None
        - class_id: str | None
        - source: str | None
    """
    enriched: list[dict] = []
    for b in bimester_calendar:
        b_end = b["end"]
        owning: Optional[dict] = None
        for p in periods:
            try:
                p_start = date.fromisoformat(p["period_start"])
                p_end = date.fromisoformat(p["period_end"])
            except (ValueError, TypeError, KeyError):
                continue
            if p_start <= b_end <= p_end:
                owning = p
                break
        enriched.append({
            "bimester": b["bimester"],
            "start": str(b["start"]),
            "end": str(b["end"]),
            "period_index": owning["period_index"] if owning else None,
            "class_id": owning["class_id"] if owning else None,
            "source": owning["source"] if owning else None,
            "governing_event_id": (
                owning["governing_event_id"] if owning else None
            ),
        })
    return enriched


async def compute_class_window_for_student(
    db,
    *,
    student_id: str,
    class_id: str,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
) -> Optional[dict]:
    """Retorna a janela [start, end] em que `class_id` é dona do aluno no ano.

    Se a turma nunca foi dona do aluno em nenhum período → None.
    Se a turma foi dona em períodos não-contíguos → retorna o ENVELOPE
    (start = primeiro start; end = último end) e o campo `segments` com a lista exata.
    """
    periods = await compute_temporal_periods(
        db,
        student_id=student_id,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
    )
    own = [p for p in periods if p["class_id"] == class_id]
    if not own:
        return None

    own.sort(key=lambda p: p["period_start"])
    return {
        "class_id": class_id,
        "envelope_start": own[0]["period_start"],
        "envelope_end": own[-1]["period_end"],
        "segments": own,
    }


async def compute_composite_closure(
    db,
    *,
    student_id: str,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Retorna o fechamento composto completo: períodos + bimestres atribuídos.

    Estrutura canônica para Boletim/Histórico Escolar consumir.
    """
    periods = await compute_temporal_periods(
        db,
        student_id=student_id,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
    )
    bimester_cal = await _load_bimester_calendar(db, academic_year=academic_year)
    bimesters = assign_bimesters_to_periods(bimester_cal, periods)

    return {
        "closure_version": CLOSURE_VERSION,
        "student_id": student_id,
        "academic_year": academic_year,
        "periods": periods,
        "bimesters": bimesters,
        "is_composite": len(periods) > 1,
    }
