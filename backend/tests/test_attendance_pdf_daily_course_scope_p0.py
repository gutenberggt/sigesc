"""P0 — PDF diário não pode filtrar Infantil/Anos Iniciais por componente residual.

Regressão do incidente observado em 21/08/2026: o relatório em tela encontrava
os dias de frequência, mas o PDF retornava zero quando a navegação carregava um
`course_id` que não pertence à chave natural de frequência `class_daily`.
"""

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
EXT_DVD = BACKEND / "routers" / "attendance_ext_dvd.py"


def _source() -> str:
    return EXT_DVD.read_text(encoding="utf-8")


def test_daily_pdf_drops_residual_course_filter_before_legacy_renderer_query():
    source = _source()

    assert "def _uses_component_attendance(class_info: dict) -> bool:" in source
    assert "effective_course_id = course_id" in source
    assert "if class_info and not _uses_component_attendance(class_info):" in source
    assert "effective_course_id = None" in source
    assert '"course_id": effective_course_id' in source


def test_component_attendance_levels_keep_course_filter_contract():
    source = _source()

    assert '{"fundamental_anos_finais", "eja_final", "ensino_medio"}' in source


def test_daily_level_inference_covers_infantil_and_first_to_fifth_year():
    source = _source()

    assert 're.search(r"PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL", ref)' in source
    assert 'return int(match.group(1)) >= 6' in source


def test_fix_is_read_only_and_does_not_mutate_attendance():
    source = _source()

    forbidden = (
        ".insert_one(",
        ".update_one(",
        ".delete_one(",
        ".replace_one(",
        "bulk_write(",
    )
    for token in forbidden:
        assert token not in source
