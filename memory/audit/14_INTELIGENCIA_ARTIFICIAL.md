# ENTREGA 14 — Inteligência Artificial

⏳ **PENDENTE — Onda 2.** (Resumo preliminar da Onda 1.)

Arquitetura: `services/llm_client.py` — cliente unificado **híbrido**:
`ANTHROPIC_API_KEY` → SDK oficial `anthropic`; senão `EMERGENT_LLM_KEY` →
`emergentintegrations`; senão `None` → **fallback determinístico**. Apenas Claude
(modelo padrão `claude-sonnet-4-5`), texto único system+user (sem streaming/multimodal).
Consumidores: `pmpi_ai.py`, `plano_acao_ai.py`, `monthly_report_service.py`,
motores de risco/diagnóstico. Detalhar: prompts, fluxos, snapshots de análise
(`ai_analysis_snapshots`, `ai_risk_analyses`, `ai_plans`), limitações e oportunidades.
