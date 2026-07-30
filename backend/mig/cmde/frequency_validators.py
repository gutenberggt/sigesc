"""
Regras de prontidão do item de FREQUÊNCIA CMDE (Sprint 002.b).

Independentes de IO. Um item está pronto para envio quando possui INEP da escola e ao menos
um identificador do aluno (CPF ou NIS). A "competência encerrada" é avaliada no nível do lote
(não do item), pelo Batch Builder.
"""
from mig.core.validation import ValidationEngine

READINESS_RULES = [
    ("INEP Escola", lambda r: bool(r.get("school_inep"))),
    ("Identificador (CPF/NIS)", lambda r: bool(r.get("cpf") or r.get("nis"))),
]

_engine = ValidationEngine(READINESS_RULES)


def missing_fields(record: dict) -> list:
    return _engine.missing_fields(record)


def is_ready(record: dict) -> bool:
    return _engine.is_ready(record)
