"""
Diary Matching Mode — Fase 10 (Fev/2026).

Resolve falsos positivos de `orphan/inconsistent` no Calendário Operacional
do Diário para etapas onde a grade pedagógica é INTEGRADA (não disciplinar):
  - Educação Infantil
  - Anos Iniciais do Ensino Fundamental
  - EJA — Anos Iniciais
  - Turmas multisseriadas

Conceito institucional aprovado pelo owner:
  - STRICT: comportamento atual (mesma_data + mesmo_slot + mesmo_componente
    + mesmo_professor). Adequado a Anos Finais e Ensino Médio.
  - FLEXIBLE: mesma_data E (mesmo_professor OU mesmo_componente).
    Adequado às etapas pedagogicamente integradas.

NÃO é "afrouxar" o Diário. É reconhecer que a semântica de "slot" só vale
quando a grade é disciplinar de fato.

Regras:
  - Modo é resolvido a partir do campo `diary_matching_mode` na turma
    (quando setado explicitamente) OU inferido a partir da `education_level`
    + `is_multi_grade`.
  - Frontend NUNCA infere ou recalcula. Backend decide.
  - Snapshots congelam o modo usado no momento da publicação.
"""
from __future__ import annotations

MODES = {"strict", "flexible"}

# Valores de `education_level` na base que mapeiam para flexible por default.
# Inclui EJA Anos Iniciais e variações conhecidas. Checagem case-insensitive
# por substring para tolerar diferentes convenções de escrita.
_FLEXIBLE_KEYWORDS = (
    "infantil",            # educacao_infantil, ensino_infantil
    "anos_iniciais",       # fundamental_anos_iniciais, eja_anos_iniciais
    "fundamental_i",       # ensino_fundamental_i
    "creche",
    "pre_escola",
    "pre-escola",
    "preescola",
)


def infer_default_matching_mode(class_doc: dict) -> str:
    """Inferência institucional de default a partir dos campos canônicos da turma.

    Regras (ordem):
      1. Turma multisseriada → flexible (sempre).
      2. education_level que contenha palavra-chave pedagogicamente
         integrada (infantil, anos_iniciais, EJA-Anos Iniciais, creche,
         pré-escola) → flexible.
      3. Caso contrário → strict.
    """
    if not isinstance(class_doc, dict):
        return "strict"

    if class_doc.get("is_multi_grade") is True:
        return "flexible"

    level = (class_doc.get("education_level") or "").lower().strip()
    if not level:
        return "strict"
    for kw in _FLEXIBLE_KEYWORDS:
        if kw in level:
            return "flexible"
    return "strict"


def resolve_matching_mode(class_doc: dict) -> str:
    """Resolve o modo efetivo da turma.

    Prioridade absoluta: campo `diary_matching_mode` persistido na turma.
    Fallback: inferência por etapa pedagógica.

    Esse "fallback de leitura" é diferente de "inferência dinâmica em
    runtime" porque é determinístico, função pura, sem consulta extra.
    Quando o usuário definir explicitamente o modo, ele será respeitado.
    """
    explicit = (class_doc or {}).get("diary_matching_mode")
    if explicit in MODES:
        return explicit
    return infer_default_matching_mode(class_doc)
