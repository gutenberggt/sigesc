"""
Router para Acompanhamento de Frequência - Bolsa Família.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone, date, timedelta
import logging
import io
import calendar

from auth_middleware import AuthMiddleware
from pdf.utils import format_date_pt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bolsa Família"])

MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}


def setup_router(db, **kwargs):

    async def _calc_monthly_school_days(academic_year):
        """Calcula dias letivos por mês com base no calendário (seg-sex excl. feriados + sábados letivos)."""
        events = await db.calendar_events.find(
            {"academic_year": academic_year},
            {"_id": 0, "start_date": 1, "end_date": 1, "event_type": 1, "is_school_day": 1}
        ).to_list(1000)

        holidays = set()
        extra_days = set()
        for ev in events:
            sd = ev.get("start_date", "")
            ed = ev.get("end_date", sd)
            if not sd:
                continue
            try:
                start = datetime.strptime(sd[:10], "%Y-%m-%d").date()
                end = datetime.strptime(ed[:10], "%Y-%m-%d").date()
            except:
                continue

            if ev.get("is_school_day"):
                d = start
                while d <= end:
                    extra_days.add(d)
                    d += timedelta(days=1)
            elif ev.get("event_type") in ("feriado", "recesso", "ferias"):
                d = start
                while d <= end:
                    holidays.add(d)
                    d += timedelta(days=1)

        # Buscar calendário letivo para saber datas dos bimestres
        cal = await db.calendario_letivo.find_one({"academic_year": academic_year}, {"_id": 0})
        year_start = date(academic_year, 2, 1)
        year_end = date(academic_year, 12, 20)
        if cal:
            try:
                b1s = cal.get("bimestre1_inicio", "")
                b4e = cal.get("bimestre4_fim", "")
                if b1s:
                    year_start = datetime.strptime(b1s[:10], "%Y-%m-%d").date()
                if b4e:
                    year_end = datetime.strptime(b4e[:10], "%Y-%m-%d").date()
            except:
                pass

        monthly = {}
        for m in range(1, 13):
            days_in_month = calendar.monthrange(academic_year, m)[1]
            count = 0
            for d in range(1, days_in_month + 1):
                dt = date(academic_year, m, d)
                if dt < year_start or dt > year_end:
                    continue
                if dt in holidays:
                    continue
                if dt in extra_days:
                    count += 1
                elif dt.weekday() < 5:  # seg-sex
                    count += 1
            monthly[m] = count
        return monthly

    async def _calc_student_monthly_attendance(student_id, academic_year, months_range):
        """Calcula a frequência real mensal de um aluno com base nos registros de presença."""
        attendance_records = await db.attendance.find(
            {"student_id": student_id, "academic_year": academic_year},
            {"_id": 0, "date": 1, "status": 1, "records": 1}
        ).to_list(10000)

        monthly_presence = {}
        monthly_total = {}

        for rec in attendance_records:
            rec_date = rec.get("date", "")
            if not rec_date:
                continue
            try:
                dt = datetime.strptime(rec_date[:10], "%Y-%m-%d")
                m = dt.month
            except:
                continue

            if m not in months_range:
                continue

            # Check individual records or status
            records = rec.get("records", [])
            if records:
                for r in records:
                    st = r.get("status", "")
                    if st:
                        monthly_total[m] = monthly_total.get(m, 0) + 1
                        if st in ("present", "presente", "P"):
                            monthly_presence[m] = monthly_presence.get(m, 0) + 1
            else:
                status = rec.get("status", "")
                if status:
                    monthly_total[m] = monthly_total.get(m, 0) + 1
                    if status in ("present", "presente", "P"):
                        monthly_presence[m] = monthly_presence.get(m, 0) + 1

        return monthly_presence, monthly_total

    EDIT_ROLES = ['admin', 'admin_teste', 'secretario']
    VIEW_ROLES = ['admin', 'admin_teste', 'secretario', 'semed3', 'diretor', 'ass_social_2']

    @router.get("/bolsa-familia/students")
    async def list_bolsa_familia_students(
        request: Request,
        school_id: str = Query(...),
        academic_year: Optional[int] = None
    ):
        """Lista alunos com Bolsa Família de uma escola."""
        current_user = await AuthMiddleware.require_roles(VIEW_ROLES)(request)

        if not academic_year:
            academic_year = datetime.now().year

        query = {
            "school_id": school_id,
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]}
        }

        students = await db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "nis": 1,
             "mother_name": 1, "class_id": 1, "school_id": 1,
             "inep_code": 1, "mother_phone": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(10000)

        class_ids = list(set(s.get("class_id") for s in students if s.get("class_id")))
        classes = await db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "grade_level": 1}).to_list(1000)
        class_map = {c["id"]: c for c in classes}

        # Buscar mantenedora
        mant = await db.mantenedora.find_one({}, {"_id": 0, "municipio": 1, "uf": 1})
        municipio_uf = ""
        if mant:
            mun = mant.get("municipio", "")
            uf = mant.get("uf", "")
            municipio_uf = f"{mun}/{uf}" if uf else mun

        # Calcular dias letivos por mês
        monthly_school_days = await _calc_monthly_school_days(academic_year)

        # Buscar tracking records
        bf_records = await db.bolsa_familia_tracking.find(
            {"school_id": school_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(10000)
        record_map = {}
        for r in bf_records:
            key = f"{r['student_id']}_{r['month']}"
            record_map[key] = r

        # Calcular frequência mensal para todos os alunos
        student_ids = [s["id"] for s in students]
        all_attendance = await db.attendance.find(
            {"academic_year": academic_year},
            {"_id": 0, "date": 1, "students": 1}
        ).to_list(50000)

        # Mapear presença por aluno/mês
        student_presence = {}  # {student_id: {month: present_count}}
        student_total_days = {}  # {student_id: {month: total_registered}}

        for att in all_attendance:
            att_date = att.get("date", "")
            if not att_date:
                continue
            try:
                dt = datetime.strptime(att_date[:10], "%Y-%m-%d")
                m = dt.month
            except:
                continue

            for st_rec in att.get("students", []):
                sid = st_rec.get("student_id", "")
                if sid not in student_ids:
                    continue
                records = st_rec.get("records", [])
                for r in records:
                    status = r.get("status", "")
                    if status:
                        if sid not in student_total_days:
                            student_total_days[sid] = {}
                        student_total_days[sid][m] = student_total_days[sid].get(m, 0) + 1
                        if status in ("present", "presente", "P"):
                            if sid not in student_presence:
                                student_presence[sid] = {}
                            student_presence[sid][m] = student_presence[sid].get(m, 0) + 1

        result = []
        for s in students:
            cls = class_map.get(s.get("class_id"), {})
            student_data = {
                "id": s["id"],
                "full_name": s["full_name"],
                "birth_date": s.get("birth_date", ""),
                "nis": s.get("nis", ""),
                "responsible": s.get("mother_name") or "",
                "contact": s.get("mother_phone") or "",
                "series": cls.get("grade_level") or cls.get("name", ""),
                "class_name": cls.get("name", ""),
                "inep_code": s.get("inep_code", ""),
                "months": {}
            }

            for m in range(1, 13):
                key = f"{s['id']}_{m}"
                rec = record_map.get(key, {})

                # Calcular frequência com base no calendário letivo
                school_days = monthly_school_days.get(m, 0)
                presences = (student_presence.get(s["id"]) or {}).get(m, 0)
                freq_pct = ""
                if school_days > 0:
                    freq_pct = f"{round((presences / school_days) * 100, 1)}%"

                student_data["months"][str(m)] = {
                    "frequency": freq_pct,
                    "motive": rec.get("motive", ""),
                    "school_days": school_days,
                    "presences": presences
                }

            result.append(student_data)

        return {
            "students": result,
            "total": len(result),
            "municipio_uf": municipio_uf,
            "monthly_school_days": monthly_school_days,
            "can_edit": current_user['role'] in EDIT_ROLES
        }

    @router.put("/bolsa-familia/tracking")
    async def save_tracking(request: Request):
        """Salva dados de acompanhamento (motivo). Apenas secretários e admins."""
        await AuthMiddleware.require_roles(EDIT_ROLES)(request)

        body = await request.json()
        student_id = body.get("student_id")
        school_id = body.get("school_id")
        month = body.get("month")
        academic_year = body.get("academic_year", datetime.now().year)
        motive = body.get("motive", "")

        if not student_id or not school_id or not month:
            raise HTTPException(status_code=400, detail="student_id, school_id e month são obrigatórios")

        now = datetime.now(timezone.utc).isoformat()

        await db.bolsa_familia_tracking.update_one(
            {"student_id": student_id, "school_id": school_id, "month": month, "academic_year": academic_year},
            {"$set": {
                "student_id": student_id,
                "school_id": school_id,
                "month": month,
                "academic_year": academic_year,
                "motive": motive,
                "updated_at": now
            }},
            upsert=True
        )

        return {"message": "Salvo com sucesso"}

    @router.get("/bolsa-familia/pdf/{school_id}")
    async def generate_bolsa_familia_pdf(
        school_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        month_start: int = Query(2, description="Mês inicial"),
        month_end: int = Query(3, description="Mês final")
    ):
        """Gera PDF de Acompanhamento de Frequência - Bolsa Família."""
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)

        if not academic_year:
            academic_year = datetime.now().year

        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        mant = await db.mantenedora.find_one({}, {"_id": 0, "municipio": 1, "uf": 1})
        municipio_uf = ""
        if mant:
            mun = mant.get("municipio", "")
            uf = mant.get("uf", "")
            municipio_uf = f"{mun}/{uf}" if uf else mun

        query = {
            "school_id": school_id,
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]}
        }
        students = await db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "nis": 1,
             "mother_name": 1, "class_id": 1, "inep_code": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(10000)

        if not students:
            raise HTTPException(status_code=404, detail="Nenhum aluno com Bolsa Família encontrado nesta escola")

        class_ids = list(set(s.get("class_id") for s in students if s.get("class_id")))
        classes = await db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "grade_level": 1}).to_list(1000)
        class_map = {c["id"]: c for c in classes}

        bf_records = await db.bolsa_familia_tracking.find(
            {"school_id": school_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(10000)
        record_map = {}
        for r in bf_records:
            key = f"{r['student_id']}_{r['month']}"
            record_map[key] = r

        monthly_school_days = await _calc_monthly_school_days(academic_year)

        # Buscar frequência
        student_ids = [s["id"] for s in students]
        all_attendance = await db.attendance.find(
            {"academic_year": academic_year},
            {"_id": 0, "date": 1, "students": 1}
        ).to_list(50000)

        student_presence = {}
        for att in all_attendance:
            att_date = att.get("date", "")
            if not att_date:
                continue
            try:
                dt = datetime.strptime(att_date[:10], "%Y-%m-%d")
                m = dt.month
            except:
                continue
            for st_rec in att.get("students", []):
                sid = st_rec.get("student_id", "")
                if sid not in student_ids:
                    continue
                for r in st_rec.get("records", []):
                    if r.get("status") in ("present", "presente", "P"):
                        if sid not in student_presence:
                            student_presence[sid] = {}
                        student_presence[sid][m] = student_presence[sid].get(m, 0) + 1

        secretario = school.get("secretario_escolar") or ""
        months_range = list(range(month_start, month_end + 1))

        try:
            pdf_buffer = _generate_bf_pdf(
                school=school, students=students, class_map=class_map,
                record_map=record_map, months_range=months_range,
                academic_year=academic_year, secretario=secretario,
                municipio_uf=municipio_uf, monthly_school_days=monthly_school_days,
                student_presence=student_presence
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF Bolsa Família: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

        filename = f"bolsa_familia_{school.get('name', 'escola').replace(' ', '_')}_{academic_year}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )

    def _generate_bf_pdf(school, students, class_map, record_map, months_range, academic_year, secretario, municipio_uf, monthly_school_days, student_presence):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm, cm
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
        elements = []

        title_style = ParagraphStyle('BFTitle', fontSize=12, fontName='Helvetica-Bold', alignment=TA_CENTER, leading=14, spaceAfter=4)
        info_style = ParagraphStyle('BFInfo', fontSize=7, leading=9, alignment=TA_LEFT)
        cell_style = ParagraphStyle('BFCell', fontSize=6.5, leading=8, alignment=TA_LEFT)
        cell_center = ParagraphStyle('BFCellCenter', fontSize=6.5, leading=8, alignment=TA_CENTER)
        sign_style = ParagraphStyle('BFSign', fontSize=8, alignment=TA_CENTER, leading=10)

        elements.append(Paragraph("Acompanhamento de Frequência Escolar", title_style))
        elements.append(Spacer(1, 4))

        school_name = school.get('name', '')
        inep = school.get('inep_code', '')

        school_data = [
            [Paragraph(f"<b>Nome da Escola:</b> {school_name}", info_style),
             Paragraph(f"<b>Código INEP:</b> {inep}", info_style),
             Paragraph(f"<b>Município/UF:</b> {municipio_uf}", info_style)]
        ]
        school_table = Table(school_data, colWidths=[8*cm, 4.5*cm, 4.5*cm])
        school_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(school_table)
        elements.append(Spacer(1, 6))

        for student in students:
            cls = class_map.get(student.get("class_id"), {})
            serie = cls.get("grade_level") or cls.get("name", "")
            birth = student.get("birth_date", "")
            if isinstance(birth, str) and "-" in birth:
                try:
                    bd = datetime.strptime(birth.split("T")[0], "%Y-%m-%d")
                    birth = bd.strftime("%d/%m/%Y")
                except:
                    pass
            nis = student.get("nis", "")
            responsible = student.get("mother_name") or ""
            student_inep = student.get("inep_code", "")

            student_header = [
                [Paragraph(f"<b>Nome do Estudante:</b> {student['full_name']}", info_style),
                 Paragraph(f"<b>Dt. Nasc.:</b> {birth}", info_style),
                 Paragraph(f"<b>NIS:</b> {nis}", info_style)],
                [Paragraph(f"<b>Responsável familiar:</b> {responsible}", info_style),
                 Paragraph(f"<b>Código INEP:</b> {student_inep}", info_style),
                 Paragraph(f"<b>Série:</b> {serie}", info_style)]
            ]
            header_table = Table(student_header, colWidths=[8*cm, 4.5*cm, 4.5*cm])
            header_table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('BACKGROUND', (0, 0), (-1, -1), colors.Color(0.95, 0.95, 0.95)),
            ]))
            elements.append(header_table)

            freq_header = [Paragraph("<b>Mês</b>", cell_center),
                          Paragraph("<b>Frequência</b>", cell_center),
                          Paragraph("<b>Motivo</b>", cell_center)]
            freq_data = [freq_header]

            for m in months_range:
                key = f"{student['id']}_{m}"
                rec = record_map.get(key, {})
                motive_val = rec.get("motive", "")

                school_days = monthly_school_days.get(m, 0)
                presences = (student_presence.get(student["id"]) or {}).get(m, 0)
                freq_pct = ""
                if school_days > 0:
                    freq_pct = f"{round((presences / school_days) * 100, 1)}%"

                freq_data.append([
                    Paragraph(MESES_PT.get(m, str(m)), cell_center),
                    Paragraph(freq_pct, cell_center),
                    Paragraph(motive_val, cell_style)
                ])

            freq_table = Table(freq_data, colWidths=[3.5*cm, 3.5*cm, 10*cm])
            freq_table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.85, 0.85, 0.85)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(freq_table)
            elements.append(Spacer(1, 8))

        elements.append(Spacer(1, 20))
        elements.append(Paragraph("_" * 60, sign_style))
        if secretario:
            elements.append(Paragraph(f"Validado digitalmente por {secretario}", sign_style))
        else:
            elements.append(Paragraph("Assinatura do Responsável pelas Informações na Escola", sign_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer

    return router
