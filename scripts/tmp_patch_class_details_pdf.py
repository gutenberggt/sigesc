from pathlib import Path


# 1) class_details.py: usar o mesmo roster canônico na tela e no PDF.
router_path = Path("backend/routers/class_details.py")
router_text = router_path.read_text(encoding="utf-8")

import_anchor = "from pdf_generator import generate_class_details_pdf\n"
import_line = "from services.class_details_roster import build_class_students\n"
if import_line not in router_text:
    if router_text.count(import_anchor) != 1:
        raise SystemExit(f"class_details import anchor count={router_text.count(import_anchor)}")
    router_text = router_text.replace(import_anchor, import_anchor + import_line, 1)

start_marker = "        # Busca alunos matriculados - usando múltiplas fontes para maior robustez\n"
series_marker = "        # Calcula contagem por série para turmas multisseriadas\n"
pdf_try_marker = "        try:\n            pdf_buffer = generate_class_details_pdf(\n"

if router_text.count(start_marker) != 2:
    raise SystemExit(f"class_details roster block count={router_text.count(start_marker)}")

first_start = router_text.index(start_marker)
first_end = router_text.index(series_marker, first_start)
first_replacement = (
    "        # Roster canônico compartilhado com o PDF. Inclui estudantes que já\n"
    "        # pertenceram à turma (transferidos, remanejados, progredidos,\n"
    "        # desistentes e reclassificados), preservando a série da matrícula.\n"
    "        students_list = await build_class_students(db, class_doc)\n\n"
)
router_text = router_text[:first_start] + first_replacement + router_text[first_end:]

second_start = router_text.index(start_marker)
second_end = router_text.index(pdf_try_marker, second_start)
second_replacement = (
    "        # O PDF usa exatamente o mesmo roster canônico da tela Detalhes da Turma.\n"
    "        # Matrículas canceladas permanecem fora e seguem na visão de auditoria.\n"
    "        students_list = await build_class_students(db, class_doc)\n\n"
)
router_text = router_text[:second_start] + second_replacement + router_text[second_end:]
router_path.write_text(router_text, encoding="utf-8")


# 2) turma.py: coluna Série apenas para turma multisseriada e rótulo de movimentação.
pdf_path = Path("backend/pdf/turma.py")
pdf_text = pdf_path.read_text(encoding="utf-8")
block_start_marker = "    # ===== ALUNOS MATRICULADOS =====\n"
block_end_marker = "    # Gerar PDF\n"
if pdf_text.count(block_start_marker) != 1 or pdf_text.count(block_end_marker) != 1:
    raise SystemExit("turma.py student table anchors invalid")

block_start = pdf_text.index(block_start_marker)
block_end = pdf_text.index(block_end_marker, block_start)
new_block = '''    # ===== ALUNOS MATRICULADOS =====
    elements.append(section_header(f"ESTUDANTES MATRICULADOS ({len(students)})"))

    if students:
        is_multi_grade = bool(class_info.get('is_multi_grade'))
        num_header_style = ParagraphStyle(
            'THNum',
            fontSize=8,
            fontName='Helvetica-Bold',
            textColor=colors.white,
            alignment=TA_CENTER,
        )
        s_header = [
            Paragraph('#', num_header_style),
            Paragraph('Estudante', th_style),
        ]
        if is_multi_grade:
            s_header.append(Paragraph('Série', th_style))
        s_header.extend([
            Paragraph('Data Nasc.', th_style),
            Paragraph('Responsável', th_style),
            Paragraph('Celular', th_style),
        ])
        s_data = [s_header]

        for idx, student in enumerate(students, 1):
            birth_date = student.get('birth_date', '')
            if birth_date:
                try:
                    if isinstance(birth_date, str) and '-' in birth_date:
                        parts = birth_date.split('T')[0].split('-')
                        if len(parts) == 3:
                            birth_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
                except Exception:
                    pass

            num_style = ParagraphStyle('TDNum', fontSize=8, textColor=TEXT_DARK, alignment=TA_CENTER)
            student_name = xml_escape(student.get('full_name', '-') or '-')
            action_label = student.get('action_label') or ''
            if action_label:
                student_name += (
                    f' <font color="#c2410c"><b>({xml_escape(str(action_label))})</b></font>'
                )

            row = [
                Paragraph(str(idx), num_style),
                Paragraph(student_name, td_style),
            ]
            if is_multi_grade:
                row.append(
                    Paragraph(
                        xml_escape(str(student.get('student_series') or 'N/D')),
                        td_style,
                    )
                )
            row.extend([
                Paragraph(xml_escape(str(birth_date or '-')), td_style),
                Paragraph(xml_escape(student.get('guardian_name', '-') or '-'), td_style),
                Paragraph(xml_escape(student.get('guardian_phone', '-') or '-'), td_style),
            ])
            s_data.append(row)

        if is_multi_grade:
            # Mantém A4 em retrato, redistribuindo somente a tabela de estudantes.
            col_widths = [0.8*cm, 4.9*cm, 2.0*cm, 2.0*cm, 5.5*cm, 2.8*cm]
        else:
            # Preserva o layout anterior para turmas não multisseriadas.
            col_widths = [1*cm, 6*cm, 2.2*cm, usable_width - 12.8*cm, 2.6*cm]

        s_table = Table(s_data, colWidths=col_widths, repeatRows=1)
        s_styles = [
            ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(s_data)):
            if i % 2 == 0:
                s_styles.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
        s_table.setStyle(TableStyle(s_styles))
        elements.append(s_table)
    else:
        no_data_style = ParagraphStyle('NoData2', fontSize=9, textColor=TEXT_MUTED, alignment=TA_CENTER)
        elements.append(Paragraph("Nenhum estudante matriculado", no_data_style))

'''
pdf_text = pdf_text[:block_start] + new_block + pdf_text[block_end:]
pdf_path.write_text(pdf_text, encoding="utf-8")

print("CLASS_DETAILS_PDF_PATCH_APPLIED")
