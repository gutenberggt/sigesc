# ENTREGA 14 — Inteligência Artificial (consumindo a camada de BI)

> **Onda 2 · Prioridade #5.** READ-ONLY. Diretriz do arquiteto: a IA **não** deve
> consumir MongoDB nem APIs operacionais diretamente — deve consumir **conhecimento
> estruturado** (indicadores/marts do Motor).

## 1. Arquitetura atual de IA
- **Cliente unificado** `services/llm_client.py` (híbrido): `ANTHROPIC_API_KEY` → SDK
  `anthropic`; senão `EMERGENT_LLM_KEY` → `emergentintegrations`; senão `None` →
  **fallback determinístico**. Modelo padrão `claude-sonnet-4-5`; texto único
  system+user (sem streaming/multimodal).
- **Consumidores atuais:** `pmpi_ai.py`, `plano_acao_ai.py`,
  `monthly_report_service.py`, motores de diagnóstico/risco.
- **Persistência:** `ai_analysis_snapshots`, `ai_risk_analyses`, `ai_plans`.
- **Fallback determinístico:** garante funcionamento sem chave (importante para custo/offline).

## 2. Problema atual (anti-padrão a evitar)
Hoje a IA tende a receber **dados brutos/agregações ad-hoc** montadas em cada router.
Isso a acopla ao OLTP e replica a lógica de indicadores dentro dos prompts/pré-processamento
— violando o SSoT e encarecendo tokens/latência.

## 3. Arquitetura-alvo: IA sobre conhecimento estruturado
```
 OLTP → Motor de Indicadores (SSoT) → Marts → API BI (/api/bi/*)
                                                     │
                                                     ▼
                              ┌───────── Camada de Conhecimento ─────────┐
                              │  "Indicator Context Pack" por escopo:     │
                              │  { indicadores, séries temporais, deltas, │
                              │    metas, benchmarks, alertas }           │
                              └───────────────────┬───────────────────────┘
                                                  ▼
                                     Serviços de IA (Claude)
                              (narrativa, insight, plano de ação, priorização)
                                                  ▼
                              ai_* snapshots (auditável, versionado)
```

## 4. Princípios para a IA na nova geração
1. **IA consome indicadores, não linhas** — o prompt recebe um *Indicator Context Pack*
   (JSON estruturado vindo do Motor), não documentos do Mongo.
2. **SSoT também para a IA** — números citados pela IA são os do Motor (consistência total
   entre dashboard e narrativa da IA).
3. **Determinismo auditável** — toda análise gera snapshot (`ai_analysis_snapshots`) com
   as entradas (indicadores/versão das defs) e a saída.
4. **Fallback preservado** — sem chave/limite, gerar insight determinístico a partir dos
   mesmos indicadores.
5. **Custo/latência** — enviar agregados (não brutos) reduz tokens e melhora qualidade.

## 5. Casos de uso habilitados pela camada de BI
- **Insight executivo automático** (SEMED): "frequência caiu 6pp em 3 escolas rurais;
  distorção idade-série concentrada no 6º ano".
- **Planos de ação assistidos** (`plano_acao_ai`) baseados em indicadores reais + metas.
- **Priorização de intervenções** (risco unificado G1-G3) com justificativa.
- **Relatórios mensais narrados** (`monthly_report_service`) consumindo marts.
- **Q&A sobre a rede** (futuro): perguntas em linguagem natural resolvidas via `/api/bi/query`.

## 6. Impactos / dependências
- **Depende de:** Motor de Indicadores (BI-1) + marts (BI-2) + API BI (BI-3).
- **Refatorar:** `pmpi_ai`/`plano_acao_ai`/`monthly_report_service` para consumir o
  *Indicator Context Pack* em vez de montar dados ad-hoc.
- **Manter:** `llm_client` (híbrido + fallback) — já é um bom ponto único.

## 7. Recomendação
Elevar a IA a **consumidora de 1ª classe do domínio BI**. Nenhuma nova feature de IA
deve ler OLTP diretamente; toda IA parte do conhecimento estruturado produzido pelo
Motor de Indicadores — garantindo que "o que a IA diz" e "o que o dashboard mostra"
sejam **sempre o mesmo número**.
