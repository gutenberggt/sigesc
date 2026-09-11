"""PDF de Objetos de Conhecimento no cutover parcial F2.7/F4.

A tela class-wide do professor já projeta ``learning_objects`` legado e
``content_entries`` canônico pela mesma SSoT. Este módulo aplica exatamente a
mesma projeção ao PDF quando a tela não possui ``assignment_id`` explícito.

Não escreve, migra ou remapeia dados. O fluxo DVD com ``assignment_id`` continua
sob o adaptador histórico específico.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from services.class_teachers import get_multi_teacher_names_for_pdf
from services.content_form_canonical_cutover import list_learning_objects_cutover


def _records_in_period(
    records: list[dict[str, Any]],
    *,
    period_start: str,
    period_end: str,
    academic_year: int,
) -> list[dict[str, Any]]:
    """Mantém apenas registros pertencentes ao bimestre solicitado."""
    filtered = [
        dict(item)
        for item in records
        if period_start <= str(item.get("date") or "")[:10] <= period_end
        and item.get("academic_year") in (None, "", academic_year, str(academic_year))
    ]
    filtered.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            int(item.get("aula_numero") or 0),
        )
    )
    return filtered


def _period_bounds(calendario: Optional[Mapping[str, Any]], bimestre: int, academic_year: int) -> tuple[str, str]:
    bk_inicio = f"bimestre_{bimestre}_inicio"
    bk_fim = f"bimestre_{bimestre}_fim"
    if calendario and calendario.get(bk_inicio) and calendario.get(bk_fim):
        return str(calendario[bk_inicio])[:10], str(calendario[bk_fim])[:10]

    periodos = {
        1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
        2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
        3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
        4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
    }
    return periodos[bimestre]


async def _dias_previstos(db, academic_year: int, period_start: str, period_end: str) -> int:
    events = await db.calendar_events.find(
        {"academic_year": {"$in": [academic_year, str(academic_year)]}},
        {"_id": 0, "event_type": 1, "start_date": 1, "end_date": 1, "is_school_day": 1},
    ).to_list(1000)

    non_school_dates: set[str] = set()
    saturday_letivo_dates: set[str] = set()
    for event in events:
        event_type = str(event.get("event_type") or "")
        ev_start = str(event.get("start_date") or "")[:10]
        ev_end = str(event.get("end_date") or ev_start)[:10]
        if not ev_start:
            continue
        try:
            cursor_date = datetime.strptime(ev_start, "%Y-%m-%d")
            final_date = datetime.strptime(ev_end, "%Y-%m-%d")
        except ValueError:
            continue
        while cursor_date <= final_date:
            ds = cursor_date.strftime("%Y-%m-%d")
            if (
                "feriado" in event_type
                or event_type == "recesso_escolar"
                or event.get("is_school_day") is False
            ):
                non_school_dates.add(ds)
            if event_type == "sabado_letivo" or event.get("is_school_day") is True:
                if cursor_date.weekday() == 5:
                    saturday_letivo_dates.add(ds)
            cursor_date += timedelta(days=1)

    total = 0
    try:
        cursor_date = datetime.strptime(period_start, "%Y-%m-%d")
        final_date = datetime.strptime(period_end, "%Y-%m-%d")
    except ValueError:
        return 0

    while cursor_date <= final_date:
        ds = cursor_date.strftime("%Y-%m-%d")
        dow = cursor_date.weekday()
        blocked = (
            dow == 6
            or ds in non_school_dates
            or (dow == 5 and ds not in saturday_letivo_dates)
        )
        if not blocked:
            total += 1
        cursor_date += timedelta(days=1)
    return total


async def generate_professor_classwide_pdf(
    learning_objects_mod,
    db,
    current_user: Mapping[str, Any],
    request: Request,
    *,
    class_id: str,
    bimestre: int,
    academic_year: Optional[int],
    course_id: Optional[str],
):
    """Gera o PDF class-wide do professor a partir da mesma projeção da tela."""
    year = int(academic_year or datetime.now().year)

    # SSoT da tela do professor: histórico legado autorizado + conteúdo canônico.
    projected = await list_learning_objects_cutover(
        db,
        current_user,
        request,
        legacy_items=[],
        class_id=class_id,
        course_id=course_id,
        date=None,
        academic_year=year,
        month=None,
    )

    import asyncio

    turma_task = db.classes.find_one({"id": class_id}, {"_id": 0})
    mantenedora_task = learning_objects_mod.get_mantenedora_cached(db)
    calendario_task = learning_objects_mod.get_calendario_cached(db, year, None)
    turma, mantenedora, calendario = await asyncio.gather(
        turma_task, mantenedora_task, calendario_task
    )
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")

    school = await learning_objects_mod.get_school_cached(db, turma.get("school_id"))
    if not school:
        raise HTTPException(status_code=404, detail="Escola não encontrada")

    period_start, period_end = _period_bounds(calendario, bimestre, year)
    records = _records_in_period(
        projected,
        period_start=period_start,
        period_end=period_end,
        academic_year=year,
    )

    # A projeção normalmente já traz nomes; completar em lote mantém o contrato
    # do gerador mesmo diante de registros históricos incompletos.
    course_ids = sorted({
        str(item.get("course_id") or item.get("component_id") or "").strip()
        for item in records
        if str(item.get("course_id") or item.get("component_id") or "").strip()
    })
    course_names: dict[str, str] = {}
    if course_ids:
        rows = await db.courses.find(
            {"id": {"$in": course_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(course_ids))
        course_names = {str(row.get("id")): str(row.get("name") or "") for row in rows}
    for item in records:
        component_id = str(item.get("course_id") or item.get("component_id") or "").strip()
        item["course_id"] = component_id
        item["course_name"] = item.get("course_name") or course_names.get(component_id, "")

    teacher_name = str(
        current_user.get("full_name")
        or current_user.get("name")
        or current_user.get("nome")
        or ""
    )
    teacher_names = await get_multi_teacher_names_for_pdf(db, turma, year)
    if not teacher_names and teacher_name:
        teacher_names = [teacher_name]

    dias_previstos = await _dias_previstos(db, year, period_start, period_end)

    pdf_buffer = learning_objects_mod.generate_learning_objects_pdf(
        school=school,
        class_info=turma,
        records=records,
        bimestre=bimestre,
        academic_year=year,
        period_start=period_start,
        period_end=period_end,
        teacher_name=teacher_name,
        mantenedora=mantenedora,
        dias_previstos=dias_previstos,
        teacher_names=teacher_names,
    )

    course_name_part = ""
    if course_id and records:
        course_name_part = f"_{records[0].get('course_name', '')}"
    filename = (
        f"objetos_conhecimento_{turma.get('name', 'turma')}"
        f"{course_name_part}_{bimestre}bim_{year}.pdf"
    )
    filename = filename.replace(" ", "_").replace("/", "-")
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )
