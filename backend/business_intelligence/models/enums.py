"""Enums do domínio Business Intelligence.

Objetivo: vocabulário único e estável usado por definições, execução e resultados.
Responsabilidade: NÃO conter lógica; apenas valores canônicos.
"""
from enum import Enum


class Grain(str, Enum):
    """Granularidade suportada nativamente pelo Motor (do mais amplo ao mais fino)."""
    REDE = "rede"
    ESCOLA = "escola"
    ETAPA = "etapa"          # nível/etapa de ensino (Infantil, Iniciais, Finais, EJA)
    TURMA = "turma"
    PROFESSOR = "professor"
    ALUNO = "aluno"


class IndicatorCategory(str, Enum):
    RENDIMENTO = "rendimento"
    FREQUENCIA = "frequencia"
    FLUXO = "fluxo"
    DEMOGRAFIA = "demografia"
    CURRICULO = "curriculo"
    COMPARATIVO = "comparativo"
    RISCO = "risco"
    EXTERNO = "externo"


class FormulaType(str, Enum):
    """Tipos declarativos de fórmula (interpretados pelo Resolver/Calculator)."""
    RATIO = "ratio"
    WEIGHTED_AVG = "weighted_avg"
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    COMPOSITE = "composite"   # combina múltiplos indicadores base
    DERIVED = "derived"       # deriva de UM indicador base (ex.: 1 - freq)
    MANUAL = "manual"         # valor inserido (sem cálculo)
    EXTERNAL = "external"     # obtido de fonte externa


class RefreshStrategy(str, Enum):
    REALTIME = "realtime"
    CACHED = "cached"
    MATERIALIZED = "materialized"


class IndicatorStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class Unit(str, Enum):
    PERCENT = "percent"
    COUNT = "count"
    RATIO = "ratio"
    SCORE = "score"
    CURRENCY = "currency"


class KpiDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class KpiStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    """Independência de origem: o Motor consome via Data Providers/adapters."""
    OLTP = "oltp"              # SIGESC (MongoDB)
    EXTERNAL_API = "external_api"  # MEC, INEP, FNDE, IBGE...
    IMPORT = "import"          # CSV/Excel
    MANUAL = "manual"          # cadastro manual


class ResultSource(str, Enum):
    """De onde o resultado foi obtido (rastreabilidade/observabilidade)."""
    MART = "mart"
    CACHE = "cache"
    REALTIME = "realtime"


class ParameterType(str, Enum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    ENUM = "enum"
