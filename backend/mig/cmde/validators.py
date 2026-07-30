"""
Regras de prontidão do CMDE (extraídas de GET /mec/students/mapping).

Independentes de IO. Reproduzem exatamente o comportamento atual:
  - missing_fields avalia CPF, NIS e INEP (da escola);
  - ready = possui CPF E INEP (NIS não bloqueia o envio, apenas é reportado).
"""
from mig.core.validation import ValidationEngine

# (label_faltante, predicado_de_presenca) — a ordem define a ordem em missing_fields
READINESS_RULES = [
    ("CPF", lambda r: bool(r.get("cpf"))),
    ("NIS", lambda r: bool(r.get("nis"))),
    ("INEP Escola", lambda r: bool(r.get("school_inep"))),
]

_engine = ValidationEngine(READINESS_RULES)


def missing_fields(record: dict) -> list:
    return _engine.missing_fields(record)


def is_ready(record: dict) -> bool:
    # Comportamento atual: ready depende de CPF e INEP (não de NIS).
    return bool(record.get("cpf")) and bool(record.get("school_inep"))
