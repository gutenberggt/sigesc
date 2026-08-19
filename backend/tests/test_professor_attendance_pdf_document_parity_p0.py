"""Regressão P0 — PDF DVD deve espelhar metadados documentais do Admin."""

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
PDF_PARITY = BACKEND / "routers" / "attendance_pdf_dvd_parity.py"
ROUTERS_INIT = BACKEND / "routers" / "__init__.py"


def test_pdf_dvd_uses_authoritative_class_document_for_multigrade_series():
    source = PDF_PARITY.read_text(encoding="utf-8")

    assert "current_db.classes.find_one" in source
    assert 'class_info = _canonical_pdf_class_info(class_info, context)' in source
    assert "class_info=class_info" in source


def test_pdf_dvd_reuses_official_multi_teacher_helper_and_renderer_contract():
    source = PDF_PARITY.read_text(encoding="utf-8")

    assert "get_multi_teacher_names_for_pdf" in source
    assert "teacher_names = await get_multi_teacher_names_for_pdf" in source
    assert "teacher_names=teacher_names or None" in source
    assert "generate_relatorio_frequencia_bimestre_pdf" in source


def test_pdf_document_parity_adapter_is_installed_after_dvd_tabs():
    source = ROUTERS_INIT.read_text(encoding="utf-8")

    assert "from .attendance_pdf_dvd_parity import install_attendance_pdf_dvd_parity" in source
    assert "configured = install_attendance_tabs_dvd_adapter" in source
    assert "return install_attendance_pdf_dvd_parity" in source


def test_pdf_parity_does_not_write_or_migrate_attendance():
    source = PDF_PARITY.read_text(encoding="utf-8")

    forbidden = (
        ".insert_one(",
        ".update_one(",
        ".delete_one(",
        ".replace_one(",
        "bulk_write(",
    )
    for token in forbidden:
        assert token not in source
