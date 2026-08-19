"""Regressão: startup deve delegar índices de frequência ao serviço DVD."""

import inspect

from startup import indexes


def test_startup_delega_indices_de_frequencia_ao_servico_dvd():
    source = inspect.getsource(indexes.create_all_indexes)

    assert "await ensure_attendance_assignment_indexes(db)" in source
    assert 'name="ux_attendance_class_date_course_aula"' not in source


def test_startup_importa_a_autoridade_canonica_de_indices():
    assert (
        indexes.ensure_attendance_assignment_indexes.__module__
        == "services.attendance_assignment_scope"
    )
