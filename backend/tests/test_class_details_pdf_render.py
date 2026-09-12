from pdf import turma as turma_pdf
from pdf.turma import generate_class_details_pdf


def _text(cell):
    if hasattr(cell, "getPlainText"):
        return cell.getPlainText()
    return str(cell)


def _render_and_capture_student_table(monkeypatch, class_info):
    captured = []
    original_table = turma_pdf.Table

    def recording_table(data, *args, **kwargs):
        captured.append(data)
        return original_table(data, *args, **kwargs)

    monkeypatch.setattr(turma_pdf, "get_logo_image", lambda *args, **kwargs: None)
    monkeypatch.setattr(turma_pdf, "Table", recording_table)

    buffer = generate_class_details_pdf(
        class_info=class_info,
        school={"name": "Escola Teste"},
        teachers=[],
        students=[_base_student()],
        mantenedora={"nome": "Prefeitura Teste", "secretaria": "Secretaria de Educação"},
    )

    assert buffer.getbuffer().nbytes > 0
    for table in captured:
        if table and table[0] and "Estudante" in [_text(cell) for cell in table[0]]:
            return table
    raise AssertionError("Tabela de estudantes não encontrada durante a renderização")


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
    table = _render_and_capture_student_table(monkeypatch, _class_info(False))

    assert [_text(cell) for cell in table[0]] == [
        "#",
        "Estudante",
        "Data Nasc.",
        "Responsável",
        "Celular",
    ]
    assert "Transferido" in " ".join(_text(cell) for row in table for cell in row)


def test_pdf_multigrade_class_adds_series_column(monkeypatch):
    table = _render_and_capture_student_table(monkeypatch, _class_info(True))

    assert [_text(cell) for cell in table[0]] == [
        "#",
        "Estudante",
        "Série",
        "Data Nasc.",
        "Responsável",
        "Celular",
    ]
    assert _text(table[1][2]) == "6º ANO"
    assert "Transferido" in " ".join(_text(cell) for row in table for cell in row)
