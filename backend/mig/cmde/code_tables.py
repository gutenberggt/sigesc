"""Tabelas explícitas de conversão SIGESC -> CMDEB v2.

Fase B.2 da interoperabilidade Student + Enrollment.

Regras de segurança semântica:
- somente equivalências confirmadas podem produzir código CMDE;
- exemplos de payload NÃO são usados como legenda de código;
- valores ``None`` permanecem ``None``;
- valores internos ambíguos geram erro explícito, nunca fallback/default;
- dimensões cuja legenda oficial pública ainda não é inequívoca ficam bloqueadas.

Fonte oficial verificada em 2026-08-14:
API CMDEB v2 (Swagger/ReDoc oficial do MEC Gestão Presente), versão 2.0.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional


CMDE_CODE_TABLES_VERSION = "cmdeb-v2.2026-08-14"
CMDE_OFFICIAL_DOC_VERSION = "2.0.0"


class CmdeCodeMappingError(ValueError):
    """Conversão bloqueada por valor inválido, ambíguo ou tabela não confirmada."""


@dataclass(frozen=True)
class CmdeCodeTable:
    """Descrição imutável de uma dimensão de conversão canônica -> CMDE."""

    name: str
    canonical_field: str
    cmde_field: str
    accepted_values: frozenset[Any]
    mapping: Mapping[Any, int]
    verified: bool
    source_note: str
    blocked_reason: Optional[str] = None
    allow_any_string: bool = False

    def convert(self, value: Any) -> Optional[int]:
        """Converte apenas valores explicitamente confirmados.

        ``None`` nunca é transformado em zero, string vazia ou outro default.
        """
        if value is None:
            return None

        normalized = value.strip().lower() if isinstance(value, str) else value

        if self.allow_any_string:
            if not isinstance(normalized, str) or not normalized:
                raise CmdeCodeMappingError(
                    f"{self.name}: valor canônico inválido: {value!r}"
                )
        elif normalized not in self.accepted_values:
            raise CmdeCodeMappingError(
                f"{self.name}: valor canônico não reconhecido: {value!r}"
            )

        if not self.verified:
            reason = self.blocked_reason or "legenda oficial ainda não confirmada"
            raise CmdeCodeMappingError(
                f"{self.name}: conversão bloqueada ({reason})"
            )

        try:
            return self.mapping[normalized]
        except KeyError as exc:
            raise CmdeCodeMappingError(
                f"{self.name}: valor {value!r} é válido no SIGESC, "
                "mas não possui equivalência CMDE inequívoca"
            ) from exc


def _immutable_mapping(data: Mapping[Any, int]) -> Mapping[Any, int]:
    return MappingProxyType(dict(data))


# Catálogo oficial de situação de matrícula exposto pela API CMDEB v2.
# Este catálogo descreve o CMDE; NÃO significa que todo status SIGESC tenha
# equivalência automática com um destes códigos.
CMDE_ENROLLMENT_STATUS_CATALOG: Mapping[int, str] = MappingProxyType(
    {
        0: "Em andamento",
        1: "Informação Incorreta",
        2: "Transferência para outra unidade escolar dentro da mesma rede",
        3: "Transferência para outra unidade escolar em outra rede pública",
        4: "Transferência para outra unidade escolar em outra rede privada",
        5: "Transferência para outra rede não identificada",
        6: "Evasão",
        7: "Abandono",
        8: "Óbito Informado",
        9: "Reclassificação",
        10: "Aprovado",
        11: "Concluinte",
        12: "Reprovado",
        21: "Transferência entre modalidades (EM <> EJA)",
        22: "Trancamento de matrícula em curso técnico",
    }
)


ENROLLMENT_STATUS = CmdeCodeTable(
    name="situação da matrícula",
    canonical_field="enrollment.status",
    cmde_field="estudante_matricula_situacao",
    accepted_values=frozenset(
        {
            "active",
            "completed",
            "cancelled",
            "transferred",
            "relocated",
            "progressed",
            "dropout",
        }
    ),
    # Única equivalência direta e inequívoca confirmada na B.2.
    mapping=_immutable_mapping({"active": 0}),
    verified=True,
    source_note=(
        "CMDEB v2 GET /api/v2/estudantes: parâmetro situacoes_matricula "
        "publica a legenda oficial completa; situação 0 = Em andamento."
    ),
)


SEX = CmdeCodeTable(
    name="sexo do estudante",
    canonical_field="student.sex",
    cmde_field="estudante_sexo",
    accepted_values=frozenset(
        {"masculino", "feminino", "prefere_nao_informar"}
    ),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note="O OpenAPI v2 expõe o campo e exemplos, mas não uma legenda pública inequívoca.",
    blocked_reason="legenda oficial de estudante_sexo não confirmada",
)


RACE_COLOR = CmdeCodeTable(
    name="raça/cor do estudante",
    canonical_field="student.color_race",
    cmde_field="estudante_raca_cor",
    accepted_values=frozenset(
        {"branca", "preta", "parda", "amarela", "indigena", "nao_declarada"}
    ),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note="O OpenAPI v2 expõe o campo e exemplos, mas não uma legenda pública inequívoca.",
    blocked_reason="legenda oficial de estudante_raca_cor não confirmada",
)


NATIONALITY = CmdeCodeTable(
    name="nacionalidade do estudante",
    canonical_field="student.nationality",
    cmde_field="estudante_nacionalidade",
    accepted_values=frozenset(),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note=(
        "Exemplos públicos do CMDEB v2 usam valores distintos (por exemplo 1 em cadastro "
        "e 76 em resposta), insuficientes para inferir a tabela semântica."
    ),
    blocked_reason="tabela oficial de nacionalidade não confirmada",
    allow_any_string=True,
)


QUILOMBOLA = CmdeCodeTable(
    name="indicador quilombola",
    canonical_field="student.quilombola",
    cmde_field="estudante_quilombola",
    accepted_values=frozenset({True, False}),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note=(
        "O OpenAPI v2 exibe valores diferentes em exemplos de cadastro e resposta; "
        "exemplo não é usado como legenda."
    ),
    blocked_reason="legenda oficial de estudante_quilombola não confirmada",
)


GEOGRAPHIC_LOCATION = CmdeCodeTable(
    name="localização geográfica",
    canonical_field="student.address.geographic_location",
    cmde_field="turma_localizacao",
    accepted_values=frozenset({"urbana", "rural"}),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note=(
        "O OpenAPI v2 utiliza turma_localizacao em payloads, porém a legenda pública "
        "não foi localizada de forma inequívoca na verificação B.2."
    ),
    blocked_reason="legenda oficial de turma_localizacao não confirmada",
)


DIFFERENTIATED_LOCATION = CmdeCodeTable(
    name="localização diferenciada",
    canonical_field="student.address.differentiated_location",
    cmde_field="localizacao_diferenciada",
    accepted_values=frozenset(
        {
            "nao_se_aplica",
            "area_assentamento",
            "terra_indigena",
            "comunidade_quilombola",
            "povos_comunidades_tradicionais",
        }
    ),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note=(
        "A política pública confirma a existência da dimensão, mas a B.2 não encontrou "
        "legenda numérica pública inequívoca aplicável ao payload de estudante."
    ),
    blocked_reason="legenda oficial de localização diferenciada não confirmada",
)


PEDAGOGICAL_SUPPORT = CmdeCodeTable(
    name="apoio pedagógico",
    canonical_field="enrollment.needs_pedagogical_support",
    cmde_field="estudante_apoio_pedagogico",
    accepted_values=frozenset({True, False}),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note="O OpenAPI v2 expõe o campo e exemplos, sem legenda pública inequívoca.",
    blocked_reason="legenda oficial de estudante_apoio_pedagogico não confirmada",
)


EDUCATION_STAGE = CmdeCodeTable(
    name="etapa de ensino",
    canonical_field="enrollment.education_level + enrollment.grade_level",
    cmde_field="estudante_etapa_de_ensino",
    accepted_values=frozenset(),
    mapping=_immutable_mapping({}),
    verified=False,
    source_note=(
        "O CMDEB v2 aceita códigos de etapa, mas a conversão depende da combinação "
        "nível+série e exige tabela oficial completa antes de habilitação."
    ),
    blocked_reason="tabela oficial completa de etapas não consolidada na B.2",
    allow_any_string=True,
)


CMDE_CODE_TABLES: Mapping[str, CmdeCodeTable] = MappingProxyType(
    {
        "enrollment_status": ENROLLMENT_STATUS,
        "sex": SEX,
        "race_color": RACE_COLOR,
        "nationality": NATIONALITY,
        "quilombola": QUILOMBOLA,
        "geographic_location": GEOGRAPHIC_LOCATION,
        "differentiated_location": DIFFERENTIATED_LOCATION,
        "pedagogical_support": PEDAGOGICAL_SUPPORT,
        "education_stage": EDUCATION_STAGE,
    }
)


def convert_cmde_code(table_name: str, value: Any) -> Optional[int]:
    """Converte uma dimensão registrada, sempre em modo fail-closed."""
    try:
        table = CMDE_CODE_TABLES[table_name]
    except KeyError as exc:
        raise CmdeCodeMappingError(
            f"tabela CMDE desconhecida: {table_name!r}"
        ) from exc
    return table.convert(value)
