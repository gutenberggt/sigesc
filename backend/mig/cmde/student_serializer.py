"""Mapper/Serializer canônico -> payload CMDEB v2 para cadastro sem turma.

Fase B.3 da interoperabilidade Student + Enrollment.

O alvo inicial é deliberadamente específico:
POST /api/v2/estudantes/sem-turma/cadastro/lote

Princípios:
- recebe somente o contrato canônico da B.1 + contexto escolar explícito;
- usa nomes de campos observados no contrato público CMDEB v2;
- não consulta banco, HTTP, fila ou provider;
- não inventa códigos nem defaults;
- não serializa IDs internos do SIGESC;
- não omite silenciosamente dimensões codificadas presentes no canônico cuja
  tabela B.2 ainda esteja bloqueada;
- preserva UTF-8 e não remove acentos/cedilha/til.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field

from mig.cmde.code_tables import CmdeCodeMappingError, convert_cmde_code
from mig.core.canonical_student import CanonicalStudentEnrollmentDTO


CMDE_STUDENT_WITHOUT_CLASS_CREATE_ENDPOINT = (
    "/api/v2/estudantes/sem-turma/cadastro/lote"
)
CMDE_STUDENT_SERIALIZER_VERSION = "cmdeb-v2.student-without-class.create.2026-08-14"


class CmdeStudentSerializationError(ValueError):
    """Payload não pode ser produzido sem perder ou inventar semântica."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CmdeStudentSchoolContext(_FrozenModel):
    """Contexto escolar necessário ao payload e ausente do DTO canônico B.1.

    Os valores devem vir da escola/matrícula vigente. Nenhuma resolução é feita
    dentro do serializer.
    """

    school_inep_code: Optional[str] = None
    school_name: Optional[str] = None


class CmdeStudentWithoutClassRecordDTO(_FrozenModel):
    """Subconjunto confirmado do registro de cadastro sem turma CMDEB v2.

    Campos codificados bloqueados pela B.2 só são incluídos quando a tabela
    correspondente estiver verificada. Na data desta versão, esses campos
    provocam erro antes da criação do DTO quando o canônico contém valor.
    """

    co_entidade: Optional[str] = None
    co_matricula_rede: Optional[str] = None
    data_inicio_matricula: Optional[str] = None

    estudante_bairro_res: Optional[str] = None
    estudante_cep_res: Optional[str] = None
    estudante_co_municipio_res: Optional[int] = None
    estudante_co_uf_res: Optional[int] = None
    estudante_cpf: Optional[str] = None
    estudante_dt_nascimento: Optional[str] = None
    estudante_email: Optional[str] = None
    estudante_logradouro_res: Optional[str] = None
    estudante_nome: Optional[str] = None
    estudante_nu_endereco_res: Optional[str] = None
    estudante_telefone: Optional[str] = None

    # Campos abaixo existem no contrato público, mas só podem ser preenchidos
    # por tabelas B.2 verificadas. Permanecem opcionais no DTO para que o schema
    # espelhe o provider sem criar defaults.
    estudante_apoio_pedagogico: Optional[int] = None
    estudante_etapa_de_ensino: Optional[int] = None
    estudante_nacionalidade: Optional[int] = None
    estudante_quilombola: Optional[int] = None
    estudante_raca_cor: Optional[int] = None
    estudante_sexo: Optional[int] = None

    no_entidade: Optional[str] = None
    nu_ano_matricula: Optional[int] = None


class CmdeStudentWithoutClassBatchDTO(_FrozenModel):
    estudantes: tuple[CmdeStudentWithoutClassRecordDTO, ...] = Field(min_length=1)


def _optional_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _date_ddmmyyyy(value: Any, *, field_name: str) -> Optional[str]:
    """Normaliza somente formatos de data inequívocos aceitos pelo canônico.

    O contrato público de requisição usa DD/MM/AAAA. Aceitamos esse formato ou
    ISO AAAA-MM-DD e nunca tentamos interpretar outras representações.
    """
    text = _optional_text(value)
    if text is None:
        return None

    for source_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, source_format)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue

    raise CmdeStudentSerializationError(
        f"{field_name}: data fora dos formatos suportados DD/MM/AAAA ou AAAA-MM-DD"
    )


def _ibge_code(value: Any, *, field_name: str, digits: int) -> Optional[int]:
    text = _optional_text(value)
    if text is None:
        return None
    if not text.isdigit() or len(text) != digits:
        raise CmdeStudentSerializationError(
            f"{field_name}: código IBGE deve conter exatamente {digits} dígitos"
        )
    return int(text)


def _school_inep(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    if not text.isdigit() or len(text) != 8:
        raise CmdeStudentSerializationError(
            "school_inep_code: código INEP deve conter exatamente 8 dígitos"
        )
    return text


def _convert_if_present(table_name: str, value: Any) -> Optional[int]:
    """Aplica a política B.2 e reexpõe erro com contexto de serialização."""
    if value is None:
        return None
    try:
        return convert_cmde_code(table_name, value)
    except CmdeCodeMappingError as exc:
        raise CmdeStudentSerializationError(str(exc)) from exc


def _education_stage_value(canonical: CanonicalStudentEnrollmentDTO) -> Optional[str]:
    enrollment = canonical.enrollment
    level = _optional_text(enrollment.education_level)
    grade = _optional_text(enrollment.grade_level)
    if level is None and grade is None:
        return None
    return " | ".join(part for part in (level, grade) if part is not None)


def map_canonical_student_without_class(
    canonical: CanonicalStudentEnrollmentDTO,
    *,
    school: Optional[CmdeStudentSchoolContext] = None,
) -> CmdeStudentWithoutClassRecordDTO:
    """Mapeia um contrato canônico para um registro CMDEB sem turma.

    A função é pura. Se o canônico trouxer uma dimensão codificada que a B.2
    ainda não consegue converter com segurança, a serialização é interrompida.
    """
    student = canonical.student
    enrollment = canonical.enrollment
    address = student.address
    school_context = school or CmdeStudentSchoolContext()

    # Guardas fail-closed: valores presentes não podem desaparecer do payload
    # silenciosamente se o CMDE os representa por código ainda não confirmado.
    sex = _convert_if_present("sex", student.sex)
    race_color = _convert_if_present("race_color", student.color_race)
    nationality = _convert_if_present("nationality", student.nationality)
    quilombola = _convert_if_present("quilombola", student.quilombola)
    pedagogical_support = _convert_if_present(
        "pedagogical_support", enrollment.needs_pedagogical_support
    )
    education_stage = _convert_if_present(
        "education_stage", _education_stage_value(canonical)
    )

    if student.student_with_disability is not None:
        raise CmdeStudentSerializationError(
            "student.student_with_disability: conversão CMDE não definida na B.2"
        )

    return CmdeStudentWithoutClassRecordDTO(
        co_entidade=_school_inep(school_context.school_inep_code),
        co_matricula_rede=_optional_text(enrollment.enrollment_number),
        data_inicio_matricula=_date_ddmmyyyy(
            enrollment.enrollment_date,
            field_name="enrollment.enrollment_date",
        ),
        estudante_bairro_res=(
            _optional_text(address.neighborhood) if address is not None else None
        ),
        estudante_cep_res=(
            _optional_text(address.zip_code) if address is not None else None
        ),
        estudante_co_municipio_res=(
            _ibge_code(
                address.city_ibge_code,
                field_name="student.address.city_ibge_code",
                digits=7,
            )
            if address is not None
            else None
        ),
        estudante_co_uf_res=(
            _ibge_code(
                address.state_ibge_code,
                field_name="student.address.state_ibge_code",
                digits=2,
            )
            if address is not None
            else None
        ),
        estudante_cpf=_optional_text(student.cpf),
        estudante_dt_nascimento=_date_ddmmyyyy(
            student.birth_date,
            field_name="student.birth_date",
        ),
        estudante_email=_optional_text(student.email),
        estudante_logradouro_res=(
            _optional_text(address.street) if address is not None else None
        ),
        estudante_nome=_optional_text(student.full_name),
        estudante_nu_endereco_res=(
            _optional_text(address.number) if address is not None else None
        ),
        estudante_telefone=_optional_text(student.phone),
        estudante_apoio_pedagogico=pedagogical_support,
        estudante_etapa_de_ensino=education_stage,
        estudante_nacionalidade=nationality,
        estudante_quilombola=quilombola,
        estudante_raca_cor=race_color,
        estudante_sexo=sex,
        no_entidade=_optional_text(school_context.school_name),
        nu_ano_matricula=enrollment.academic_year,
    )


def serialize_student_without_class_batch(
    records: Iterable[CmdeStudentWithoutClassRecordDTO],
) -> dict[str, Any]:
    """Serializa lote JSON-ready no envelope oficial ``estudantes``.

    ``None`` é removido do JSON; nenhum zero/string vazia é criado para suprir
    ausência. A lista vazia é rejeitada porque o contrato oficial exige array
    não vazio.
    """
    batch = CmdeStudentWithoutClassBatchDTO(estudantes=tuple(records))
    return batch.model_dump(mode="json", exclude_none=True)


def map_and_serialize_student_without_class_batch(
    items: Iterable[
        tuple[CanonicalStudentEnrollmentDTO, Optional[CmdeStudentSchoolContext]]
    ],
) -> dict[str, Any]:
    """Atalho puro para mapear e serializar múltiplos registros."""
    mapped = (
        map_canonical_student_without_class(canonical, school=school)
        for canonical, school in items
    )
    return serialize_student_without_class_batch(mapped)
