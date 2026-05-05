"""Normalização leve de texto na ENTRADA (POST/PUT) — Mai/2026.

Função única: detectar se o usuário enviou um campo de texto livre em
CAIXA ALTA e converter para sentence case ANTES de gravar no banco.

Política (decisão proprietário):
- Aplica-se APENAS aos campos da whitelist explícita por coleção
  (mesma whitelist do `/admin/content-review`).
- Reusa heurísticas defensivas e o conversor `to_sentence_case` do
  script `scripts/normalize_content.py` — ZERO duplicação de regras.
- Se o texto cair em alguma heurística defensiva (lista, romano,
  estrutura enumerada), preserva o original SEM tocar.
- Se já estiver em sentence case, retorna inalterado.

NÃO toca em AEE, BNCC, learning_objects.{methodology, evidencia, resources},
nem em campos nominais (esses são tratados pelos models Pydantic e por
`scripts/normalize_names_back.py`).

Uso típico em routers:

    from utils.text_normalize import normalize_input_fields, INPUT_WHITELIST

    payload_dict = body.model_dump(exclude_unset=True)
    payload_dict = normalize_input_fields(payload_dict, "students")
    await db.students.update_one({"id": id}, {"$set": payload_dict})
"""
from __future__ import annotations

from typing import Any, Dict, Set

from scripts.normalize_content import (
    is_likely_caps,
    should_skip_text,
    to_sentence_case,
)

# Whitelist de campos onde a normalização leve é aplicada na entrada.
# Mantenha em sync com `routers/content_review.py::WHITELIST` e
# `scripts/normalize_content.py::CONTENT_FIELDS_BY_COLLECTION`.
INPUT_WHITELIST: Dict[str, Set[str]] = {
    "students": {"observations"},
    "student_history": {"observations"},
    "enrollments": {"observations"},
    "staff": {"observacoes"},
    "learning_objects": {"content", "methodology", "pratica_pedagogica", "observations"},
}


def normalize_input_text(value: Any) -> Any:
    """Normaliza um único campo se for string em CAPS narrativa."""
    if not isinstance(value, str) or not value.strip():
        return value
    if not is_likely_caps(value):
        return value
    if should_skip_text(value):
        return value  # bate em heurística defensiva → preserva
    new_value = to_sentence_case(value)
    return new_value if new_value != value else value


def normalize_input_fields(payload: Dict[str, Any], collection: str) -> Dict[str, Any]:
    """Aplica normalize_input_text aos campos whitelistados da `collection`.

    Modifica e retorna o mesmo dict (para encadeamento). Campos ausentes
    no payload são ignorados.
    """
    if not isinstance(payload, dict):
        return payload
    fields = INPUT_WHITELIST.get(collection)
    if not fields:
        return payload
    for f in fields:
        if f in payload:
            payload[f] = normalize_input_text(payload[f])
    return payload
