"""Contrato puro da Fase 0 — Diário por Vínculo Docente v1.0.

IMPORTANTE:
- Este módulo NÃO está conectado a routers, models, persistência ou cálculos.
- Ele existe para tornar o escopo e as invariantes da Fase 0 executáveis/testáveis.
- A integração funcional começa apenas nas fases seguintes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from utils.serie_canonical import canonicalize_serie


class DiaryProfile(str, Enum):
    REGULAR = "regular"
    INTEGRAL_CONTENT = "integral_content"
    SHARED = "shared"


class AttendanceMode(str, Enum):
    CLASS_DAILY = "class_daily"
    ASSIGNMENT_SESSION = "assignment_session"
    NONE = "none"


class AttendancePurpose(str, Enum):
    OFFICIAL = "official"


class StudentScope(str, Enum):
    ALL = "all"
    GROUP = "group"


class MigrationStatus(str, Enum):
    PENDING = "pending"
    MIGRATED = "migrated"
    NEEDS_REVIEW = "needs_review"


class MigrationSource(str, Enum):
    EXPLICIT_TEACHER_ID = "explicit_teacher_id"
    EXPLICIT_TEACHER_COMPONENT = "explicit_teacher_component"
    UNIQUE_ACTIVE_ASSIGNMENT = "unique_active_assignment"
    AUDIT_ASSIGNMENT = "audit_assignment"
    CREATED_BY_COMPATIBLE = "created_by_compatible"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class DiaryCapabilities:
    attendance_enabled: bool
    attendance_required: bool
    attendance_mode: AttendanceMode
    attendance_purpose: Optional[AttendancePurpose]
    content_enabled: bool
    grades_enabled: bool


PROFILE_CAPABILITIES = {
    DiaryProfile.REGULAR: DiaryCapabilities(
        True,
        True,
        AttendanceMode.CLASS_DAILY,
        AttendancePurpose.OFFICIAL,
        True,
        True,
    ),
    DiaryProfile.INTEGRAL_CONTENT: DiaryCapabilities(
        False,
        False,
        AttendanceMode.NONE,
        None,
        True,
        False,
    ),
    DiaryProfile.SHARED: DiaryCapabilities(
        True,
        True,
        AttendanceMode.ASSIGNMENT_SESSION,
        AttendancePurpose.OFFICIAL,
        True,
        True,
    ),
}

ELIGIBLE_FUNDAMENTAL_SERIES = frozenset({"1º ANO", "2º ANO", "3º ANO", "4º ANO", "5º ANO"})
ELIGIBLE_EJA_SERIES = frozenset({"1ª ETAPA", "2ª ETAPA"})
EJA_INITIAL_LEVELS = frozenset({"eja", "eja_inicial", "eja_anos_iniciais"})
AEE_PROGRAM_VALUES = frozenset({"aee"})


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def canonical_series(grade_level: Optional[str]) -> Optional[str]:
    """Reutiliza a canonicalização institucional já existente no SIGESC."""
    return canonicalize_serie(grade_level)


def is_stage_in_scope(education_level: Optional[str], grade_level: Optional[str]) -> bool:
    """Escopo aprovado: Ed. Infantil, 1º–5º Ano e EJA 1ª/2ª Etapa.

    Na Educação Infantil, `education_level` é a autoridade de enquadramento e o
    rótulo da turma não precisa existir na tabela canônica de séries.
    """
    level = _norm(education_level)
    if level == "educacao_infantil":
        return True
    serie = canonical_series(grade_level)
    if level == "fundamental_anos_iniciais":
        return serie in ELIGIBLE_FUNDAMENTAL_SERIES
    if level in EJA_INITIAL_LEVELS:
        return serie in ELIGIBLE_EJA_SERIES
    return False


def is_aee_program(atendimento_programa: Optional[str]) -> bool:
    """AEE é guardrail negativo explícito e não participa do DVD v1.0."""
    return _norm(atendimento_programa) in AEE_PROGRAM_VALUES


def is_class_in_scope(class_info: Mapping[str, Any]) -> bool:
    if is_aee_program(class_info.get("atendimento_programa")):
        return False
    return is_stage_in_scope(
        class_info.get("education_level") or class_info.get("nivel_ensino"),
        class_info.get("grade_level") or class_info.get("grade"),
    )


def are_multigrade_series_in_scope(
    education_level: Optional[str], student_series: Iterable[Optional[str]]
) -> bool:
    """Só libera uma multisseriada em bloco quando todas as séries são elegíveis.

    No Fundamental/EJA, série vazia ou não reconhecida bloqueia a classificação
    automática. Na Educação Infantil, o nível de ensino é a autoridade de
    enquadramento; os rótulos podem não ser canônicos, mas precisam estar
    preenchidos para evitar migração parcial ou inferida.
    """
    level = _norm(education_level)
    series = list(student_series)
    if not series:
        return False
    if level == "educacao_infantil":
        return all(bool(str(s or "").strip()) for s in series)
    return all(is_stage_in_scope(level, s) for s in series)


def capabilities_for(profile: DiaryProfile | str) -> DiaryCapabilities:
    return PROFILE_CAPABILITIES[DiaryProfile(profile)]


def is_explicitly_official_attendance(
    purpose: AttendancePurpose | str | None,
) -> bool:
    """Regra positiva: somente `official` é frequência acadêmica.

    Registros legados sem o campo serão tratados por compatibilidade/migração
    nas fases posteriores; este contrato puro não promove None para official.
    Valores futuros/desconhecidos também não são promovidos implicitamente.
    """
    if purpose is None:
        return False
    try:
        return AttendancePurpose(purpose) is AttendancePurpose.OFFICIAL
    except ValueError:
        return False
