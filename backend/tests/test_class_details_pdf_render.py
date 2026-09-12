from io import BytesIO

import pdfplumber

from pdf.turma import generate_class_details_pdf


def _student_table(pdf_buffer):
    pdf_buffer.seek(0)
    with pdfplumber.open(pdf_buffer) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if table and table[0] and "Estudante" in table[0]:
                    return table
    raise AssertionError("Tabela de estudantes não encontrada no PDF")


def _base_student():
    return {
        "id": "student-1",
        "full_name": "Ana Teste",
        "student_series": "6º ANO",
        "birth_date": "2013-01-02",
        "guardian_name": "Maria Teste",
        "guardian_phone": "(94) 99999-9999",
        "action_label": "Transferido",
    }


def _class_info(is_multi_grade):
    return {
        "id": "class-1",
        "name": "6º e 7º ANO MULTI" if is_multi_grade else "6º ANO A",
        "academic_year": 2026,
        "education_level": "fundamental_anos_finais",
        "shift": "morning",
        "grade_level": "6º ANO",
        "is_multi_grade": is_multi_grade,
        "series": ["6º ANO", "7º ANO"] if is_multi_grade else [],
    }


def test_pdf_regular_class_does_not_add_series_column(monkeypatch):
    monkeypatch.setattr("pdf.turma.get_logo_image", lambda *args, **kwargs: None)
    buffer = generate_class_details_pdf(
        class_info=_class_info(False),
        school={"name": "Escola Teste"},
        teachers=[],
        students=[_base_student()],
        mantenedora={"nome": "Prefeitura Teste", "secretaria": "Secretaria de Educação"},
    )

    table = _student_table(buffer)
    assert table[0] == ["#", "Estudante", "Data Nasc.", "Responsável", "Celular"]
    assert "Transferido" in " ".join(cell or "" for row in table for cell in row)


def test_pdf_multigrade_class_adds_series_column(monkeypatch):
    monkeypatch.setattr("pdf.turma.get_logo_image", lambda *args, **kwargs: None)
    buffer = generate_class_details_pdf(
        class_info=_class_info(True),
        school={"name": "Escola Teste"},
        teachers=[],
        students=[_base_student()],
        mantenedora={"nome": "Prefeitura Teste", "secretaria": "Secretaria de Educação"},
    )

    table = _student_table(buffer)
    assert table[0] == ["#", "Estudante", "Série", "Data Nasc.", "Responsável", "Celular"]
    assert table[1][2] == "6º ANO"
    assert "Transferido" in " ".join(cell or "" for row in table for cell in row)
