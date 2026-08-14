import pytest

from mig.cmde.code_tables import (
    CMDE_CODE_TABLES,
    CMDE_ENROLLMENT_STATUS_CATALOG,
    CmdeCodeMappingError,
    convert_cmde_code,
)


def test_active_enrollment_maps_to_official_in_progress_code():
    assert convert_cmde_code("enrollment_status", "active") == 0


def test_none_is_never_replaced_by_fictitious_default():
    assert convert_cmde_code("enrollment_status", None) is None
    assert convert_cmde_code("sex", None) is None


def test_official_enrollment_status_catalog_is_explicit():
    assert CMDE_ENROLLMENT_STATUS_CATALOG[0] == "Em andamento"
    assert CMDE_ENROLLMENT_STATUS_CATALOG[2].startswith("Transferência")
    assert CMDE_ENROLLMENT_STATUS_CATALOG[6] == "Evasão"
    assert CMDE_ENROLLMENT_STATUS_CATALOG[7] == "Abandono"
    assert CMDE_ENROLLMENT_STATUS_CATALOG[10] == "Aprovado"
    assert CMDE_ENROLLMENT_STATUS_CATALOG[11] == "Concluinte"
    assert CMDE_ENROLLMENT_STATUS_CATALOG[21].startswith("Transferência entre modalidades")


@pytest.mark.parametrize(
    "status",
    ["completed", "cancelled", "transferred", "relocated", "progressed", "dropout"],
)
def test_ambiguous_sigesc_enrollment_statuses_fail_closed(status):
    with pytest.raises(CmdeCodeMappingError, match="não possui equivalência CMDE inequívoca"):
        convert_cmde_code("enrollment_status", status)


@pytest.mark.parametrize(
    "table_name,value",
    [
        ("sex", "feminino"),
        ("race_color", "parda"),
        ("nationality", "Brasileira"),
        ("quilombola", True),
        ("geographic_location", "urbana"),
        ("differentiated_location", "nao_se_aplica"),
        ("pedagogical_support", True),
        ("education_stage", "fundamental_anos_finais:6º Ano"),
    ],
)
def test_unverified_dimensions_are_blocked_instead_of_guessed(table_name, value):
    with pytest.raises(CmdeCodeMappingError, match="conversão bloqueada"):
        convert_cmde_code(table_name, value)


def test_prefere_nao_informar_is_not_coerced_to_binary_sex_code():
    with pytest.raises(CmdeCodeMappingError, match="conversão bloqueada"):
        convert_cmde_code("sex", "prefere_nao_informar")


def test_unknown_table_and_unknown_canonical_value_fail_explicitly():
    with pytest.raises(CmdeCodeMappingError, match="tabela CMDE desconhecida"):
        convert_cmde_code("does_not_exist", "x")

    with pytest.raises(CmdeCodeMappingError, match="valor canônico não reconhecido"):
        convert_cmde_code("enrollment_status", "invented")


def test_registry_covers_b1_dimensions_without_touching_core_contract():
    assert set(CMDE_CODE_TABLES) == {
        "enrollment_status",
        "sex",
        "race_color",
        "nationality",
        "quilombola",
        "geographic_location",
        "differentiated_location",
        "pedagogical_support",
        "education_stage",
    }
