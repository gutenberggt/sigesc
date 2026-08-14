"""Regras canônicas da Ficha de Saúde do Estudante."""
from __future__ import annotations

HEALTH_DATA_FIELDS = (
    'blood_type',
    'has_allergies',
    'allergies_description',
    'has_comorbidities',
    'comorbidities_description',
    'uses_continuous_medication',
    'continuous_medication_description',
    'continuous_medication_instructions',
    'individualized_nutritional_need',
    'nutritional_need_details',
    'health_notes',
)

HEALTH_TEXT_FIELDS = (
    'allergies_description',
    'comorbidities_description',
    'continuous_medication_description',
    'continuous_medication_instructions',
    'nutritional_need_details',
    'health_notes',
)

BLOOD_TYPES = ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')

HEALTH_READ_ROLES = {
    'super_admin', 'admin', 'admin_teste', 'gerente', 'secretario', 'diretor'
}
HEALTH_WRITE_ROLES = {
    'super_admin', 'admin', 'admin_teste', 'gerente', 'secretario'
}
SCHOOL_SCOPED_HEALTH_ROLES = {'secretario', 'diretor'}


def blank_profile(student_id: str) -> dict:
    return {
        'student_id': student_id,
        **{field: None for field in HEALTH_DATA_FIELDS},
    }


def normalize_health_payload(data: dict) -> dict:
    """Normaliza campos e impede detalhes órfãos de um estado tri-state."""
    normalized = {field: data.get(field) for field in HEALTH_DATA_FIELDS}

    for field in HEALTH_TEXT_FIELDS:
        value = normalized.get(field)
        if value is not None:
            text = str(value).strip()
            normalized[field] = text or None

    if normalized.get('has_allergies') is not True:
        normalized['allergies_description'] = None
    if normalized.get('has_comorbidities') is not True:
        normalized['comorbidities_description'] = None
    if normalized.get('uses_continuous_medication') is not True:
        normalized['continuous_medication_description'] = None
        normalized['continuous_medication_instructions'] = None
    if normalized.get('individualized_nutritional_need') is not True:
        normalized['nutritional_need_details'] = None

    return normalized


def changed_health_fields(previous: dict | None, incoming: dict) -> list[str]:
    previous = previous or {}
    return [
        field
        for field in HEALTH_DATA_FIELDS
        if previous.get(field) != incoming.get(field)
    ]
