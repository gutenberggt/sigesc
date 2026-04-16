"""
Router para Acompanhamento de Frequência - Bolsa Família.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone, date
import logging
import io

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

    @router.get("/bolsa-familia/students")
    async def list_bolsa_familia_students(
        request: Request,
        school_id: str = Query(...),
        academic_year: Optional[int] = None
    ):
        """Lista alunos com Bolsa Família de uma escola."""
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Buscar alunos ativos com Bolsa Família
        query = {
            "school_id": school_id,
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]}
        }

        students = await db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "nis": 1,
             "mother_name": 1, "father_name": 1, "class_id": 1, "school_id": 1,
             "inep_code": 1, "mother_phone": 1, "father_phone": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(10000)

        # Buscar turmas para série
        class_ids = list(set(s.get("class_id") for s in students if s.get("class_id")))
        classes = await db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "grade_level": 1}).to_list(1000)
        class_map = {c["id"]: c for c in classes}

        # Buscar dados de motivo salvos
        bf_records = await db.bolsa_familia_tracking.find(
            {"school_id": school_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(10000)
        record_map = {}
        for r in bf_records:
            key = f"{r['student_id']}_{r['month']}"
            record_map[key] = r

        result = []
        for s in students:
            cls = class_map.get(s.get("class_id"), {})
            student_data = {
                "id": s["id"],
                "full_name": s["full_name"],
                "birth_date": s.get("birth_date", ""),
                "nis": s.get("nis", ""),
                "responsible": s.get("mother_name") or s.get("father_name") or "",
                "contact": s.get("mother_phone") or s.get("father_phone") or "",
                "series": cls.get("grade_level") or cls.get("name", ""),
                "class_name": cls.get("name", ""),
                "inep_code": s.get("inep_code", ""),
                "months": {}
            }

            # Preencher dados de cada mês
            for m in range(1, 13):
                key = f"{s['id']}_{m}"
                rec = record_map.get(key, {})
                student_data["months"][str(m)] = {
                    "frequency": rec.get("frequency", ""),
                    "motive": rec.get("motive", ""),
                    "not_found": rec.get("not_found", False)
                }

            result.append(student_data)

        return {"students": result, "total": len(result)}

    @router.put("/bolsa-familia/tracking")
    async def save_tracking(request: Request):
        """Salva dados de acompanhamento (motivo, frequência)."""
        await AuthMiddleware.get_current_user(request)

        body = await request.json()
        student_id = body.get("student_id")
        school_id = body.get("school_id")
        month = body.get("month")
        academic_year = body.get("academic_year", datetime.now().year)
        motive = body.get("motive", "")
        frequency = body.get("frequency", "")
        not_found = body.get("not_found", False)

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
                "frequency": frequency,
                "not_found": not_found,
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
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        # Buscar alunos
        query = {
            "school_id": school_id,
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]}
        }
        students = await db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "nis": 1,
             "mother_name": 1, "father_name": 1, "class_id": 1,
             "mother_phone": 1, "father_phone": 1, "inep_code": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(10000)

        if not students:
            raise HTTPException(status_code=404, detail="Nenhum aluno com Bolsa Família encontrado nesta escola")

        class_ids = list(set(s.get("class_id") for s in students if s.get("class_id")))
        classes = await db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "grade_level": 1}).to_list(1000)
        class_map = {c["id"]: c for c in classes}

        # Buscar tracking records
        bf_records = await db.bolsa_familia_tracking.find(
            {"school_id": school_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(10000)
        record_map = {}
        for r in bf_records:
            key = f"{r['student_id']}_{r['month']}"
            record_map[key] = r

        # Buscar secretário
        secretario = school.get("secretario_escolar") or ""

        # Buscar frequência real dos alunos
        months_range = list(range(month_start, month_end + 1))

        # Gerar PDF
        try:
            pdf_buffer = _generate_bf_pdf(
                school=school,
                students=students,
                class_map=class_map,
                record_map=record_map,
                months_range=months_range,
                academic_year=academic_year,
                secretario=secretario
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

    def _generate_bf_pdf(school, students, class_map, record_map, months_range, academic_year, secretario):
        """Gera o PDF de acompanhamento Bolsa Família."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm, cm
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
        elements = []

        # Estilos
        title_style = ParagraphStyle('BFTitle', fontSize=12, fontName='Helvetica-Bold', alignment=TA_CENTER, leading=14, spaceAfter=4)
        subtitle_style = ParagraphStyle('BFSubtitle', fontSize=8, alignment=TA_CENTER, leading=10, spaceAfter=2)
        info_style = ParagraphStyle('BFInfo', fontSize=7, leading=9, alignment=TA_LEFT)
        info_bold = ParagraphStyle('BFInfoBold', fontSize=7, fontName='Helvetica-Bold', leading=9, alignment=TA_LEFT)
        small_style = ParagraphStyle('BFSmall', fontSize=6, leading=7, alignment=TA_LEFT)
        cell_style = ParagraphStyle('BFCell', fontSize=6.5, leading=8, alignment=TA_LEFT)
        cell_center = ParagraphStyle('BFCellCenter', fontSize=6.5, leading=8, alignment=TA_CENTER)
        sign_style = ParagraphStyle('BFSign', fontSize=8, alignment=TA_CENTER, leading=10)

        # Título
        elements.append(Paragraph("Acompanhamento de Frequência Escolar", title_style))
        elements.append(Spacer(1, 4))

        # Dados da escola
        school_name = school.get('name', '')
        inep = school.get('inep_code', '')
        uf = school.get('uf', 'PA')

        school_data = [
            [Paragraph(f"<b>Nome da Escola:</b> {school_name}", info_style),
             Paragraph(f"<b>Código INEP:</b> {inep}", info_style),
             Paragraph(f"<b>Dep. Adm.:</b> Municipal", info_style),
             Paragraph(f"<b>UF:</b> {uf}", info_style)]
        ]
        school_table = Table(school_data, colWidths=[8*cm, 4*cm, 3*cm, 2*cm])
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

        # Meses do período
        month_names = [MESES_PT.get(m, '') for m in months_range]

        # Tabela de alunos
        for idx, student in enumerate(students):
            cls = class_map.get(student.get("class_id"), {})
            serie = cls.get("grade_level") or cls.get("name", "")
            birth = student.get("birth_date", "")
            if isinstance(birth, str) and "-" in birth:
                try:
                    from datetime import datetime as dt
                    bd = dt.strptime(birth.split("T")[0], "%Y-%m-%d")
                    birth = bd.strftime("%d/%m/%Y")
                except:
                    pass
            nis = student.get("nis", "")
            responsible = student.get("mother_name") or student.get("father_name") or ""
            contact = student.get("mother_phone") or student.get("father_phone") or ""

            # Cabeçalho do aluno
            student_header = [
                [Paragraph(f"<b>Nome do Estudante:</b> {student['full_name']}", info_style),
                 Paragraph(f"<b>Dt. Nasc.:</b> {birth}", info_style),
                 Paragraph(f"<b>NIS:</b> {nis}", info_style)],
                [Paragraph(f"<b>Responsável familiar:</b> {responsible}", info_style),
                 Paragraph(f"<b>Contato:</b> {contact}", info_style),
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

            # Tabela de frequência mensal
            freq_header = [Paragraph("<b>Mês</b>", cell_center),
                          Paragraph("<b>Frequência</b>", cell_center),
                          Paragraph("<b>Motivo</b>", cell_center),
                          Paragraph("<b>Não localizado</b>", cell_center)]
            freq_data = [freq_header]

            for m in months_range:
                key = f"{student['id']}_{m}"
                rec = record_map.get(key, {})
                freq_val = rec.get("frequency", "")
                motive_val = rec.get("motive", "")
                not_found = "X" if rec.get("not_found") else ""

                freq_data.append([
                    Paragraph(MESES_PT.get(m, str(m)), cell_center),
                    Paragraph(str(freq_val), cell_center),
                    Paragraph(motive_val, cell_style),
                    Paragraph(not_found, cell_center)
                ])

            freq_table = Table(freq_data, colWidths=[3*cm, 3*cm, 7*cm, 4*cm])
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

        # Assinatura
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
