from PyPDF2 import PdfReader

from pdf.turma import generate_class_details_pdf


def _student_section_text(pdf_buffer):
    pdf_buffer.seek(0)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_buffer).pages)
    marker = "ESTUDANTES MATRICULADOS"
    assert marker in text
    return text.split(marker, 1)[1]


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


def _render(monkeypatch, is_multi_grade):
    monkeypatch.setattr("pdf.turma.get_logo_image", lambda *args, **kwargs: None)
    return generate_class_details_pdf(
        class_info=_class_info(is_multi_grade),
        school={"name": "Escola Teste"},
        teachers=[],
        students=[_base_student()],
        mantenedora={"nome": "Prefeitura Teste", "secretaria": "Secretaria de Educação"},
    )


def test_pdf_regular_class_does_not_add_series_column(monkeypatch):
    section = _student_section_text(_render(monkeypatch, False))

    assert "Estudante" in section
    assert "Data Nasc." in section
    assert "Responsável" in section
    assert "Celular" in section
    assert "Série" not in section
    assert "Transferido" in section


def test_pdf_multigrade_class_adds_series_column(monkeypatch):
    section = _student_section_text(_render(monkeypatch, True))

    assert "Estudante" in section
    assert "Série" in section
    assert "6º ANO" in section
    assert "Transferido" in section
