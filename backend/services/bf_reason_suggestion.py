"""Suggestion Engine determinística para Motivos MEC do Bolsa Família.

Fase 2 (Fev/2026) — Owner spec:
  - Regras EXPLÍCITAS, AUDITÁVEIS, DETERMINÍSTICAS.
  - ZERO IA, ZERO ML, ZERO scoring probabilístico.
  - Toda sugestão deve ser EXPLICÁVEL (rules_triggered + human_explanation).

Escopo mínimo desta primeira versão:
  R1) ≥50% das ausências do mês têm atestado médico → sugerir `1a` (HEALTH).
  R2) (RESERVADO — depende de absence_type granular que ainda não existe).
      Hook deixado pronto para Layer 2 futura.
  R3) Se reason atualmente selecionado tem `severity_level >= 5` →
      `requires_followup_flag = True` (encaminhar para Busca Ativa).

Características arquiteturais:
  - **Lógica pura**: módulo NÃO faz I/O. Recebe tudo via parâmetros.
  - **Idempotente**: mesma entrada → mesma saída sempre.
  - **Confidence determinística**: baseada em proporção observada,
    NÃO em estatística probabilística.
  - **Rastreabilidade**: cada regra que dispara aparece em `rules_triggered`
    junto com os dados que a justificaram.
"""
from typing import Optional


# Versão do contrato — bump quando regras mudam (para audit log).
SUGGESTION_ENGINE_VERSION = "1.0"

# Threshold canônico das regras de proporção.
PROPORTION_THRESHOLD = 0.50

# Severity level a partir do qual o caso é flagado para acompanhamento.
SEVERITY_FOLLOWUP_THRESHOLD = 5


def suggest_reason_for_month(
    *,
    medical_days_count: int = 0,
    valid_absences: int = 0,
    school_days: int = 0,
    frequency_percentage: Optional[float] = None,
    reasons_by_subcode: Optional[dict] = None,
    current_reason: Optional[dict] = None,
) -> dict:
    """Calcula sugestão MEC para um par (aluno, mês).

    Args:
      medical_days_count: nº de dias com atestado médico no mês.
      valid_absences: nº de faltas válidas (já descontadas atestado e J).
      school_days: nº de dias letivos do mês.
      frequency_percentage: % de frequência válida calculada. None se desconhecido.
      reasons_by_subcode: `{"1a": {id, name, group_id, severity_level, ...}, ...}`
        Permite à engine resolver subcode → id sem fazer I/O.
      current_reason: motivo já selecionado pelo operador (dict completo)
        — usado APENAS pela R3 (severity flag); não influencia R1/R2.

    Returns:
      Dict com shape canônico:
      ```
      {
        "engine_version": "1.0",
        "suggested_reason_id": str | None,
        "suggested_reason_subcode": str | None,
        "confidence": float (0.0–1.0),  # proporção determinística que disparou a regra
        "rules_triggered": [
          {"code": "R1_MEDICAL_DAYS_GTE_50PCT", "value": 0.80, "threshold": 0.5}
        ],
        "requires_followup_flag": bool,
        "human_explanation": str,  # pronto para UI
        "should_show_suggestion": bool  # útil para frontend decidir
      }
      ```
    """
    reasons_by_subcode = reasons_by_subcode or {}
    rules_triggered: list = []
    suggested_reason_id: Optional[str] = None
    suggested_reason_subcode: Optional[str] = None
    confidence: float = 0.0
    explanations: list = []

    # ----- R3 (severity flag) — independente das outras regras -----
    requires_followup_flag = False
    if current_reason and isinstance(current_reason, dict):
        sev = current_reason.get("severity_level", 0) or 0
        try:
            sev_int = int(sev)
        except (TypeError, ValueError):
            sev_int = 0
        if sev_int >= SEVERITY_FOLLOWUP_THRESHOLD:
            requires_followup_flag = True
            rules_triggered.append({
                "code": "R3_HIGH_SEVERITY",
                "value": sev_int,
                "threshold": SEVERITY_FOLLOWUP_THRESHOLD,
            })
            explanations.append(
                f"Motivo selecionado tem severidade {sev_int} "
                f"(≥ {SEVERITY_FOLLOWUP_THRESHOLD}) — encaminhar para Busca Ativa."
            )

    # ----- R1 (atestados médicos) -----
    # Denominador: faltas válidas + atestado (= total de ausências observadas).
    # Evita divisão por zero e regra prematura quando aluno foi 100% presente.
    total_absences_observed = (valid_absences or 0) + (medical_days_count or 0)
    if total_absences_observed > 0 and medical_days_count > 0:
        medical_ratio = medical_days_count / total_absences_observed
        if medical_ratio >= PROPORTION_THRESHOLD:
            reason_1a = reasons_by_subcode.get("1a")
            if reason_1a:
                suggested_reason_id = reason_1a.get("id")
                suggested_reason_subcode = "1a"
                confidence = round(medical_ratio, 2)
                rules_triggered.append({
                    "code": "R1_MEDICAL_DAYS_GTE_50PCT",
                    "value": confidence,
                    "threshold": PROPORTION_THRESHOLD,
                    "medical_days": medical_days_count,
                    "total_absences_observed": total_absences_observed,
                })
                explanations.append(
                    f"{medical_days_count} de {total_absences_observed} ausências "
                    f"({int(confidence * 100)}%) têm atestado médico — "
                    f"sugerido '1a — Doença/problemas físicos'."
                )

    # ----- R2 (transporte) — RESERVADO -----
    # Hook deixado pronto. Requer `absence_type` granular (Layer 2 futura).
    # Quando habilitado:
    #   if absence_type_counts.get("TRANSPORT", 0) / total_absences_observed >= 0.5:
    #       suggested_reason_id = reasons_by_subcode["3b"]["id"]
    # ...

    # ----- Output canônico -----
    should_show_suggestion = bool(
        suggested_reason_id and not (current_reason and current_reason.get("id") == suggested_reason_id)
    )

    return {
        "engine_version": SUGGESTION_ENGINE_VERSION,
        "suggested_reason_id": suggested_reason_id,
        "suggested_reason_subcode": suggested_reason_subcode,
        "confidence": confidence,
        "rules_triggered": rules_triggered,
        "requires_followup_flag": requires_followup_flag,
        "human_explanation": " ".join(explanations) if explanations else "",
        "should_show_suggestion": should_show_suggestion,
    }
