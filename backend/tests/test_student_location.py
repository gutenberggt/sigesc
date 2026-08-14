import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.student_location import normalize_student_address_location


def test_blank_locations_become_none_and_other_fields_are_preserved():
    result = normalize_student_address_location({
        'city': 'Floresta do Araguaia',
        'geographic_location': '  ',
        'differentiated_location': '',
    })
    assert result['city'] == 'Floresta do Araguaia'
    assert result['geographic_location'] is None
    assert result['differentiated_location'] is None


def test_explicit_no_differentiated_location_is_preserved():
    result = normalize_student_address_location({
        'geographic_location': 'urbana',
        'differentiated_location': 'nao_se_aplica',
    })
    assert result['geographic_location'] == 'urbana'
    assert result['differentiated_location'] == 'nao_se_aplica'


def test_known_differentiated_location_is_accepted():
    result = normalize_student_address_location({
        'geographic_location': 'rural',
        'differentiated_location': 'comunidade_quilombola',
    })
    assert result['geographic_location'] == 'rural'
    assert result['differentiated_location'] == 'comunidade_quilombola'


@pytest.mark.parametrize('field,value', [
    ('geographic_location', 'metropolitana'),
    ('differentiated_location', 'valor_desconhecido'),
])
def test_unknown_location_values_are_rejected(field, value):
    payload = {
        'geographic_location': 'urbana',
        'differentiated_location': 'nao_se_aplica',
    }
    payload[field] = value
    with pytest.raises(ValueError):
        normalize_student_address_location(payload)
