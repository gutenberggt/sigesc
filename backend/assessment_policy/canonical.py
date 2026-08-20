"""Canonicalização determinística da Assessment Policy v1."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .models import AssessmentPolicy


RULE_PAYLOAD_FIELDS = (
    "mantenedora_id",
    "academic_year",
    "effective_from",
    "effective_until",
    "scope",
    "assessment",
    "recovery",
    "academic_outcome",
    "parent_policy",
)


def canonical_rule_payload(policy: AssessmentPolicy) -> Dict[str, Any]:
    """Retorna somente os campos que alteram a resolução/cálculo da política.

    Metadados administrativos (nome, autores, timestamps, status, fontes
    normativas e o próprio hash) ficam fora do hash das regras. Assim, a mesma
    regra efetiva produz o mesmo hash independentemente de quem a publicou.
    """

    raw = policy.model_dump(mode="json")
    return {field: raw.get(field) for field in RULE_PAYLOAD_FIELDS}


def canonical_rule_json(policy: AssessmentPolicy) -> str:
    """JSON estável usado como entrada do SHA-256."""

    return json.dumps(
        canonical_rule_payload(policy),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def calculate_rule_hash(policy: AssessmentPolicy) -> str:
    """Calcula `sha256:<hex>` para a regra efetiva da política."""

    digest = hashlib.sha256(canonical_rule_json(policy).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
