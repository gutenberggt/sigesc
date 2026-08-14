from scripts.backfill_student_ibge_codes import build_student_ibge_patch


MANTENEDORA = {
    'estado': 'PA',
    'codigo_ibge_uf': '15',
    'municipio': 'Floresta do Araguaia',
    'codigo_ibge_municipio': '1502939',
}


def test_fills_missing_codes_for_compatible_legacy_address():
    student = {
        'address': {
            'state': 'PA',
            'city': 'Floresta do Araguaia',
        }
    }

    assert build_student_ibge_patch(student, MANTENEDORA) == {
        'address.state_ibge_code': '15',
        'address.city_ibge_code': '1502939',
    }


def test_does_not_overwrite_existing_codes():
    student = {
        'address': {
            'state': 'PA',
            'state_ibge_code': '17',
            'city': 'Floresta do Araguaia',
            'city_ibge_code': '1700000',
        }
    }

    assert build_student_ibge_patch(student, MANTENEDORA) == {}


def test_skips_municipal_code_when_city_is_different():
    student = {
        'address': {
            'state': 'PA',
            'city': 'Conceição do Araguaia',
        }
    }

    assert build_student_ibge_patch(student, MANTENEDORA) == {
        'address.state_ibge_code': '15',
    }


def test_text_comparison_is_case_and_accent_insensitive():
    student = {
        'address': {
            'state': 'pa',
            'city': 'FLORESTA DO ARAGUAIA',
        }
    }

    assert build_student_ibge_patch(student, MANTENEDORA) == {
        'address.state_ibge_code': '15',
        'address.city_ibge_code': '1502939',
    }
