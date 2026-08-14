"""Domínio canônico interno para localização residencial do estudante.

Os códigos abaixo pertencem ao domínio SIGESC. O mapper CMDE será responsável
por convertê-los para o contrato oficial vigente, sem acoplar o cadastro ao MEC.
"""
from __future__ import annotations

GEOGRAPHIC_LOCATIONS = {"urbana", "rural"}
DIFFERENTIATED_LOCATIONS = {
    "nao_se_aplica",
    "area_assentamento",
    "terra_indigena",
    "comunidade_quilombola",
    "povos_comunidades_tradicionais",
}


def _blank_to_none(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_student_address_location(address: dict | None) -> dict | None:
    """Normaliza/valida apenas os campos territoriais de um endereço.

    Mantém os demais componentes do endereço intactos. ``None`` significa dado
    não informado e permanece distinto de ``nao_se_aplica`` para localização
    diferenciada explicitamente inexistente.
    """
    if address is None:
        return None

    normalized = dict(address)
    geographic = _blank_to_none(normalized.get("geographic_location"))
    differentiated = _blank_to_none(normalized.get("differentiated_location"))

    if geographic not in {None, *GEOGRAPHIC_LOCATIONS}:
        raise ValueError("Localização geográfica inválida")
    if differentiated not in {None, *DIFFERENTIATED_LOCATIONS}:
        raise ValueError("Localização diferenciada inválida")

    normalized["geographic_location"] = geographic
    normalized["differentiated_location"] = differentiated
    return normalized
