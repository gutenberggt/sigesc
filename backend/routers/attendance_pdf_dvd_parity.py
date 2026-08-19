"""Paridade documental do PDF de Frequência do professor em modo DVD.

Reinstala somente a rota de PDF do Diário por Vínculo para que o documento
utilize as mesmas fontes institucionais do PDF administrativo:
- documento canônico da turma (incluindo configuração multisseriada);
- helper oficial de múltiplos professores;
- mesmo renderer e mesma regra de assinaturas.

Nenhuma frequência é escrita, migrada ou reatribuída por este adaptador.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from auth_middleware import AuthMiddleware
from services.attendance_assignment_roster import build_attendance_roster
from services.class_teachers import get_multi_teacher_names_for_pdf
from services.diary_assignment_contract import AttendanceMode


def _remove_existing_dvd_pdf_route(router) -> None:
    """Remove a rota PDF DVD já instalada, independentemente do prefixo."""
    suffix = "/dvd/pdf/bimestre/{assignment_id}"
    for route in list(router.routes):
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", set()) or set()
        if path.endswith(suffix) and "GET" in methods:
            router.routes.remove(route)


def _canonical_pdf_class_info(class_info: dict, context) -> dict:
    """Preserva a turma canônica e garante nome de fallback do vínculo."""
    return {
        **(class_info or {}),
        "name": (class_info or {}).get("name")
        or context.class_info.get("name")
        or context.assignment.get("class_name"),
    }


def install_attendance_pdf_dvd_parity(base_router, db, sandbox_db=None):
    """Instala a rota de PDF DVD com metadados documentais canônicos."""
    if getattr(base_router, "_dvd_pdf_document_parity_installed", False):
        return base_router

    # Import tardio evita ciclo; reutilizamos toda a infraestrutura da Fase 4.
    from routers import attendance_dvd as dvd_mod

    _remove_existing_dvd_pdf_route(base_router)

    @base_router.get("/dvd/pdf/bimestre/{assignment_id}")
    async def dvd_bimestre_pdf_document_parity(
        assignment_id: str,
        request: Request,
        bimestre: int = Query(..., ge=1, le=4),
        academic_year: Optional[int] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = dvd_mod._db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year

        assignment = await current_db.teacher_class_assignments.find_one(
            {"id": assignment_id}, {"_id": 0}
        )
        if not assignment:
            raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")

        ref = max(
            str(assignment.get("valid_from") or f"{year}-01-01")[:10],
            f"{year}-01-01",
        )
        context, meta = await dvd_mod._dvd_context_payload(
            current_db, user, request, assignment_id, ref
        )

        periods = await dvd_mod._calendar_periods(current_db, year)
        _, start, end = next(
            (item for item in periods if item[0] == bimestre),
            (bimestre, None, None),
        )

        docs = await dvd_mod._assignment_docs(
            current_db, context, year, start=start, end=end
        )
        attendance_days: list[str] = []
        for doc in docs:
            ds = str(doc.get("date") or "")[:10]
            if not ds:
                continue
            if (
                context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION
                and doc.get("aula_numero") is not None
            ):
                attendance_days.append(f"{ds}#{doc.get('aula_numero')}")
            else:
                attendance_days.append(ds)
        attendance_days = sorted(set(attendance_days))

        roster = await build_attendance_roster(
            current_db,
            class_id=context.assignment.get("class_id"),
            academic_year=year,
            course_id=context.effective_course_id,
            tenant_id=context.snapshot.get("mantenedora_id"),
        )
        by_student = {
            student["id"]: {
                "name": student.get("full_name"),
                "attendance_by_date": {},
                "attendance_classes_by_date": {},
                "medical_days": [],
            }
            for student in roster
        }

        for doc in docs:
            ds = str(doc.get("date") or "")[:10]
            key = (
                f"{ds}#{doc.get('aula_numero')}"
                if (
                    context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION
                    and doc.get("aula_numero") is not None
                )
                else ds
            )
            for row in doc.get("records") or []:
                sid = row.get("student_id")
                if sid in by_student:
                    by_student[sid]["attendance_by_date"][key] = row.get("status")
                    by_student[sid]["attendance_classes_by_date"][key] = 1

        dates_only = {key.split("#")[0] for key in attendance_days}
        if dates_only and by_student:
            certs = await current_db.medical_certificates.find(
                {
                    "student_id": {"$in": list(by_student)},
                    "start_date": {"$lte": max(dates_only)},
                    "end_date": {"$gte": min(dates_only)},
                },
                {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1},
            ).to_list(None)
            for cert in certs:
                sid = cert.get("student_id")
                if sid not in by_student:
                    continue
                cert_start = str(cert.get("start_date") or "")[:10]
                cert_end = str(cert.get("end_date") or "")[:10]
                for ds in dates_only:
                    if cert_start <= ds <= cert_end:
                        by_student[sid]["medical_days"].append(ds)

        tenant_id = context.snapshot.get("mantenedora_id")
        class_id = context.assignment.get("class_id")

        # Diferentemente do snapshot do vínculo, o documento de turma é a fonte
        # institucional para série/ano, inclusive turmas multisseriadas.
        class_info = await current_db.classes.find_one(
            {"id": class_id}, {"_id": 0}
        )
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma do vínculo não encontrada")
        if tenant_id and class_info.get("mantenedora_id") not in (None, tenant_id):
            raise HTTPException(status_code=403, detail="Turma fora da mantenedora do vínculo")
        class_info = _canonical_pdf_class_info(class_info, context)

        school = await current_db.schools.find_one(
            {"id": context.snapshot.get("school_id"), "mantenedora_id": tenant_id},
            {"_id": 0},
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola do vínculo não encontrada")

        course = None
        if context.effective_course_id:
            course = await current_db.courses.find_one(
                {"id": context.effective_course_id, "mantenedora_id": tenant_id},
                {"_id": 0},
            )

        mantenedora = await current_db.mantenedoras.find_one(
            {"id": tenant_id}, {"_id": 0}
        ) or {}

        previstos = await dvd_mod._expected_sessions(
            current_db,
            context,
            start=start,
            end=end,
            academic_year=year,
        )

        # Mesma regra do PDF administrativo. Em Infantil/Anos Iniciais, mais
        # de um professor ativo => cabeçalho plural + assinaturas adicionais.
        teacher_names = await get_multi_teacher_names_for_pdf(
            current_db, class_info, year
        )

        from pdf_generator import generate_relatorio_frequencia_bimestre_pdf

        teacher_name = context.snapshot.get("teacher_name") or ""
        if meta["documentary_only"]:
            teacher_name = f"{teacher_name} - REGISTRO DOCUMENTAL (NÃO OFICIAL)"

        pdf_buffer: BytesIO = generate_relatorio_frequencia_bimestre_pdf(
            school=school,
            class_info=class_info,
            course_info=course or {},
            students_attendance=list(by_student.values()),
            bimestre=bimestre,
            academic_year=year,
            period_start=start,
            period_end=end,
            attendance_days=attendance_days,
            aulas_previstas=previstos,
            aulas_ministradas=len(attendance_days),
            teacher_name=teacher_name,
            mantenedora=mantenedora,
            teacher_names=teacher_names or None,
        )

        filename = f"frequencia_{assignment_id}_{bimestre}bim_{year}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    base_router._dvd_pdf_document_parity_installed = True
    return base_router
