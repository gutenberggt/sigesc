# SPRINT 000 — Sumário da Auditoria Arquitetural do SIGESC IA

> Documento-índice da auditoria READ-ONLY. Data-base: **Jun/2026**.
> Natureza: **somente análise, documentação e diagnóstico** — nenhum código foi
> alterado, removido ou refatorado nesta sprint.

## Legenda de classificação (usada em toda a auditoria)
- 🟢 **Consolidado** — maduro, estável, coberto por testes.
- 🟡 **Precisa Evoluir** — funciona, mas tem lacunas/limitações conhecidas.
- 🔴 **Recomendado Refatorar** — dívida técnica relevante / risco.
- ⚫ **Obsoleto** — legado / candidato a remoção controlada.

## Métricas globais do sistema (coletadas do código)
| Dimensão | Quantidade |
|---|---|
| Routers backend (`backend/routers/*.py`) | **89** |
| Endpoints HTTP (`@router.<verbo>`) | **574** (GET 319 · POST 158 · PUT 54 · DELETE 43) |
| Services de domínio (`backend/services/*.py`) | **~44** |
| Coleções MongoDB referenciadas (`db.<coll>`) | **102** |
| Índices criados (`create_index`) | **~190** |
| Páginas React (`frontend/src/pages`) | **77** |
| Componentes React (`frontend/src/components`) | **105** (dos quais **46** são shadcn/ui) |
| Hooks customizados (`frontend/src/hooks`) | **17** |
| Context Providers (`frontend/src/contexts`) | **9** |
| Rotas declaradas (`<Route>` em `App.js`) | **86** |
| Serviços de API no frontend (`services/api.js`) | **38** |
| Papéis (roles) referenciados no backend | **16** |
| Arquivos de teste backend (`backend/tests`) | **173** |
| Iterações de teste registradas (`test_reports`) | **113** |
| LOC backend (excl. testes) | **~83.700** |
| LOC frontend (js/jsx) | **~82.559** |

## Índice das entregas
### Onda 1 — Fundação arquitetural (ENTREGUE)
- [01 — Arquitetura Geral](01_ARQUITETURA_GERAL.md) 🟢
- [02 — Inventário de Módulos](02_INVENTARIO_MODULOS.md) 🟢
- [05 — Banco de Dados](05_BANCO_DADOS.md) 🟢
- [06 — APIs](06_APIS.md) 🟢
- [11 — Rotas](11_ROTAS.md) 🟢
- [12 — Sistema de Permissões](12_PERMISSOES.md) 🟢
- [18 — Avaliação Arquitetural](18_AVALIACAO_ARQUITETURAL.md) 🟢
- [19 — Matriz de Capacidades](19_MATRIZ_CAPACIDADES.md) 🟢
- [20 — Roadmap Arquitetural](20_ROADMAP.md) 🟢
- Documento mestre: [`../ARCHITECTURE_BASELINE.md`](../ARCHITECTURE_BASELINE.md)

### Onda 2 — Reorientada para "Plataforma de Inteligência" (foco: dados + BI)
> Reprioridade definida pelo arquiteto (Sprint 000.1): o foco deixa de ser inventário
> técnico e passa a **preparar o SIGESC IA para BI + Motor de Indicadores + IA (SSoT)**.

**Prioridade máxima (ENTREGUE nesta rodada):**
- [21 — Business Intelligence (domínio)](21_BUSINESS_INTELLIGENCE.md) ✅
- [04 — Catálogo de Indicadores (doc central)](04_INDICADORES.md) ✅
- [03 — Dashboards (arquitetura definitiva)](03_DASHBOARDS.md) ✅
- [09 — Services (camada analítica)](09_SERVICES.md) ✅
- [14 — IA consumindo BI](14_INTELIGENCIA_ARTIFICIAL.md) ✅

**Podem ficar para o final (não são foco estratégico agora):**
- [07 — Componentes](07_COMPONENTES.md) ⏳
- [08 — Hooks](08_HOOKS.md) ⏳
- [10 — Contexts](10_CONTEXTS.md) ⏳
- [15 — Relatórios](15_RELATORIOS.md) ⏳
- [16 — Código Duplicado](16_CODIGO_DUPLICADO.md) ⏳
- [17 — Código Obsoleto](17_CODIGO_OBSOLETO.md) ⏳

### Sprint 000.1 — Consolidação Arquitetural (decisões)
- [Índice 000.1](000.1/00_INDICE.md) · Executivo: [`../EXECUTIVE_ARCHITECT_REVIEW.md`](../EXECUTIVE_ARCHITECT_REVIEW.md)

## Como manter viva esta baseline
Sempre que houver mudança estrutural relevante (novo módulo, nova coleção,
mudança no fluxo de auth/deploy, alteração no modelo de permissões), atualizar
o documento correspondente e refletir o resumo em `ARCHITECTURE_BASELINE.md`.
