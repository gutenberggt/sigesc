"""Guards/adapters para superfícies estendidas de Frequência.

O PDF e os alertas legados permanecem disponíveis para gestão/consolidação.
Professor em turma DVD usa `assignment_id`, evitando exposição de dados de
outros vínculos e reutilizando o relatório canônico autorizado do próprio DVD.

A camada também normaliza o escopo documental do PDF legado: Educação Infantil,
Anos Iniciais e EJA inicial usam frequência diária por turma. Nesses níveis, um
`course_id` residual da navegação não pode filtrar a frequência e zerar o PDF.

P0 27/08/2026: a consulta individual usada pela Assistência Social deixa de
usar a leitura antiga e passa a operar com autorização explícita, escopo por
tenant, calendário letivo real e consolidação diária compatível com o motor do
Bolsa Família. A rota é somente leitura e não altera documentos acadêmicos.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from services.attendance_utils import (
    compute_monthly_valid_absences,
    fetch_medical_days_for_student,
)
from tenant_scope import apply_tenant_filter


_SOCIAL_FREQUENCY_ROLES = ["admin", "admin_teste", "ass_social", "ass_social_2"]
_NON_SCHOOL_EVENT_TYPES = {
    "feriado_nacional",
    "feriado_estadual",
    "feriado_municipal",
    "recesso_escolar",
}


def _remove_route(router, path: str, method: str):
    for route in list(router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            router.routes.remove(route)
            return route.endpoint
    return None


async def _professor_has_dvd_in_year(db, user: dict, class_id: str, academic_year: int) -> bool:
    if user.get("role") != "professor" or not user.get("id"):
        return False
    return bool(await db.teacher_class_assignments.find_one(
        {
            "teacher_id": user.get("id"),
            "class_id": class_id,
            "deleted": {"$ne": True},
            "diary_settings.enabled": True,
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{academic_year}-01-01"}}],
        },
        {"_id": 0, "id": 1},
    ))


def _accepted_call(endpoint, values: dict):
    return {
        name: values[name]
        for name in inspect.signature(endpoint).parameters
        if name in values
    }


def _uses_component_attendance(class_info: dict) -> bool:
    """Retorna True somente quando a frequência oficial é por componente/aula.

    Educação Infantil, Anos Iniciais e EJA inicial são `class_daily`; portanto
    `course_id` é contexto de navegação/conteúdo, não chave de leitura da
    frequência. A inferência replica as regras já usadas pela tela/relatórios.
    """
    level = str(
        (class_info or {}).get("education_level")
        or (class_info or {}).get("nivel_ensino")
        or ""
    ).strip().lower()
    if level:
        return level in {"fundamental_anos_finais", "eja_final", "ensino_medio"}

    ref = str(
        (class_info or {}).get("grade_level")
        or (class_info or {}).get("grade")
        or (class_info or {}).get("name")
        or ""
    ).upper()
    if re.search(r"PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL", ref):
        return False
    if re.search(r"\bEJA\b", ref):
        return bool(re.search(r"FINAL|[6-9]", ref))

    match = re.match(r"\s*(\d+)", ref)
    if match:
        return int(match.group(1)) >= 6
    return False


def _parse_date(value):
    raw = str(value or "")[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _normalize_social_attendance_docs(attendances: list[dict], student_id: str) -> list[dict]:
    """Normaliza legado multi-aula para a engine diária já usada pelo BF.

    Um status `P|F|P` representa três registros do mesmo aluno/dia. A expansão
    permite que `compute_monthly_valid_absences` aplique a mesma regra de 50%
    usada para frequência por componente, sem inventar uma segunda fórmula.
    """
    normalized = []
    for attendance in attendances or []:
        records = []
        for record in attendance.get("records") or []:
            if record.get("student_id") != student_id:
                continue
            raw_status = str(record.get("status") or "").strip()
            statuses = [part.strip() for part in raw_status.split("|")] if "|" in raw_status else [raw_status]
            for status_value in statuses:
                clone = dict(record)
                clone["status"] = status_value
                records.append(clone)
        if records:
            clone_doc = dict(attendance)
            clone_doc["records"] = records
            normalized.append(clone_doc)
    return normalized


async def _social_school_days_until_today(current_db, user: dict, request: Request, academic_year: int, today: str):
    """Conta dias letivos do calendário oficial do tenant até `today`.

    O início vem do primeiro bimestre cadastrado. Só usa 01/02 como fallback
    quando o calendário não possui início válido. Eventos inválidos são
    ignorados de forma fail-safe; `end_date` ausente equivale a evento de um dia.
    """
    calendar_query = apply_tenant_filter(
        {"ano_letivo": academic_year, "school_id": None},
        user,
        request,
    )
    calendar_doc = await current_db.calendario_letivo.find_one(calendar_query, {"_id": 0})
    if not calendar_doc:
        calendar_doc = await current_db.calendario_letivo.find_one(
            apply_tenant_filter({"ano_letivo": academic_year}, user, request),
            {"_id": 0},
        )

    starts = []
    if calendar_doc:
        for index in range(1, 5):
            parsed = _parse_date(calendar_doc.get(f"bimestre_{index}_inicio"))
            if parsed:
                starts.append(parsed)
    start_date = min(starts) if starts else _parse_date(f"{academic_year}-02-01")
    end_date = _parse_date(today)
    if start_date is None or end_date is None or end_date < start_date:
        return 0, f"{academic_year}-02-01"

    if calendar_doc:
        official_end = _parse_date(calendar_doc.get("bimestre_4_fim"))
        if official_end and official_end < end_date:
            end_date = official_end

    events = await current_db.calendar_events.find(
        apply_tenant_filter(
            {
                "academic_year": academic_year,
                "start_date": {"$lte": today},
            },
            user,
            request,
        ),
        {"_id": 0, "event_type": 1, "is_school_day": 1, "start_date": 1, "end_date": 1},
    ).to_list(5000)

    non_school_dates = set()
    saturday_school_dates = set()
    for event in events:
        event_start = _parse_date(event.get("start_date"))
        event_end = _parse_date(event.get("end_date") or event.get("start_date"))
        if not event_start or not event_end or event_end < event_start:
            continue
        if event_start > end_date:
            continue
        if event_end > end_date:
            event_end = end_date

        current = event_start
        while current <= event_end:
            event_type = event.get("event_type")
            if event_type in _NON_SCHOOL_EVENT_TYPES:
                non_school_dates.add(current)
            elif event_type == "sabado_letivo" or (event.get("is_school_day") and current.weekday() == 5):
                saturday_school_dates.add(current)
            current += timedelta(days=1)

    school_days = 0
    current = start_date
    while current <= end_date:
        if current in saturday_school_dates:
            school_days += 1
        elif current.weekday() < 5 and current not in non_school_dates:
            school_days += 1
        current += timedelta(days=1)

    return school_days, start_date.isoformat()


def install_attendance_ext_dvd_setup() -> None:
    from routers import attendance_ext as attendance_ext_mod

    if getattr(attendance_ext_mod, "_dvd_phase4_setup_wrapped", False):
        return

    original_setup = attendance_ext_mod.setup_router

    def wrapped_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        result = original_setup(db, audit_service, sandbox_db, **kwargs)
        if getattr(attendance_ext_mod.router, "_dvd_phase4_ext_guard", False):
            return result

        legacy_social_frequency = _remove_route(
            attendance_ext_mod.router,
            "/attendance/frequency/student/{student_id}",
            "GET",
        )
        legacy_pdf = _remove_route(
            attendance_ext_mod.router,
            "/attendance/pdf/bimestre/{class_id}",
            "GET",
        )
        legacy_alerts = _remove_route(
            attendance_ext_mod.router,
            "/attendance/alerts",
            "GET",
        )

        if legacy_social_frequency is not None:
            @attendance_ext_mod.router.get("/attendance/frequency/student/{student_id}")
            async def social_frequency_p0(
                student_id: str,
                request: Request,
                academic_year: Optional[int] = None,
            ):
                user = await AuthMiddleware.require_roles(_SOCIAL_FREQUENCY_ROLES)(request)
                current_db = (
                    sandbox_db
                    if user.get("is_sandbox") and sandbox_db is not None
                    else db
                )
                year = academic_year or datetime.now().year
                today = datetime.now().strftime("%Y-%m-%d")

                student = await current_db.students.find_one(
                    apply_tenant_filter({"id": student_id}, user, request),
                    {"_id": 0},
                )
                if not student:
                    raise HTTPException(status_code=404, detail="Estudante não encontrado")

                school_id = student.get("school_id")
                if school_id:
                    await AuthMiddleware.verify_school_access(request, school_id)

                class_id = student.get("class_id")
                if not class_id:
                    enrollment = await current_db.enrollments.find_one(
                        apply_tenant_filter(
                            {
                                "student_id": student_id,
                                "status": "active",
                                "academic_year": year,
                            },
                            user,
                            request,
                        ),
                        {"_id": 0, "class_id": 1},
                    )
                    if enrollment:
                        class_id = enrollment.get("class_id")

                school_days, school_year_start = await _social_school_days_until_today(
                    current_db,
                    user,
                    request,
                    year,
                    today,
                )

                attendances = await current_db.attendance.find(
                    apply_tenant_filter(
                        {
                            "academic_year": year,
                            "records.student_id": student_id,
                            "date": {"$gte": school_year_start, "$lte": today},
                        },
                        user,
                        request,
                    ),
                    {"_id": 0, "date": 1, "records": 1},
                ).to_list(10000)

                normalized = _normalize_social_attendance_docs(attendances, student_id)
                attendance_dates = {
                    str(item.get("date") or "")[:10]
                    for item in normalized
                    if item.get("date")
                }

                # medical_certificates é coleção legado sem mantenedora_id.
                # A consulta é segura porque `student_id` já foi resolvido dentro
                # do tenant autorizado e o UUID do aluno é a chave institucional.
                certificates = await current_db.medical_certificates.find(
                    {
                        "student_id": student_id,
                        "start_date": {"$lte": today},
                        "end_date": {"$gte": school_year_start},
                    },
                    {"_id": 0, "start_date": 1, "end_date": 1},
                ).to_list(None)
                medical_days = fetch_medical_days_for_student(certificates, attendance_dates)

                absences_by_month = compute_monthly_valid_absences(
                    normalized,
                    {student_id: medical_days},
                    {student_id},
                )
                absences = sum((absences_by_month.get(student_id) or {}).values())

                justified_dates = set()
                for attendance in normalized:
                    date_value = str(attendance.get("date") or "")[:10]
                    if not date_value or date_value in medical_days:
                        continue
                    if any(
                        str(record.get("status") or "").strip() in {"J", "justified"}
                        for record in attendance.get("records") or []
                    ):
                        justified_dates.add(date_value)

                medical = len(medical_days)
                justified = len(justified_dates)
                presences = max(0, len(attendance_dates) - absences - medical - justified)

                if school_days > 0:
                    attendance_percentage = ((school_days - absences) / school_days) * 100
                else:
                    attendance_percentage = 100.0
                attendance_percentage = max(0.0, min(100.0, attendance_percentage))
                percentage = round(attendance_percentage, 1)

                return {
                    "student_id": student_id,
                    "student_name": student.get("full_name"),
                    "academic_year": year,
                    "class_id": class_id,
                    "calculation_date": today,
                    "summary": {
                        "school_days_until_today": school_days,
                        "absences": absences,
                        "presences": presences,
                        "justified": justified,
                        "medical": medical,
                        "attendance_percentage": percentage,
                        "status": "regular" if percentage >= 75 else "alerta",
                    },
                    "formula": f"(({school_days} - {absences}) / {school_days}) × 100 = {percentage}%",
                    "calculation_version": "social_daily_canonical_v2",
                }

        if legacy_pdf is not None:
            @attendance_ext_mod.router.get("/attendance/pdf/bimestre/{class_id}")
            async def dvd_aware_legacy_pdf(
                class_id: str,
                request: Request,
                bimestre: int = Query(..., ge=1, le=4),
                academic_year: Optional[int] = None,
                course_id: Optional[str] = None,
            ):
                user = await AuthMiddleware.get_current_user(request)
                current_db = (
                    sandbox_db
                    if user.get("is_sandbox") and sandbox_db is not None
                    else db
                )
                year = academic_year or datetime.now().year
                if await _professor_has_dvd_in_year(current_db, user, class_id, year):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "DVD_ASSIGNMENT_REQUIRED",
                            "message": (
                                "Em turma DVD, o PDF do professor deve ser gerado a partir "
                                "de Meus Diários para preservar o vínculo docente."
                            ),
                        },
                    )

                # P0 21/08/2026 — o botão de PDF pode herdar `course_id` do
                # contexto de Meus Diários mesmo em turma de frequência diária.
                # O relatório em tela não usa esse filtro nesses níveis; o PDF
                # também não pode usá-lo, sob pena de retornar 0 dias quando os
                # documentos oficiais possuem `course_id=None`.
                effective_course_id = course_id
                if course_id:
                    class_info = await current_db.classes.find_one(
                        {"id": class_id},
                        {
                            "_id": 0,
                            "education_level": 1,
                            "nivel_ensino": 1,
                            "grade_level": 1,
                            "grade": 1,
                            "name": 1,
                        },
                    )
                    if class_info and not _uses_component_attendance(class_info):
                        effective_course_id = None

                return await legacy_pdf(**_accepted_call(legacy_pdf, {
                    "class_id": class_id,
                    "request": request,
                    "bimestre": bimestre,
                    "academic_year": academic_year,
                    "course_id": effective_course_id,
                }))

        if legacy_alerts is not None:
            @attendance_ext_mod.router.get("/attendance/alerts")
            async def dvd_aware_alerts(
                request: Request,
                school_id: Optional[str] = None,
                academic_year: Optional[int] = None,
                assignment_id: Optional[str] = None,
            ):
                user = await AuthMiddleware.get_current_user(request)
                current_db = (
                    sandbox_db
                    if user.get("is_sandbox") and sandbox_db is not None
                    else db
                )
                year = academic_year or datetime.now().year

                if assignment_id:
                    # Import local evita ciclo no bootstrap. `_dvd_report` já passa
                    # pelo autorizador central e, após o adaptador de paridade,
                    # inclui o histórico class_daily legitimamente herdado.
                    from routers.attendance_dvd import _dvd_report

                    report = await _dvd_report(
                        current_db,
                        user,
                        request,
                        assignment_id,
                        year,
                        None,
                    )
                    report_school = (report.get("class") or {}).get("school_id") or report.get("school_id")
                    if school_id and report_school and school_id != report_school:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "code": "SCHOOL_MISMATCH",
                                "message": "O vínculo não pertence à escola informada.",
                            },
                        )

                    if report.get("documentary_only"):
                        return {
                            "academic_year": year,
                            "assignment_id": assignment_id,
                            "class_id": report.get("class_id"),
                            "documentary_only": True,
                            "total_alerts": 0,
                            "alerts": [],
                        }

                    class_info = report.get("class") or {}
                    alerts = []
                    for row in report.get("students") or []:
                        percentage = float(row.get("attendance_percentage") or 0)
                        total = int(row.get("total") or 0)
                        if total <= 0 or percentage >= 75:
                            continue
                        alerts.append({
                            "student_id": row.get("student_id"),
                            "student_name": row.get("student_name"),
                            "class_id": report.get("class_id") or class_info.get("id"),
                            "class_name": class_info.get("name"),
                            "school_id": report_school,
                            "attendance_percentage": percentage,
                            "total_records": total,
                            "absent": int(row.get("absent") or 0),
                        })
                    alerts.sort(key=lambda item: item["attendance_percentage"])
                    return {
                        "academic_year": year,
                        "assignment_id": assignment_id,
                        "class_id": report.get("class_id") or class_info.get("id"),
                        "documentary_only": False,
                        "total_alerts": len(alerts),
                        "alerts": alerts,
                    }

                return await legacy_alerts(**_accepted_call(legacy_alerts, {
                    "request": request,
                    "school_id": school_id,
                    "academic_year": academic_year,
                }))

        attendance_ext_mod.router._dvd_phase4_ext_guard = True
        return result

    attendance_ext_mod.setup_router = wrapped_setup
    attendance_ext_mod._dvd_phase4_setup_wrapped = True
